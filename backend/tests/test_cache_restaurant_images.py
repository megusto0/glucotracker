"""Tests for restaurant image discovery helpers."""

import json
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType

from glucotracker.infra.db.models import Pattern


def _load_script() -> ModuleType:
    path = Path(__file__).parents[1] / "scripts" / "cache_restaurant_images.py"
    spec = spec_from_file_location("cache_restaurant_images", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def _pattern(prefix: str, name: str) -> Pattern:
    return Pattern(prefix=prefix, key="test", display_name=name, owner_id=None)


def test_extracts_rostics_product_image() -> None:
    html = (
        '<img itemProp="image" '
        'src="https://s82079.cdn.ngenix.net/330x0/dish" alt="product">'
    )
    assert SCRIPT.rostics_product_image(html) == (
        "https://s82079.cdn.ngenix.net/330x0/dish"
    )


def test_extracts_rostics_menu_catalogue() -> None:
    state = {
        "remoteData": {
            "menu": {
                "response": {
                    "value": {
                        "products": {
                            "1": {"title": "Шефбургер", "image": "dish-token"},
                            "2": {
                                "title": "Сырные палочки",
                                "short": "Сырные палочки",
                                "spec": "6 шт",
                                "image": "cheese-token",
                            },
                            "3": {
                                "title": "Байтсы",
                                "short": "Байтсы",
                                "spec": "Большие",
                                "image": "bites-token",
                            },
                        },
                    },
                },
            },
        },
    }
    html = f"<script>{SCRIPT.ROSTICS_STATE_MARKER}{json.dumps(state)}</script>"
    assert SCRIPT.rostics_menu_images(html) == {
        "шефбургер": f"{SCRIPT.ROSTICS_IMAGE_BASE}dish-token",
        "сырные палочки": f"{SCRIPT.ROSTICS_IMAGE_BASE}cheese-token",
        "сырные палочки 6 шт": f"{SCRIPT.ROSTICS_IMAGE_BASE}cheese-token",
        "байтсы": f"{SCRIPT.ROSTICS_IMAGE_BASE}bites-token",
        "байтсы большие": f"{SCRIPT.ROSTICS_IMAGE_BASE}bites-token",
        "байтсы из куриного филе, большие": (
            f"{SCRIPT.ROSTICS_IMAGE_BASE}bites-token"
        ),
    }


def test_extracts_vkusno_i_tochka_menu_cards() -> None:
    html = """
    <li class="product-card tile">
      <img src="/resize/dish.png" alt="Наггетсы">
      <span itemprop="name">Наггетсы</span>
    </li>
    """
    assert SCRIPT.vit_menu_images(html) == {
        "наггетсы": "https://vkusnoitochka.ru/resize/dish.png",
    }


def test_bk_nuggets_use_one_official_family_image() -> None:
    assert SCRIPT.built_in_family_image(_pattern("bk", "Наггетсы (3 Шт)")) == (
        SCRIPT.BK_NUGGETS_IMAGE
    )
    assert SCRIPT.built_in_family_image(
        _pattern("bk", "Наггетсы (12 Шт) + Приправа")
    ) == SCRIPT.BK_NUGGETS_IMAGE


def test_bk_onion_rings_use_official_family_image() -> None:
    assert SCRIPT.built_in_family_image(
        _pattern("bk", "Луковые Кольца (9 Шт)")
    ) == SCRIPT.BK_ONION_RINGS_IMAGE
    assert SCRIPT.built_in_family_image(
        _pattern("bk", "Луковые Кольца (3 Шт) + Приправа")
    ) == SCRIPT.BK_ONION_RINGS_IMAGE


def test_whopper_roll_is_not_folded_into_whopper_family() -> None:
    assert SCRIPT.built_in_family_image(_pattern("bk", "Двойной Воппер")) == (
        SCRIPT.BK_WHOPPER_IMAGE
    )
    assert SCRIPT.built_in_family_image(_pattern("bk", "Воппер Ролл")) is None
