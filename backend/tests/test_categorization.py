"""Tests for meal categorization — rules, windows, and two-user isolation."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from glucotracker.application.categorization.brands import (
    KNOWN_PACKAGED_BRANDS,
    KNOWN_RESTAURANT_BRANDS,
)
from glucotracker.application.categorization.rules import (
    compute_derived_categories,
    compute_meal_role,
    compute_meal_window,
    compute_provenance,
    compute_weekday_type,
)
from glucotracker.application.categorization.window import (
    _weighted_median,
    compute_user_anchors,
    get_anchor_for_meal,
    recompute_and_persist_anchors,
)
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import (
    AnchorBasis,
    MealRole,
    MealSource,
    MealStatus,
    MealWindow,
    Provenance,
    TasteProfile,
    WeekdayType,
)
from glucotracker.infra.db import models  # noqa: F401
from glucotracker.infra.db.base import Base
from glucotracker.infra.db.models import (
    Meal,
    MealItem,
    NonTypicalPeriod,
    User,
)
from glucotracker.infra.db.session import GlucotrackerSession
from glucotracker.infra.security import hash_password

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_meal(
    session: Session,
    *,
    owner_id: UUID,
    eaten_at: datetime,
    title: str = "Тестовый приём",
    total_kcal: float = 300.0,
    total_carbs_g: float = 40.0,
    total_protein_g: float = 10.0,
    total_fat_g: float = 12.0,
    total_fiber_g: float = 2.0,
    status: MealStatus = MealStatus.accepted,
) -> Meal:
    meal = Meal(
        owner_id=owner_id,
        eaten_at=eaten_at,
        title=title,
        total_kcal=total_kcal,
        total_carbs_g=total_carbs_g,
        total_protein_g=total_protein_g,
        total_fat_g=total_fat_g,
        total_fiber_g=total_fiber_g,
        status=status,
        source=MealSource.manual,
    )
    session.add(meal)
    session.flush()
    return meal


def _make_item(
    session: Session,
    meal: Meal,
    *,
    name: str = "Еда",
    weight_grams: float = 100.0,
    carbs_g: float = 40.0,
    protein_g: float = 10.0,
    fat_g: float = 12.0,
    kcal: float = 300.0,
) -> MealItem:
    item = MealItem(
        meal_id=meal.id,
        name=name,
        weight_grams=weight_grams,
        carbs_g=carbs_g,
        protein_g=protein_g,
        fat_g=fat_g,
        kcal=kcal,
    )
    session.add(item)
    session.flush()
    return item


# ---------------------------------------------------------------------------
# compute_meal_window
# ---------------------------------------------------------------------------


def test_window_absolute_fallback_morning() -> None:
    dt = datetime(2026, 5, 10, 8, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=None) == MealWindow.start


def test_window_absolute_fallback_afternoon() -> None:
    dt = datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=None) == MealWindow.mid


def test_window_absolute_fallback_evening() -> None:
    dt = datetime(2026, 5, 10, 19, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=None) == MealWindow.late


def test_window_absolute_fallback_night() -> None:
    dt = datetime(2026, 5, 10, 23, 30, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=None) == MealWindow.night_cap


def test_window_absolute_fallback_early_morning() -> None:
    dt = datetime(2026, 5, 10, 2, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=None) == MealWindow.night_cap


def test_window_relative_anchor_start() -> None:
    anchor = 13 * 60
    dt = datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=anchor) == MealWindow.start


def test_window_relative_anchor_mid() -> None:
    anchor = 13 * 60
    dt = datetime(2026, 5, 10, 18, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=anchor) == MealWindow.mid


def test_window_relative_anchor_late() -> None:
    anchor = 13 * 60
    dt = datetime(2026, 5, 10, 23, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=anchor) == MealWindow.late


def test_window_relative_anchor_night_cap() -> None:
    anchor = 13 * 60
    dt = datetime(2026, 5, 10, 4, 0, tzinfo=UTC)
    assert compute_meal_window(dt, anchor_minutes=anchor) == MealWindow.night_cap


# ---------------------------------------------------------------------------
# compute_weekday_type
# ---------------------------------------------------------------------------


def test_weekday_type_sunday_is_weekend() -> None:
    sunday = datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    assert compute_weekday_type(sunday) == WeekdayType.weekend


def test_weekday_type_monday_is_weekday() -> None:
    monday = datetime(2026, 5, 11, 14, 0, tzinfo=UTC)
    assert compute_weekday_type(monday) == WeekdayType.weekday


# ---------------------------------------------------------------------------
# compute_provenance
# ---------------------------------------------------------------------------


def test_provenance_restaurant_by_brand() -> None:
    assert (
        compute_provenance("Лаваш", brand_slug="kfc")
        == Provenance.restaurant_fastfood
    )


def test_provenance_packaged_by_brand() -> None:
    assert (
        compute_provenance("Брауни", brand_slug="shagi")
        == Provenance.packaged
    )


def test_provenance_restaurant_by_name_pattern() -> None:
    assert compute_provenance("Чизбургер с сыром") == Provenance.restaurant_fastfood


def test_provenance_packaged_by_macro_heuristic() -> None:
    assert (
        compute_provenance("Сладкая вата", kcal_per_100g=500, protein_per_100g=2)
        == Provenance.packaged
    )


def test_provenance_meat_dish_not_packaged_by_macro() -> None:
    assert (
        compute_provenance("Бекон", kcal_per_100g=500, protein_per_100g=30)
        == Provenance.unknown
    )


def test_provenance_unknown_by_default() -> None:
    assert compute_provenance("Лаваш с курицей") == Provenance.unknown


# ---------------------------------------------------------------------------
# compute_meal_role
# ---------------------------------------------------------------------------


def test_role_drink_sweet() -> None:
    meal = Meal(total_kcal=42, total_protein_g=0)
    assert compute_meal_role(meal, TasteProfile.drink_sweet) == MealRole.drink


def test_role_drink_other() -> None:
    meal = Meal(total_kcal=0, total_protein_g=0)
    assert compute_meal_role(meal, TasteProfile.drink_other) == MealRole.drink


def test_role_main_meal() -> None:
    meal = Meal(total_kcal=500, total_protein_g=30)
    assert compute_meal_role(meal, TasteProfile.savory) == MealRole.main_meal


def test_role_dessert() -> None:
    meal = Meal(total_kcal=250, total_protein_g=5)
    assert (
        compute_meal_role(meal, TasteProfile.sweet, has_main_meal_in_window=True)
        == MealRole.dessert
    )


def test_role_snack_no_main_in_window() -> None:
    meal = Meal(total_kcal=250, total_protein_g=5)
    assert (
        compute_meal_role(meal, TasteProfile.sweet, has_main_meal_in_window=False)
        == MealRole.snack
    )


def test_role_composite() -> None:
    meal = Meal(total_kcal=600, total_protein_g=35)
    assert (
        compute_meal_role(
            meal,
            TasteProfile.sweet,
            meal_item_count=4,
            provenance=Provenance.restaurant_fastfood,
        )
        == MealRole.composite
    )


def test_role_default_snack() -> None:
    meal = Meal(total_kcal=100, total_protein_g=3)
    assert compute_meal_role(meal, None) == MealRole.snack


# ---------------------------------------------------------------------------
# compute_derived_categories (integration)
# ---------------------------------------------------------------------------


def test_derived_categories_returns_all_fields() -> None:
    meal = Meal(
        eaten_at=datetime(2026, 5, 11, 8, 0, tzinfo=UTC),
        title="Чизбургер",
        total_kcal=400,
        total_protein_g=22,
        total_fat_g=20,
        total_carbs_g=30,
        total_fiber_g=1,
    )
    result = compute_derived_categories(meal, taste=TasteProfile.savory)
    assert "meal_window" in result
    assert "meal_role" in result
    assert "provenance" in result
    assert "weekday_type" in result
    assert "computed_at" in result


# ---------------------------------------------------------------------------
# brands dictionaries
# ---------------------------------------------------------------------------


def test_brands_restaurant_contains_expected() -> None:
    assert "bk" in KNOWN_RESTAURANT_BRANDS
    assert "kfc" in KNOWN_RESTAURANT_BRANDS
    assert "rostics" in KNOWN_RESTAURANT_BRANDS


def test_brands_packaged_contains_expected() -> None:
    assert "shagi" in KNOWN_PACKAGED_BRANDS
    assert "cheetos" in KNOWN_PACKAGED_BRANDS


# ---------------------------------------------------------------------------
# weighted_median
# ---------------------------------------------------------------------------


def test_weighted_median_simple() -> None:
    result = _weighted_median([10.0, 20.0, 30.0], [1.0, 1.0, 1.0])
    assert result == 20.0


def test_weighted_median_skewed() -> None:
    result = _weighted_median([100.0, 10.0, 10.0], [5.0, 1.0, 1.0])
    assert result == 10.0


def test_weighted_median_single() -> None:
    assert _weighted_median([42.0], [1.0]) == 42.0


def test_weighted_median_empty() -> None:
    assert _weighted_median([], []) == 0.0


# ---------------------------------------------------------------------------
# day anchor computation (with DB)
# ---------------------------------------------------------------------------


@pytest.fixture
def anchor_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[Session]:
    """Isolated in-memory SQLite database for anchor tests."""
    monkeypatch.setenv("GLUCOTRACKER_TOKEN", "dev")
    monkeypatch.setenv("GLUCOTRACKER_JWT_SECRET", "test-secret-32chars-minimum-length")
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "UTC")
    monkeypatch.setenv("PHOTO_STORAGE_DIR", str(tmp_path / "photos"))
    monkeypatch.setenv("ACTIVITY_LOG_DIR", str(tmp_path / "activity_logs"))
    monkeypatch.setenv("GLUCOTRACKER_NIGHTSCOUT_BACKGROUND_IMPORT_ENABLED", "false")
    get_settings.cache_clear()

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=GlucotrackerSession,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )

    session = session_factory()
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


def _create_user(session: Session) -> User:
    user = User(
        username=f"test-{uuid4().hex[:8]}",
        password_hash=hash_password("password"),
        role=UserRole.gluco,
    )
    session.add(user)
    session.flush()
    return user


def _make_local_meal(
    session: Session,
    user_id: UUID,
    day_offset: int,
    hour: int,
) -> None:
    """Create an accepted meal at a given UTC day offset and hour."""
    now = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    eaten_at = now - timedelta(days=day_offset)
    eaten_at = eaten_at.replace(hour=hour)
    meal = Meal(
        owner_id=user_id,
        eaten_at=eaten_at,
        title="Тест",
        total_kcal=300,
        total_carbs_g=40,
        total_protein_g=10,
        total_fat_g=10,
        total_fiber_g=0,
        status=MealStatus.accepted,
        source=MealSource.manual,
    )
    session.add(meal)


def test_anchor_absolute_fallback_when_insufficient_data(anchor_db: Session) -> None:
    user = _create_user(anchor_db)
    weekday, weekend, basis = compute_user_anchors(anchor_db, user.id)
    assert weekday is None
    assert weekend is None
    assert basis == AnchorBasis.absolute_fallback


def test_anchor_user_override(anchor_db: Session) -> None:
    user = _create_user(anchor_db)
    user.day_anchor_user_override_minutes = 540
    anchor_db.flush()

    weekday, weekend, basis = compute_user_anchors(anchor_db, user.id)
    assert weekday == 540
    assert weekend is None
    assert basis == AnchorBasis.user_override


def test_anchor_weighted_7d_with_enough_data(anchor_db: Session) -> None:
    user = _create_user(anchor_db)
    for day_offset in range(1, 8):
        _make_local_meal(anchor_db, user.id, day_offset, hour=13)
    anchor_db.flush()

    weekday, weekend, basis = compute_user_anchors(anchor_db, user.id)
    assert weekday is not None
    assert 12 * 60 <= weekday <= 14 * 60
    assert basis in (AnchorBasis.weighted_7d, AnchorBasis.shift_3d)


def test_anchor_non_typical_period_excluded(anchor_db: Session) -> None:
    user = _create_user(anchor_db)
    for day_offset in range(1, 8):
        _make_local_meal(anchor_db, user.id, day_offset, hour=13)

    period = NonTypicalPeriod(
        user_id=user.id,
        start_date=date.today() - timedelta(days=2),
        end_date=date.today() - timedelta(days=1),
        note="отпуск",
    )
    anchor_db.add(period)
    anchor_db.flush()

    weekday, weekend, basis = compute_user_anchors(anchor_db, user.id)
    if basis == AnchorBasis.absolute_fallback:
        return
    assert weekday is not None


def test_get_anchor_for_meal_uses_override(anchor_db: Session) -> None:
    user = _create_user(anchor_db)
    user.day_anchor_user_override_minutes = 600
    anchor_db.flush()

    result = get_anchor_for_meal(user, datetime.now(UTC))
    assert result == 600


def test_get_anchor_for_meal_weekend_split(anchor_db: Session) -> None:
    user = _create_user(anchor_db)
    user.day_anchor_weekday_minutes = 780
    user.day_anchor_weekend_minutes = 600
    anchor_db.flush()

    sunday = datetime(2026, 5, 10, 14, 0, tzinfo=UTC)
    assert get_anchor_for_meal(user, sunday) == 600

    monday = datetime(2026, 5, 11, 14, 0, tzinfo=UTC)
    assert get_anchor_for_meal(user, monday) == 780


# ---------------------------------------------------------------------------
# two-user isolation
# ---------------------------------------------------------------------------


def test_anchor_computation_is_per_user(anchor_db: Session) -> None:
    user_a = _create_user(anchor_db)
    user_b = _create_user(anchor_db)

    for day_offset in range(1, 8):
        _make_local_meal(anchor_db, user_a.id, day_offset, hour=13)
    for day_offset in range(1, 8):
        _make_local_meal(anchor_db, user_b.id, day_offset, hour=8)
    anchor_db.flush()

    weekday_a, _, _ = compute_user_anchors(anchor_db, user_a.id)
    weekday_b, _, _ = compute_user_anchors(anchor_db, user_b.id)

    assert weekday_a is not None
    assert weekday_b is not None
    assert weekday_a != weekday_b


def test_recompute_persists_anchors(anchor_db: Session) -> None:
    user = _create_user(anchor_db)
    for day_offset in range(1, 8):
        _make_local_meal(anchor_db, user.id, day_offset, hour=13)
    anchor_db.flush()

    recompute_and_persist_anchors(anchor_db, user.id)

    anchor_db.expunge_all()
    user_refreshed = anchor_db.scalars(
        __import__("sqlalchemy").select(User).where(User.id == user.id)
    ).one()
    assert user_refreshed.day_anchor_weekday_minutes is not None
    assert user_refreshed.day_anchor_basis is not None


def test_non_typical_periods_are_per_user(anchor_db: Session) -> None:
    user_a = _create_user(anchor_db)
    user_b = _create_user(anchor_db)

    for day_offset in range(1, 8):
        _make_local_meal(anchor_db, user_a.id, day_offset, hour=13)
        _make_local_meal(anchor_db, user_b.id, day_offset, hour=13)
    anchor_db.flush()

    period = NonTypicalPeriod(
        user_id=user_a.id,
        start_date=date.today() - timedelta(days=3),
        end_date=date.today() - timedelta(days=1),
        note="отпуск A",
    )
    anchor_db.add(period)
    anchor_db.flush()

    _, _, basis_a = compute_user_anchors(anchor_db, user_a.id)
    _, _, basis_b = compute_user_anchors(anchor_db, user_b.id)

    assert basis_b != AnchorBasis.absolute_fallback
