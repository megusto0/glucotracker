"""Command line utilities for backend administration."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import User
from glucotracker.infra.db.session import get_session_factory
from glucotracker.infra.security import hash_password


def _create_user(args: argparse.Namespace) -> int:
    try:
        get_settings().validated_jwt_secret()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    username = args.username.strip()
    if not username:
        print("username must not be empty", file=sys.stderr)
        return 2

    password = getpass.getpass("Password: ")
    password_repeat = getpass.getpass("Repeat password: ")
    if password != password_repeat:
        print("passwords do not match", file=sys.stderr)
        return 2
    if not password:
        print("password must not be empty", file=sys.stderr)
        return 2

    session_factory = get_session_factory()
    session = session_factory()
    try:
        existing = session.scalar(select(User).where(User.username == username))
        if existing is not None:
            print("user already exists", file=sys.stderr)
            return 1

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=UserRole(args.role),
        )
        session.add(user)
        session.commit()
        print(f"user_id={user.id}")
        return 0
    except IntegrityError:
        session.rollback()
        print("user already exists", file=sys.stderr)
        return 1
    finally:
        session.close()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="python -m glucotracker.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_user = subparsers.add_parser("create-user")
    create_user.add_argument("--username", required=True)
    create_user.add_argument(
        "--role",
        choices=[role.value for role in UserRole],
        required=True,
    )
    create_user.set_defaults(func=_create_user)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
