"""Procrastinate task bodies. No application transaction spans external I/O."""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from html import escape
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import delete
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from .config import Settings, get_settings
from .database import engine
from .events import audit, publish
from .models import CanvasQuiz, EmailJob, Training, TrainingType, User, utcnow
from .services.canvas import CanvasClient, CanvasError, TrainingSpec, apply_snapshot, canvas_issuer

logger = logging.getLogger(__name__)


class EmailUnavailable(Exception):
    """Safe transactional mail configuration failure."""


class BackgroundFailure(Exception):
    """Safe retryable error without request, SQL parameters or private payloads."""


def run_canvas_sync(
    db: Engine | None = None,
    settings: Settings | None = None,
    training_type_id: str | None = None,
    *,
    canvas_client=None,
) -> dict:
    db, settings = db or engine, settings or get_settings()
    if not settings.canvas_configured:
        raise BackgroundFailure("Canvas is not configured")
    with Session(db) as session:
        stmt = select(TrainingType).where(
            TrainingType.active, TrainingType.canvas_assignment_id.is_not(None)
        )
        if training_type_id is not None:
            stmt = stmt.where(TrainingType.id == UUID(training_type_id))
        specs = [TrainingSpec.from_model(t, settings) for t in session.exec(stmt).all()]
    # Capture T0 before the first request. It becomes the successful fetch-start
    # checkpoint only after every page and its complete cache have committed.
    started = utcnow()
    scope = "whole" if training_type_id is None else "training"
    sync_context = {
        "scope": scope,
        "training_type_id": training_type_id,
        "issuer": canvas_issuer(settings),
        "course_id": settings.canvas_course_id,
        "started_at": started.isoformat(),
    }
    client = canvas_client or CanvasClient(settings)
    try:
        snapshot = client.fetch_snapshot(specs)
        with Session(db) as session:
            counts = apply_snapshot(session, snapshot, settings=settings)
            for spec in specs:
                training = session.get(TrainingType, spec.training_type_id)
                training.canvas_sync_started_at = started
                training.canvas_synced_at = utcnow()
                training.canvas_sync_error = None
                session.add(training)
            audit(
                session,
                "canvas.sync_completed",
                "training_types",
                training_type_id,
                worker="canvas",
                counts=counts,
                finished_at=utcnow().isoformat(),
                **sync_context,
            )
            publish(session, "canvas", "trainings")
            session.commit()
            return counts
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, CanvasError)
            else f"Canvas synchronization failed ({type(exc).__name__})"
        )
        with Session(db) as session:
            for spec in specs:
                training = session.get(TrainingType, spec.training_type_id)
                if training:
                    training.canvas_sync_error = error
                    session.add(training)
            audit(
                session,
                "canvas.sync_failed",
                "training_types",
                training_type_id,
                worker="canvas",
                error=error,
                finished_at=utcnow().isoformat(),
                **sync_context,
            )
            publish(session, "canvas")
            session.commit()
        raise BackgroundFailure(error) from None
    finally:
        if canvas_client is None:
            client.close()


def refresh_quiz_cache(
    db: Engine | None = None, settings: Settings | None = None, *, canvas_client=None
) -> int:
    db, settings = db or engine, settings or get_settings()
    client = canvas_client or CanvasClient(settings)
    try:
        records = client.fetch_quizzes()
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, CanvasError)
            else f"Canvas quiz catalog failed ({type(exc).__name__})"
        )
        raise BackgroundFailure(error) from None
    finally:
        if canvas_client is None:
            client.close()
    # Fetch and validate every page before touching the previous catalog.
    with Session(db) as session:
        now = utcnow()
        ids = [r.id for r in records]
        referenced = select(TrainingType.canvas_assignment_id).where(
            TrainingType.canvas_assignment_id.is_not(None)
        )
        session.execute(
            delete(CanvasQuiz).where(CanvasQuiz.id.not_in(ids), CanvasQuiz.id.not_in(referenced))
        )
        for record in records:
            row = session.get(CanvasQuiz, record.id) or CanvasQuiz(id=record.id, title=record.title)
            row.title, row.points_possible, row.fetched_at = (
                record.title,
                record.points_possible,
                now,
            )
            session.add(row)
        audit(
            session,
            "canvas.quiz_catalog_refreshed",
            "canvas_quizzes",
            worker="canvas",
            count=len(records),
        )
        publish(session, "canvas")
        session.commit()
    return len(records)


def _safe_url(value: Any, *, origin: str | None = None) -> str:
    if not isinstance(value, str):
        raise EmailUnavailable("Email link configuration is invalid")
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or "\n" in value
        or "\r" in value
    ):
        raise EmailUnavailable("Email link configuration is invalid")
    if origin and f"{parsed.scheme}://{parsed.netloc}" != origin.rstrip("/"):
        raise EmailUnavailable("Password reset link must use the configured application origin")
    return value


def deliver_email(
    settings: Settings,
    recipient: str | None,
    name: str,
    kind: str,
    payload: dict,
    *,
    smtp_factory=None,
) -> None:
    """Send only configured transactional templates; never log recipient/token payloads."""
    if not settings.smtp_host or not settings.smtp_from:
        raise EmailUnavailable("Configure SMTP_HOST and SMTP_FROM to send email")
    try:
        address = validate_email(recipient or "", check_deliverability=False).normalized
        sender = validate_email(settings.smtp_from, check_deliverability=False).normalized
    except EmailNotValidError as exc:
        raise EmailUnavailable("Transactional email has an invalid recipient or sender") from exc
    if kind == "canvas_invite":
        link = _safe_url(settings.canvas_enrollment_url)
        subject = "Join the Super Fab Lab Canvas course"
        body = f"Hello {name},\n\nJoin the Super Fab Lab Canvas course to complete your lab training:\n{link}\n"
    elif kind == "password_reset":
        link = _safe_url(payload.get("reset_url"), origin=settings.app_origin)
        subject = "Reset your Super Fab Lab password"
        body = f"Hello {name},\n\nUse this link to reset your password. If you did not request it, you can ignore this email.\n{link}\n"
    else:
        raise EmailUnavailable("Unsupported transactional email template")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = address
    message["Subject"] = subject
    message.set_content(body)
    message.add_alternative(
        f'<p>Hello {escape(name)},</p><p><a href="{escape(link, quote=True)}">{escape(subject)}</a></p>',
        subtype="html",
    )
    factory = smtp_factory or smtplib.SMTP
    with factory(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


def run_email(
    email_job_id: str,
    db: Engine | None = None,
    settings: Settings | None = None,
    *,
    smtp_factory=None,
) -> None:
    db, settings = db or engine, settings or get_settings()
    id = UUID(email_job_id)
    with Session(db) as session:
        email = session.get(EmailJob, id)
        if email is None or email.state in {"sent", "cancelled"}:
            return
        user = session.exec(select(User).where(User.id == email.user_id).with_for_update()).first()
        if user is None:
            return
        if (
            not settings.smtp_host
            or not settings.smtp_from
            or (email.kind == "canvas_invite" and not settings.canvas_enrollment_url)
        ):
            email.state = "unconfigured"
            email.last_error = "SMTP sender or Canvas enrollment configuration is incomplete"
            session.add(email)
            publish(session, "email")
            session.commit()
            return
        recipient, name, kind, payload = (
            user.email,
            user.display_name,
            email.kind,
            dict(email.payload),
        )
        email.state = "sending"
        email.attempts += 1
        session.add(email)
        session.commit()
    try:
        deliver_email(settings, recipient, name, kind, payload, smtp_factory=smtp_factory)
    except Exception as exc:
        error = (
            str(exc)
            if isinstance(exc, EmailUnavailable)
            else f"SMTP handoff failed ({type(exc).__name__})"
        )
        with Session(db) as session:
            email = session.get(EmailJob, id)
            if email and email.state not in {"cancelled", "sent"}:
                email.state = "unconfigured" if isinstance(exc, EmailUnavailable) else "failed"
                email.last_error = error
                session.add(email)
                publish(session, "email")
                session.commit()
        if isinstance(exc, EmailUnavailable):
            return
        raise BackgroundFailure(error) from None
    with Session(db) as session:
        email = session.get(EmailJob, id)
        if email is None or email.state == "cancelled":
            return
        email.state, email.sent_at, email.last_error, email.payload = "sent", utcnow(), None, {}
        session.add(email)
        audit(session, "email.sent", "email_jobs", id, worker="email", kind=email.kind)
        publish(session, "email")
        session.commit()


def expire_training(training_id: str, expected_expiry: str, db: Engine | None = None) -> None:
    with Session(db or engine) as session:
        cert = session.get(Training, UUID(training_id))
        expected = datetime.fromisoformat(expected_expiry)
        if (
            cert
            and cert.revoked_at is None
            and cert.expires_at
            and expected.tzinfo is not None
            and cert.expires_at == expected
            and cert.expires_at <= utcnow()
        ):
            audit(session, "training.expired", "trainings", cert.id, worker="expiry")
            publish(session, "trainings", "occupancy")
            session.commit()


def main() -> None:
    from .jobs import app

    logging.basicConfig(level=logging.INFO)
    logger.info(
        "Procrastinate worker starting; Canvas configured=%s", get_settings().canvas_configured
    )
    app.run_worker(concurrency=4)


if __name__ == "__main__":
    main()
