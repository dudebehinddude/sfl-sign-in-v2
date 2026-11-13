"""Bounded superadmin SQL execution using separately authenticated database roles.

The first version intentionally supports SELECT/EXPLAIN and explicit domain-table
DML, not DDL, transaction control, COPY or arbitrary server functions. Console
connections never fall back to the application's owner connection. Successful
writes finalize audit and live revisions atomically through a protected function.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from datetime import date, datetime
from datetime import time as datetime_time
from decimal import Decimal
from functools import lru_cache
from typing import Any, Literal
from uuid import UUID

from fastapi import HTTPException
from pglast import ast, parse_sql
from pglast.parser import ParseError
from pglast.visitors import Visitor
from psycopg import sql as pgsql
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session

from app.config import get_settings
from app.events import audit, publish

MAX_SQL_CHARACTERS = 64_000
MAX_RESPONSE_BYTES = 2_000_000
MAX_CELL_CHARACTERS = 32_768
# Authentication secrets cannot be browsed using raw SQL.
HIDDEN_TABLES = {
    "auth_sessions",
    "password_resets",
    "login_attempts",
    "email_jobs",  # Pending recovery mail contains the bearer reset link.
}
HIDDEN_COLUMNS = {"users": {"password_hash"}}
# Updating these tables must go through the permission/workflow services.
PROTECTED_TABLES = HIDDEN_TABLES | {
    "audit_events",
    "scope_revisions",
    "email_jobs",
}
PROTECTED_WRITE_COLUMNS = {"users": {"password_hash", "role", "active", "email"}}
SAFE_FUNCTIONS = {
    "abs",
    "avg",
    "bit_length",
    "btrim",
    "cardinality",
    "ceil",
    "ceiling",
    "char_length",
    "character_length",
    "concat",
    "concat_ws",
    "count",
    "date_part",
    "date_trunc",
    "encode",
    "extract",
    "floor",
    "format",
    "generate_series",
    "greatest",
    "json_agg",
    "json_array_length",
    "json_build_array",
    "json_build_object",
    "json_object_agg",
    "json_typeof",
    "jsonb_agg",
    "jsonb_array_elements",
    "jsonb_array_elements_text",
    "jsonb_array_length",
    "jsonb_build_array",
    "jsonb_build_object",
    "jsonb_each",
    "jsonb_each_text",
    "jsonb_extract_path",
    "jsonb_extract_path_text",
    "jsonb_object_agg",
    "jsonb_object_keys",
    "jsonb_pretty",
    "jsonb_typeof",
    "least",
    "left",
    "length",
    "lower",
    "ltrim",
    "max",
    "min",
    "mod",
    "now",
    "nullif",
    "octet_length",
    "pg_typeof",
    "position",
    "replace",
    "right",
    "round",
    "row_number",
    "rtrim",
    "split_part",
    "sqrt",
    "string_agg",
    "strpos",
    "substr",
    "substring",
    "sum",
    "timezone",
    "to_char",
    "to_date",
    "to_json",
    "to_jsonb",
    "to_timestamp",
    "trim",
    "trunc",
    "unnest",
    "upper",
    "array_agg",
    "array_length",
    "array_to_string",
    "bool_and",
    "bool_or",
    "current_database",
    "gen_random_uuid",
    "version",
    "pg_sleep",
}
READ_ROOTS = (ast.SelectStmt, ast.ExplainStmt)
WRITE_ROOTS = (ast.InsertStmt, ast.UpdateStmt, ast.DeleteStmt)


def role_names(database: str) -> tuple[str, str, str]:
    """Database-specific identifiers avoid sharing grants across beta databases."""
    suffix = hashlib.sha256(database.encode()).hexdigest()[:12]
    return f"sfl_{suffix}_read", f"sfl_{suffix}_write", f"sfl_{suffix}_console"


def _quote(identifier: str) -> str:
    return pgsql.Identifier(identifier).as_string()


def _settings_url(mode: Literal["read", "write"]) -> str:
    value = getattr(get_settings(), f"sql_{mode}_database_url", "")
    if not value:
        raise HTTPException(
            503,
            f"SQL {mode} connection is not configured. Provision its restricted database role first.",
        )
    owner = make_url(get_settings().database_url)
    configured = make_url(value)
    if configured.drivername != "postgresql+psycopg":
        raise HTTPException(503, "SQL console connections must use postgresql+psycopg")
    expected = role_names(owner.database or "")[0 if mode == "read" else 1]
    if (
        configured.username != expected
        or configured.database != owner.database
        or configured.host != owner.host
        or (configured.port or 5432) != (owner.port or 5432)
    ):
        raise HTTPException(
            503,
            "SQL console connection must target this instance using its dedicated restricted role",
        )
    return value


@lru_cache(maxsize=4)
def _console_engine(url: str) -> Engine:
    return create_engine(url, pool_size=2, max_overflow=0, pool_timeout=5, pool_pre_ping=True)


def clear_console_pools() -> None:
    """Tests/config changes must not retain another instance's pool."""
    _console_engine.cache_clear()


def _table_names(session: Session) -> list[str]:
    return list(
        session.execute(
            text(
                "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
        ).scalars()
    )


def _table_columns(connection, table: str) -> list[str]:
    return list(
        connection.execute(
            text("""SELECT column_name FROM information_schema.columns
                    WHERE table_schema='public' AND table_name=:table
                    ORDER BY ordinal_position"""),
            {"table": table},
        ).scalars()
    )


def _visible_columns(connection, table: str) -> list[str]:
    hidden = HIDDEN_COLUMNS.get(table, set())
    return [column for column in _table_columns(connection, table) if column not in hidden]


def bootstrap_console_roles(session: Session) -> dict[str, str | bool]:
    """Provision configured LOGIN roles. Call as the schema owner during setup.

    Passwords come only from the explicitly configured console URLs. Missing URLs
    leave that mode disabled. No default production credential is manufactured.
    The caller commits this transaction after the rest of schema setup succeeds.
    """
    owner = make_url(get_settings().database_url)
    read_role, write_role, internal_schema = role_names(owner.database or "")
    tables = _table_names(session)
    modes: dict[str, str | bool] = {
        "read_role": read_role,
        "write_role": write_role,
        "read_enabled": False,
        "write_enabled": False,
    }
    for mode, role in (("read", read_role), ("write", write_role)):
        if not getattr(get_settings(), f"sql_{mode}_database_url", ""):
            continue
        url = make_url(_settings_url(mode))
        if not url.password:
            raise ValueError(f"SQL_{mode.upper()}_DATABASE_URL needs an explicit role password")
        existing = session.execute(
            text(
                "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_catalog.pg_roles WHERE rolname=:role"
            ),
            {"role": role},
        ).first()
        if existing and any(existing[1:]):
            raise ValueError("Refusing to reuse an elevated database role as a SQL console role")
        member = session.execute(
            text(
                "SELECT 1 FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid=m.member WHERE r.rolname=:role LIMIT 1"
            ),
            {"role": role},
        ).first()
        if member:
            raise ValueError("SQL console roles must not be members of another role")
        verb = "ALTER" if existing else "CREATE"
        password_literal = pgsql.Literal(url.password).as_string()
        session.connection().exec_driver_sql(
            f"{verb} ROLE {_quote(role)} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS PASSWORD {password_literal}",
            execution_options={"no_parameters": True},
        )
        session.connection().exec_driver_sql(
            f"GRANT CONNECT ON DATABASE {_quote(owner.database or '')} TO {_quote(role)}"
        )
        session.connection().exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {_quote(role)}")
        for table in tables:
            # Clear our previous grants before applying the current policy.
            session.connection().exec_driver_sql(
                f"REVOKE ALL ON TABLE public.{_quote(table)} FROM {_quote(role)}"
            )
            if table in HIDDEN_COLUMNS:
                # Table-level REVOKE does not remove pre-existing column grants.
                all_columns = ",".join(_quote(c) for c in _table_columns(session, table))
                session.connection().exec_driver_sql(
                    f"REVOKE ALL ({all_columns}) ON TABLE public.{_quote(table)} FROM {_quote(role)}"
                )
                visible = ",".join(_quote(c) for c in _visible_columns(session, table))
                session.connection().exec_driver_sql(
                    f"GRANT SELECT ({visible}) ON TABLE public.{_quote(table)} TO {_quote(role)}"
                )
                if mode == "write":
                    writable = ",".join(
                        _quote(c)
                        for c in _visible_columns(session, table)
                        if c not in PROTECTED_WRITE_COLUMNS.get(table, set())
                    )
                    session.connection().exec_driver_sql(
                        f"GRANT INSERT ({writable}), UPDATE ({writable}) ON TABLE public.{_quote(table)} TO {_quote(role)}"
                    )
            else:
                if table not in HIDDEN_TABLES:
                    session.connection().exec_driver_sql(
                        f"GRANT SELECT ON TABLE public.{_quote(table)} TO {_quote(role)}"
                    )
                if mode == "write" and table not in PROTECTED_TABLES:
                    session.connection().exec_driver_sql(
                        f"GRANT INSERT, UPDATE, DELETE ON TABLE public.{_quote(table)} TO {_quote(role)}"
                    )
        modes[f"{mode}_enabled"] = True
    if modes["write_enabled"]:
        session.connection().exec_driver_sql(
            f"CREATE SCHEMA IF NOT EXISTS {_quote(internal_schema)}"
        )
        session.connection().exec_driver_sql(
            f"REVOKE ALL ON SCHEMA {_quote(internal_schema)} FROM PUBLIC"
        )
        # Runtime SQL cannot invoke this function: submitted calls are restricted
        # to a small pg_catalog allowlist. SECURITY DEFINER is needed only for
        # protected audit/revision rows after the domain statement succeeds.
        session.connection().exec_driver_sql(f"""
CREATE OR REPLACE FUNCTION {_quote(internal_schema)}.finalize_write(actor uuid, digest text)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $sfl$
DECLARE
    scope_name text;
    scope_value bigint;
    versions jsonb := '{{}}'::jsonb;
BEGIN
    FOREACH scope_name IN ARRAY ARRAY['public','staff'] LOOP
        UPDATE public.scope_revisions SET revision=revision+1 WHERE scope=scope_name RETURNING revision INTO scope_value;
        IF NOT FOUND THEN RAISE EXCEPTION 'Missing live revision scope'; END IF;
        versions := versions || jsonb_build_object(scope_name, scope_value);
    END LOOP;
    INSERT INTO public.audit_events(id,actor_user_id,action,entity_type,details,occurred_at)
        VALUES(gen_random_uuid(),actor,'database.query.succeeded','database',jsonb_build_object('mode','write','query_sha256',digest),clock_timestamp());
    PERFORM pg_notify('sfl_changes',jsonb_build_object('revision',(versions->>'staff')::bigint,'revisions',versions,'topics','["all"]'::jsonb)::text);
    RETURN (versions->>'public')::bigint;
END
$sfl$;
""")
        session.connection().exec_driver_sql(
            f"REVOKE ALL ON FUNCTION {_quote(internal_schema)}.finalize_write(uuid,text) FROM PUBLIC"
        )
        session.connection().exec_driver_sql(
            f"GRANT USAGE ON SCHEMA {_quote(internal_schema)} TO {_quote(write_role)}"
        )
        session.connection().exec_driver_sql(
            f"GRANT EXECUTE ON FUNCTION {_quote(internal_schema)}.finalize_write(uuid,text) TO {_quote(write_role)}"
        )
    return modes


class _QueryPolicy(Visitor):
    def __init__(self, mode: str):
        super().__init__()
        self.mode = mode

    def visit_SelectStmt(self, ancestors, node):
        if node.intoClause or node.lockingClause:
            raise ValueError("SELECT INTO and explicit row locks are not supported")

    def visit_FuncCall(self, ancestors, node):
        names = [item.sval for item in node.funcname]
        if (
            names[-1].lower() not in SAFE_FUNCTIONS
            or len(names) > 2
            or (len(names) == 2 and names[0] != "pg_catalog")
        ):
            raise ValueError(
                "This server function is outside the SQL workbench's supported function set"
            )

    def visit_RangeVar(self, ancestors, node):
        if node.catalogname or node.schemaname not in {
            None,
            "public",
            "pg_catalog",
            "information_schema",
        }:
            raise ValueError(
                "Only public application tables and PostgreSQL metadata can be queried"
            )
        if node.relname in HIDDEN_TABLES:
            raise ValueError(
                "Credential and workflow-intent tables are not exposed by the SQL workbench"
            )

    def _write(self, node):
        if self.mode != "write":
            raise ValueError(
                "Read mode cannot contain a data-changing statement, including inside a CTE"
            )
        relation = node.relation
        if (
            relation.catalogname
            or relation.schemaname not in {None, "public"}
            or relation.relname in PROTECTED_TABLES
        ):
            raise ValueError(
                "Write mode only changes domain tables; use dedicated administration controls for protected infrastructure"
            )
        if relation.relname == "users" and isinstance(node, ast.DeleteStmt):
            raise ValueError("Use user administration to deactivate accounts")
        columns = (
            node.cols
            if isinstance(node, ast.InsertStmt)
            else node.targetList
            if isinstance(node, ast.UpdateStmt)
            else ()
        )
        protected = PROTECTED_WRITE_COLUMNS.get(relation.relname, set())
        if protected and isinstance(node, ast.InsertStmt) and not columns:
            raise ValueError("Name the permitted columns explicitly when inserting users")
        if any(column.name in protected for column in columns or ()):
            raise ValueError(
                "Use account administration for roles, passwords, activation and recovery email"
            )

    def visit_InsertStmt(self, ancestors, node):
        self._write(node)

    def visit_UpdateStmt(self, ancestors, node):
        self._write(node)

    def visit_DeleteStmt(self, ancestors, node):
        self._write(node)

    def visit_ExplainStmt(self, ancestors, node):
        if not isinstance(node.query, ast.SelectStmt) or any(
            option.defname == "analyze" for option in node.options or ()
        ):
            raise ValueError("Only EXPLAIN SELECT without ANALYZE is supported")


def validate_query(statement: str, mode: str, confirm_write: bool = False) -> None:
    if not statement.strip() or len(statement) > MAX_SQL_CHARACTERS:
        raise ValueError("Enter one SQL statement, up to 64,000 characters")
    if mode not in {"read", "write"}:
        raise ValueError("SQL mode must be read or write")
    if mode == "write" and not confirm_write:
        raise ValueError("Explicit confirmation is required for write mode")
    try:
        parsed = parse_sql(statement)
    except ParseError as error:
        raise ValueError("SQL syntax is invalid") from error
    if len(parsed) != 1:
        raise ValueError(
            "Execute one statement at a time; transaction control is managed by the server"
        )
    root = parsed[0].stmt
    if (mode == "read" and not isinstance(root, READ_ROOTS)) or (
        mode == "write" and not isinstance(root, WRITE_ROOTS)
    ):
        raise ValueError(
            "Read mode supports SELECT/EXPLAIN; write mode supports INSERT/UPDATE/DELETE. DDL and session commands are not supported."
        )
    _QueryPolicy(mode)(root)


def _json_value(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if isinstance(value, (Decimal, UUID)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "base64:" + base64.b64encode(bytes(value)).decode()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    result = str(value)
    return result[:MAX_CELL_CHARACTERS] + "…" if len(result) > MAX_CELL_CHARACTERS else result


def _consume(result, limit: int) -> tuple[list[str], list[list[Any]], bool, int]:
    if not result.returns_rows:
        return [], [], False, max(result.rowcount, 0)
    columns = list(result.keys())
    rows: list[list[Any]] = []
    used_bytes = 0
    truncated = False
    for _ in range(limit + 1):
        raw = result.fetchone()
        if raw is None:
            break
        if len(rows) >= limit:
            truncated = True
            break
        row = [_json_value(value) for value in raw]
        size = len(json.dumps(row, ensure_ascii=False, default=str).encode())
        if used_bytes + size > MAX_RESPONSE_BYTES:
            truncated = True
            break
        used_bytes += size
        rows.append(row)
    return columns, rows, truncated, len(rows)


def _connection(mode: Literal["read", "write"]):
    return _console_engine(_settings_url(mode)).connect()


def _configure(conn, mode: str) -> None:
    settings = get_settings()
    # Called before any user statement. A genuine read-only transaction is the
    # second boundary after the restricted LOGIN role's database privileges.
    if mode == "read":
        conn.exec_driver_sql("SET TRANSACTION READ ONLY")
    conn.execute(
        text(
            "SELECT set_config('statement_timeout',:timeout,true), set_config('lock_timeout',:timeout,true), set_config('search_path','pg_catalog,public',true), set_config('TimeZone',:timezone,true)"
        ),
        {"timeout": f"{settings.sql_statement_timeout_ms}ms", "timezone": settings.lab_timezone},
    )
    role = conn.execute(
        text(
            "SELECT current_user, session_user, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members WHERE member=pg_catalog.pg_roles.oid) AS has_membership FROM pg_catalog.pg_roles WHERE rolname=current_user"
        )
    ).one()
    expected = role_names(make_url(settings.database_url).database or "")[
        0 if mode == "read" else 1
    ]
    if role[0] != expected or role[1] != expected or any(role[2:]):
        raise HTTPException(503, "The SQL connection is not a restricted console login")


def _audit_attempt(
    session: Session, actor_id: UUID, action: str, digest: str, mode: str, **details
) -> None:
    audit(session, action, "database", actor_id=actor_id, query_sha256=digest, mode=mode, **details)
    publish(session, "audit")
    session.commit()


def execute_query(
    session: Session,
    actor_id: UUID,
    statement: str,
) -> dict:
    mode = "read"
    digest = hashlib.sha256(statement.encode()).hexdigest()
    _audit_attempt(session, actor_id, "database.query.attempted", digest, mode)
    started = time.perf_counter()
    try:
        validate_query(statement, mode)
        with _connection(mode) as conn, conn.begin():
            _configure(conn, mode)
            # SQL is intentionally submitted by a trusted superadmin. The AST
            # restricts statement kinds; the dedicated PostgreSQL LOGIN role
            # supplies actual database privileges, rather than an owner fallback.
            result = conn.exec_driver_sql(
                statement,
                execution_options={"stream_results": mode == "read", "no_parameters": True},
            )
            columns, rows, truncated, row_count = _consume(result, get_settings().sql_max_rows)
            result.close()
        _audit_attempt(session, actor_id, "database.query.succeeded", digest, mode)
    except HTTPException:
        _audit_attempt(
            session, actor_id, "database.query.failed", digest, mode, error_kind="configuration"
        )
        raise
    except ValueError as error:
        _audit_attempt(
            session, actor_id, "database.query.failed", digest, mode, error_kind="policy"
        )
        raise HTTPException(400, str(error)) from error
    except DBAPIError as error:
        sqlstate = getattr(error.orig, "sqlstate", None)
        _audit_attempt(
            session,
            actor_id,
            "database.query.failed",
            digest,
            mode,
            error_kind="database",
            sqlstate=sqlstate,
        )
        message = (
            getattr(getattr(error.orig, "diag", None), "message_primary", None)
            or "Database query failed"
        )
        raise HTTPException(400, message) from error
    return {
        "columns": columns,
        "rows": rows,
        "row_count": row_count,
        "truncated": truncated,
        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        "transaction_status": "read_only",
    }


def list_tables() -> dict:
    with _connection("read") as conn, conn.begin():
        _configure(conn, "read")
        records = conn.execute(
            text("""
SELECT c.table_schema,c.table_name,c.column_name,c.data_type,c.is_nullable,
       EXISTS(SELECT 1 FROM pg_catalog.pg_index i
              JOIN pg_catalog.pg_class t ON t.oid=i.indrelid
              JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
              JOIN pg_catalog.pg_attribute a ON a.attrelid=t.oid AND a.attnum=ANY(i.indkey)
              WHERE i.indisprimary AND n.nspname=c.table_schema
                AND t.relname=c.table_name AND a.attname=c.column_name) AS primary_key
FROM information_schema.columns c
WHERE c.table_schema='public'
ORDER BY c.table_name,c.ordinal_position
""")
        ).mappings()
        tables: dict[str, dict] = {}
        for item in records:
            if item["table_name"] in HIDDEN_TABLES or item["column_name"] in HIDDEN_COLUMNS.get(
                item["table_name"], set()
            ):
                continue
            table = tables.setdefault(
                item["table_name"],
                {"schema": item["table_schema"], "name": item["table_name"], "columns": []},
            )
            table["columns"].append(
                {
                    "name": item["column_name"],
                    "type": item["data_type"],
                    "nullable": item["is_nullable"] == "YES",
                    "primary_key": item["primary_key"],
                }
            )
    return {"tables": list(tables.values())}


def table_rows(table: str, page: int = 1, page_size: int = 100) -> dict:
    if page < 1 or not 1 <= page_size <= 1000:
        raise HTTPException(422, "Invalid database page or page size")
    page_size = min(page_size, get_settings().sql_max_rows)
    with _connection("read") as conn, conn.begin():
        _configure(conn, "read")
        exists = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:table"
            ),
            {"table": table},
        ).first()
        if table in HIDDEN_TABLES or not exists:
            raise HTTPException(404, "Database table is unavailable")
        quoted = "public." + _quote(table)
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
        ordering = ",".join(_quote(name) for name in primary) or "ctid"
        total = conn.execute(text(f"SELECT count(*) FROM {quoted}")).scalar_one()
        projection = ",".join(_quote(name) for name in _visible_columns(conn, table))
        result = conn.execute(
            text(
                f"SELECT {projection} FROM {quoted} ORDER BY {ordering} LIMIT :limit OFFSET :offset"
            ),
            {"limit": page_size, "offset": (page - 1) * page_size},
        )
        columns, rows, truncated, _ = _consume(result, page_size)
    return {
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "truncated": truncated,
    }
