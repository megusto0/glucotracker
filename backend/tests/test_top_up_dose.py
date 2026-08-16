"""Follow-up bolus suggestion during a rise."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)
from glucotracker.infra.db.repositories.twin import TwinRepository

# The dashboard reads a local wall clock; the test app timezone is UTC.
NOW = datetime.now(UTC).replace(second=0, microsecond=0)


def _cgm(session: Session, owner_id: UUID, offsets: dict[int, float]) -> None:
    for minutes, value in offsets.items():
        session.add(
            NightscoutGlucoseEntry(
                owner_id=owner_id,
                source_key=f"topup-{minutes}",
                timestamp=NOW - timedelta(minutes=minutes),
                value_mmol_l=value,
                value_mg_dl=round(value * 18.0182),
                source="CGM",
            )
        )


def _meal(session: Session, owner_id: UUID, minutes_ago: int, carbs: float) -> None:
    session.add(
        Meal(
            owner_id=owner_id,
            eaten_at=(NOW - timedelta(minutes=minutes_ago)).replace(tzinfo=None),
            title="Приём",
            source=MealSource.photo,
            status=MealStatus.accepted,
            total_carbs_g=carbs,
            total_protein_g=10,
            total_fat_g=8,
            total_kcal=carbs * 5,
        )
    )


def _insulin(session: Session, owner_id: UUID, minutes_ago: int, units: float) -> None:
    key = f"topup-insulin-{minutes_ago}-{units}"
    session.add(
        NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key=key,
            nightscout_id=key,
            timestamp=NOW - timedelta(minutes=minutes_ago),
            insulin_units=units,
            event_type="Meal Bolus",
            entered_by="Nightscout",
        )
    )


def _setup(api_client: TestClient, *, carbs: float, units: float, glucose: float):
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        _cgm(session, owner_id, {15: glucose - 0.4, 10: glucose - 0.2, 0: glucose})
        _meal(session, owner_id, 45, carbs)
        _insulin(session, owner_id, 40, units)
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 10.0
        params.isf = 2.0
        params.last_fit_method = "manual"
        session.commit()
    return owner_id


def test_suggests_a_top_up_from_carbs_left_minus_insulin_on_board(
    api_client: TestClient,
) -> None:
    """A big meal with a small bolus still has uncovered carbohydrate."""
    _setup(api_client, carbs=80.0, units=1.0, glucose=9.0)

    response = api_client.get("/glucose/top-up-dose", params={"target_mmol_l": 6.0})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["cob_g"] > 30
    assert body["carb_units"] > 3.0
    assert body["correction_units"] > 0
    # Every term of the arithmetic is reported, not just the answer.
    assert body["icr_g_per_unit"] == 10.0
    assert body["isf_mmol_l_per_unit"] == 2.0
    assert body["isf_source"] == "manual"
    assert body["iob_minutes_remaining"] > 0
    assert body["cob_minutes_remaining"] > 0
    expected = body["carb_units"] + body["correction_units"] - body["iob_units"]
    assert abs(body["units"] - round(expected * 10) / 10) < 0.15


def test_no_top_up_when_active_insulin_already_covers_the_meal(
    api_client: TestClient,
) -> None:
    """The conservative case: a large bolus is already working."""
    _setup(api_client, carbs=30.0, units=9.0, glucose=7.0)

    response = api_client.get("/glucose/top-up-dose", params={"target_mmol_l": 6.0})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_needed"
    assert body["units"] == 0.0
    assert body["iob_units"] > body["carb_units"]
    assert body["note"]


def test_low_glucose_withholds_any_number(api_client: TestClient) -> None:
    _setup(api_client, carbs=60.0, units=1.0, glucose=3.5)

    response = api_client.get("/glucose/top-up-dose", params={"target_mmol_l": 6.0})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "low_or_falling"
    assert body["units"] is None


def test_reports_glucose_unavailable_without_cgm(api_client: TestClient) -> None:
    response = api_client.get("/glucose/top-up-dose")

    assert response.status_code == 200
    assert response.json()["status"] == "glucose_unavailable"


def test_top_up_never_reads_another_users_state(api_client: TestClient) -> None:
    from uuid import uuid4

    from glucotracker.domain.auth import UserRole
    from glucotracker.infra.db.models import User
    from glucotracker.infra.security import hash_password

    factory = api_client.app_state["session_factory"]
    with factory() as session:
        other = User(
            username=f"topup-other-{uuid4().hex}",
            password_hash=hash_password("other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        _cgm(session, other.id, {0: 12.0})
        _meal(session, other.id, 30, 90.0)
        session.commit()

    response = api_client.get("/glucose/top-up-dose")

    assert response.status_code == 200
    assert response.json()["status"] == "glucose_unavailable"


def test_high_and_rising_is_not_reported_as_handled(
    api_client: TestClient,
) -> None:
    """Reported 2026-08-02 17:30 onward.

    78 g still absorbing against 9.8 U on board makes the balance a difference
    of two large numbers; it returned "enough" for ninety minutes while glucose
    climbed from 10.1 to 11.7. Above the high band the reading has already
    contradicted that, so a correction toward target is offered.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    factory = api_client.app_state["session_factory"]
    with factory() as session:
        _cgm(session, owner_id, {15: 10.6, 10: 10.8, 0: 11.0})
        _meal(session, owner_id, 70, 90.0)
        _meal(session, owner_id, 10, 18.5)
        _insulin(session, owner_id, 68, 10.1)
        _insulin(session, owner_id, 42, 1.8)
        _insulin(session, owner_id, 11, 1.0)
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 9.3
        params.isf = 2.6
        params.last_fit_method = "manual"
        session.commit()

    response = api_client.get("/glucose/top-up-dose", params={"target_mmol_l": 6.0})

    assert response.status_code == 200
    body = response.json()
    # The balance alone would have said the meal was already covered.
    assert body["iob_units"] > 8.0
    assert body["cob_g"] > 50
    assert body["carb_units"] + body["correction_units"] - body["iob_units"] < 0.2
    # But the reading is above the high band, so a number is offered.
    assert body["status"] == "ready"
    assert body["units"] is not None
    assert 1.0 <= body["units"] <= 2.5


def test_moderate_high_still_defers_to_the_balance(
    api_client: TestClient,
) -> None:
    """Below the high band an over-insulinized meal still reports enough."""
    _setup(api_client, carbs=30.0, units=9.0, glucose=9.5)

    response = api_client.get("/glucose/top-up-dose", params={"target_mmol_l": 6.0})

    assert response.status_code == 200
    assert response.json()["status"] == "not_needed"



def test_top_up_can_be_asked_about_a_past_moment(api_client: TestClient) -> None:
    """The same arithmetic, as of when a chasing bolus was actually given.

    A catch-up raises exactly one question — how much did the moment call for —
    and the diary cannot answer it afterwards unless every term can be recomputed
    at that timestamp. They can: each was already keyed to a supplied moment, and
    only the endpoint was pinned to the present.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    then = NOW - timedelta(days=3)
    with api_client.app_state["session_factory"]() as session:
        for minutes, value in {15: 8.6, 10: 9.0, 0: 9.4}.items():
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"past-topup-{minutes}",
                    timestamp=then - timedelta(minutes=minutes),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        session.add(
            Meal(
                owner_id=owner_id,
                eaten_at=(then - timedelta(minutes=54)).replace(tzinfo=None),
                title="Ужин",
                source=MealSource.photo,
                status=MealStatus.accepted,
                total_carbs_g=78,
                total_protein_g=10,
                total_fat_g=8,
                total_kcal=470,
            )
        )
        key = "past-topup-insulin"
        session.add(
            NightscoutInsulinEvent(
                owner_id=owner_id,
                source_key=key,
                nightscout_id=key,
                timestamp=then - timedelta(minutes=45),
                insulin_units=6.0,
                event_type="Meal Bolus",
                entered_by="Nightscout",
            )
        )
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 10.0
        params.isf = 2.0
        params.last_fit_method = "manual"
        session.commit()

    dated = api_client.get(
        "/glucose/top-up-dose",
        params={"at": then.replace(tzinfo=None).isoformat(), "target_mmol_l": 6.0},
    )
    undated = api_client.get("/glucose/top-up-dose", params={"target_mmol_l": 6.0})

    assert dated.status_code == 200
    body = dated.json()
    # Every term of the mockup's arithmetic block, as of that minute.
    assert body["glucose_mmol_l"] == 9.4
    assert body["cob_g"] is not None
    assert body["iob_units"] is not None
    assert body["icr_g_per_unit"] == 10.0
    assert body["isf_mmol_l_per_unit"] == 2.0
    # A moment three days old has no live forecast left to lean on, and the
    # response says so rather than quietly reusing a stale one.
    assert body["projection_source"] == "none"
    # The undated call still means "now", where this owner has no CGM at all.
    assert undated.json()["status"] == "glucose_unavailable"


def test_retrospective_top_up_excludes_the_bolus_being_explained(
    api_client: TestClient,
) -> None:
    """A bolus cannot appear inside the IOB used to explain that same bolus."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    then = NOW - timedelta(days=4)
    with api_client.app_state["session_factory"]() as session:
        for minutes, value in {15: 6.0, 10: 6.0, 0: 6.0}.items():
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"self-iob-cgm-{minutes}",
                    timestamp=then - timedelta(minutes=minutes),
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        session.add(
            Meal(
                owner_id=owner_id,
                eaten_at=then.replace(tzinfo=None),
                title="Ужин",
                source=MealSource.photo,
                status=MealStatus.accepted,
                total_carbs_g=60,
                total_protein_g=10,
                total_fat_g=8,
                total_kcal=400,
            )
        )
        selected = NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key="self-iob-selected",
            nightscout_id="self-iob-selected",
            timestamp=then,
            insulin_units=4.0,
            event_type="Meal Bolus",
            entered_by="Nightscout",
        )
        session.add(selected)
        params = TwinRepository(session, owner_id).get_or_create_params()
        params.icr_morning = params.icr_day = params.icr_evening = 10.0
        params.isf = 2.0
        params.last_fit_method = "manual"
        session.commit()
        selected_id = selected.id

    common = {
        # Android sends kotlinx.datetime.Instant with a Z suffix. Production
        # PostgreSQL preserves that tzinfo, unlike the earlier naive-only test.
        "at": then.isoformat().replace("+00:00", "Z"),
        "target_mmol_l": 6.0,
    }
    included = api_client.get("/glucose/top-up-dose", params=common)
    excluded = api_client.get(
        "/glucose/top-up-dose",
        params={**common, "exclude_insulin_id": str(selected_id)},
    )

    assert included.status_code == excluded.status_code == 200
    included_body = included.json()
    excluded_body = excluded.json()
    assert included_body["iob_units"] == 4.0
    assert excluded_body["iob_units"] == 0.0
    assert included_body["units"] == 2.0
    assert excluded_body["units"] == 6.0
