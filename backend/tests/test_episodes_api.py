"""Unified meal/insulin episode grouping rules."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.application.insulin_links import InsulinLinkDayService
from glucotracker.domain.auth import UserRole
from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    HealthConnectRecord,
    Meal,
    MealInsulinEpisodeSnapshot,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
    User,
)
from glucotracker.infra.security import hash_password, issue_access_token


def _headers(user_id: UUID, role: UserRole = UserRole.gluco) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(user_id, role)}"}


def _seed_meal(
    session: Session,
    owner_id: UUID,
    title: str,
    eaten_at: datetime,
    *,
    carbs: float = 20,
) -> Meal:
    meal = Meal(
        owner_id=owner_id,
        eaten_at=eaten_at,
        title=title,
        source=MealSource.manual,
        status=MealStatus.accepted,
        total_carbs_g=carbs,
        total_protein_g=5,
        total_fat_g=3,
        total_kcal=120,
    )
    session.add(meal)
    session.flush()
    return meal


def _seed_glucose(
    session: Session,
    owner_id: UUID,
    timestamp: datetime,
    value: float,
) -> None:
    session.add(
        NightscoutGlucoseEntry(
            owner_id=owner_id,
            source_key=f"episodes-cgm-{timestamp.isoformat()}",
            timestamp=timestamp,
            value_mmol_l=value,
            value_mg_dl=round(value * 18.0182),
            source="CGM",
        )
    )


def _seed_insulin(
    session: Session,
    owner_id: UUID,
    source_key: str,
    timestamp: datetime,
    *,
    units: float = 2,
    event_type: str = "Correction Bolus",
) -> NightscoutInsulinEvent:
    event = NightscoutInsulinEvent(
        owner_id=owner_id,
        source_key=source_key,
        nightscout_id=source_key,
        timestamp=timestamp,
        insulin_units=units,
        event_type=event_type,
        entered_by="Nightscout",
    )
    session.add(event)
    session.flush()
    return event


def _seed_sleep(
    session: Session,
    owner_id: UUID,
    *,
    start: datetime,
    end: datetime,
) -> None:
    session.add(
        HealthConnectRecord(
            owner_id=owner_id,
            record_id=f"episode-sleep-{owner_id}-{start.isoformat()}",
            record_type="SleepSessionRecord",
            start_time=start,
            end_time=end,
            payload={},
        )
    )


def test_episodes_group_many_meals_and_insulin_into_one(
    api_client: TestClient,
) -> None:
    """Two dishes plus their bolus is one episode; the bolus anchors nearby."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        nuggets = _seed_meal(
            session,
            owner_id,
            "Наггетсы",
            datetime(2026, 5, 20, 19, 12),
            carbs=24,
        )
        roll = _seed_meal(
            session,
            owner_id,
            "Воппер Ролл",
            datetime(2026, 5, 20, 19, 13),
            carbs=34,
        )
        bolus = _seed_insulin(
            session,
            owner_id,
            "ns-evening-bolus",
            datetime(2026, 5, 20, 19, 12),
            units=12,
        )
        session.commit()

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
    )

    assert response.status_code == 200
    episodes = response.json()["episodes"]
    assert len(episodes) == 1
    episode = episodes[0]
    assert episode["kind"] == "food"
    assert set(episode["meal_ids"]) == {str(nuggets.id), str(roll.id)}
    assert episode["total_carbs_g"] == 58.0
    assert episode["total_insulin_units"] == 12.0
    event = episode["insulin"][0]
    assert event["id"] == str(bolus.id)
    assert event["kind"] == "food"
    assert event["anchor_meal_id"] == str(nuggets.id)


def test_episode_gains_owner_scoped_first_after_sleep_context_retroactively(
    api_client: TestClient,
) -> None:
    """A late sleep sync marks the already-dosed sitting on the next read."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    other_id = UUID("22222222-2222-2222-2222-222222222222")
    session_factory = api_client.app_state["session_factory"]
    target_at = datetime(2026, 8, 8, 10, 55)
    target_utc = target_at.replace(tzinfo=UTC)
    with session_factory() as session:
        session.add(
            User(
                id=other_id,
                username="other-sleeper",
                password_hash=hash_password("test-password"),
                role=UserRole.gluco,
            )
        )
        _seed_meal(
            session,
            owner_id,
            "Previous meal",
            target_at - timedelta(hours=8, minutes=29),
        )
        target = _seed_meal(session, owner_id, "Breakfast", target_at, carbs=39)
        _seed_insulin(session, owner_id, "breakfast-bolus", target_at, units=6)
        # Another user's sleep must never influence this user's marker.
        _seed_sleep(
            session,
            other_id,
            start=target_utc - timedelta(hours=6, minutes=35),
            end=target_utc - timedelta(minutes=48),
        )
        session.commit()

    params = {"from": "2026-08-08T00:00:00", "to": "2026-08-09T00:00:00"}
    before = api_client.get("/glucose/episodes", params=params).json()["episodes"]
    target_before = next(row for row in before if str(target.id) in row["meal_ids"])
    assert target_before["first_after_sleep"] is False

    with session_factory() as session:
        _seed_sleep(
            session,
            owner_id,
            start=target_utc - timedelta(hours=6, minutes=35),
            end=target_utc - timedelta(minutes=48),
        )
        session.commit()

    after = api_client.get("/glucose/episodes", params=params).json()["episodes"]
    target_after = next(row for row in after if str(target.id) in row["meal_ids"])
    assert target_after["first_after_sleep"] is True


def test_a_sitting_is_anchored_to_its_first_meal_not_chained(
    api_client: TestClient,
) -> None:
    """Observed 2026-08-05: 18:10 → 18:41 → 19:25 became one episode because
    every individual hop was under the window, so three eating events 75
    minutes apart end to end shared one carbohydrate total and one dose."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        first = _seed_meal(
            session,
            owner_id,
            "Пирожки",
            datetime(2026, 8, 5, 18, 10),
            carbs=55,
        )
        # 31 minutes after the anchor: a new sitting, though only 31 minutes
        # from the meal before it, which is what used to chain them.
        second = _seed_meal(
            session,
            owner_id,
            "Выпечка",
            datetime(2026, 8, 5, 18, 41),
            carbs=42,
        )
        # 44 minutes after the second, 75 after the first.
        third = _seed_meal(
            session,
            owner_id,
            "Лапша",
            datetime(2026, 8, 5, 19, 25),
            carbs=55,
        )
        # Inside the anchor's span, so it joins the third sitting.
        with_third = _seed_meal(
            session,
            owner_id,
            "Лепёшка",
            datetime(2026, 8, 5, 19, 40),
            carbs=43,
        )
        session.commit()

    episodes = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-05T00:00:00", "to": "2026-08-06T00:00:00"},
    ).json()["episodes"]

    by_meals = {frozenset(episode["meal_ids"]): episode for episode in episodes}
    assert len(episodes) == 3
    assert frozenset({str(first.id)}) in by_meals
    assert frozenset({str(second.id)}) in by_meals
    third_sitting = by_meals[frozenset({str(third.id), str(with_third.id)})]
    assert third_sitting["total_carbs_g"] == 98.0


def test_insulin_joins_one_sitting_and_never_bridges_two(
    api_client: TestClient,
) -> None:
    """The sitting rule only touched meals with no bolus, so on a real day it
    never ran. A bolus links to every meal from 30 min before to 90 min after,
    and the component walk chained meal -> insulin -> meal, so 18:10 to 20:31
    stayed one episode."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        early = _seed_meal(
            session,
            owner_id,
            "Пирожки",
            datetime(2026, 8, 5, 18, 10),
            carbs=55,
        )
        late = _seed_meal(
            session,
            owner_id,
            "Лапша",
            datetime(2026, 8, 5, 19, 25),
            carbs=55,
        )
        # Inside the 90-minute window of BOTH meals, so it used to link to each
        # and fuse them into one episode.
        _seed_insulin(
            session,
            owner_id,
            "ns-bridging-bolus",
            datetime(2026, 8, 5, 19, 33),
            units=12,
        )
        _seed_insulin(
            session,
            owner_id,
            "ns-early-bolus",
            datetime(2026, 8, 5, 18, 12),
            units=4.6,
        )
        session.commit()

    episodes = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-05T00:00:00", "to": "2026-08-06T00:00:00"},
    ).json()["episodes"]

    assert len(episodes) == 2
    by_meal = {
        episode["meal_ids"][0]: episode for episode in episodes if episode["meal_ids"]
    }
    # Each bolus lands on its own sitting rather than bridging the two.
    assert by_meal[str(early.id)]["total_insulin_units"] == 4.6
    assert by_meal[str(late.id)]["total_insulin_units"] == 12.0


def test_a_bolus_chasing_a_rise_is_marked_catch_up(
    api_client: TestClient,
) -> None:
    """A second bolus an hour in, given after watching glucose climb, was
    recorded as ordinary meal insulin — so the food looked like it needed the
    whole amount, when what it needed was the same amount earlier."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    meal_at = datetime(2026, 8, 5, 12, 0)
    with session_factory() as session:
        _seed_meal(session, owner_id, "Панкейки", meal_at, carbs=62)
        _seed_insulin(session, owner_id, "ns-meal", meal_at, units=8.0)
        _seed_insulin(
            session,
            owner_id,
            "ns-chase",
            meal_at + timedelta(hours=1),
            units=4.0,
        )
        # Climbing hard through the hour before the second bolus.
        for index, value in enumerate((6.2, 8.1, 10.0, 11.6, 12.8)):
            _seed_glucose(
                session,
                owner_id,
                meal_at + timedelta(minutes=15 * index),
                value,
            )
        session.commit()

    episodes = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-05T00:00:00", "to": "2026-08-06T00:00:00"},
    ).json()["episodes"]

    kinds = {
        event["insulin_units"]: event["kind"]
        for episode in episodes
        for event in episode["insulin"]
    }
    assert kinds[8.0] == "food"
    assert kinds[4.0] == "catch_up"


def test_a_bolus_given_on_a_flat_trace_stays_ordinary(
    api_client: TestClient,
) -> None:
    """Only a rise makes it a chase. Split dosing on a steady trace is not."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    meal_at = datetime(2026, 8, 5, 12, 0)
    with session_factory() as session:
        _seed_meal(session, owner_id, "Панкейки", meal_at, carbs=62)
        _seed_insulin(session, owner_id, "ns-meal", meal_at, units=8.0)
        _seed_insulin(
            session,
            owner_id,
            "ns-second",
            meal_at + timedelta(hours=1),
            units=4.0,
        )
        for index in range(5):
            _seed_glucose(
                session,
                owner_id,
                meal_at + timedelta(minutes=15 * index),
                6.2,
            )
        session.commit()

    episodes = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-05T00:00:00", "to": "2026-08-06T00:00:00"},
    ).json()["episodes"]

    kinds = [event["kind"] for episode in episodes for event in episode["insulin"]]
    assert "catch_up" not in kinds


def test_episodes_standalone_insulin_is_correction(api_client: TestClient) -> None:
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        _seed_meal(
            session,
            owner_id,
            "Завтрак",
            datetime(2026, 5, 20, 9, 0),
        )
        correction = _seed_insulin(
            session,
            owner_id,
            "ns-lone-correction",
            datetime(2026, 5, 20, 15, 0),
            units=1.5,
        )
        session.commit()

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
    )

    assert response.status_code == 200
    episodes = response.json()["episodes"]
    kinds = {episode["kind"] for episode in episodes}
    assert kinds == {"food_only", "correction"}
    lone = next(e for e in episodes if e["kind"] == "correction")
    assert lone["meal_ids"] == []
    assert lone["outcome"]["status"] == "no_cgm"
    assert lone["outcome"]["kind"] == "minimum"
    event = lone["insulin"][0]
    assert event["id"] == str(correction.id)
    assert event["kind"] == "correction"
    assert event["anchor_meal_id"] is None


def test_episodes_are_scoped_to_current_user(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        other = User(
            username="episode-other",
            password_hash=hash_password("episode-other-password"),
            role=UserRole.gluco,
        )
        session.add(other)
        session.flush()
        other_id = other.id
        _seed_meal(
            session,
            other_id,
            "Чужой обед",
            datetime(2026, 5, 20, 13, 0),
        )
        session.commit()

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
    )

    assert response.status_code == 200
    assert response.json()["episodes"] == []
    assert "Чужой" not in response.text


def test_episodes_are_glucose_gated_for_food_users(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        food_user = User(
            username="episode-food-user",
            password_hash=hash_password("episode-food-password"),
            role=UserRole.food,
        )
        session.add(food_user)
        session.commit()
        food_user_id = food_user.id

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-05-20T00:00:00", "to": "2026-05-21T00:00:00"},
        headers=_headers(food_user_id, UserRole.food),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "feature_disabled",
        "feature": "glucose",
    }


def test_materialize_day_persists_snapshots_without_manual_review(
    api_client: TestClient,
) -> None:
    """The worker path fills the export tables with auto-grouped episodes."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        _seed_meal(
            session,
            owner_id,
            "Суп с фрикадельками",
            datetime(2026, 5, 20, 4, 54),
            carbs=35,
        )
        _seed_insulin(
            session,
            owner_id,
            "ns-soup-bolus",
            datetime(2026, 5, 20, 4, 53),
            units=3,
        )
        session.commit()

    with session_factory() as session:
        InsulinLinkDayService(session, owner_id).materialize_day(date(2026, 5, 20))

    with session_factory() as session:
        snapshots = list(
            session.scalars(
                select(MealInsulinEpisodeSnapshot).where(
                    MealInsulinEpisodeSnapshot.owner_id == owner_id,
                    MealInsulinEpisodeSnapshot.date == date(2026, 5, 20),
                )
            )
        )

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.kind == "food"
    assert snapshot.total_carbs_g == 35.0
    assert snapshot.total_insulin_units == 3.0
    assert len(snapshot.meal_ids_json) == 1
    assert len(snapshot.insulin_event_ids_json) == 1


def _seed_evening(session: Session, owner_id: UUID) -> dict[str, UUID]:
    """The owner's 2026-08-07 evening: dinner, a chase, then a croissant.

    6 U with dinner at 18:44; glucose climbed faster than wanted, so 1 U more at
    19:38; then a croissant at 20:03 with its own 2 U.
    """
    day = datetime(2026, 8, 7)

    def at(hour: int, minute: int) -> datetime:
        return day.replace(hour=hour, minute=minute)

    plate = _seed_meal(session, owner_id, "Ужин", at(18, 44), carbs=51)
    second = _seed_meal(session, owner_id, "Ужин, второе", at(18, 53), carbs=27)
    croissant = _seed_meal(session, owner_id, "Круассан", at(20, 3), carbs=29)
    _seed_insulin(
        session, owner_id, "ns-dinner", at(18, 53), units=6, event_type="Bolus"
    )
    chase = _seed_insulin(
        session, owner_id, "ns-chase", at(19, 38), units=1, event_type="Bolus"
    )
    _seed_insulin(session, owner_id, "ns-snack", at(20, 3), units=2, event_type="Bolus")

    # Climbing hard through the chase, which is why it was given.
    curve = [
        (17, 30, 5.4),
        (18, 44, 6.0),
        (19, 0, 7.2),
        (19, 20, 8.6),
        (19, 38, 9.4),
        (20, 0, 9.6),
        (20, 40, 8.8),
        (21, 30, 7.3),
    ]
    for index in range(len(curve) - 1):
        (h0, m0, v0), (h1, m1, v1) = curve[index], curve[index + 1]
        start, end = at(h0, m0), at(h1, m1)
        step = start
        while step < end:
            share = (step - start) / (end - start)
            _seed_glucose(session, owner_id, step, v0 + (v1 - v0) * share)
            step += timedelta(minutes=5)
    return {
        "plate": plate.id,
        "second": second.id,
        "croissant": croissant.id,
        "chase": chase.id,
    }


def test_a_chasing_dose_stays_with_the_meal_it_chases(
    api_client: TestClient,
) -> None:
    """A dose given on a rise belongs to what caused the rise.

    Nearest-by-clock handed this one to the croissant — 25 minutes ahead of it
    beat 54 minutes behind the dinner — even though at 19:38 the croissant did
    not exist as a decision yet. The croissant then read as 29 g on 3 U, a
    carbohydrate ratio of 9.7 g/U where the same evening with the same doses
    gives 14.5 if the snack happens an hour later. The tie now breaks on what
    glucose was doing, which is the test the catch-up label already used.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        ids = _seed_evening(session, owner_id)
        session.commit()

    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-07T00:00:00", "to": "2026-08-08T00:00:00"},
    )

    assert response.status_code == 200
    episodes = response.json()["episodes"]
    by_meal = {
        meal_id: episode for episode in episodes for meal_id in episode["meal_ids"]
    }
    dinner = by_meal[str(ids["plate"])]
    croissant = by_meal[str(ids["croissant"])]

    assert dinner["total_insulin_units"] == 7.0
    assert croissant["total_insulin_units"] == 2.0
    assert croissant["total_carbs_g"] == 29.0
    assert dinner["outcome"] == {
        "status": "complete",
        "kind": "peak",
        "start_value": 6.0,
        "result_value": 9.6,
        "delta_mmol_l": 3.6,
        "is_low": False,
    }
    # And the chase is named as one rather than passing for meal insulin.
    chased = next(
        event for event in dinner["insulin"] if event["id"] == str(ids["chase"])
    )
    assert chased["kind"] == "catch_up"
