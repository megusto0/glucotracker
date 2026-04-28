"""Importer for public Вкусно и точка menu data.

The official menu page is region-based and may expose names, weights, prices,
and images without nutrition values. This importer exports only public official
data it can observe and marks rows as review-required partial data.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from urllib.parse import urljoin

import httpx

from glucotracker.infra.importers.restaurant_pdf_importer import (
    RestaurantItem,
    aliases_for_name,
    deduplicate_items,
    normalize_space,
    slugify_key,
    write_seed_yaml,
)

PREFIX = "vit"
SOURCE_NAME = "Вкусно и точка official menu"
DEFAULT_SOURCE_URL = "https://vkusnoitochka.ru/menu"

_CARD_RE = re.compile(
    r'<a[^>]+href="(?P<href>[^"]+)"[^>]*class="[^"]*product-card[^"]*"[^>]*>'
    r"(?P<body>.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
_NAME_RE = re.compile(r'itemprop="name"[^>]*>(?P<label>.*?)</span>', re.DOTALL)
_IMG_RE = re.compile(r'<img[^>]+src="(?P<src>[^"]+)"', re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_IMAGE_RE = re.compile(r"https://[^\"'\\\s]+(?:jpg|jpeg|png|webp)", re.IGNORECASE)
_CATEGORY_LINK_RE = re.compile(
    r'href="(?P<href>(?:https://vkusnoitochka\.ru)?/menu/[^"]+)"',
    re.IGNORECASE,
)
_CATEGORY_ITEM_RE = re.compile(
    r'<a[^>]+class="[^"]*menu-category-item[^"]*"[^>]+href="(?P<href>[^"]+)"',
    re.IGNORECASE,
)
_NAME_WITH_WEIGHT_RE = re.compile(
    r"(?P<name>[А-ЯЁA-Z][^<>]{2,120}?)\s+"
    r"(?P<weight>\d+(?:[,.]\d+)?)\s*(?P<unit>г|мл)",
    re.IGNORECASE,
)


def _clean_label(value: str) -> str:
    """Strip HTML tags and noisy price text from a menu label."""
    text = html.unescape(_TAG_RE.sub(" ", value))
    text = normalize_space(text)
    text = re.sub(r"\s+от\s+\d+\s*₽.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*Новинка\s+", "", text, flags=re.IGNORECASE)
    return normalize_space(text)


def _item_from_label(
    label: str,
    *,
    href: str,
    image_url: str | None,
    source_url: str,
) -> RestaurantItem | None:
    """Build one partial item from a visible official menu card label."""
    label = _clean_label(label)
    if not label or label.casefold() in {"ещё", "меню"}:
        return None
    grams = None
    name = label
    weight_match = _NAME_WITH_WEIGHT_RE.search(label)
    if weight_match:
        name = normalize_space(weight_match.group("name"))
        grams = float(weight_match.group("weight").replace(",", "."))

    return RestaurantItem(
        source_namespace=PREFIX,
        key=slugify_key(name),
        display_name=name,
        default_grams=grams,
        default_kcal=0,
        default_carbs_g=0,
        default_protein_g=0,
        default_fat_g=0,
        default_fiber_g=0,
        image_url=image_url,
        aliases=aliases_for_name(name),
        source_name=SOURCE_NAME,
        source_url=urljoin(source_url, href),
        source_file=None,
        source_page=None,
        source_confidence="official_menu_partial",
        is_verified=False,
    )


def parse_vit_html(
    body: str,
    *,
    source_url: str = DEFAULT_SOURCE_URL,
) -> list[RestaurantItem]:
    """Extract partial menu rows from official public HTML when available."""
    items: list[RestaurantItem] = []

    for match in _CARD_RE.finditer(body):
        href = match.group("href")
        card_body = match.group("body")
        name_match = _NAME_RE.search(card_body)
        if not name_match:
            continue
        image_match = _IMG_RE.search(card_body)
        image_url = (
            urljoin(source_url, html.unescape(image_match.group("src")))
            if image_match
            else None
        )
        item = _item_from_label(
            name_match.group("label"),
            href=href,
            image_url=image_url,
            source_url=source_url,
        )
        if item is not None:
            items.append(item)

    if items:
        return deduplicate_items(items)

    images = _IMAGE_RE.findall(body)
    image_iter = iter(dict.fromkeys(images))
    for match in re.finditer(r">([^<>]{3,160})</a>", body, re.IGNORECASE):
        label = match.group(1)
        try:
            image_url = next(image_iter)
        except StopIteration:
            image_url = None
        item = _item_from_label(
            label,
            href=source_url,
            image_url=image_url,
            source_url=source_url,
        )
        if item is not None:
            items.append(item)

    return deduplicate_items(items)


def discover_category_urls(body: str, *, source_url: str) -> list[str]:
    """Return public official menu category URLs linked from a menu page."""
    urls: list[str] = []
    seen = {source_url.rstrip("/")}
    for match in [*_CATEGORY_LINK_RE.finditer(body), *_CATEGORY_ITEM_RE.finditer(body)]:
        url = urljoin(source_url, html.unescape(match.group("href"))).rstrip("/")
        if not url.startswith("https://vkusnoitochka.ru/"):
            continue
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def fetch_vit_items(
    *,
    source_url: str = DEFAULT_SOURCE_URL,
    timeout: float = 20,
) -> list[RestaurantItem]:
    """Fetch the official public menu page and extract partial rows."""
    headers = {"User-Agent": "glucotracker-importer/0.1"}
    response = httpx.get(
        source_url,
        follow_redirects=True,
        timeout=timeout,
        headers=headers,
    )
    response.raise_for_status()
    items = parse_vit_html(response.text, source_url=source_url)

    for category_url in discover_category_urls(response.text, source_url=source_url):
        category_response = httpx.get(
            category_url,
            follow_redirects=True,
            timeout=timeout,
            headers=headers,
        )
        if category_response.status_code >= 400:
            continue
        items.extend(parse_vit_html(category_response.text, source_url=category_url))

    return deduplicate_items(items)


def main() -> None:
    """CLI entry point for Вкусно и точка partial seed generation."""
    parser = argparse.ArgumentParser(
        description="Import public Вкусно и точка menu data."
    )
    parser.add_argument("--source-url", default=DEFAULT_SOURCE_URL)
    parser.add_argument(
        "--city", default=None, help="Reserved for future city support."
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    items = fetch_vit_items(source_url=args.source_url)
    write_seed_yaml(
        prefix=PREFIX,
        source_name=SOURCE_NAME,
        source_url=args.source_url,
        source_file=None,
        items=items,
        out=args.out,
    )
    found_images = any(item.image_url for item in items)
    print("Found official nutrition: no")
    print(f"Found official images: {'yes' if found_images else 'no'}")
    print(f"Generated vit YAML: yes ({args.out})")
    print(f"Extracted {len(items)} partial Вкусно и точка items.")


if __name__ == "__main__":
    main()
