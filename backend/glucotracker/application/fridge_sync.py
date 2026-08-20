"""Fridge and MealPrep integration service for GlucoTracker.

Connects GlucoTracker with Fridge API (http://127.0.0.1:8011) and SQLite database
to expose live available food stock and sync consumption events.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from glucotracker.config import Settings, get_settings

logger = logging.getLogger("glucotracker.fridge")

#: Addresses that only mean anything on the machine the two services share.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "0.0.0.0", "::1", "[::1]"})


def _row_value(row: Any, column: str) -> Any:
    """A column that may not exist yet on an older fridge database."""
    try:
        return row[column]
    except (IndexError, KeyError):
        return None


def _shared_media_url(raw: Any, api_url: str) -> str | None:
    """Turn a Fridge picture address into one a phone can actually fetch.

    The Fridge stamps its own base into the address it hands out, and that base
    is `http://127.0.0.1:8011` — the loopback of the machine it shares with
    GlucoTracker. A browser on that machine loads the picture; a phone resolves
    127.0.0.1 to itself and gets nothing, which is why a meal prep photographed
    in the Fridge showed an empty frame here while lots whose picture happened
    to be stored as a bare path showed up fine.

    Both services read the same directory — GlucoTracker mounts it at
    `/uploaded-media` — so the path is the whole of what is worth keeping. A
    picture that genuinely lives elsewhere, on a shop's CDN, is passed through
    untouched: it is reachable from anywhere already.
    """
    if raw is None:
        return None
    value = str(raw).strip()
    if not value:
        return None
    if value.startswith("/"):
        return value

    parts = urllib.parse.urlsplit(value)
    if not parts.scheme or not parts.netloc:
        return value

    fridge_host = urllib.parse.urlsplit(api_url).hostname
    is_ours = parts.hostname in _LOOPBACK_HOSTS or (
        fridge_host is not None and parts.hostname == fridge_host
    )
    if not is_ours:
        return value

    path = parts.path or ""
    if not path:
        return None
    return f"{path}?{parts.query}" if parts.query else path


class FridgeItem:
    def __init__(
        self,
        id: str,
        lot_id: str,
        name: str,
        brand: str | None,
        unit: str,
        remaining_quantity: float,
        weight_grams: float | None,
        kcal_per_100g: float | None,
        protein_per_100g: float | None,
        fat_per_100g: float | None,
        carbs_per_100g: float | None,
        image_url: str | None,
        days_to_expiry: int | None = None,
        # Grams of one piece, for lots counted in pieces. The fridge's
        # enrichment estimates it per product — an egg is not an apple is not a
        # head of garlic — and without it every piece was assumed to weigh 100 g.
        piece_weight_g: float | None = None,
        # "pcs", "g", or None while nobody has said. Whether a piece is what
        # you eat is not something the weight of one can answer: an apple and a
        # jar of sweetener both weigh 180 g apiece.
        serving_unit: str | None = None,
        # The fridge's product this lot is of. The serving unit is answered
        # once for the product, not again for every jar of it bought since.
        product_id: str | None = None,
    ):
        self.id = id
        self.lot_id = lot_id
        self.name = name
        self.brand = brand
        self.unit = unit
        self.remaining_quantity = remaining_quantity
        self.weight_grams = weight_grams
        self.kcal_per_100g = kcal_per_100g
        self.protein_per_100g = protein_per_100g
        self.fat_per_100g = fat_per_100g
        self.carbs_per_100g = carbs_per_100g
        self.image_url = image_url
        self.days_to_expiry = days_to_expiry
        self.piece_weight_g = piece_weight_g
        self.serving_unit = serving_unit
        self.product_id = product_id


class MealPrepItem:
    def __init__(
        self,
        container_id: str,
        batch_id: str,
        dish_name: str,
        public_code: str,
        net_weight_g: float,
        remaining_weight_g: float,
        kcal: float,
        protein: float,
        fat: float,
        carbs: float,
        image_url: str | None,
    ):
        self.container_id = container_id
        self.batch_id = batch_id
        self.dish_name = dish_name
        self.public_code = public_code
        self.net_weight_g = net_weight_g
        self.remaining_weight_g = remaining_weight_g
        self.kcal = kcal
        self.protein = protein
        self.fat = fat
        self.carbs = carbs
        self.image_url = image_url


class FridgeIntegrationService:
    """Orchestrates communication with Fridge API and database."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.api_url = getattr(self.settings, "fridge_api_url", "http://127.0.0.1:8011").rstrip("/")
        self.db_path = getattr(self.settings, "fridge_db_path", "/media/megusto/storage/fridge/data/fridge.db")

    def _open_db(self) -> sqlite3.Connection | None:
        db_file = Path(self.db_path)
        if db_file.exists():
            try:
                conn = sqlite3.connect(str(db_file), timeout=2.0)
                conn.row_factory = sqlite3.Row
                return conn
            except Exception as e:
                logger.warning("Could not connect directly to Fridge SQLite: %s", e)
        return None

    def _media_url(self, raw: Any) -> str | None:
        """This service's Fridge base, applied to :func:`_shared_media_url`."""
        return _shared_media_url(raw, self.api_url)

    def fetch_available_inventory(self, owner_id: UUID | str | None = None) -> list[FridgeItem]:
        """Fetch available (non-empty) inventory lots from Fridge API or local database."""
        # 1. Try Fridge HTTP API
        try:
            headers = {"Content-Type": "application/json"}
            if owner_id:
                headers["X-User-Id"] = str(owner_id)
            req = urllib.request.Request(f"{self.api_url}/inventory?include_empty=false", headers=headers)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=1.5) as resp:
                data = json.load(resp)
                items = []
                for lot in data:
                    rem = float(lot.get("remaining_quantity") or 0)
                    # Filter out 0/depleted stock
                    if rem <= 0 or lot.get("status") not in ("available", "reserved"):
                        continue
                    p = lot.get("product") or {}
                    items.append(
                        FridgeItem(
                            id=lot["id"],
                            lot_id=lot["id"],
                            name=lot.get("display_name") or p.get("canonical_name") or "Продукт",
                            brand=p.get("brand"),
                            unit=lot.get("unit") or "г",
                            remaining_quantity=rem,
                            weight_grams=float(lot["weight_grams"]) if lot.get("weight_grams") else None,
                            kcal_per_100g=float(p["kcal_per_100"]) if p.get("kcal_per_100") is not None else None,
                            protein_per_100g=float(p["protein_per_100"]) if p.get("protein_per_100") is not None else None,
                            fat_per_100g=float(p["fat_per_100"]) if p.get("fat_per_100") is not None else None,
                            carbs_per_100g=float(p["carbs_per_100"]) if p.get("carbs_per_100") is not None else None,
                            image_url=self._media_url(p.get("image_url")),
                            serving_unit=p.get("serving_unit"),
                            product_id=str(p["id"]) if p.get("id") else None,
                            days_to_expiry=lot.get("days_to_expiry"),
                            piece_weight_g=(
                                float(p["piece_weight_g"])
                                if p.get("piece_weight_g")
                                else None
                            ),
                        )
                    )
                return items
        except Exception as e:
            logger.debug("Fridge API HTTP /inventory unavailable, falling back to SQLite: %s", e)

        # 2. Fallback to direct SQLite read
        conn = self._open_db()
        if not conn:
            return []

        try:
            query = """
                SELECT 
                    l.id AS lot_id,
                    l.display_name,
                    l.remaining_quantity,
                    l.unit,
                    l.status,
                    p.id AS product_id,
                    p.canonical_name,
                    p.brand,
                    p.kcal_per_100,
                    p.protein_per_100,
                    p.fat_per_100,
                    p.carbs_per_100,
                    p.image_url,
                    p.piece_weight_g,
                    p.serving_unit,
                    p.net_quantity,
                    p.net_unit
                FROM inventory_lots l
                LEFT JOIN products p ON l.product_id = p.id
                WHERE l.remaining_quantity > 0
                  -- The fridge stores enum names, and they are upper case:
                  -- AVAILABLE, DEPLETED, DISCARDED. Matching them in lower
                  -- case matched nothing at all, so this fallback quietly
                  -- reported an empty fridge every time the service was down
                  -- — which is the only time it runs.
                  AND lower(l.status) IN ('available', 'reserved')
            """
            rows = conn.execute(query).fetchall()
            items = []
            for r in rows:
                rem = float(r["remaining_quantity"] or 0)
                if rem <= 0:
                    continue
                name = r["canonical_name"] or r["display_name"]
                if r["brand"] and r["brand"].lower() not in name.lower():
                    name = f"{r['brand']} {name}"
                # These three columns were selected and then thrown away, which
                # is why every piece item came back weighing 100 g: the mapper
                # divided a None total by the count and fell to its default.
                piece_weight = (
                    float(r["piece_weight_g"]) if r["piece_weight_g"] is not None else None
                )
                net_quantity = (
                    float(r["net_quantity"]) if r["net_quantity"] is not None else None
                )
                net_unit = (r["net_unit"] or "").lower().strip()
                if piece_weight:
                    total_grams: float | None = piece_weight * rem
                elif net_quantity and net_unit in ("g", "г", "ml", "мл"):
                    total_grams = net_quantity
                else:
                    total_grams = None
                items.append(
                    FridgeItem(
                        id=str(r["lot_id"]),
                        lot_id=str(r["lot_id"]),
                        name=name,
                        brand=r["brand"],
                        unit=r["unit"] or "г",
                        remaining_quantity=rem,
                        weight_grams=total_grams,
                        piece_weight_g=piece_weight,
                        kcal_per_100g=float(r["kcal_per_100"]) if r["kcal_per_100"] is not None else None,
                        protein_per_100g=float(r["protein_per_100"]) if r["protein_per_100"] is not None else None,
                        fat_per_100g=float(r["fat_per_100"]) if r["fat_per_100"] is not None else None,
                        carbs_per_100g=float(r["carbs_per_100"]) if r["carbs_per_100"] is not None else None,
                        image_url=self._media_url(r["image_url"]),
                        serving_unit=_row_value(r, "serving_unit"),
                        product_id=(
                            str(r["product_id"]) if _row_value(r, "product_id") else None
                        ),
                    )
                )
            return items
        finally:
            conn.close()

    def fetch_available_mealpreps(self, owner_id: UUID | str | None = None) -> list[MealPrepItem]:
        """Fetch ready (unconsumed) MealPrep containers from Fridge API or local database."""
        # 1. Try Fridge HTTP API
        try:
            headers = {"Content-Type": "application/json"}
            if owner_id:
                headers["X-User-Id"] = str(owner_id)
            req = urllib.request.Request(f"{self.api_url}/meal-prep/batches", headers=headers)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=1.5) as resp:
                batches = json.load(resp)
                items = []
                for b in batches:
                    dish_name = b.get("name") or "Милпреп"
                    img = self._media_url(b.get("image_url"))
                    for c in b.get("containers", []):
                        rem_w = float(c.get("remaining_weight_g") or c.get("net_weight_g") or 0)
                        if rem_w <= 0 or c.get("status") == "consumed":
                            continue
                        items.append(
                            MealPrepItem(
                                container_id=c["id"],
                                batch_id=b["id"],
                                dish_name=dish_name,
                                public_code=c.get("public_code") or "MP",
                                net_weight_g=float(c.get("net_weight_g") or 0),
                                remaining_weight_g=rem_w,
                                kcal=float(c.get("kcal") or 0),
                                protein=float(c.get("protein") or 0),
                                fat=float(c.get("fat") or 0),
                                carbs=float(c.get("carbs") or 0),
                                image_url=img or self._media_url(c.get("image_url")),
                            )
                        )
                return items
        except Exception as e:
            logger.debug("Fridge API HTTP /meal-prep/batches unavailable, falling back to SQLite: %s", e)

        # 2. Fallback to direct SQLite read
        conn = self._open_db()
        if not conn:
            return []

        try:
            query = """
                SELECT 
                    c.id AS container_id,
                    c.batch_id,
                    c.public_code,
                    c.net_weight_g,
                    c.remaining_weight_g,
                    c.status,
                    c.kcal,
                    c.protein,
                    c.fat,
                    c.carbs,
                    c.image_url AS container_img,
                    b.name AS dish_name,
                    b.image_url AS batch_img
                FROM meal_prep_containers c
                JOIN meal_prep_batches b ON c.batch_id = b.id
                WHERE (c.status != 'consumed' OR c.status IS NULL)
                  AND (c.remaining_weight_g > 0 OR c.remaining_weight_g IS NULL)
            """
            rows = conn.execute(query).fetchall()
            items = []
            for r in rows:
                net_w = float(r["net_weight_g"] or 0)
                rem_w = float(r["remaining_weight_g"] if r["remaining_weight_g"] is not None else net_w)
                if rem_w <= 0 or r["status"] == "consumed":
                    continue
                items.append(
                    MealPrepItem(
                        container_id=str(r["container_id"]),
                        batch_id=str(r["batch_id"]),
                        dish_name=r["dish_name"] or "Милпреп",
                        public_code=r["public_code"] or "MP",
                        net_weight_g=net_w,
                        remaining_weight_g=rem_w,
                        kcal=float(r["kcal"] or 0),
                        protein=float(r["protein"] or 0),
                        fat=float(r["fat"] or 0),
                        carbs=float(r["carbs"] or 0),
                        image_url=self._media_url(r["batch_img"] or r["container_img"]),
                    )
                )
            return items
        finally:
            conn.close()

    def consume_item(
        self,
        *,
        lot_id: str | UUID | None = None,
        container_id: str | UUID | None = None,
        quantity: Decimal | float | int | None = None,
        unit: str | None = None,
        meal_id: UUID | str | None = None,
        owner_id: UUID | str | None = None,
    ) -> bool:
        """Deduct stock from Fridge when consumed in GlucoTracker."""
        owner_hdr = str(owner_id) if owner_id else "f51669a5-b262-475b-979c-4da82b072266"

        # A) MealPrep Container Consumption
        if container_id:
            cid = str(container_id).replace("mp:", "").strip()
            try:
                payload: dict[str, Any] = {}
                if quantity is not None:
                    payload["consumed_weight_g"] = str(quantity)
                if meal_id:
                    payload["glucotracker_meal_id"] = str(meal_id)
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.api_url}/containers/{cid}/consume",
                    data=data,
                    headers={"Content-Type": "application/json", "X-User-Id": owner_hdr},
                    method="POST",
                )
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(req, timeout=2.0) as resp:
                    return resp.status in (200, 201)
            except Exception as e:
                logger.warning("Failed to consume MealPrep container %s via HTTP: %s", cid, e)
                # Fallback to direct SQLite update
                conn = self._open_db()
                if conn:
                    try:
                        conn.execute(
                            # Upper case, as the fridge's own enum stores it.
                            # 'consumed' is a value it cannot read back.
                            "UPDATE meal_prep_containers"
                            " SET status = 'CONSUMED', remaining_weight_g = 0"
                            " WHERE id = ?",
                            (cid,),
                        )
                        conn.commit()
                        return True
                    except Exception as sqle:
                        logger.error("Failed SQLite consume for container %s: %s", cid, sqle)
                    finally:
                        conn.close()
            return False

        # B) Inventory Product Lot Consumption
        if lot_id:
            lid = str(lot_id).replace("fridge:", "").strip()
            qty = str(quantity) if quantity is not None else None
            u = unit or "g"
            try:
                payload = {
                    "items": [{"lot_id": lid, "quantity": qty, "unit": u}],
                    "reason": "consumed",
                }
                # So deleting the meal can find this movement again. Without it
                # the fridge records what left the shelf but not why, and an
                # entry added by mistake takes its stock with it for good.
                if meal_id:
                    payload["glucotracker_meal_id"] = str(meal_id)
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    f"{self.api_url}/inventory/consume",
                    data=data,
                    headers={"Content-Type": "application/json", "X-User-Id": owner_hdr},
                    method="POST",
                )
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(req, timeout=2.0) as resp:
                    return resp.status == 200
            except Exception as e:
                logger.warning("Failed to consume inventory lot %s via HTTP: %s", lid, e)
                # Fallback to direct SQLite update
                conn = self._open_db()
                if conn:
                    try:
                        conn.execute(
                            "UPDATE inventory_lots"
                            " SET remaining_quantity = MAX(0, remaining_quantity - ?),"
                            " status = CASE WHEN remaining_quantity <= ?"
                            " THEN 'DEPLETED' ELSE status END"
                            " WHERE id = ?",
                            (float(quantity or 1), float(quantity or 1), lid),
                        )
                        conn.commit()
                        return True
                    except Exception as sqle:
                        logger.error("Failed SQLite consume for lot %s: %s", lid, sqle)
                    finally:
                        conn.close()
            return False

    def revert_consumption(
        self,
        meal_id: UUID | str,
        owner_id: UUID | str | None = None,
    ) -> str:
        """Put back what one deleted meal took out of the fridge.

        Whole, not partial: an entry from GlucoTracker is either the whole
        container or a mistake, and it is the mistakes that get deleted.

        HTTP only, deliberately. The direct-SQLite fallback that `consume_item`
        keeps is a single UPDATE; putting stock back means restoring quantities,
        clearing a depleted flag, resurrecting a container and writing the
        compensating movement, and half of that applied by hand is worse than
        none of it. If the fridge is down the caller is told and the meal is
        deleted anyway.
        """
        try:
            headers = {"Content-Type": "application/json"}
            if owner_id:
                headers["X-User-Id"] = str(owner_id)
            data = json.dumps({"glucotracker_meal_id": str(meal_id)}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_url}/inventory/consume/revert",
                data=data,
                headers=headers,
                method="POST",
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=2.0) as resp:
                if resp.status != 200:
                    return f"HTTP {resp.status}"
            return ""
        except Exception as exc:
            logger.warning("Could not return stock for meal %s: %s", meal_id, exc)
            return str(exc) or exc.__class__.__name__

    def _product_for_lot(
        self,
        lot_id: str,
        owner_id: UUID | str | None = None,
    ) -> str | None:
        """Which product a lot is of, whether or not any of it is left.

        Deliberately not `fetch_available_inventory`: that one hides empty
        lots, which is right for a shopping list and wrong here. Answering
        «как это едят» about the bottle you have just finished is the most
        natural moment to be asked, and resolving through the available list
        made exactly that answer land nowhere.
        """
        wanted = str(lot_id).replace("fridge:", "").strip()
        headers = {"Content-Type": "application/json"}
        if owner_id:
            headers["X-User-Id"] = str(owner_id)
        try:
            req = urllib.request.Request(
                f"{self.api_url}/inventory?include_empty=true", headers=headers
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=1.5) as resp:
                for lot in json.load(resp):
                    if str(lot.get("id", "")).strip() != wanted:
                        continue
                    product = lot.get("product") or {}
                    return str(product["id"]) if product.get("id") else None
        except Exception as exc:
            logger.debug("Fridge HTTP could not resolve lot %s: %s", wanted, exc)

        conn = self._open_db()
        if not conn:
            return None
        try:
            row = conn.execute(
                "SELECT product_id FROM inventory_lots"
                " WHERE REPLACE(id, '-', '') = ? LIMIT 1",
                (wanted.replace("-", "").lower(),),
            ).fetchone()
            return str(row["product_id"]) if row and row["product_id"] else None
        except Exception as exc:
            logger.warning("Could not resolve lot %s in fridge SQLite: %s", wanted, exc)
            return None
        finally:
            conn.close()

    def set_serving_unit(
        self,
        lot_id: str,
        unit: str,
        owner_id: UUID | str | None = None,
    ) -> str:
        """Tell the fridge how one of its products is eaten.

        Addressed by lot, because a lot is what a client holds — the code on a
        jar resolves to the jar, not to the idea of the jar. The answer is
        stored against the product, so the next jar of the same thing arrives
        already knowing.

        HTTP only. This writes a field the fridge's own screens read, and a
        half-applied write by hand is worse than a failure that says so.
        """
        wanted = str(lot_id).replace("fridge:", "").strip()
        product_id = self._product_for_lot(wanted, owner_id)
        if not product_id:
            return "not_found"
        try:
            headers = {"Content-Type": "application/json"}
            if owner_id:
                headers["X-User-Id"] = str(owner_id)
            data = json.dumps({"serving_unit": unit}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_url}/products/{product_id}/serving-unit",
                data=data,
                headers=headers,
                method="PATCH",
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=2.0) as resp:
                return "ok" if resp.status == 200 else f"HTTP {resp.status}"
        except Exception as exc:
            logger.warning("Could not set serving unit for lot %s: %s", wanted, exc)
            return str(exc) or exc.__class__.__name__

    def set_batch_image(self, batch_id: str, image_url: str) -> str:
        """Attach a picture to a meal-prep batch, and to its containers.

        A batch is cooked once and photographed once; every container of it is
        the same food, so the picture belongs to all of them. Written straight
        to the fridge database rather than through its HTTP API — the same path
        `consume_item` already takes, and it works when the fridge service is
        down while its file is not.

        Returns why it failed rather than just that it did: «no such batch» and
        «the file is not writable by this process» are different problems with
        different fixes, and reporting both as a 404 sends you looking in the
        wrong place. Reading the fridge needs only read permission, so this is
        the first call that can fail on a database everything else can use.
        """
        conn = self._open_db()
        if not conn:
            logger.error("Fridge database not reachable at %s", self.db_path)
            return "unreachable"
        try:
            clean = str(batch_id).replace("-", "").lower().strip()
            cursor = conn.execute(
                "UPDATE meal_prep_batches SET image_url = ?"
                " WHERE REPLACE(id, '-', '') = ?",
                (image_url, clean),
            )
            if cursor.rowcount == 0:
                return "not_found"
            conn.execute(
                "UPDATE meal_prep_containers SET image_url = ?"
                " WHERE REPLACE(batch_id, '-', '') = ?",
                (image_url, clean),
            )
            conn.commit()
            return "ok"
        except sqlite3.OperationalError as exc:
            # «attempt to write a readonly database» lands here when the file
            # belongs to the fridge service and this process only reads it.
            logger.error("Cannot write to fridge database %s: %s", self.db_path, exc)
            return "readonly"
        except Exception as exc:
            logger.error("Failed to attach image to batch %s: %s", batch_id, exc)
            return "error"
        finally:
            conn.close()

    def containers_for_batch(
        self,
        container_id: str,
        count: int,
        owner_id: UUID | str | None = None,
    ) -> list[str]:
        """The oldest `count` containers still standing in one batch.

        Two containers means two real lids, not one lid holding twice as much:
        consuming a container empties it whole, so a portion of «two» that
        wrote off a single box would leave the fridge counting stock nobody
        has. `_collapse_mealpreps` shows a batch through its oldest container
        and this walks the same order onwards, so what gets written off is what
        the list said was there.

        Never returns more than it was asked for, and never fewer than the one
        container the client named — if the batch cannot be read at all, that
        one is still consumable.
        """
        wanted = str(container_id).replace("mp:", "").strip()
        if count <= 1:
            return [wanted]
        try:
            items = self.fetch_available_mealpreps(owner_id)
        except Exception as exc:
            logger.warning("Could not list the batch holding %s: %s", wanted, exc)
            return [wanted]
        batch = next(
            (i.batch_id for i in items if str(i.container_id).strip() == wanted),
            None,
        )
        if not batch:
            return [wanted]
        ordered = [
            str(i.container_id).strip()
            for i in sorted(
                (i for i in items if i.batch_id == batch),
                key=lambda i: i.public_code,
            )
        ]
        # The named container goes first whatever the sort thinks: it is the
        # one whose code the person was looking at when they picked.
        if wanted in ordered:
            ordered.remove(wanted)
        ordered.insert(0, wanted)
        return ordered[:count]

    def find_batch_for_container(self, container_id: str) -> str | None:
        """Return the batch a container belongs to.

        The client holds container ids, because that is what a code on a lid
        resolves to, but a photograph is of the dish, not of one box.
        """
        conn = self._open_db()
        if not conn:
            return None
        try:
            clean = str(container_id).replace("-", "").lower().strip()
            row = conn.execute(
                "SELECT batch_id FROM meal_prep_containers"
                " WHERE REPLACE(id, '-', '') = ? LIMIT 1",
                (clean,),
            ).fetchone()
            return str(row["batch_id"]) if row else None
        except Exception as exc:
            logger.warning("Could not resolve batch for container %s: %s", container_id, exc)
            return None
        finally:
            conn.close()

    def get_image_for_item_id(self, item_id: str, owner_id: UUID | str | None = None) -> str | None:
        """Resolve image URL for a given product lot or mealprep container UUID/id."""
        clean_id = str(item_id).replace("fridge:", "").replace("mp:", "").replace("-", "").lower().strip()
        conn = self._open_db()
        if not conn:
            return None
        try:
            row = conn.execute(
                """
                SELECT p.image_url FROM inventory_lots l
                JOIN products p ON l.product_id = p.id
                WHERE REPLACE(l.id, '-', '') = ? OR REPLACE(p.id, '-', '') = ?
                LIMIT 1
                """,
                (clean_id, clean_id),
            ).fetchone()
            if row and row["image_url"]:
                return self._media_url(row["image_url"])

            row2 = conn.execute(
                """
                SELECT b.image_url FROM meal_prep_containers c
                JOIN meal_prep_batches b ON c.batch_id = b.id
                WHERE REPLACE(c.id, '-', '') = ? OR REPLACE(b.id, '-', '') = ?
                LIMIT 1
                """,
                (clean_id, clean_id),
            ).fetchone()
            if row2 and row2["image_url"]:
                return self._media_url(row2["image_url"])
        except Exception as e:
            logger.debug("Failed looking up image in Fridge SQLite: %s", e)
        finally:
            conn.close()
        return None
