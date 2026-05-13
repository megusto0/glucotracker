"""Meal categorization worker — categorize_one, categorize_batch, recompute_derived."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from glucotracker.application.categorization.rules import compute_derived_categories
from glucotracker.application.categorization.taste_profile import (
    TASTE_PROFILE_PROMPT_VERSION,
    classify_taste_profiles,
)
from glucotracker.application.categorization.window import get_anchor_for_meal
from glucotracker.domain.entities import MealStatus, TasteProfile
from glucotracker.infra.db.models import Meal, User
from glucotracker.infra.db.session import get_session_factory
from glucotracker.infra.gemini.flash_lite import FlashLiteClient, FlashLiteError

logger = logging.getLogger(__name__)

BATCH_SIZE = 25


def _get_user(session: Session, user_id: UUID) -> User | None:
    return session.scalar(select(User).where(User.id == user_id))


def _get_meal(session: Session, meal_id: UUID) -> Meal | None:
    return session.scalar(
        select(Meal)
        .where(Meal.id == meal_id)
        .options(selectinload(Meal.items))
    )


def categorize_one(
    meal_id: UUID,
    *,
    client: FlashLiteClient | None = None,
    session: Session | None = None,
) -> None:
    """Categorize a single meal (for fresh captures).

    Runs the LLM taste profile classification and computes derived categories.
    Uses its own session if none provided.
    """
    own_session = session is None
    active_session = session or get_session_factory()()
    active_client = client or FlashLiteClient()

    try:
        meal = _get_meal(active_session, meal_id)
        if meal is None:
            logger.warning("categorize_one: meal %s not found", meal_id)
            return

        user = _get_user(active_session, meal.owner_id)
        if user is None:
            logger.warning("categorize_one: user %s not found", meal.owner_id)
            return

        taste_result = None
        taste_error = None
        try:
            results = classify_taste_profiles(active_client, [meal])
            if results:
                taste_result = results[0]
        except FlashLiteError as exc:
            taste_error = str(exc)
            logger.warning(
                "categorize_one: taste classification failed for meal %s: %s",
                meal_id,
                exc,
            )

        ai_categories = None
        if taste_result is not None:
            taste = taste_result["taste_profile"]
            confidence = taste_result["confidence"]
            ai_categories = {
                "taste_profile": taste,
                "confidence": confidence,
                "model": active_client.model,
                "version": TASTE_PROFILE_PROMPT_VERSION,
                "classified_at": datetime.now(UTC).isoformat(),
            }
            if taste_error:
                ai_categories["error"] = taste_error
        elif taste_error:
            ai_categories = {
                "taste_profile": None,
                "confidence": 0.0,
                "model": active_client.model,
                "version": TASTE_PROFILE_PROMPT_VERSION,
                "classified_at": datetime.now(UTC).isoformat(),
                "error": taste_error,
            }

        taste_profile = (
            TasteProfile(taste_result["taste_profile"])
            if taste_result
            else None
        )

        anchor_minutes = get_anchor_for_meal(user, meal.eaten_at)

        brand_slug: str | None = None
        if meal.items:
            first_item = meal.items[0]
            if first_item.product and first_item.product.brand:
                brand_slug = first_item.product.brand

        has_main_meal_in_window = _has_main_meal_in_window(
            active_session, meal, taste_profile, anchor_minutes
        ) if taste_profile else False

        derived = compute_derived_categories(
            meal,
            anchor_minutes=anchor_minutes,
            brand_slug=brand_slug,
            has_main_meal_in_window=has_main_meal_in_window,
            taste=taste_profile,
        )

        meal.ai_categories = ai_categories
        meal.derived_categories = derived
        meal.categorized_at = datetime.now(UTC)

        if own_session:
            active_session.commit()
        else:
            active_session.flush()
    except Exception:
        logger.exception("categorize_one failed for meal %s", meal_id)
        if own_session:
            active_session.rollback()
        raise
    finally:
        if own_session:
            active_session.close()


def categorize_batch(
    meal_ids: list[UUID],
    *,
    client: FlashLiteClient | None = None,
    session: Session | None = None,
) -> None:
    """Categorize a batch of meals (for backfill).

    Processes meals in batches of 25 for the LLM call.
    """
    if not meal_ids:
        return

    own_session = session is None
    active_session = session or get_session_factory()()
    active_client = client or FlashLiteClient()

    try:
        for chunk_start in range(0, len(meal_ids), BATCH_SIZE):
            chunk = meal_ids[chunk_start:chunk_start + BATCH_SIZE]
            meals: list[Meal] = []
            for mid in chunk:
                meal = _get_meal(active_session, mid)
                if meal is not None:
                    meals.append(meal)
                else:
                    logger.warning("categorize_batch: meal %s not found", mid)

            if not meals:
                continue

            taste_results_by_id: dict[UUID, dict[str, Any]] = {}
            try:
                batch_results = classify_taste_profiles(active_client, meals)
                for result in batch_results:
                    if result["i"] < len(meal_ids):
                        meal_id = meal_ids[chunk_start + result["i"]]
                        taste_results_by_id[meal_id] = result
            except FlashLiteError as exc:
                logger.warning(
                    "categorize_batch: taste classification failed for chunk %d-%d: %s",
                    chunk_start,
                    chunk_start + len(chunk),
                    exc,
                )

            for _, meal in enumerate(meals):
                mid = meal.id
                taste_result = taste_results_by_id.get(mid)
                taste_profile = (
                    TasteProfile(taste_result["taste_profile"])
                    if taste_result
                    else None
                )

                user = _get_user(active_session, meal.owner_id)
                anchor_minutes = None
                if user is not None:
                    anchor_minutes = get_anchor_for_meal(user, meal.eaten_at)

                brand_slug: str | None = None
                if meal.items:
                    first_item = meal.items[0]
                    if first_item.product and first_item.product.brand:
                        brand_slug = first_item.product.brand

                ai_categories = None
                if taste_result is not None:
                    ai_categories = {
                        "taste_profile": taste_result["taste_profile"],
                        "confidence": taste_result["confidence"],
                        "model": active_client.model,
                        "version": TASTE_PROFILE_PROMPT_VERSION,
                        "classified_at": datetime.now(UTC).isoformat(),
                    }

                has_main = (
                    _has_main_meal_in_window(
                        active_session, meal, taste_profile, anchor_minutes
                    )
                    if taste_profile
                    else False
                )

                derived = compute_derived_categories(
                    meal,
                    anchor_minutes=anchor_minutes,
                    brand_slug=brand_slug,
                    has_main_meal_in_window=has_main,
                    taste=taste_profile,
                )

                meal.ai_categories = ai_categories
                meal.derived_categories = derived
                meal.categorized_at = datetime.now(UTC)

            active_session.flush()
            logger.info(
                "categorize_batch: processed %d meals (chunk %d-%d)",
                len(meals),
                chunk_start,
                chunk_start + len(chunk),
            )

        if own_session:
            active_session.commit()
    except Exception:
        logger.exception("categorize_batch failed")
        if own_session:
            active_session.rollback()
        raise
    finally:
        if own_session:
            active_session.close()


def recompute_derived(
    meal_id: UUID,
    *,
    session: Session | None = None,
) -> None:
    """Recompute derived categories for a single meal (no LLM call)."""
    own_session = session is None
    active_session = session or get_session_factory()()

    try:
        meal = _get_meal(active_session, meal_id)
        if meal is None:
            logger.warning("recompute_derived: meal %s not found", meal_id)
            return

        user = _get_user(active_session, meal.owner_id)
        anchor_minutes = None
        if user is not None:
            anchor_minutes = get_anchor_for_meal(user, meal.eaten_at)

        taste_profile = None
        if meal.ai_categories and meal.ai_categories.get("taste_profile"):
            try:
                taste_profile = TasteProfile(meal.ai_categories["taste_profile"])
            except ValueError:
                pass

        brand_slug: str | None = None
        if meal.items:
            first_item = meal.items[0]
            if first_item.product and first_item.product.brand:
                brand_slug = first_item.product.brand

        has_main = (
            _has_main_meal_in_window(
                active_session, meal, taste_profile, anchor_minutes
            )
            if taste_profile
            else False
        )

        derived = compute_derived_categories(
            meal,
            anchor_minutes=anchor_minutes,
            brand_slug=brand_slug,
            has_main_meal_in_window=has_main,
            taste=taste_profile,
        )

        meal.derived_categories = derived

        if own_session:
            active_session.commit()
        else:
            active_session.flush()
    finally:
        if own_session:
            active_session.close()


def _has_main_meal_in_window(
    session: Session,
    meal: Meal,
    taste: TasteProfile | None,
    anchor_minutes: int | None,
) -> bool:
    """Check if another accepted meal in the same window qualifies as a main_meal."""
    from glucotracker.application.categorization.rules import compute_meal_window
    from glucotracker.domain.entities import TasteProfile as TP

    if taste in (TP.drink_sweet, TP.drink_other):
        return False

    meal_window = compute_meal_window(meal.eaten_at, anchor_minutes)

    other_meals = session.scalars(
        select(Meal)
        .where(
            Meal.owner_id == meal.owner_id,
            Meal.status == MealStatus.accepted,
            Meal.id != meal.id,
        )
        .options(selectinload(Meal.items))
    ).all()

    for other in other_meals:
        other_window = compute_meal_window(other.eaten_at, anchor_minutes)
        if other_window != meal_window:
            continue

        other_brand: str | None = None
        if other.items:
            first_item = other.items[0]
            if first_item.product and first_item.product.brand:
                other_brand = first_item.product.brand

        other_provenance = compute_derived_categories(
            other,
            anchor_minutes=anchor_minutes,
            brand_slug=other_brand,
            has_main_meal_in_window=False,
            taste=None,
        ).get("provenance")

        from glucotracker.domain.entities import Provenance

        if other.total_kcal >= 350 and other.total_protein_g >= 20:
            item_count = len(other.items)
            other_taste = (
                TasteProfile(other.ai_categories["taste_profile"])
                if other.ai_categories and other.ai_categories.get("taste_profile")
                else None
            )
            if (
                other_provenance == Provenance.restaurant_fastfood.value
                and item_count >= 3
                and other_taste == TasteProfile.sweet
            ):
                pass
            return True

    return False
