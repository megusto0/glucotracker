"""Owner-scoped orchestration tests for retrospective IOB/COB fits."""

from __future__ import annotations

from collections.abc import Callable, Generator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.on_board.fitter import (
    CobTimingOverride,
    ErrorMetrics,
    FitMetrics,
    OnBoardFitResult,
    OnBoardTimingModel,
    RetrospectiveDay,
)
from glucotracker.application.on_board.service import OnBoardFitService
from glucotracker.application.twin.kernels import (
    POPULATION_INSULIN_KERNEL_V2,
    CarbProfileWeights,
    PersonalizedInsulinKernel,
    carb_profile_prior_weights,
)
from glucotracker.config import get_settings
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    OnBoardModelFit,
    User,
)
from glucotracker.infra.db.repositories.on_board import OnBoardRepository
from glucotracker.infra.db.repositories.twin import TwinRepository
from glucotracker.infra.security import hash_password


@pytest.fixture
def samara_api(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient]:
    """Run service time conversion with the deployment's local timezone."""
    monkeypatch.setenv("GLUCOTRACKER_APP_TIMEZONE", "Europe/Samara")
    get_settings.cache_clear()
    try:
        yield api_client
    finally:
        get_settings.cache_clear()


def _seed_user(session: Session, username: str) -> User:
    user = User(
        username=username,
        password_hash=hash_password("test-password"),
        role=UserRole.gluco,
    )
    session.add(user)
    session.flush()
    return user


def _seed_glucose(
    session: Session,
    owner_id: UUID,
    *,
    source_key: str,
    timestamp: datetime,
    value: float,
) -> NightscoutGlucoseEntry:
    row = NightscoutGlucoseEntry(
        owner_id=owner_id,
        source_key=source_key,
        timestamp=timestamp,
        value_mmol_l=value,
        source="nightscout",
    )
    session.add(row)
    return row


def _seed_insulin(
    session: Session,
    owner_id: UUID,
    *,
    source_key: str,
    timestamp: datetime,
    units: float,
    insulin_type: str,
    event_type: str,
) -> NightscoutInsulinEvent:
    row = NightscoutInsulinEvent(
        owner_id=owner_id,
        source_key=source_key,
        timestamp=timestamp,
        insulin_units=units,
        insulin_type=insulin_type,
        event_type=event_type,
    )
    session.add(row)
    return row


def _seed_meal(
    session: Session,
    owner_id: UUID,
    *,
    title: str,
    eaten_at: datetime,
    carbs_g: float,
) -> Meal:
    row = Meal(
        owner_id=owner_id,
        title=title,
        eaten_at=eaten_at,
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=carbs_g,
        total_protein_g=8.0,
        total_fat_g=6.0,
        total_fiber_g=3.0,
        total_kcal=280.0,
    )
    session.add(row)
    return row


def _empty_metrics() -> FitMetrics:
    return FitMetrics(
        complete_day_count=0,
        excluded_day_count=0,
        training_day_starts=(),
        holdout_day_starts=(),
        training_sample_count=0,
        holdout_sample_count=0,
        rapid_insulin_event_count=0,
        rapid_insulin_day_count=0,
        meal_event_count=0,
        meal_day_count=0,
    )


def _capturing_fitter(
    captured: list[tuple[RetrospectiveDay, ...]],
) -> Callable[..., OnBoardFitResult]:
    def fit(
        days: tuple[RetrospectiveDay, ...] | list[RetrospectiveDay],
        *,
        fallback: OnBoardTimingModel | None = None,
        config: object | None = None,
    ) -> OnBoardFitResult:
        del config
        captured.append(tuple(days))
        return OnBoardFitResult(
            status="insufficient_data",
            reason="captured_for_service_test",
            model=fallback or OnBoardTimingModel(),
            metrics=_empty_metrics(),
        )

    return fit


def test_first_fit_baseline_matches_dashboard_legacy_timing(
    api_client: TestClient,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))

    with session_factory() as session:
        twin_params = TwinRepository(session, owner_id).get_or_create_params(
            persist=False
        )
        model = OnBoardFitService(session, owner_id)._active_model()

    assert model.insulin_kernel is None
    assert model.legacy_dia_minutes == twin_params.dia_minutes
    assert model.normal_carb_duration_minutes == twin_params.carb_duration_minutes


def test_dataset_is_owner_scoped_and_aligns_utc_nightscout_with_local_day(
    samara_api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = samara_api.app_state["session_factory"]
    alice_id = UUID(str(samara_api.app_state["current_user_id"]))
    captured: list[tuple[RetrospectiveDay, ...]] = []
    monkeypatch.setattr(
        "glucotracker.application.on_board.service.fit_on_board_timing",
        _capturing_fitter(captured),
    )

    with session_factory() as session:
        bob = _seed_user(session, f"bob-service-{uuid4().hex}")
        # Europe/Samara is UTC+4: these Nightscout instants are 00:05 and
        # 12:00 on the same local-wall day as the meal below.
        _seed_glucose(
            session,
            alice_id,
            source_key="alice-cgm",
            timestamp=datetime(2026, 6, 9, 20, 5, tzinfo=UTC),
            value=6.1,
        )
        _seed_glucose(
            session,
            bob.id,
            source_key="bob-cgm",
            timestamp=datetime(2026, 6, 9, 20, 5, tzinfo=UTC),
            value=19.0,
        )
        _seed_insulin(
            session,
            alice_id,
            source_key="alice-rapid",
            timestamp=datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
            units=1.5,
            insulin_type="Fiasp",
            event_type="Correction Bolus",
        )
        _seed_insulin(
            session,
            alice_id,
            source_key="alice-basal",
            timestamp=datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
            units=12.0,
            insulin_type="Lantus",
            event_type="Basal",
        )
        _seed_insulin(
            session,
            bob.id,
            source_key="bob-rapid",
            timestamp=datetime(2026, 6, 10, 8, 0, tzinfo=UTC),
            units=9.0,
            insulin_type="Fiasp",
            event_type="Correction Bolus",
        )
        _seed_meal(
            session,
            alice_id,
            title="Alice lunch",
            eaten_at=datetime(2026, 6, 10, 12, 0),
            carbs_g=34.0,
        )
        _seed_meal(
            session,
            bob.id,
            title="Bob lunch",
            eaten_at=datetime(2026, 6, 10, 12, 0),
            carbs_g=91.0,
        )
        session.commit()

        run = OnBoardFitService(session, alice_id).fit_range(
            datetime(2026, 6, 10),
            datetime(2026, 6, 11),
        )

    assert run.training_from == datetime(2026, 6, 10)
    assert run.training_to == datetime(2026, 6, 11)
    assert len(captured) == 1
    (day,) = captured[0]
    assert day.day_start == datetime(2026, 6, 10)
    assert [(sample.timestamp, sample.glucose_mmol_l) for sample in day.cgm] == [
        (datetime(2026, 6, 10, 0, 5), 6.1)
    ]
    assert [(event.timestamp, event.units) for event in day.rapid_insulin] == [
        (datetime(2026, 6, 10, 12, 0), 1.5)
    ]
    assert [(meal.timestamp, meal.carbs_g) for meal in day.meals] == [
        (datetime(2026, 6, 10, 12, 0), 34.0)
    ]


@pytest.mark.parametrize(
    ("local_now", "expected_training_to", "expected_days"),
    [
        (
            datetime(2026, 7, 13, 6, 59),
            datetime(2026, 7, 12),
            (datetime(2026, 7, 11),),
        ),
        (
            datetime(2026, 7, 13, 7, 0),
            datetime(2026, 7, 13),
            (datetime(2026, 7, 11), datetime(2026, 7, 12)),
        ),
    ],
)
def test_fit_range_waits_420_minutes_and_uses_only_full_local_days(
    samara_api: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    local_now: datetime,
    expected_training_to: datetime,
    expected_days: tuple[datetime, ...],
) -> None:
    session_factory = samara_api.app_state["session_factory"]
    owner_id = UUID(str(samara_api.app_state["current_user_id"]))
    captured: list[tuple[RetrospectiveDay, ...]] = []
    monkeypatch.setattr(
        "glucotracker.application.on_board.service.local_now",
        lambda: local_now,
    )
    monkeypatch.setattr(
        "glucotracker.application.on_board.service.fit_on_board_timing",
        _capturing_fitter(captured),
    )

    with session_factory() as session:
        run = OnBoardFitService(session, owner_id).fit_range(
            datetime(2026, 7, 11),
            datetime(2026, 7, 14),
        )

    assert run.training_from == datetime(2026, 7, 11)
    assert run.training_to == expected_training_to
    assert tuple(day.day_start for day in captured[0]) == expected_days


@pytest.mark.parametrize(
    "response,computed_at",
    [
        (
            {
                "coverage_180min": 1.0,
                "extended_coverage_300min": 1.0,
            },
            datetime(2026, 5, 1, 11, 59, tzinfo=UTC),
        ),
        (
            {
                "coverage_180min": 0.50,
                "extended_coverage_300min": 1.0,
            },
            datetime(2026, 5, 1, 12, 1, tzinfo=UTC),
        ),
        (
            {
                "coverage_180min": 1.0,
                "extended_coverage_300min": 1.0,
                "is_meal_during_low": True,
            },
            datetime(2026, 5, 1, 12, 1, tzinfo=UTC),
        ),
        (
            {
                "coverage_180min": 1.0,
                "extended_coverage_300min": 1.0,
                "is_hypo_recovery": True,
            },
            datetime(2026, 5, 1, 12, 1, tzinfo=UTC),
        ),
    ],
    ids=("stale", "low-coverage", "during-low", "hypo-recovery"),
)
def test_unsafe_postprandial_meals_keep_macro_prior_without_personal_keys(
    api_client: TestClient,
    response: dict[str, object],
    computed_at: datetime,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    meal = Meal(
        owner_id=owner_id,
        title="Repeated meal",
        eaten_at=datetime(2026, 5, 1, 9, 0),
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=40.0,
        total_protein_g=18.0,
        total_fat_g=14.0,
        total_fiber_g=5.0,
        total_kcal=420.0,
        postprandial_response=response,
        postprandial_computed_at=computed_at,
        updated_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    expected_prior = carb_profile_prior_weights(
        carbs_g=40.0,
        protein_g=18.0,
        fat_g=14.0,
        fiber_g=5.0,
        is_liquid=False,
        is_sweetened=False,
    )

    with session_factory() as session:
        event = OnBoardFitService(session, owner_id)._meal_event(meal)

    assert event.prior_weights == expected_prior
    assert event.exact_key is None
    assert event.category_key is None


def _validation_metrics() -> FitMetrics:
    baseline = ErrorMetrics(0.80, 0.78, 1.20, (("2026-06-01", 0.78),))
    candidate = ErrorMetrics(0.60, 0.58, 1.00, (("2026-06-01", 0.58),))
    return FitMetrics(
        complete_day_count=12,
        excluded_day_count=0,
        training_day_starts=("2026-06-01T00:00:00",),
        holdout_day_starts=("2026-06-10T00:00:00",),
        training_sample_count=700,
        holdout_sample_count=200,
        rapid_insulin_event_count=40,
        rapid_insulin_day_count=10,
        meal_event_count=35,
        meal_day_count=10,
        baseline=baseline,
        candidate=candidate,
        mae_improvement_mmol=0.20,
        mae_improvement_fraction=0.25,
        median_improvement_mmol=0.20,
        median_improvement_fraction=0.25,
    )


def _personal_candidate() -> OnBoardTimingModel:
    return OnBoardTimingModel(
        insulin_kernel=PersonalizedInsulinKernel(0.50, 15.0, 70.0),
        cob_overrides=(
            CobTimingOverride(
                scope="category",
                scope_key="category:slow:solid",
                weights=CarbProfileWeights(0.05, 0.25, 0.70),
                event_count=18,
                day_count=11,
                learned_weight=0.35,
            ),
        ),
    )


def _add_active_population_fit(
    repository: OnBoardRepository,
) -> OnBoardModelFit:
    return repository.add_fit(
        kind="iob",
        scope_key="rapid",
        model_version="on-board-v2",
        params_json=POPULATION_INSULIN_KERNEL_V2.to_mapping(),
        metrics_json={},
        training_from=None,
        training_to=None,
        sample_count=30,
        day_count=10,
        validation_mae_mmol=0.7,
        baseline_mae_mmol=0.9,
        confidence="medium",
        status="accepted",
        activate=True,
    )


def _add_active_cob_fit(
    repository: OnBoardRepository,
    *,
    scope_key: str,
) -> OnBoardModelFit:
    return repository.add_fit(
        kind="cob",
        scope_key=scope_key,
        model_version="on-board-v2",
        params_json={
            "weights": CarbProfileWeights(0.10, 0.30, 0.60).to_mapping(),
            "scope": "exact" if scope_key.startswith("pattern:") else "category",
        },
        metrics_json={},
        training_from=None,
        training_to=None,
        sample_count=12,
        day_count=8,
        validation_mae_mmol=0.7,
        baseline_mae_mmol=0.9,
        confidence="medium",
        status="accepted",
        activate=True,
    )


def test_accepted_fit_activates_only_current_users_rows(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    alice_id = UUID(str(api_client.app_state["current_user_id"]))
    candidate = _personal_candidate()

    def accepted_fitter(
        days: object,
        *,
        fallback: OnBoardTimingModel,
        config: object,
    ) -> OnBoardFitResult:
        del days, fallback, config
        return OnBoardFitResult(
            status="accepted",
            reason="accepted",
            model=candidate,
            candidate_model=candidate,
            metrics=_validation_metrics(),
            confidence="medium",
        )

    monkeypatch.setattr(
        "glucotracker.application.on_board.service.fit_on_board_timing",
        accepted_fitter,
    )

    with session_factory() as session:
        bob = _seed_user(session, f"bob-accepted-{uuid4().hex}")
        alice_repository = OnBoardRepository(session, alice_id)
        bob_repository = OnBoardRepository(session, bob.id)
        alice_old = _add_active_population_fit(alice_repository)
        alice_stale_cob = _add_active_cob_fit(
            alice_repository,
            scope_key="pattern:stale",
        )
        bob_active = _add_active_population_fit(bob_repository)
        bob_stale_cob = _add_active_cob_fit(
            bob_repository,
            scope_key="pattern:stale",
        )

        run = OnBoardFitService(session, alice_id).fit_range(
            datetime(2026, 6, 1),
            datetime(2026, 6, 12),
        )
        session.commit()

        alice_active = list(
            session.scalars(
                select(OnBoardModelFit).where(
                    OnBoardModelFit.owner_id == alice_id,
                    OnBoardModelFit.active.is_(True),
                )
            )
        )
        bob_rows = list(
            session.scalars(
                select(OnBoardModelFit).where(OnBoardModelFit.owner_id == bob.id)
            )
        )

    assert run.activated_fit_count == 2
    assert {(row.kind, row.scope_key) for row in alice_active} == {
        ("iob", "rapid"),
        ("cob", "category:slow:solid"),
    }
    assert alice_old.active is False
    assert alice_stale_cob.active is False
    assert {row.id for row in bob_rows} == {bob_active.id, bob_stale_cob.id}
    assert all(row.active is True for row in bob_rows)


def test_rejected_fit_preserves_existing_active_fit(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    candidate = _personal_candidate()

    def rejected_fitter(
        days: object,
        *,
        fallback: OnBoardTimingModel,
        config: object,
    ) -> OnBoardFitResult:
        del days, config
        return OnBoardFitResult(
            status="rejected",
            reason="held_out_day_worsened",
            model=fallback,
            candidate_model=candidate,
            metrics=_validation_metrics(),
            confidence="none",
        )

    monkeypatch.setattr(
        "glucotracker.application.on_board.service.fit_on_board_timing",
        rejected_fitter,
    )

    with session_factory() as session:
        repository = OnBoardRepository(session, owner_id)
        existing = _add_active_population_fit(repository)
        existing_cob = _add_active_cob_fit(
            repository,
            scope_key="pattern:existing",
        )
        run = OnBoardFitService(session, owner_id).fit_range(
            datetime(2026, 6, 1),
            datetime(2026, 6, 12),
        )
        session.commit()

        active = repository.get_active_fit("iob", "rapid")
        active_cob = repository.get_active_fit("cob", "pattern:existing")
        rejected_rows = list(
            session.scalars(
                select(OnBoardModelFit).where(
                    OnBoardModelFit.owner_id == owner_id,
                    OnBoardModelFit.status == "rejected",
                )
            )
        )

    assert run.activated_fit_count == 0
    assert run.recorded_fit_count == 2
    assert active is not None
    assert active.id == existing.id
    assert existing.active is True
    assert active_cob is not None
    assert active_cob.id == existing_cob.id
    assert existing_cob.active is True
    assert {(row.kind, row.scope_key) for row in rejected_rows} == {
        ("iob", "rapid"),
        ("cob", "category:slow:solid"),
    }
    assert all(row.active is False for row in rejected_rows)


def test_insufficient_fit_preserves_existing_active_cob_set(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_factory = api_client.app_state["session_factory"]
    owner_id = UUID(str(api_client.app_state["current_user_id"]))

    def insufficient_fitter(
        days: object,
        *,
        fallback: OnBoardTimingModel,
        config: object,
    ) -> OnBoardFitResult:
        del days, config
        return OnBoardFitResult(
            status="insufficient_data",
            reason="not_enough_complete_days",
            model=fallback,
            metrics=FitMetrics(
                complete_day_count=0,
                excluded_day_count=0,
                training_day_starts=(),
                holdout_day_starts=(),
                training_sample_count=0,
                holdout_sample_count=0,
                rapid_insulin_event_count=0,
                rapid_insulin_day_count=0,
                meal_event_count=0,
                meal_day_count=0,
            ),
            confidence="none",
        )

    monkeypatch.setattr(
        "glucotracker.application.on_board.service.fit_on_board_timing",
        insufficient_fitter,
    )

    with session_factory() as session:
        repository = OnBoardRepository(session, owner_id)
        existing_cob = _add_active_cob_fit(
            repository,
            scope_key="pattern:existing",
        )
        run = OnBoardFitService(session, owner_id).fit_range(
            datetime(2026, 6, 1),
            datetime(2026, 6, 12),
        )
        session.commit()

        active_cob = repository.get_active_fit("cob", "pattern:existing")
        insufficient_rows = list(
            session.scalars(
                select(OnBoardModelFit).where(
                    OnBoardModelFit.owner_id == owner_id,
                    OnBoardModelFit.status == "insufficient_data",
                )
            )
        )

    assert run.activated_fit_count == 0
    assert active_cob is not None
    assert active_cob.id == existing_cob.id
    assert existing_cob.active is True
    assert len(insufficient_rows) == 1
    assert insufficient_rows[0].active is False
