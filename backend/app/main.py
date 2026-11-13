from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlmodel import Session, select

from .database import engine
from .events import EventHub
from .models import ScopeRevision, TrainingType, training_type_order
from .responses import (
    InvalidationMessage,
    KioskCommandEnvelope,
    Occupancy,
    PrinterJobEnvelope,
    SnapshotMessage,
)
from .routes import (
    auth,
    canvas,
    database,
    imports,
    kiosk,
    live,
    operations,
    profile,
    storage,
    storage_preview,
    training_icons,
    trainings,
    users,
)
from .services.printing import PrinterHub
from .services.projections import public_snapshot
from .services.sqlpreviews import SQLPreviews


@asynccontextmanager
async def lifespan(app):
    hub = EventHub()
    app.state.events = hub
    app.state.printer = PrinterHub(engine)
    app.state.sql_previews = SQLPreviews(engine)
    await app.state.sql_previews.start()
    await hub.start()
    try:
        yield
    finally:
        await app.state.sql_previews.stop()
        await app.state.printer.stop()
        await hub.stop()


def create_app():
    app = FastAPI(title="SFL Sign In API", version="0.1.0", lifespan=lifespan)
    for router in [
        auth.router,
        kiosk.router,
        users.router,
        trainings.router,
        operations.router,
        profile.router,
        live.router,
        database.router,
        imports.router,
        canvas.router,
        storage.router,
        storage_preview.router,
        training_icons.router,
    ]:
        app.include_router(router)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc):
        return JSONResponse(
            status_code=409,
            content={
                "detail": "This change conflicts with an existing identity, open visit, or related record"
            },
        )

    @app.exception_handler(OperationalError)
    async def database_unavailable(request: Request, exc):
        return JSONResponse(
            status_code=503,
            content={
                "detail": "Database is temporarily unavailable; check the current state before scanning again"
            },
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/admin") or request.url.path.startswith("/api/auth"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health", tags=["health"])
    def health():
        with Session(engine) as session:
            initialized = session.execute(
                text("SELECT to_regclass('users'), to_regclass('scope_revisions')")
            ).one()
            if not all(initialized) or set(session.exec(select(ScopeRevision.scope)).all()) != {
                "public",
                "staff",
            }:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "uninitialized",
                        "detail": "Initialize the candidate schema with init-db",
                    },
                )
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/api/public/occupancy", tags=["public"], response_model=Occupancy)
    def public_occupancy():
        return public_snapshot(engine)

    @app.get("/api/public/training-types", tags=["public"])
    def public_training_types():
        with Session(engine) as session:
            return {
                "items": [
                    {
                        "id": str(t.id),
                        "name": t.name,
                        "icon_key": t.icon_key,
                        "display_order": t.display_order,
                    }
                    for t in session.exec(
                        select(TrainingType)
                        .where(TrainingType.active.is_(True))
                        .order_by(*training_type_order())
                    ).all()
                ]
            }

    @app.get("/api/public/leaderboard", tags=["public"])
    def forgotten_leaderboard():
        with Session(engine) as session:
            rows = (
                session.execute(
                    text("""SELECT u.first_name,u.last_name,COUNT(*) total_visits,
              COUNT(*) FILTER(WHERE v.forgot_to_sign_out) forgotten,
              COUNT(*) FILTER(WHERE v.forgot_to_sign_out)::float/COUNT(*) ratio
              FROM visits v JOIN users u ON u.id=v.user_id WHERE u.active GROUP BY u.id HAVING COUNT(*)>=5 ORDER BY ratio DESC LIMIT 5""")
                )
                .mappings()
                .all()
            )
            return {
                "items": [
                    {
                        "display_name": f"{r['first_name']} {r['last_name']}",
                        "total_visits": r["total_visits"],
                        "forgotten_signouts": r["forgotten"],
                        "ratio": r["ratio"],
                    }
                    for r in rows
                ]
            }

    original_openapi = app.openapi

    def documented_openapi():
        schema = original_openapi()
        from pydantic.json_schema import models_json_schema

        _, definitions = models_json_schema(
            [
                (model, "validation")
                for model in [
                    SnapshotMessage,
                    InvalidationMessage,
                    KioskCommandEnvelope,
                    PrinterJobEnvelope,
                ]
            ],
            ref_template="#/components/schemas/{model}",
        )
        schema.setdefault("components", {}).setdefault("schemas", {}).update(
            definitions.get("$defs", {})
        )
        schema["x-websockets"] = {
            "/ws/public": {"receive": "SnapshotMessage"},
            "/ws/admin": {"receive": "InvalidationMessage"},
            "/ws/kiosk": {
                "send": "KioskCommandEnvelope",
                "receive": "SnapshotMessage or result/error envelope",
            },
            "/ws/printer": {
                "receive": "PrinterJobEnvelope",
                "send": "ack with id,status (printed/failed/unknown),error",
            },
        }
        return schema

    app.openapi = documented_openapi
    return app


app = create_app()
