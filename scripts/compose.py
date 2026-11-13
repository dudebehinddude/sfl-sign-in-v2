#!/usr/bin/env python3
"""Run an isolated SFL Compose instance from one explicit dotenv file."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parents[1]
KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not KEY.fullmatch(key):
            raise ValueError(f"Invalid env assignment on line {line_number}")
        if value.startswith(('"', "'")):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f"Unterminated quoted value on line {line_number}")
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if "${" in value or "$(" in value or "`" in value:
            raise ValueError(f"Use literal env values, not expansion, on line {line_number}")
        values[key] = value
    return values


def compose_command(
    env_file: Path, args: list[str], *, dev: bool = False
) -> tuple[list[str], dict[str, str]]:
    values = read_env(env_file)
    port_text = values.get("APP_PORT", "8080")
    if not port_text.isdecimal() or not 1024 <= int(port_text) <= 65535:
        raise ValueError("APP_PORT must be an integer from 1024 through 65535")
    # Namespaced by the chosen port: another beta port means different volumes/network.
    project = f"sfl-{int(port_text)}"
    env = os.environ.copy()
    # Explicit file values win over an unrelated shell's APP_PORT/DB settings.
    env.update(values)
    env["APP_PORT"] = str(int(port_text))
    env["COMPOSE_PROJECT_NAME"] = project
    # Compose interpolation cannot URL-encode credentials. Derive the private
    # connection URL here so punctuation in an env-file password remains valid.
    username = quote(values.get("POSTGRES_USER", "sfl"), safe="")
    password = quote(values.get("POSTGRES_PASSWORD", ""), safe="")
    database = quote(values.get("POSTGRES_DB", "sfl"), safe="")
    env["SFL_DATABASE_URL"] = f"postgresql+psycopg://{username}:{password}@db:5432/{database}"
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(REPO),
        "--env-file",
        str(env_file),
        "--project-name",
        project,
        "-f",
        str(REPO / "compose.yaml"),
        *(["-f", str(REPO / "compose.dev.yaml")] if dev else []),
        *args,
    ]
    return command, env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--dev", action="store_true", help="Use the Vite hot-reload frontend")
    parser.add_argument("compose_args", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    path = options.env_file.expanduser().resolve()
    if not path.is_file():
        parser.error("The selected env file does not exist")
    args = options.compose_args
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        parser.error("Specify a Compose command such as config or up --build -d")
    # Prevent overriding the isolation selected by the env file.
    if any(
        arg in {"-p", "--project-name", "--env-file", "--project-directory", "-f", "--file"}
        or arg.startswith(("--project-name=", "--env-file=", "--file="))
        for arg in args
    ):
        parser.error("Compose project/file overrides are not accepted; select another env file")
    try:
        command, env = compose_command(path, args, dev=options.dev)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"SFL instance {env['COMPOSE_PROJECT_NAME']} on port {env['APP_PORT']}", file=sys.stderr)
    return subprocess.call(command, cwd=REPO, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
