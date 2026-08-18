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
                            image_url=p.get("image_url"),
                            days_to_expiry=lot.get("days_to_expiry"),
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
                    p.net_quantity,
                    p.net_unit
                FROM inventory_lots l
                LEFT JOIN products p ON l.product_id = p.id
                WHERE l.remaining_quantity > 0
                  AND l.status IN ('available', 'reserved')
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
                items.append(
                    FridgeItem(
                        id=str(r["lot_id"]),
                        lot_id=str(r["lot_id"]),
                        name=name,
                        brand=r["brand"],
                        unit=r["unit"] or "г",
                        remaining_quantity=rem,
                        weight_grams=None,
                        kcal_per_100g=float(r["kcal_per_100"]) if r["kcal_per_100"] is not None else None,
                        protein_per_100g=float(r["protein_per_100"]) if r["protein_per_100"] is not None else None,
                        fat_per_100g=float(r["fat_per_100"]) if r["fat_per_100"] is not None else None,
                        carbs_per_100g=float(r["carbs_per_100"]) if r["carbs_per_100"] is not None else None,
                        image_url=r["image_url"],
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
                    img = b.get("image_url")
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
                                image_url=img or c.get("image_url"),
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
                        image_url=r["batch_img"] or r["container_img"],
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
                            "UPDATE meal_prep_containers SET status = 'consumed', remaining_weight_g = 0 WHERE id = ?",
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
                            "UPDATE inventory_lots SET remaining_quantity = MAX(0, remaining_quantity - ?), status = CASE WHEN remaining_quantity <= ? THEN 'depleted' ELSE status END WHERE id = ?",
                            (float(quantity or 1), float(quantity or 1), lid),
                        )
                        conn.commit()
                        return True
                    except Exception as sqle:
                        logger.error("Failed SQLite consume for lot %s: %s", lid, sqle)
                    finally:
                        conn.close()
            return False

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
                return row["image_url"]

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
                return row2["image_url"]
        except Exception as e:
            logger.debug("Failed looking up image in Fridge SQLite: %s", e)
        finally:
            conn.close()
        return None
