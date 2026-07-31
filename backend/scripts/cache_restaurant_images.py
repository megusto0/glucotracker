"""Cache official restaurant images in the local pattern image store.

The nutrition catalogue remains the source of truth. This script only fills image
files and ``image_url`` for existing patterns; it never creates food entries or
changes nutrition values.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select

from glucotracker.config import get_settings
from glucotracker.infra.db.models import Pattern, utc_now
from glucotracker.infra.db.session import get_session_factory
from glucotracker.infra.storage import pattern_image_store
from glucotracker.infra.storage.photo_store import MAX_PHOTO_BYTES

RESTAURANT_PREFIXES = {"bk", "rostics", "vit"}
OFFICIAL_IMAGE_HOSTS = {
    "www.bk.com",
    "cdn.prod.website-files.com",
    "rostics.ru",
    "s82079.cdn.ngenix.net",
    "vkusnoitochka.ru",
}
BK_NUGGETS_IMAGE = (
    "https://www.bk.com/assets/src/features/app-takeover/takeovers/elevation/"
    "assets/nuggets-topper.c1571c68bea4e86ee4f8f57c37bc4b7d.webp"
)
BK_ONION_RINGS_IMAGE = (
    "https://cdn.prod.website-files.com/631b4b4e277091ef01450237/"
    "636bf0cfa8793e99236a5eca_Onion%20Rings%201.png"
)
ROSTICS_MENU_URL = "https://rostics.ru/menu"
ROSTICS_IMAGE_BASE = "https://s82079.cdn.ngenix.net/330x0/"
ROSTICS_STATE_MARKER = "window.__INITIAL_STATE__ = "
VIT_MENU_URL = "https://vkusnoitochka.ru/menu"
BK_WHOPPER_IMAGE = (
    "https://cdn.prod.website-files.com/631b4b4e277091ef01450237/"
    "65947c9a2edd7ddb328fd61f_Whopper.png"
)
BK_NUGGETS_FAMILY = re.compile(r"(?iu)^наггетсы\s*\(\d+\s*шт\.?\)")
BK_ONION_RINGS_FAMILY = re.compile(
    r"(?iu)^луковые\s+кольца\s*\(\d+\s*шт\.?\)"
)
BK_STANDALONE_WHOPPER = re.compile(r"(?iu)(^|\s)воппер($|\s)")


@dataclass(frozen=True)
class ImagePayload:
    data: bytes
    extension: str


class _ProductImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.image_url: str | None = None

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "img" or self.image_url is not None:
            return
        values = {key.casefold(): value for key, value in attrs}
        if (values.get("itemprop") or "").casefold() == "image":
            self.image_url = values.get("src")


class _VitMenuParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: dict[str, str] = {}
        self._root_tag: str | None = None
        self._root_depth = 0
        self._image_url: str | None = None
        self._reading_name = False
        self._name_parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        values = {key.casefold(): value for key, value in attrs}
        classes = set((values.get("class") or "").split())
        if self._root_tag is None and tag in {"a", "li"} and "product-card" in classes:
            self._root_tag = tag
            self._root_depth = 1
            self._image_url = None
            self._name_parts = []
        elif tag == self._root_tag:
            self._root_depth += 1
        if self._root_tag is None:
            return
        if tag == "img" and self._image_url is None:
            self._image_url = values.get("src")
        if (values.get("itemprop") or "").casefold() == "name":
            self._reading_name = True

    def handle_data(self, data: str) -> None:
        if self._reading_name:
            self._name_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._root_tag is None:
            return
        if self._reading_name and tag == "span":
            self._reading_name = False
        if tag != self._root_tag:
            return
        self._root_depth -= 1
        if self._root_depth > 0:
            return
        name = " ".join("".join(self._name_parts).split())
        if name and self._image_url:
            normalized = name.casefold().replace("ё", "е")
            self.images[normalized] = urljoin(VIT_MENU_URL, self._image_url)
        self._root_tag = None
        self._image_url = None
        self._name_parts = []


def vit_menu_images(html: str) -> dict[str, str]:
    """Return current product-title to official Vkusno i tochka images."""
    parser = _VitMenuParser()
    parser.feed(html)
    return parser.images


def rostics_product_image(html: str) -> str | None:
    """Extract the official product image from a ROSTIC'S product page."""
    parser = _ProductImageParser()
    parser.feed(html)
    return parser.image_url


def rostics_menu_images(html: str) -> dict[str, str]:
    """Return normalized product-title to official CDN image mappings."""
    try:
        start = html.index(ROSTICS_STATE_MARKER) + len(ROSTICS_STATE_MARKER)
        state, _ = json.JSONDecoder().raw_decode(html[start:])
        products = state["remoteData"]["menu"]["response"]["value"]["products"]
    except (KeyError, TypeError, ValueError):
        return {}

    images: dict[str, str] = {}
    for product in products.values():
        title = product.get("title")
        image = product.get("image")
        if not isinstance(title, str) or not isinstance(image, str):
            continue
        image_url = (
            image if image.startswith("https://") else ROSTICS_IMAGE_BASE + image
        )
        short = product.get("short")
        spec = product.get("spec")
        labels = {title}
        if isinstance(spec, str) and spec.strip():
            labels.add(f"{title} {spec}")
            if isinstance(short, str) and short.strip():
                labels.add(f"{short} {spec}")
            if title.casefold().replace("ё", "е").strip() == "байтсы":
                labels.add(f"Байтсы из куриного филе, {spec}")
        for label in labels:
            images[label.casefold().replace("ё", "е").strip()] = image_url
    return images


def built_in_family_image(pattern: Pattern) -> str | None:
    """Return an official representative image for supported BK families."""
    if pattern.prefix.casefold() != "bk":
        return None
    name = pattern.display_name.strip()
    normalized = name.casefold().replace("ё", "е")
    if BK_NUGGETS_FAMILY.match(normalized):
        return BK_NUGGETS_IMAGE
    if BK_ONION_RINGS_FAMILY.match(normalized):
        return BK_ONION_RINGS_IMAGE
    if (
        BK_STANDALONE_WHOPPER.search(normalized)
        and " ролл" not in normalized
        and not normalized.startswith("экстра ")
    ):
        return BK_WHOPPER_IMAGE
    return None


def _is_official_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and host in OFFICIAL_IMAGE_HOSTS


def _extension(content_type: str, data: bytes) -> str:
    media_type = content_type.partition(";")[0].strip().casefold()
    if media_type == "image/jpeg" or data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if media_type == "image/png" or data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if media_type == "image/webp" or (
        len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    ):
        return ".webp"
    msg = f"unsupported image type: {media_type or 'unknown'}"
    raise ValueError(msg)


def _download_image(client: httpx.Client, url: str) -> ImagePayload:
    if not _is_official_url(url):
        msg = f"image host is not allow-listed: {url}"
        raise ValueError(msg)
    response = client.get(url)
    response.raise_for_status()
    data = response.content
    if not data:
        raise ValueError("image response is empty")
    if len(data) > MAX_PHOTO_BYTES:
        raise ValueError("image exceeds 10MB limit")
    return ImagePayload(
        data=data,
        extension=_extension(response.headers.get("content-type", ""), data),
    )


def _source_for_pattern(
    client: httpx.Client,
    pattern: Pattern,
    page_cache: dict[str, str | None],
    rostics_images: dict[str, str],
    vit_images: dict[str, str],
) -> str | None:
    normalized_name = pattern.display_name.casefold().replace("ё", "е").strip()
    if pattern.prefix.casefold() == "vit":
        menu_source = vit_images.get(normalized_name)
        if menu_source is not None:
            return menu_source
    if pattern.image_url and pattern.image_url.startswith(("https://", "http://")):
        return pattern.image_url
    family_source = built_in_family_image(pattern)
    if family_source is not None:
        return family_source
    if pattern.prefix.casefold() == "rostics":
        menu_source = rostics_images.get(normalized_name)
        quantity = re.search(r"(?iu)\b(\d+)\s*шт\.?", normalized_name)
        if (
            menu_source is None
            and normalized_name.startswith("сырные палочки с клюквенным соусом")
            and quantity is not None
        ):
            menu_source = rostics_images.get(
                f"сырные палочки {quantity.group(1)} шт"
            )
        if (
            menu_source is None
            and normalized_name == "байтсы из куриного филе с соусом терияки"
        ):
            menu_source = rostics_images.get("глазированные байтсы терияки")
        if menu_source is not None:
            return menu_source
    source_url = pattern.source_url or ""
    if pattern.prefix.casefold() != "rostics" or "/product/" not in source_url:
        return None
    if source_url not in page_cache:
        response = client.get(source_url)
        response.raise_for_status()
        page_cache[source_url] = rostics_product_image(response.text)
    return page_cache[source_url]


def _save_image(pattern: Pattern, payload: ImagePayload) -> Path:
    root = get_settings().photo_storage_dir.parent / "pattern_images"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{pattern.id}{payload.extension}"
    temporary = root / f".{pattern.id}{payload.extension}.tmp"
    temporary.write_bytes(payload.data)
    temporary.replace(target)
    for extension in {".jpg", ".png", ".webp"} - {payload.extension}:
        (root / f"{pattern.id}{extension}").unlink(missing_ok=True)
    return target


def cache_images(
    prefixes: Iterable[str],
    *,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Cache images and return ``(cached, already_local, unavailable)``."""
    selected_prefixes = {prefix.casefold() for prefix in prefixes}
    unknown = selected_prefixes - RESTAURANT_PREFIXES
    if unknown:
        msg = f"unsupported prefixes: {', '.join(sorted(unknown))}"
        raise ValueError(msg)

    cached = 0
    already_local = 0
    unavailable = 0
    page_cache: dict[str, str | None] = {}
    image_cache: dict[str, ImagePayload] = {}
    timeout = httpx.Timeout(25.0, connect=10.0)
    headers = {"User-Agent": "Glucotracker restaurant image cache/1.0"}

    with get_session_factory()() as session, httpx.Client(
        follow_redirects=True,
        timeout=timeout,
        headers=headers,
    ) as client:
        rostics_images: dict[str, str] = {}
        if "rostics" in selected_prefixes:
            try:
                response = client.get(ROSTICS_MENU_URL)
                rostics_images = rostics_menu_images(response.text)
                if not rostics_images:
                    response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"skip ROSTIC'S menu catalogue: {exc}")
        vit_images: dict[str, str] = {}
        if "vit" in selected_prefixes:
            try:
                response = client.get(VIT_MENU_URL)
                response.raise_for_status()
                vit_images = vit_menu_images(response.text)
            except httpx.HTTPError as exc:
                print(f"skip Vkusno i tochka menu catalogue: {exc}")
        patterns = session.scalars(
            select(Pattern)
            .where(
                Pattern.prefix.in_(selected_prefixes),
                Pattern.is_archived.is_(False),
            )
            .order_by(Pattern.prefix, Pattern.display_name)
        ).all()
        for pattern in patterns:
            family_source = built_in_family_image(pattern)
            if (
                family_source is None
                or family_source in image_cache
                or not pattern.image_url
                or not pattern.image_url.startswith("/patterns/")
            ):
                continue
            try:
                path = pattern_image_store.get_full_path(pattern.id)
                image_cache[family_source] = ImagePayload(
                    data=path.read_bytes(),
                    extension=path.suffix.casefold(),
                )
            except (OSError, pattern_image_store.PatternImageStorageError):
                continue
        for pattern in patterns:
            if pattern.image_url and pattern.image_url.startswith("/patterns/"):
                already_local += 1
                continue
            try:
                source = _source_for_pattern(
                    client,
                    pattern,
                    page_cache,
                    rostics_images,
                    vit_images,
                )
                if source is None:
                    unavailable += 1
                    continue
                payload = image_cache.get(source)
                if payload is None:
                    payload = _download_image(client, source)
                    image_cache[source] = payload
                if not dry_run:
                    _save_image(pattern, payload)
                    pattern.image_url = f"/patterns/{pattern.id}/image/file"
                    pattern.updated_at = utc_now()
                cached += 1
            except (httpx.HTTPError, ValueError) as exc:
                unavailable += 1
                print(f"skip {pattern.prefix}:{pattern.display_name}: {exc}")
        if not dry_run:
            session.commit()
    return cached, already_local, unavailable


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        action="append",
        choices=sorted(RESTAURANT_PREFIXES),
        help="Restaurant prefix to process (repeatable; defaults to all).",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    cached, already_local, unavailable = cache_images(
        args.prefix or sorted(RESTAURANT_PREFIXES),
        dry_run=args.dry_run,
    )
    action = "would cache" if args.dry_run else "cached"
    print(
        f"{action}: {cached}; already local: {already_local}; "
        f"no official image: {unavailable}"
    )


if __name__ == "__main__":
    main()
