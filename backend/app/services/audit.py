"""Batch-load readable audit actors and record targets for the operator history."""

from uuid import UUID

from sqlalchemy import func
from sqlmodel import select

from ..models import EmailJob, ExternalIdentity, KeyholderShift, Training, TrainingType, User, Visit


def _id(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


ACTIONS = {
    "user.created": "Created user",
    "user.registered": "Registered visitor",
    "user.updated": "Updated user",
    "user.role_changed": "Changed staff role",
    "user.password_set": "Set account password",
    "profile.updated": "Updated profile",
    "profile.avatar_updated": "Updated profile image",
    "training.awarded": "Assigned training",
    "training.revoked": "Revoked training",
    "training.expired": "Training expired",
    "training_type.created": "Created training definition",
    "training_type.updated": "Updated training definition",
    "visit.closed": "Closed visit",
    "kiosk.tap": "Scanned identifier",
    "kiosk.register": "Registered at kiosk",
    "kiosk.keyholder": "Changed keyholder state",
    "database.query.attempted": "Ran SQL query",
    "database.query.succeeded": "SQL query succeeded",
    "database.query.failed": "SQL query failed",
    "database.query.rolled_back": "Rolled back SQL preview",
    "canvas.sync_requested": "Requested Canvas sync",
    "canvas.synced": "Synchronized Canvas",
    "canvas.sync_failed": "Canvas sync failed",
    "canvas.quiz_refresh_requested": "Requested quiz refresh",
    "canvas.user_matched": "Matched cached Canvas record",
    "print.requested": "Sent label",
    "email.sent": "Sent email",
    "bootstrap.superadmin": "Created first superadmin",
    "demo.seeded": "Loaded synthetic demo",
    "users.imported": "Imported users",
}


def readable_audits(session, rows):
    grouped = {}
    for row in rows:
        identifier = _id(row.entity_id)
        if identifier:
            grouped.setdefault(row.entity_type, set()).add(identifier)
    user_ids = {row.actor_user_id for row in rows if row.actor_user_id} | grouped.get(
        "users", set()
    )
    targets = {}
    for model, kind in [
        (Visit, "visits"),
        (KeyholderShift, "keyholder_shifts"),
        (EmailJob, "email_jobs"),
    ]:
        ids = grouped.get(kind, set())
        if ids:
            for record in session.exec(select(model).where(model.id.in_(ids))).all():
                user_ids.add(record.user_id)
                targets[(kind, str(record.id))] = (record.user_id, None)
    type_ids = set(grouped.get("training_types", set()))
    ids = grouped.get("trainings", set())
    if ids:
        records = session.exec(
            select(
                Training.id,
                Training.training_type_id,
                func.coalesce(Training.user_id, ExternalIdentity.user_id),
            )
            .outerjoin(ExternalIdentity, Training.external_identity_id == ExternalIdentity.id)
            .where(Training.id.in_(ids))
        ).all()
        for record_id, type_id, user_id in records:
            if user_id:
                user_ids.add(user_id)
            type_ids.add(type_id)
            targets[("trainings", str(record_id))] = (user_id, type_id)
    users = (
        {user.id: user for user in session.exec(select(User).where(User.id.in_(user_ids))).all()}
        if user_ids
        else {}
    )
    types = (
        {
            definition.id: definition
            for definition in session.exec(
                select(TrainingType).where(TrainingType.id.in_(type_ids))
            ).all()
        }
        if type_ids
        else {}
    )
    result = []
    for row in rows:
        actor = users.get(row.actor_user_id)
        user_id, type_id = targets.get((row.entity_type, row.entity_id), (None, None))
        if row.entity_type == "users":
            user_id = _id(row.entity_id)
        if row.entity_type == "training_types":
            type_id = _id(row.entity_id)
        user, definition = users.get(user_id), types.get(type_id)
        name = user.display_name if user else None
        if definition:
            name = f"{definition.name} · {name}" if name else definition.name
        target_name = name or {
            "database": "Database",
            "canvas_quizzes": "Canvas quizzes",
            "storage": "Storage",
        }.get(row.entity_type, row.entity_type.replace("_", " ").capitalize())
        href = (
            f"/admin/users/{user.id}"
            if user
            else "/admin/training-types"
            if definition
            else {
                "database": "/admin/database",
                "storage": "/admin/storage",
                "canvas_quizzes": "/admin/canvas",
            }.get(row.entity_type)
        )
        result.append(
            {
                "id": str(row.id),
                "occurred_at": row.occurred_at,
                "action": row.action,
                "action_label": ACTIONS.get(
                    row.action, row.action.replace(".", " ").replace("_", " ").capitalize()
                ),
                "actor_name": actor.display_name
                if actor
                else str(row.details.get("worker", "System")).replace("_", " ").capitalize(),
                "actor_href": f"/admin/users/{actor.id}" if actor else None,
                "target_name": target_name,
                "target_href": href,
                "details": row.details,
            }
        )
    return result
