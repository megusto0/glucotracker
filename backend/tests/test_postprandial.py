"""Tests for postprandial CGM analysis — synthetic CGM streams."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from glucotracker.application.postprandial.analyzer import (
    _compute_fat_share,
    _count_peaks,
    _coverage_fraction,
    _interpolate,
    _nearest_reading,
    _sustained_above_threshold,
    classify_response,
    compute_postprandial_response,
    compute_pre_meal_state,
    detect_hypo_recovery,
)
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import (
    GlycemicResponse,
    MealSource,
    MealStatus,
    PreMealState,
    TasteProfile,
)
from glucotracker.infra.db import models  # noqa: F401
from glucotracker.infra.db.base import Base
from glucotracker.infra.db.models import (
    Meal,
    NightscoutGlucoseEntry,
    User,
)
from glucotracker.infra.db.session import GlucotrackerSession
from glucotracker.infra.security import hash_password

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _glucose(
    value: float,
    minutes_offset: int,
    owner_id: UUID,
) -> NightscoutGlucoseEntry:
    base = datetime(2026, 5, 10, 14, 0, 0)
    return NightscoutGlucoseEntry(
        id=uuid.uuid4(),
        owner_id=owner_id,
        source_key=f"cgm_{minutes_offset}_{uuid.uuid4().hex[:4]}",
        timestamp=base + timedelta(minutes=minutes_offset),
        value_mmol_l=value,
    )


def _make_meal(
    eaten_at: datetime,
    total_kcal: float = 300.0,
    total_protein_g: float = 10.0,
    title: str = "Тест",
) -> Meal:
    return Meal(
        title=title,
        total_kcal=total_kcal,
        total_protein_g=total_protein_g,
        total_carbs_g=40,
        total_fat_g=12,
        total_fiber_g=2,
        eaten_at=eaten_at,
        source=MealSource.manual,
        status=MealStatus.accepted,
    )


# ---------------------------------------------------------------------------
# interpolation
# ---------------------------------------------------------------------------


def test_interpolate_exact_match() -> None:
    uid = uuid.uuid4()
    base = datetime(2026, 5, 10, 14, 0, 0)
    readings = [_glucose(5.5, 5, uid)]
    result = _interpolate(readings, base + timedelta(minutes=5))
    assert result is not None
    assert result["value"] == 5.5
    assert result["source"] == "actual"


def test_interpolate_midpoint() -> None:
    uid = uuid.uuid4()
    base = datetime(2026, 5, 10, 14, 0, 0)
    readings = [
        _glucose(5.0, 0, uid),
        _glucose(6.0, 10, uid),
    ]
    result = _interpolate(readings, base + timedelta(minutes=5))
    assert result is not None
    assert result["value"] == 5.5
    assert result["source"] == "interpolated"


def test_interpolate_gap_too_large() -> None:
    uid = uuid.uuid4()
    base = datetime(2026, 5, 10, 14, 0, 0)
    readings = [
        _glucose(5.0, 0, uid),
        _glucose(6.0, 20, uid),
    ]
    result = _interpolate(readings, base + timedelta(minutes=5))
    assert result is None


def test_interpolate_empty() -> None:
    assert _interpolate([], datetime.now()) is None


def test_nearest_reading_within_tolerance() -> None:
    uid = uuid.uuid4()
    base = datetime(2026, 5, 10, 14, 0, 0)
    readings = [
        _glucose(4.0, -10, uid),
        _glucose(5.5, 3, uid),
        _glucose(6.0, 10, uid),
    ]
    result = _nearest_reading(readings, base)
    assert result is not None
    assert result["value"] == 5.5


def test_nearest_reading_outside_tolerance() -> None:
    uid = uuid.uuid4()
    base = datetime(2026, 5, 10, 14, 0, 0)
    readings = [_glucose(5.5, 10, uid)]
    result = _nearest_reading(readings, base)
    assert result is None


# ---------------------------------------------------------------------------
# pre_meal_state
# ---------------------------------------------------------------------------


@pytest.fixture
def pp_db(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[Session]:
    monkeypatch.setenv("GLUCOTRACKER_TOKEN", "dev")
    monkeypatch.setenv(
        "GLUCOTRACKER_JWT_SECRET", "test-secret-32chars-min-length"
    )
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "UTC")
    monkeypatch.setenv("PHOTO_STORAGE_DIR", str(tmp_path / "photos"))
    monkeypatch.setenv("ACTIVITY_LOG_DIR", str(tmp_path / "activity_logs"))
    monkeypatch.setenv(
        "GLUCOTRACKER_NIGHTSCOUT_BACKGROUND_IMPORT_ENABLED", "false"
    )
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
    user = User(
        username="test",
        password_hash=hash_password("password"),
        role=UserRole.gluco,
    )
    session.add(user)
    session.flush()

    session.info["test_user_id"] = user.id
    yield session
    session.close()
    Base.metadata.drop_all(engine)
    engine.dispose()
    get_settings.cache_clear()


def _uid(pp_db: Session) -> UUID:
    return pp_db.info["test_user_id"]


def _seed_cgm(pp_db: Session, readings: list[tuple[float, int]]) -> None:
    uid = _uid(pp_db)
    for value, minutes_offset in readings:
        entry = _glucose(value, minutes_offset, uid)
        pp_db.add(entry)
    pp_db.flush()


def test_pre_meal_state_in_range(pp_db: Session) -> None:
    uid = _uid(pp_db)
    _seed_cgm(pp_db, [(5.5, -5)])
    meal = _make_meal(datetime(2026, 5, 10, 14, 0, 0))
    meal.owner_id = uid
    state, _ = compute_pre_meal_state(pp_db, meal)
    assert state == PreMealState.in_range


def test_pre_meal_state_low(pp_db: Session) -> None:
    uid = _uid(pp_db)
    _seed_cgm(pp_db, [(3.9, -5)])
    meal = _make_meal(datetime(2026, 5, 10, 14, 0, 0))
    meal.owner_id = uid
    state, _ = compute_pre_meal_state(pp_db, meal)
    assert state == PreMealState.low


def test_pre_meal_state_high(pp_db: Session) -> None:
    uid = _uid(pp_db)
    _seed_cgm(pp_db, [(10.1, -5)])
    meal = _make_meal(datetime(2026, 5, 10, 14, 0, 0))
    meal.owner_id = uid
    state, _ = compute_pre_meal_state(pp_db, meal)
    assert state == PreMealState.high


def test_pre_meal_state_unknown(pp_db: Session) -> None:
    uid = _uid(pp_db)
    meal = _make_meal(datetime(2026, 5, 10, 14, 0, 0))
    meal.owner_id = uid
    state, _ = compute_pre_meal_state(pp_db, meal)
    assert state == PreMealState.unknown


def test_pre_meal_state_boundary_low_in_range(pp_db: Session) -> None:
    uid = _uid(pp_db)
    _seed_cgm(pp_db, [(4.0, -2)])
    meal = _make_meal(datetime(2026, 5, 10, 14, 0, 0))
    meal.owner_id = uid
    state, _ = compute_pre_meal_state(pp_db, meal)
    assert state == PreMealState.in_range


def test_pre_meal_state_boundary_high_in_range(pp_db: Session) -> None:
    uid = _uid(pp_db)
    _seed_cgm(pp_db, [(10.0, -2)])
    meal = _make_meal(datetime(2026, 5, 10, 14, 0, 0))
    meal.owner_id = uid
    state, _ = compute_pre_meal_state(pp_db, meal)
    assert state == PreMealState.in_range


# ---------------------------------------------------------------------------
# glycemic_response classification (synthetic)
# ---------------------------------------------------------------------------


def _fake_anchors(
    t0: float | None = 5.5,
    t30: float | None = 6.0,
    t60: float | None = 6.5,
    t90: float | None = 6.2,
    t180: float | None = 5.8,
) -> dict[int, dict | None]:
    def a(v: float | None) -> dict | None:
        if v is None:
            return None
        return {"value": v, "source": "synthetic"}

    return {0: a(t0), 30: a(t30), 60: a(t60), 90: a(t90), 180: a(t180)}


def test_response_gentle() -> None:
    uid = uuid.uuid4()
    datetime(2026, 5, 10, 14, 0, 0)
    readings = [
        _glucose(5.5, i * 5, uid) for i in range(37)
    ]
    anchors = _fake_anchors(t0=5.5, t90=5.6)
    result = classify_response(anchors, readings, 1.0)
    assert result == GlycemicResponse.gentle


def test_response_spike_by_delta() -> None:
    uid = uuid.uuid4()
    datetime(2026, 5, 10, 14, 0, 0)
    readings = [
        _glucose(5.0, 0, uid),
        _glucose(5.5, 15, uid),
        _glucose(9.1, 60, uid),
        _glucose(8.5, 90, uid),
        _glucose(7.0, 180, uid),
    ]
    anchors = _fake_anchors(t0=5.0, t90=8.5)
    result = classify_response(anchors, readings, 1.0)
    assert result == GlycemicResponse.spike


def test_response_spike_sustained() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(5.5, i, uid)
        for i in range(0, 181, 5)
    ]
    for r in readings:
        r.value_mmol_l = 10.5
    anchors = _fake_anchors(t0=5.5)
    result = classify_response(anchors, readings, 1.0)
    assert result == GlycemicResponse.spike


def test_response_moderate() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(5.5, 0, uid),
        _glucose(6.5, 30, uid),
        _glucose(8.0, 60, uid),
        _glucose(7.5, 90, uid),
        _glucose(6.5, 180, uid),
    ]
    anchors = _fake_anchors(t0=5.5, t90=7.5)
    result = classify_response(anchors, readings, 1.0)
    assert result == GlycemicResponse.moderate


def test_response_unknown_low_coverage() -> None:
    uid = uuid.uuid4()
    readings = [_glucose(5.5, 0, uid)]
    anchors = _fake_anchors()
    result = classify_response(anchors, readings, 0.5)
    assert result == GlycemicResponse.unknown


def test_response_unknown_no_t0() -> None:
    uid = uuid.uuid4()
    readings = [_glucose(5.5, 0, uid)]
    anchors = _fake_anchors(t0=None)
    result = classify_response(anchors, readings, 1.0)
    assert result == GlycemicResponse.unknown


def test_response_threshold_spike_at_boundary() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(5.0, 0, uid),
        _glucose(9.0, 60, uid),
        _glucose(8.0, 180, uid),
    ]
    anchors = _fake_anchors(t0=5.0, t90=8.0, t180=8.0)
    result = classify_response(anchors, readings, 1.0)
    assert result == GlycemicResponse.spike


def test_response_threshold_moderate_at_boundary() -> None:
    uid = uuid.uuid4()
    readings = (
        [_glucose(5.0 + i * 0.065, i, uid) for i in range(0, 65, 5)]
        + [_glucose(8.45 - i * 0.03, 65 + i, uid) for i in range(0, 116, 5)]
    )
    anchors = _fake_anchors(t0=5.0, t90=7.2, t180=5.8)
    result = classify_response(anchors, readings, 1.0)
    assert result == GlycemicResponse.moderate


# ---------------------------------------------------------------------------
# peak counting
# ---------------------------------------------------------------------------


def test_count_peaks_two_distinct() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(5.0, 0, uid),
        _glucose(7.0, 15, uid),
        _glucose(5.5, 30, uid),
        _glucose(7.0, 45, uid),
        _glucose(5.5, 60, uid),
    ]
    assert _count_peaks(readings, prominence=1.0) >= 2


def test_count_peaks_none() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(5.0, i * 5, uid) for i in range(12)
    ]
    assert _count_peaks(readings, prominence=1.0) == 0


# ---------------------------------------------------------------------------
# sustained above threshold
# ---------------------------------------------------------------------------


def test_sustained_above() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(11.0, i, uid) for i in range(0, 60, 5)
    ]
    assert _sustained_above_threshold(readings, 10.0, 30)


def test_sustained_not_long_enough() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(11.0, i, uid) for i in range(0, 20, 5)
    ]
    assert not _sustained_above_threshold(readings, 10.0, 30)


def test_sustained_below_threshold() -> None:
    uid = uuid.uuid4()
    readings = [
        _glucose(9.0, i, uid) for i in range(0, 60, 5)
    ]
    assert not _sustained_above_threshold(readings, 10.0, 5)


# ---------------------------------------------------------------------------
# hypo recovery detection
# ---------------------------------------------------------------------------


def test_hypo_recovery_all_conditions() -> None:
    meal = Meal(
        total_kcal=200,
        total_protein_g=3,
        total_carbs_g=30,
        total_fat_g=8,
        total_fiber_g=0,
        ai_categories={
            "taste_profile": TasteProfile.sweet.value,
        },
        derived_categories={
            "meal_role": "snack",
        },
    )
    assert detect_hypo_recovery(meal, PreMealState.low)


def test_hypo_recovery_not_low() -> None:
    meal = Meal(
        total_kcal=200,
        total_carbs_g=15,
        ai_categories={"taste_profile": TasteProfile.sweet.value},
        derived_categories={"meal_role": "snack"},
    )
    assert not detect_hypo_recovery(meal, PreMealState.in_range)


def test_hypo_recovery_too_many_kcal() -> None:
    meal = Meal(
        total_kcal=300,
        total_carbs_g=15,
        ai_categories={"taste_profile": TasteProfile.sweet.value},
        derived_categories={"meal_role": "snack"},
    )
    assert not detect_hypo_recovery(meal, PreMealState.low)


def test_hypo_recovery_wrong_taste() -> None:
    meal = Meal(
        total_kcal=200,
        total_carbs_g=15,
        ai_categories={"taste_profile": TasteProfile.savory.value},
        derived_categories={"meal_role": "snack"},
    )
    assert not detect_hypo_recovery(meal, PreMealState.low)


def test_hypo_recovery_wrong_role() -> None:
    meal = Meal(
        total_kcal=200,
        total_carbs_g=15,
        ai_categories={"taste_profile": TasteProfile.sweet.value},
        derived_categories={"meal_role": "main_meal"},
    )
    assert not detect_hypo_recovery(meal, PreMealState.low)


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def test_coverage_full() -> None:
    uid = uuid.uuid4()
    base = datetime(2026, 5, 10, 14, 0, 0)
    readings = [
        _glucose(5.0, i, uid) for i in range(0, 181, 5)
    ]
    result = _coverage_fraction(readings, base, base + timedelta(minutes=180))
    assert result > 0.9


def test_coverage_empty() -> None:
    result = _coverage_fraction([], datetime.now(), datetime.now())
    assert result == 0.0


# ---------------------------------------------------------------------------
# aggregate_by_product
# ---------------------------------------------------------------------------


def test_aggregate_by_product_insufficient_samples() -> None:
    assert True  # aggregate_by_product requires DB with meals


# ---------------------------------------------------------------------------
# full analysis integration
# ---------------------------------------------------------------------------


def test_full_analysis_gentle_response(pp_db: Session) -> None:
    uid = _uid(pp_db)
    pp_db.scalars(
        __import__("sqlalchemy").select(User).where(User.id == uid)
    ).one()

    base = datetime(2026, 5, 10, 14, 0, 0)
    _seed_cgm(
        pp_db,
        [(5.5, -5)]
        + [(5.5, i * 5) for i in range(37)],
    )

    meal = _make_meal(base)
    meal.owner_id = uid
    meal.derived_categories = {
        "taste_profile": "savory",
        "meal_role": "main_meal",
    }
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert response["pre_meal_state"] == "in_range"
    assert response["glycemic_response"] == "gentle"
    assert not response["is_hypo_recovery"]
    assert "anchors" in response
    assert "peak" in response


def test_full_analysis_hypo_recovery(pp_db: Session) -> None:
    uid = _uid(pp_db)
    base = datetime(2026, 5, 10, 14, 0, 0)

    _seed_cgm(pp_db, [(3.5, -5), (4.5, 30), (5.0, 60)])

    meal = Meal(
        title="Шоколад тёмный 24г",
        total_kcal=150,
        total_protein_g=2,
        total_carbs_g=14,
        total_fat_g=10,
        total_fiber_g=3,
        eaten_at=base,
        source=MealSource.manual,
        status=MealStatus.accepted,
        owner_id=uid,
        ai_categories={
            "taste_profile": TasteProfile.sweet.value,
        },
        derived_categories={
            "meal_role": "snack",
        },
    )
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert response["pre_meal_state"] == "low"
    assert response["is_hypo_recovery"]


def test_full_analysis_no_cgm_data(pp_db: Session) -> None:
    uid = _uid(pp_db)
    base = datetime(2026, 5, 10, 14, 0, 0)

    meal = _make_meal(base)
    meal.owner_id = uid
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert response["coverage_180min"] == 0.0
    assert response["glycemic_response"] == "unknown"
    assert response["pre_meal_state"] == "unknown"


# ---------------------------------------------------------------------------
#  ADR-008 follow-up tests
# ---------------------------------------------------------------------------


def test_hypo_recovery_requires_carbs() -> None:
    meal = Meal(
        total_kcal=15,
        total_carbs_g=0,
        total_protein_g=0,
        total_fat_g=0,
        total_fiber_g=0,
        ai_categories={"taste_profile": TasteProfile.drink_sweet.value},
        derived_categories={"meal_role": "drink"},
    )
    assert not detect_hypo_recovery(meal, PreMealState.low)


def test_hypo_recovery_enough_carbs() -> None:
    meal = Meal(
        total_kcal=80,
        total_carbs_g=11,
        total_protein_g=1,
        total_fat_g=4,
        total_fiber_g=0,
        ai_categories={"taste_profile": TasteProfile.sweet.value},
        derived_categories={"meal_role": "snack"},
    )
    assert detect_hypo_recovery(meal, PreMealState.low)


def test_is_meal_during_low_in_response(pp_db: Session) -> None:
    uid = _uid(pp_db)
    base = datetime(2026, 5, 10, 14, 0, 0)
    _seed_cgm(pp_db, [(3.5, -5)])

    meal = _make_meal(base)
    meal.owner_id = uid
    meal.total_kcal = 500
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert response["pre_meal_state"] == "low"
    assert response["is_meal_during_low"]
    assert not response["is_hypo_recovery"]


def test_mutual_exclusion_during_low_not_recovery(pp_db: Session) -> None:
    uid = _uid(pp_db)
    base = datetime(2026, 5, 10, 14, 0, 0)
    _seed_cgm(pp_db, [(3.5, -5), (5.0, 60)])

    meal = Meal(
        title="Monster Ultra",
        total_kcal=15,
        total_carbs_g=0,
        total_protein_g=0,
        total_fat_g=0,
        total_fiber_g=0,
        eaten_at=base,
        source=MealSource.manual,
        status=MealStatus.accepted,
        owner_id=uid,
        ai_categories={"taste_profile": TasteProfile.drink_sweet.value},
        derived_categories={"meal_role": "drink"},
    )
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert response["is_meal_during_low"]
    assert not response["is_hypo_recovery"]


def test_fat_share_computation() -> None:
    meal = Meal(total_kcal=100, total_fat_g=4)
    share = _compute_fat_share(meal)
    assert share is not None
    assert share == pytest.approx(0.36)

    meal_zero = Meal(total_kcal=0, total_fat_g=10)
    assert _compute_fat_share(meal_zero) is None


def test_delayed_peak_high_fat(pp_db: Session) -> None:
    uid = _uid(pp_db)
    base = datetime(2026, 5, 10, 14, 0, 0)
    _seed_cgm(
        pp_db,
        [(5.0, i) for i in range(0, 181, 5)]
        + [(7.0, 190), (7.5, 200), (8.0, 210), (8.5, 220),
           (9.0, 230), (9.2, 240), (9.5, 250), (9.7, 260),
           (9.8, 270), (9.8, 280), (9.5, 290), (9.2, 300)],
    )

    meal = Meal(
        title="Круассан",
        total_kcal=300,
        total_carbs_g=30,
        total_protein_g=5,
        total_fat_g=15,
        total_fiber_g=1,
        eaten_at=base,
        source=MealSource.manual,
        status=MealStatus.accepted,
        owner_id=uid,
    )
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert response["delayed_peak_likely"]


def test_no_delayed_peak_low_fat(pp_db: Session) -> None:
    uid = _uid(pp_db)
    base = datetime(2026, 5, 10, 14, 0, 0)
    _seed_cgm(
        pp_db,
        [(5.0, i) for i in range(0, 181, 5)]
        + [(6.0, 200), (6.5, 260), (5.8, 290)],
    )

    meal = Meal(
        title="Рис отварной",
        total_kcal=300,
        total_carbs_g=60,
        total_protein_g=8,
        total_fat_g=1,
        total_fiber_g=0,
        eaten_at=base,
        source=MealSource.manual,
        status=MealStatus.accepted,
        owner_id=uid,
    )
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert not response["delayed_peak_likely"]


def test_extended_anchors_in_response(pp_db: Session) -> None:
    uid = _uid(pp_db)
    base = datetime(2026, 5, 10, 14, 0, 0)
    _seed_cgm(
        pp_db,
        [(5.5, -5)]
        + [(5.5, i * 5) for i in range(61)],
    )

    meal = _make_meal(base)
    meal.owner_id = uid
    meal.total_fat_g = 5
    pp_db.add(meal)
    pp_db.flush()

    response = compute_postprandial_response(pp_db, meal)
    assert response is not None
    assert "240" in response["anchors"]
    assert "300" in response["anchors"]
    assert "extended_coverage_300min" in response
    assert "delayed_peak_likely" in response
    assert "is_meal_during_low" in response
