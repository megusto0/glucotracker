"""Restaurant official source importer tests."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from glucotracker.infra.db.models import Pattern
from glucotracker.infra.db.seed import load_pattern_seeds
from glucotracker.infra.importers.bk_pdf_importer import parse_bk_text_pages
from glucotracker.infra.importers.restaurant_pdf_importer import write_seed_yaml
from glucotracker.infra.importers.rostics_pdf_importer import parse_rostics_text_pages
from glucotracker.infra.importers.vkusno_i_tochka_importer import parse_vit_html


def test_bk_importer_extracts_whopper_from_text_fixture() -> None:
    """BK importer extracts per-portion and per-100g values from official rows."""
    pages = [
        """
        Наименование фирменного блюда
        ВОППЕР Булочка для гамбургера с кунжутом
        технологическое описание
        274 г 720 260 3010 1090 27 10 44 16 53 19
        """
    ]

    items = parse_bk_text_pages(pages, source_file="bk-fixture.pdf")

    whopper = items[0]
    assert whopper.key == "whopper"
    assert whopper.display_name == "Воппер"
    assert whopper.default_grams == 274
    assert whopper.default_kcal == 720
    assert whopper.default_carbs_g == 53
    assert whopper.default_protein_g == 27
    assert whopper.default_fat_g == 44
    assert whopper.per_100g_kcal == 260
    assert whopper.per_100g_carbs_g == 19
    assert whopper.source_page == 1
    assert "воппер" in whopper.aliases


def test_bk_importer_rejects_pdf_artifact_rows() -> None:
    """BK importer ignores allergy markers and shifted-column nutrition rows."""
    pages = [
        """
        (I)),
        5 г 110 20 460 1260 460 85 1260 1060 5 1
        НАГГЕТСЫ (6 ШТ) + ПРИПРАВА «ОСТРАЯ ШТУКА»
        7 г 290 20 1210 1260 1210 85 1260 1060 15 1
        """
    ]

    items = parse_bk_text_pages(pages, source_file="bk-fixture.pdf")

    assert items == []


def test_rostics_importer_extracts_nuggets_from_text_fixture() -> None:
    """Rostic's importer prefers in-dish macros over per-100g values."""
    pages = [
        """
        БЛЮДО Наггетсы  6 шт ТТК 1106 78 14,1 14,1 15,8 246 1031 14,0 13,9 15,6 244
        """
    ]

    items = parse_rostics_text_pages(pages, source_file="rostics-fixture.pdf")

    nuggets = items[0]
    assert nuggets.key == "nuggets_6"
    assert nuggets.display_name == "Наггетсы 6 шт"
    assert nuggets.default_grams == 78
    assert nuggets.default_kcal == 244
    assert nuggets.default_carbs_g == 15.6
    assert nuggets.default_protein_g == 14.0
    assert nuggets.default_fat_g == 13.9
    assert nuggets.per_100g_kcal == 246
    assert nuggets.per_100g_carbs_g == 15.8
    assert nuggets.source_page == 1


def test_generated_yaml_is_valid(tmp_path: Path) -> None:
    """Importer output is a human-reviewable YAML seed file."""
    item = parse_bk_text_pages(
        ["ВОППЕР Булочка\n274 г 720 260 3010 1090 27 10 44 16 53 19"],
        source_file="bk-fixture.pdf",
    )[0]
    out = tmp_path / "bk.generated.yaml"

    write_seed_yaml(
        prefix="bk",
        source_name="Burger King official PDF",
        source_url="https://burgerkingrus.ru/",
        source_file="bk-fixture.pdf",
        items=[item],
        out=out,
    )

    payload = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert payload["prefix"] == "bk"
    assert payload["items"][0]["key"] == "whopper"
    assert payload["items"][0]["source_confidence"] == "official_pdf"
    assert payload["items"][0]["is_verified"] is False


def test_vit_importer_exports_partial_official_menu_cards() -> None:
    """VIT importer extracts public names/images and does not invent nutrition."""
    html = """
    <a href="https://vkusnoitochka.ru/novinki/test" class="product-card">
      <img src="/resize/290x286/upload/test/large.png" alt="Биг Тест">
      <span itemprop="name"><span>Биг Тест 220 г</span></span>
    </a>
    """

    items = parse_vit_html(html)

    assert len(items) == 1
    item = items[0]
    assert item.source_namespace == "vit"
    assert item.display_name == "Биг Тест"
    assert item.default_grams == 220
    assert item.default_kcal == 0
    assert item.default_carbs_g == 0
    assert (
        item.image_url
        == "https://vkusnoitochka.ru/resize/290x286/upload/test/large.png"
    )
    assert item.source_confidence == "official_menu_partial"


def test_generated_seed_import_is_idempotent(
    db_engine: Engine,
    tmp_path: Path,
) -> None:
    """Generated YAML loads by file path without duplicate pattern rows."""
    item = parse_bk_text_pages(
        ["ВОППЕР Булочка\n274 г 720 260 3010 1090 27 10 44 16 53 19"],
        source_file="bk-fixture.pdf",
    )[0]
    out = tmp_path / "bk.generated.yaml"
    write_seed_yaml(
        prefix="bk",
        source_name="Burger King official PDF",
        source_url="https://burgerkingrus.ru/",
        source_file="bk-fixture.pdf",
        items=[item],
        out=out,
    )

    with Session(db_engine) as session:
        first = load_pattern_seeds(seed_file=out, session=session)
        second = load_pattern_seeds(seed_file=out, session=session)
        count = session.scalar(select(func.count(Pattern.id)))
        pattern = session.scalar(select(Pattern).where(Pattern.key == "whopper"))

    assert first == 1
    assert second == 1
    assert count == 1
    assert pattern is not None
    assert pattern.source_confidence == "official_pdf"


def test_seed_loader_can_prune_removed_generated_rows(
    db_engine: Engine,
    tmp_path: Path,
) -> None:
    """Seed loader can archive generated rows absent from the reviewed seed file."""
    first = tmp_path / "bk.generated.yaml"
    first.write_text(
        """
prefix: bk
items:
  - key: whopper
    display_name: "Воппер"
    default_carbs_g: 53
    default_protein_g: 27
    default_fat_g: 44
    default_kcal: 720
    aliases: ["воппер"]
  - key: i_8
    display_name: "(I)),"
    default_carbs_g: 5
    default_protein_g: 460
    default_fat_g: 1260
    default_kcal: 110
    aliases: ["i"]
""",
        encoding="utf-8",
    )
    second = tmp_path / "bk.generated.clean.yaml"
    second.write_text(
        """
prefix: bk
items:
  - key: whopper
    display_name: "Воппер"
    default_carbs_g: 53
    default_protein_g: 27
    default_fat_g: 44
    default_kcal: 720
    aliases: ["воппер"]
""",
        encoding="utf-8",
    )

    with Session(db_engine) as session:
        load_pattern_seeds(seed_file=first, session=session)
        load_pattern_seeds(seed_file=second, prune_missing=True, session=session)
        bad = session.scalar(select(Pattern).where(Pattern.key == "i_8"))
        good = session.scalar(select(Pattern).where(Pattern.key == "whopper"))

    assert bad is not None
    assert bad.is_archived is True
    assert good is not None
    assert good.is_archived is False


def test_autocomplete_finds_imported_restaurant_alias(
    api_client: TestClient,
    db_engine: Engine,
    tmp_path: Path,
) -> None:
    """Imported restaurant items are searchable through autocomplete aliases."""
    item = parse_bk_text_pages(
        ["ВОППЕР Булочка\n274 г 720 260 3010 1090 27 10 44 16 53 19"],
        source_file="bk-fixture.pdf",
    )[0]
    out = tmp_path / "bk.generated.yaml"
    write_seed_yaml(
        prefix="bk",
        source_name="Burger King official PDF",
        source_url="https://burgerkingrus.ru/",
        source_file="bk-fixture.pdf",
        items=[item],
        out=out,
    )
    with Session(db_engine) as session:
        load_pattern_seeds(seed_file=out, session=session)

    response = api_client.get("/autocomplete", params={"q": "bk:воппер"})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["kind"] == "pattern"
    assert body[0]["token"] == "bk:whopper"
    assert body[0]["matched_alias"] == "воппер"


def test_database_marks_missing_nutrition_as_needs_review(
    api_client: TestClient,
    db_engine: Engine,
    tmp_path: Path,
) -> None:
    """Partial official-menu rows without nutrition remain review-required."""
    out = tmp_path / "vit.generated.yaml"
    out.write_text(
        """
prefix: vit
source_name: "Вкусно и точка official menu"
source_url: "https://vkusnoitochka.ru/menu"
items:
  - key: big-test
    display_name: "Биг Тест"
    default_grams: 200
    default_carbs_g: 0
    default_protein_g: 0
    default_fat_g: 0
    default_fiber_g: 0
    default_kcal: 0
    aliases: ["биг тест"]
    source_confidence: "official_menu_partial"
    is_verified: false
""",
        encoding="utf-8",
    )
    with Session(db_engine) as session:
        load_pattern_seeds(seed_file=out, session=session)

    response = api_client.get("/database/items", params={"type": "needs_review"})

    assert response.status_code == 200
    rows = response.json()["items"]
    assert rows[0]["prefix"] == "vit"
    assert "нужно проверить" in rows[0]["quality_warnings"]
    assert rows[0]["source_confidence"] == "official_menu_partial"
