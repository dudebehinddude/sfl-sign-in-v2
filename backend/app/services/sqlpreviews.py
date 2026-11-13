"""Short-lived restricted SQL transactions. Commit never re-executes submitted SQL."""

import asyncio
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException
from pglast import ast, parse_sql
from pglast.stream import RawStream
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlmodel import Session

from ..config import get_settings
from ..models import Permission, utcnow
from . import sqlconsole as sql


@dataclass
class Preview:
    id: str
    actor_id: UUID
    session_id: UUID
    connection: object
    transaction: object
    digest: str
    deadline: float
    expires_at: str
    result: dict


class SQLPreviews:
    ttl_seconds = 90
    max_pending = 2  # Matches the restricted writer pool; reads use another pool.

    def __init__(self, engine):
        self.engine = engine
        self.pending: dict[str, Preview] = {}
        self.lock = threading.RLock()
        self.task = None

    async def start(self):
        self.task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self):
        while True:
            await asyncio.sleep(1)
            await asyncio.to_thread(self.expire)

    async def stop(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self.rollback_all)

    def _dispose(self, preview):
        try:
            preview.transaction.rollback()
        finally:
            preview.connection.close()

    def expire(self):
        with self.lock:
            for id, preview in list(self.pending.items()):
                if preview.deadline <= time.monotonic():
                    del self.pending[id]
                    self._dispose(preview)

    def rollback_all(self):
        with self.lock:
            for preview in self.pending.values():
                self._dispose(preview)
            self.pending.clear()

    def _owned(self, id, actor):
        self.expire()
        preview = self.pending.get(id)
        if not preview:
            raise HTTPException(404, "Preview expired or already ended")
        if preview.actor_id != actor.user.id or preview.session_id != actor.session.id:
            raise HTTPException(403, "This preview belongs to another session")
        return preview

    def stage(self, session, actor, statement):
        if not actor.can(Permission.DATABASE_WRITE):
            raise HTTPException(403, "Only superadmins may preview SQL changes")
        with self.lock:
            self.expire()
            if any(p.session_id == actor.session.id for p in self.pending.values()):
                raise HTTPException(409, "Commit or roll back your current preview first")
            if len(self.pending) >= self.max_pending:
                raise HTTPException(
                    503, "SQL previews are busy; try again after an existing preview ends"
                )
            digest = hashlib.sha256(statement.encode()).hexdigest()
            sql._audit_attempt(session, actor.user.id, "database.query.attempted", digest, "write")
            conn = None
            started = time.perf_counter()
            try:
                sql.validate_query(statement, "write", True)
                node = parse_sql(statement)[0].stmt
                if (
                    node.withClause
                    or (isinstance(node, ast.UpdateStmt) and node.fromClause)
                    or (isinstance(node, ast.DeleteStmt) and node.usingClause)
                ):
                    raise ValueError(
                        "Preview supports one table without WITH, UPDATE FROM or DELETE USING"
                    )
                if isinstance(node, ast.InsertStmt) and node.onConflictClause:
                    raise ValueError(
                        "Preview does not support ON CONFLICT; use a separate INSERT or UPDATE"
                    )
                if (
                    isinstance(node, ast.InsertStmt)
                    and node.selectStmt
                    and not node.selectStmt.valuesLists
                ):
                    raise ValueError("Preview supports INSERT VALUES, not INSERT SELECT")
                # Reject nested writes even if a future grammar puts one outside WITH.
                encoded = node()

                def nested_writes(value, root=True):
                    if isinstance(value, dict):
                        if not root and value.get("@") in {
                            "InsertStmt",
                            "UpdateStmt",
                            "DeleteStmt",
                        }:
                            return True
                        return any(nested_writes(item, False) for item in value.values())
                    return isinstance(value, (list, tuple)) and any(
                        nested_writes(item, False) for item in value
                    )

                if nested_writes(encoded):
                    raise ValueError("Nested data changes are not supported in a preview")
                conn = sql._connection("write")
                transaction = conn.begin()
                conn.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
                sql._configure(conn, "write")
                conn.execute(
                    text("SELECT set_config('idle_in_transaction_session_timeout', :ttl, true)"),
                    {"ttl": f"{self.ttl_seconds + 5}s"},
                )
                table = node.relation.relname
                columns = sql._visible_columns(conn, table)
                if not columns or table in sql.PROTECTED_TABLES:
                    raise ValueError("This table is unavailable for SQL changes")
                primary = list(
                    conn.execute(
                        text("""SELECT a.attname FROM pg_catalog.pg_index i
                    JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
                    JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
                    JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid AND a.attnum=ANY(i.indkey)
                    WHERE n.nspname='public' AND t.relname=:table AND i.indisprimary ORDER BY a.attnum"""),
                        {"table": table},
                    ).scalars()
                )
                if not primary or any(key not in columns for key in primary):
                    raise ValueError("Preview needs a visible primary key")
                if isinstance(node, ast.UpdateStmt) and any(
                    target.name in primary for target in node.targetList
                ):
                    raise ValueError("Primary-key updates are not supported in previews")
                node.relation.schemaname = "public"
                alias = node.relation.alias.aliasname if node.relation.alias else table
                projection = ",".join(
                    f"{sql._quote(alias)}.{sql._quote(column)}" for column in columns
                )
                limit = min(get_settings().sql_max_rows, 1000)
                if (
                    isinstance(node, ast.InsertStmt)
                    and node.selectStmt
                    and len(node.selectStmt.valuesLists or ()) > limit
                ):
                    raise ValueError("Insert exceeds the preview row limit")
                before = {}
                if isinstance(node, (ast.UpdateStmt, ast.DeleteStmt)):
                    where = " WHERE " + RawStream()(node.whereClause) if node.whereClause else ""
                    query = f"SELECT {projection} FROM {RawStream()(node.relation)}{where} LIMIT {limit + 1} FOR NO KEY UPDATE"
                    result = conn.exec_driver_sql(query, execution_options={"no_parameters": True})
                    names, values, truncated, _ = sql._consume(result, limit)
                    result.close()
                    if truncated:
                        raise ValueError(
                            "Change exceeds the preview row or byte limit; narrow its WHERE clause"
                        )
                    before = {
                        tuple(record[key] for key in primary): record
                        for record in [dict(zip(names, row, strict=True)) for row in values]
                    }
                node.returningClause = ast.ReturningClause(
                    exprs=tuple(
                        ast.ResTarget(
                            val=ast.ColumnRef(
                                fields=(ast.String(sval=alias), ast.String(sval=column))
                            )
                        )
                        for column in columns
                    )
                )
                result = conn.exec_driver_sql(
                    RawStream()(node), execution_options={"no_parameters": True}
                )
                names, values, truncated, count = sql._consume(result, limit)
                result.close()
                if truncated:
                    raise ValueError(
                        "Change exceeds the preview row or byte limit; narrow the statement"
                    )
                records = [dict(zip(names, row, strict=True)) for row in values]
                changes = []
                for record in records:
                    key = tuple(record[column] for column in primary)
                    if isinstance(node, (ast.UpdateStmt, ast.DeleteStmt)) and key not in before:
                        raise HTTPException(
                            409, "Rows changed concurrently; preview was rolled back. Run it again"
                        )
                    changes.append(
                        {
                            "before": record
                            if isinstance(node, ast.DeleteStmt)
                            else before.get(key),
                            "after": None if isinstance(node, ast.DeleteStmt) else record,
                        }
                    )
                if len(json.dumps(changes).encode()) > sql.MAX_RESPONSE_BYTES:
                    raise ValueError("Preview exceeds the byte limit; narrow the statement")
                id = str(uuid4())
                expires = (utcnow() + timedelta(seconds=self.ttl_seconds)).isoformat()
                response = {
                    "columns": names,
                    "rows": values,
                    "row_count": count,
                    "truncated": False,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "transaction_status": "preview",
                    "preview_id": id,
                    "expires_at": expires,
                    "table": table,
                    "operation": type(node).__name__.removesuffix("Stmt").lower(),
                    "changes": changes,
                }
                if len(json.dumps(response).encode()) > sql.MAX_RESPONSE_BYTES:
                    raise ValueError(
                        "Preview response exceeds the byte limit; narrow the statement"
                    )
                self.pending[id] = Preview(
                    id,
                    actor.user.id,
                    actor.session.id,
                    conn,
                    transaction,
                    digest,
                    time.monotonic() + self.ttl_seconds,
                    expires,
                    response,
                )
                return response
            except (ValueError, HTTPException, DBAPIError, PoolTimeout) as error:
                if conn:
                    conn.rollback()
                    conn.close()
                sql._audit_attempt(
                    session,
                    actor.user.id,
                    "database.query.failed",
                    digest,
                    "write",
                    error_kind="preview",
                    sqlstate=getattr(getattr(error, "orig", None), "sqlstate", None),
                )
                if isinstance(error, HTTPException):
                    raise
                if isinstance(error, PoolTimeout):
                    raise HTTPException(503, "SQL preview connection is busy") from error
                message = (
                    str(error)
                    if isinstance(error, ValueError)
                    else getattr(
                        getattr(error.orig, "diag", None),
                        "message_primary",
                        "Database preview failed",
                    )
                )
                raise HTTPException(400, message) from error

    def commit(self, id, actor):
        if not actor.can(Permission.DATABASE_WRITE):
            raise HTTPException(403, "Only superadmins may commit SQL changes")
        with self.lock:
            preview = self._owned(id, actor)
            try:
                internal = sql.role_names(preview.connection.engine.url.database)[2]
                preview.connection.execute(
                    text(f"SELECT {sql._quote(internal)}.finalize_write(:actor,:digest)"),
                    {"actor": actor.user.id, "digest": preview.digest},
                )
                preview.transaction.commit()
            except DBAPIError as error:
                preview.transaction.rollback()
                with Session(self.engine) as session:
                    sql._audit_attempt(
                        session,
                        actor.user.id,
                        "database.query.failed",
                        preview.digest,
                        "write",
                        error_kind="commit",
                        sqlstate=getattr(error.orig, "sqlstate", None),
                    )
                raise HTTPException(
                    409, "Preview could not commit and was rolled back; refresh before retrying"
                ) from error
            finally:
                preview.connection.close()
                del self.pending[id]
            return {"transaction_status": "committed", "row_count": preview.result["row_count"]}

    def rollback(self, id, actor):
        with self.lock:
            preview = self._owned(id, actor)
            del self.pending[id]
            self._dispose(preview)
            with Session(self.engine) as session:
                sql._audit_attempt(
                    session, actor.user.id, "database.query.rolled_back", preview.digest, "write"
                )
            return {"transaction_status": "rolled_back", "row_count": preview.result["row_count"]}
