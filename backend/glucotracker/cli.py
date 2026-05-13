"""Command line utilities for backend administration."""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealStatus
from glucotracker.infra.db.models import Meal, User
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


def _backfill_categories(args: argparse.Namespace) -> int:
    """Backfill ai_categories + derived_categories for existing meals."""
    from glucotracker.application.categorization.worker import categorize_batch

    session_factory = get_session_factory()
    session = session_factory()
    try:
        stmt = select(Meal.id).where(Meal.status == MealStatus.accepted)
        if args.uncategorized_only:
            stmt = stmt.where(Meal.ai_categories.is_(None))
        stmt = stmt.order_by(Meal.eaten_at)

        meal_ids = [row[0] for row in session.execute(stmt).fetchall()]
        session.close()

        if not meal_ids:
            print("No meals to backfill.")
            return 0

        print(f"Backfilling {len(meal_ids)} meals...")
        categorize_batch(meal_ids)
        print("Done.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _backfill_postprandial(args: argparse.Namespace) -> int:
    """Backfill postprandial_response for all accepted meals."""
    from glucotracker.application.postprandial.worker import (
        recompute_postprandial,
    )

    session_factory = get_session_factory()
    session = session_factory()
    try:
        meal_ids = [
            row[0]
            for row in session.execute(
                select(Meal.id).where(Meal.status == MealStatus.accepted)
            ).fetchall()
        ]
        session.close()

        if not meal_ids:
            print("No meals to backfill.")
            return 0

        print(f"Backfilling postprandial for {len(meal_ids)} meals...")
        count = 0
        for mid in meal_ids:
            if recompute_postprandial(mid):
                count += 1
        print(f"Done. Analyzed {count} meals.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


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

    backfill_cats = subparsers.add_parser("backfill-categories")
    backfill_cats.add_argument(
        "--uncategorized-only",
        action="store_true",
        default=True,
        help="Only backfill meals without ai_categories (default: true)",
    )
    backfill_cats.set_defaults(func=_backfill_categories)

    backfill_post = subparsers.add_parser("backfill-postprandial")
    backfill_post.set_defaults(func=_backfill_postprandial)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
