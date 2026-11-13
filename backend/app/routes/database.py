"""Read-only SQL for admins; real transaction previews and commits for superadmins."""

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pglast import ast, parse_sql
from pglast.parser import ParseError
from pydantic import BaseModel, ConfigDict, Field

from app.models import Permission
from app.security import DB, Actor, CurrentActor, require
from app.services.sqlconsole import execute_query, list_tables, table_rows

router = APIRouter(prefix="/api/admin/database", tags=["database"])
Reader = Annotated[Actor, Depends(require(Permission.DATABASE_READ))]
Writer = Annotated[Actor, Depends(require(Permission.DATABASE_WRITE))]


class ColumnMetadata(BaseModel):
    name: str
    type: str
    nullable: bool
    primary_key: bool


class TableMetadata(BaseModel):
    schema_name: str = Field(alias="schema")
    name: str
    columns: list[ColumnMetadata]


class TablesResponse(BaseModel):
    tables: list[TableMetadata]


class RowsResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    total: int
    page: int
    page_size: int
    truncated: bool


class RowChange(BaseModel):
    before: dict[str, Any] | None
    after: dict[str, Any] | None


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: float
    transaction_status: Literal["read_only", "preview"]
    preview_id: str | None = None
    expires_at: datetime | None = None
    table: str | None = None
    operation: str | None = None
    changes: list[RowChange] | None = None


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sql: str = Field(min_length=1, max_length=64_000)


class PreviewResult(BaseModel):
    transaction_status: Literal["committed", "rolled_back"]
    row_count: int


@router.get("/tables", response_model=TablesResponse)
def tables(actor: Reader):
    return list_tables()


@router.get("/rows", response_model=RowsResponse)
def rows(
    actor: Reader,
    table: str = Query(min_length=1, max_length=128),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
):
    return table_rows(table, page, page_size)


@router.post("/query", response_model=QueryResponse, response_model_exclude_none=True)
def query(payload: QueryRequest, request: Request, session: DB, actor: Reader):
    try:
        statements = parse_sql(payload.sql)
    except ParseError as error:
        raise HTTPException(400, "SQL syntax is invalid") from error
    if len(statements) != 1:
        raise HTTPException(400, "Run one statement at a time")
    if isinstance(statements[0].stmt, (ast.InsertStmt, ast.UpdateStmt, ast.DeleteStmt)):
        if not actor.can(Permission.DATABASE_WRITE):
            raise HTTPException(403, "Only superadmins may preview SQL changes")
        return request.app.state.sql_previews.stage(session, actor, payload.sql)
    return execute_query(session, actor.user.id, payload.sql)


@router.post("/preview/{preview_id}/commit", response_model=PreviewResult)
def commit(preview_id: str, request: Request, actor: Writer):
    return request.app.state.sql_previews.commit(preview_id, actor)


@router.post("/preview/{preview_id}/rollback", response_model=PreviewResult)
def rollback(preview_id: str, request: Request, actor: CurrentActor):
    return request.app.state.sql_previews.rollback(preview_id, actor)
