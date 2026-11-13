"""Single local transaction for kiosk commands; no network or printer I/O."""

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlmodel import Session, select

from ..database import lab_lock
from ..events import audit, publish
from ..models import (
    EmailJob,
    KeyholderShift,
    SpaceLevel,
    User,
    Visit,
    utcnow,
)
from ..schemas import KeyholderInput, RegisterInput, TapInput
from .identity import add_student_identifier, find_user
from .projections import badges_for_users, public_person


def _current_shift(session):
    return session.exec(select(KeyholderShift).where(KeyholderShift.ended_at.is_(None))).first()


def _open_visit(session, user):
    return session.exec(
        select(Visit).where(Visit.user_id == user.id, Visit.exit_time.is_(None))
    ).first()


def label_for_user(session, user):
    return {
        "display_name": user.display_name,
        "avatar_url": f"/media/avatars/{user.avatar_key}" if user.avatar_key else None,
        "badges": badges_for_users(session, [user.id]).get(user.id, []),
    }


def _check_in(session, user):
    visit = Visit(user_id=user.id)
    session.add(visit)
    session.flush()
    return visit


def _check_out(session, visit, forgot_to_sign_out=False):
    visit.exit_time = utcnow()
    visit.forgot_to_sign_out = forgot_to_sign_out
    session.add(visit)


def _prompt(session, user, kind, shift):
    actions = {
        "open": ["open"],
        "override": ["override", "continue"],
        "departure": ["handoff", "close"],
    }[kind]
    return {
        "status": "keyholder_action_required",
        "message": "Confirm opening the lab" if kind == "open" else "Choose a keyholder action",
        "user": public_person(user),
        "actions": actions,
        "expected_shift_id": str(shift.id) if shift else None,
    }


def _normal_tap(session, user, *, skip_override=False):
    if not user.active:
        raise HTTPException(409, "This visitor account is inactive; ask staff")
    shift, active = _current_shift(session), _open_visit(session, user)
    if not shift:
        if user.space_level >= SpaceLevel.VOLUNTEER:
            return _prompt(session, user, "open", None)
        return {
            "status": "lab_closed",
            "message": "A volunteer or keyholder must open the lab first",
            "user": public_person(user),
        }
    if shift.user_id == user.id:
        count = len(session.exec(select(Visit.id).where(Visit.exit_time.is_(None))).all())
        if count == 1 and active:
            shift.ended_at = utcnow()
            session.add(shift)
            _check_out(session, active)
            return {
                "status": "signed_out",
                "message": "Signed out and closed the lab",
                "user": public_person(user),
            }
        return _prompt(session, user, "departure", shift)
    holder = session.get(User, shift.user_id)
    if (
        not active
        and not skip_override
        and user.space_level >= SpaceLevel.KEYHOLDER
        and user.keyholder_priority > holder.keyholder_priority
    ):
        return _prompt(session, user, "override", shift)
    if active:
        _check_out(session, active)
        return {
            "status": "signed_out",
            "message": f"Goodbye, {user.first_name}",
            "user": public_person(user),
        }
    _check_in(session, user)
    return {
        "status": "signed_in",
        "message": f"Welcome, {user.first_name}",
        "_label": label_for_user(session, user),
        "user": public_person(user),
    }


def _tap(session, data):
    user = find_user(session, data.identifier)
    if not user:
        return {
            "status": "registration_required",
            "message": "Complete your registration",
            "user": None,
            "identifier": data.identifier,
        }
    return _normal_tap(session, user)


def _register(session, data):
    if find_user(session, data.identifier):
        raise HTTPException(409, "This identifier is already registered; scan again")
    user = User(first_name=data.first_name, last_name=data.last_name, email=str(data.email))
    session.add(user)
    session.flush()
    add_student_identifier(session, user, data.identifier)
    session.flush()
    from ..jobs import enqueue_email
    from .canvas import attach_cached_canvas

    attach_cached_canvas(session, user)
    email = EmailJob(user_id=user.id)
    session.add(email)
    session.flush()
    enqueue_email(session, email.id)
    audit(session, "user.registered", "users", user.id)
    return _normal_tap(session, user)


def _keyholder(session, data):
    user = find_user(session, data.identifier)
    shift = _current_shift(session)
    if not user or not user.active:
        raise HTTPException(409, "Scan an active visitor identifier")
    if data.expected_shift_id != (shift.id if shift else None):
        raise HTTPException(409, "The lab changed; scan again")
    if data.action == "continue":
        holder = session.get(User, shift.user_id) if shift else None
        if (
            not holder
            or shift.user_id == user.id
            or _open_visit(session, user)
            or user.space_level < SpaceLevel.KEYHOLDER
            or user.keyholder_priority <= holder.keyholder_priority
        ):
            raise HTTPException(409, "The offered keyholder action is no longer available")
    if data.action == "continue":
        return _normal_tap(session, user, skip_override=True)
    if data.action == "close":
        if not shift or shift.user_id != user.id:
            raise HTTPException(403, "Only the current keyholder may close the lab")
        shift.ended_at = utcnow()
        session.add(shift)
        for visit in session.exec(select(Visit).where(Visit.exit_time.is_(None))).all():
            _check_out(
                session,
                visit,
                forgot_to_sign_out=visit.user_id != user.id,
            )
        return {
            "status": "signed_out",
            "message": "Lab closed; remaining visitors marked forgotten",
            "user": public_person(user),
        }
    if data.action == "handoff":
        if not shift or shift.user_id != user.id:
            raise HTTPException(403, "Only the current keyholder may hand off")
        target = find_user(session, data.target_identifier or "")
        if (
            not target
            or not target.active
            or target.id == user.id
            or target.space_level < SpaceLevel.VOLUNTEER
        ):
            raise HTTPException(409, "Choose a different active volunteer or keyholder")
    else:
        target = user
        minimum = SpaceLevel.KEYHOLDER if data.action == "override" else SpaceLevel.VOLUNTEER
        if user.space_level < minimum:
            raise HTTPException(403, "This visitor cannot hold the keyholder role")
        if data.action == "open" and shift:
            raise HTTPException(409, "The lab is already open")
        if data.action == "override":
            holder = session.get(User, shift.user_id) if shift else None
            if (
                not holder
                or user.keyholder_priority <= holder.keyholder_priority
                or _open_visit(session, user)
            ):
                raise HTTPException(409, "Keyholder priority or visit state changed; scan again")
    if shift:
        shift.ended_at = utcnow()
        session.add(shift)
        session.flush()
    checked_in = not _open_visit(session, target)
    if checked_in:
        _check_in(session, target)
    session.add(KeyholderShift(user_id=target.id))
    if data.action == "handoff" and data.sign_out_current_keyholder:
        active = _open_visit(session, user)
        if active:
            _check_out(session, active)
    return {
        "status": "signed_in",
        "message": f"{target.display_name} is the current keyholder",
        "_label": label_for_user(session, target) if checked_in else None,
        "user": public_person(target),
    }


def execute_command(
    session: Session, command: str, data: TapInput | RegisterInput | KeyholderInput
) -> dict:
    lab_lock(session)
    handler = {"tap": _tap, "register": _register, "keyholder": _keyholder}[command]
    result = handler(session, data)
    audit(
        session,
        f"kiosk.{command}",
        "users",
        result.get("user", {}).get("id") if result.get("user") else None,
        result=result["status"],
    )
    result["revision"] = publish(session, "occupancy", "visits", "keyholders", "users")
    result = jsonable_encoder(result)
    session.commit()
    return result
