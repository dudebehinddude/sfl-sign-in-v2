"""Explicit local administration. Never run schema bootstrap against production."""

import argparse
import getpass
import json
import os
import sys
from datetime import timedelta

from sqlmodel import Session, select

from .database import engine, init_db, lab_lock
from .events import audit, publish
from .models import (
    KeyholderShift,
    Role,
    SpaceLevel,
    Training,
    TrainingType,
    User,
    Visit,
    utcnow,
)
from .security import hash_password
from .services.identity import add_student_identifier, canonical_email, find_user


def password_from_env(name):
    password = os.environ.get(name)
    if not password:
        if not sys.stdin.isatty():
            raise SystemExit(
                f"Set {name} to a password of at least 12 characters, or use an interactive terminal"
            )
        password = getpass.getpass("Password: ")
    hash_password(password)
    return password


def bootstrap(identifier, first_name, last_name, email, password):
    from pydantic import TypeAdapter

    from .schemas import UniversityEmail, validated_identifier

    email = TypeAdapter(UniversityEmail).validate_python(email)
    identifier = validated_identifier(identifier)
    with Session(engine) as session:
        lab_lock(session)
        user = find_user(session, identifier)
        if not user:
            user = User(
                first_name=first_name,
                last_name=last_name,
                email=canonical_email(email),
                space_level=SpaceLevel.STAFF,
                keyholder_priority=10,
            )
            session.add(user)
            session.flush()
            add_student_identifier(session, user, identifier)
        if user.password_hash:
            raise SystemExit(
                "Account already exists; use an authenticated recovery flow instead of overwriting it"
            )
        user.password_hash = hash_password(password)
        user.role = Role.SUPERADMIN
        session.add(user)
        audit(session, "bootstrap.superadmin", "users", user.id)
        publish(session, "users", "permissions")
        session.commit()
        return str(user.id)


def seed_demo(password):
    with Session(engine) as session:
        lab_lock(session)
        if session.exec(select(User).limit(1)).first():
            raise SystemExit(
                "seed-demo requires an empty users table; it never mixes fixtures into existing data"
            )
        types = []
        for display_order, (name, icon) in enumerate(
            [
                ("Policies and Procedures", "policies"),
                ("Orientation", "orientation"),
                ("FDM Printing", "3d-printer"),
                ("Laser Cutter", "laser-cutter"),
                ("Resin Printing", "resin-printer"),
                ("Waterjet", "waterjet"),
            ]
        ):
            t = TrainingType(name=name, icon_key=icon, display_order=display_order)
            session.add(t)
            types.append(t)
        session.flush()
        people = []
        for i, (first, last, access, role) in enumerate(
            [
                ("Avery", "Morgan", SpaceLevel.STAFF, Role.SUPERADMIN),
                ("Jordan", "Parker", SpaceLevel.KEYHOLDER, Role.ADMIN),
                ("Casey", "Rivera", SpaceLevel.VOLUNTEER, Role.OPERATOR),
                ("Riley", "Chen", SpaceLevel.MEMBER, None),
                ("Taylor", "Brooks", SpaceLevel.MEMBER, None),
                ("Quinn", "Patel", SpaceLevel.MEMBER, None),
            ]
        ):
            user = User(
                first_name=first,
                last_name=last,
                email=f"demo{i + 1}@charlotte.edu",
                role=role,
                space_level=access,
                keyholder_priority=10 - i if access != SpaceLevel.MEMBER else -1,
            )
            session.add(user)
            session.flush()
            add_student_identifier(session, user, f"80000000{i + 1}")
            if role:
                user.password_hash = hash_password(password)
                session.add(user)
            for t in types[: min(2 + i, len(types))]:
                session.add(
                    Training(
                        user_id=user.id,
                        training_type_id=t.id,
                        awarded_at=utcnow(),
                        awarded_by_user_id=user.id,
                    )
                )
            for day in range(1, 15):
                start = utcnow() - timedelta(days=day, hours=i)
                session.add(
                    Visit(
                        user_id=user.id,
                        enter_time=start,
                        exit_time=start + timedelta(minutes=30 + i * 15),
                    )
                )
            people.append(user)
        for user in people[:4]:
            session.add(Visit(user_id=user.id))
        session.add(KeyholderShift(user_id=people[0].id))
        audit(session, "demo.seeded", "users", count=len(people))
        publish(session, "all")
        session.commit()
        return {
            "message": "Synthetic demo only; no production data imported",
            "superadmin_identifier": "800000001",
            "admin_identifier": "800000002",
            "operator_identifier": "800000003",
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "init-db", help="Create provisional candidate schema; not a production migration"
    )
    commands.add_parser(
        "init-console-roles", help="Provision configured restricted SQL reader/writer roles"
    )
    commands.add_parser("console-role-names", help="Show expected SQL role names for this database")
    bootstrap_parser = commands.add_parser("bootstrap-superadmin", aliases=["bootstrap"])
    bootstrap_parser.add_argument("--identifier", required=True)
    bootstrap_parser.add_argument("--first-name", required=True)
    bootstrap_parser.add_argument("--last-name", required=True)
    bootstrap_parser.add_argument("--email", required=True)
    bootstrap_parser.add_argument("--password-env", default="BOOTSTRAP_PASSWORD")
    commands.add_parser("init-storage", help="Initialize the configured avatar bucket")
    commands.add_parser("init-jobs", help="Initialize the Procrastinate library schema")
    demo_parser = commands.add_parser("seed-demo")
    demo_parser.add_argument("--password-env", default="DEMO_PASSWORD")
    commands.add_parser("export-openapi")
    args = parser.parse_args()
    if args.command == "init-db":
        init_db()
        from .jobs import init_jobs

        init_jobs()
        from .services.sqlconsole import bootstrap_console_roles

        with Session(engine) as session:
            result = bootstrap_console_roles(session)
            session.commit()
        print(
            json.dumps(
                {"schema": "initialized", "production_migration": False, "sql_console": result},
                default=str,
            )
        )
    elif args.command == "init-console-roles":
        from .services.sqlconsole import bootstrap_console_roles

        with Session(engine) as session:
            result = bootstrap_console_roles(session)
            session.commit()
        print(json.dumps(result, default=str))
    elif args.command == "console-role-names":
        from .services.sqlconsole import role_names

        print(json.dumps(role_names(engine.url.database), default=str))
    elif args.command in {"bootstrap", "bootstrap-superadmin"}:
        print(
            json.dumps(
                {
                    "user_id": bootstrap(
                        args.identifier,
                        args.first_name,
                        args.last_name,
                        args.email,
                        password_from_env(args.password_env),
                    )
                }
            )
        )
    elif args.command == "init-storage":
        from .services.storage import initialize_bucket

        initialize_bucket()
        print(json.dumps({"storage": "initialized"}))
    elif args.command == "init-jobs":
        from .jobs import init_jobs

        init_jobs()
        print(json.dumps({"jobs": "initialized"}))
    elif args.command == "seed-demo":
        print(json.dumps(seed_demo(password_from_env(args.password_env))))
    elif args.command == "export-openapi":
        from .main import app

        print(json.dumps(app.openapi(), indent=2))


if __name__ == "__main__":
    main()
