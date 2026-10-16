"""Restaurant menu tidy-up: idempotent, non-destructive and owner-scoped."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from glucotracker.domain.auth import UserRole
from glucotracker.infra.db.models import Pattern, User
from glucotracker.infra.security import hash_password
from scripts.organize_restaurant_menus import (
    BK_CATALOG_PATH,
    CATALOG_PATH,
    organize_restaurant_menus,
)


def _catalog() -> dict:
    return {
        "upserts": [
            {
                "prefix": "vit",
                "key": "kartofel_fri_malenkiy",
                "name": "Картофель фри маленький",
                "grams": 76,
                "kcal": 231,
                "protein_g": 2.8,
                "fat_g": 11,
                "carbs_g": 29,
                "fiber_g": 2.8,
                "source_name": "official",
                "source_url": "https://vkusnoitochka.ru/api/nutrition/search",
                "image_url": "https://vkusnoitochka.ru/upload/fries.png",
                "aliases": ["картошка фри маленькая"],
            },
            {
                "prefix": "vit",
                "key": "kartofel_fri_bolshoi",
                "name": "Картофель фри большой",
                "grams": 147,
                "kcal": 425,
                "protein_g": 5,
                "fat_g": 20,
                "carbs_g": 53,
                "source_name": "official",
                "source_url": "https://vkusnoitochka.ru/api/nutrition/search",
                "image_url": "https://vkusnoitochka.ru/upload/fries.png",
            },
        ],
        "renames": [
            {
                "prefix": "bk",
                "key": "king_fri_bolshoi",
                "name": "Кинг Фри большой",
                "aliases": ["кинг фри xl", "картошка фри большая бк"],
                "remove_aliases": ["Кинг Фри XL"],
            },
        ],
        "archives": [
            {"prefix": "bk", "key_contains": "_priprava", "reason": "duplicate"},
        ],
    }


def _seed(session, owner_id) -> None:
    session.add_all(
        [
            Pattern(
                owner_id=owner_id,
                prefix="vit",
                key="kartofel_fri_bolshoi",
                display_name="Картофель Фри (большая порция)",
                default_grams=110,
                default_kcal=330,
                image_url="/patterns/local/image/file",
                usage_count=3,
            ),
            Pattern(
                owner_id=owner_id,
                prefix="bk",
                key="king_fri_bolshoi",
                display_name="Кинг Фри Большой",
            ),
            Pattern(
                owner_id=owner_id,
                prefix="bk",
                key="king_fri_malyi_priprava_smetana_i_luk",
                display_name="Кинг Фри Малый + Приправа «Сметана И Лук»",
            ),
        ]
    )


@pytest.mark.parametrize("target_is_first", [True, False])
def test_menu_tidy_is_idempotent_and_touches_only_its_owner(
    api_client: TestClient, target_is_first: bool
) -> None:
    factory = api_client.app_state["session_factory"]
    admin_id = api_client.app_state["current_user_id"]
    with factory() as session:
        other = User(
            username=f"other-{uuid4()}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        other_id = other.id
        _seed(session, admin_id)
        _seed(session, other_id)
        session.commit()
    target, bystander = (
        (admin_id, other_id) if target_is_first else (other_id, admin_id)
    )

    with factory() as session:
        first = organize_restaurant_menus(session, target, _catalog())
        second = organize_restaurant_menus(session, target, _catalog())
    assert (first.added, first.updated, first.archived) == (1, 1, 1)
    assert (second.added, second.updated, second.archived) == (0, 2, 0)

    with factory() as session:
        rows = {
            row.key: row
            for row in session.scalars(
                select(Pattern).where(Pattern.owner_id == target)
            )
        }
        large = rows["kartofel_fri_bolshoi"]
        assert large.display_name == "Картофель фри большой"
        assert (large.default_grams, large.default_kcal) == (147, 425)
        assert large.per_100g_kcal == round(425 / 147 * 100, 2)
        assert large.image_url == "/patterns/local/image/file"
        assert large.usage_count == 3
        small = rows["kartofel_fri_malenkiy"]
        assert small.image_url == "https://vkusnoitochka.ru/upload/fries.png"
        assert [alias.alias for alias in small.aliases] == ["картошка фри маленькая"]
        large_bk = rows["king_fri_bolshoi"]
        assert large_bk.display_name == "Кинг Фри большой"
        assert [a.alias for a in large_bk.aliases] == ["картошка фри большая бк"]
        assert rows["king_fri_malyi_priprava_smetana_i_luk"].is_archived

        untouched = {
            row.key: row
            for row in session.scalars(
                select(Pattern).where(Pattern.owner_id == bystander)
            )
        }
        assert set(untouched) == {
            "kartofel_fri_bolshoi",
            "king_fri_bolshoi",
            "king_fri_malyi_priprava_smetana_i_luk",
        }
        assert untouched["kartofel_fri_bolshoi"].default_kcal == 330
        assert not untouched["king_fri_malyi_priprava_smetana_i_luk"].is_archived
        assert untouched["king_fri_bolshoi"].aliases == []


@pytest.mark.parametrize("path", [CATALOG_PATH, BK_CATALOG_PATH])
def test_shipped_catalogue_is_well_formed(path) -> None:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    keys = [(item["prefix"], item["key"]) for item in catalog["upserts"]]
    assert len(keys) == len(set(keys))
    for item in catalog["upserts"]:
        assert item["prefix"] in {"bk", "rostics", "vit"}
        assert item["kcal"] >= 0 and item["carbs_g"] >= 0
        assert item["grams"] is None or item["grams"] > 0
        image = item.get("image_url")
        assert image is None or image.startswith(
            (
                "https://s82079.cdn.ngenix.net/",
                "https://vkusnoitochka.ru/",
                "https://eda.yandex.ru/",
            )
        )
