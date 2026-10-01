"""VIT breakfast catalogue and local image seeding."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import Pattern, User
from glucotracker.infra.security import hash_password
from glucotracker.infra.storage import pattern_image_store
from scripts.seed_vit_breakfast import CATALOG_PATH, seed_vit_breakfast

SMALL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
)


def test_breakfast_seed_is_idempotent_and_owner_scoped(
    api_client: TestClient, tmp_path: Path
) -> None:
    items = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["items"]
    image_dir = tmp_path / "breakfast-images"
    image_dir.mkdir()
    for item in items:
        (image_dir / f"{item['key']}.png").write_bytes(SMALL_PNG)

    factory = api_client.app_state["session_factory"]
    owner_id = api_client.app_state["current_user_id"]
    with factory() as session:
        session.add(
            Pattern(
                owner_id=owner_id,
                prefix="vit",
                key="official_pirozhok",
                display_name="Пирожок Вишневый",
                default_carbs_g=42,
                is_verified=True,
            )
        )
        other = User(
            username=f"other-{uuid4()}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.commit()
        other_id = other.id
    with factory() as session:
        assert seed_vit_breakfast(session, owner_id, image_dir) == len(items)
        assert seed_vit_breakfast(session, owner_id, image_dir) == len(items)
        rows = session.scalars(
            select(Pattern).where(
                Pattern.owner_id == owner_id,
                Pattern.prefix == "vit",
                Pattern.key.like("breakfast_%"),
            )
        ).all()
        assert len(rows) == len(items) - 1 == 34
        assert all(row.image_url == f"/patterns/{row.id}/image/file" for row in rows)
        assert all(pattern_image_store.get_full_path(row.id).is_file() for row in rows)
        assert all(
            row.source_confidence in {"tastyandpoint_mirror", "third_party_catalog"}
            for row in rows
        )
        assert all(not row.is_verified for row in rows)
        official = session.scalar(
            select(Pattern).where(
                Pattern.owner_id == owner_id,
                Pattern.key == "official_pirozhok",
            )
        )
        assert official is not None
        assert official.default_carbs_g == 42
        assert official.is_verified
        assert (
            session.scalar(
                select(func.count(Pattern.id)).where(Pattern.owner_id == other_id)
            )
            == 0
        )
