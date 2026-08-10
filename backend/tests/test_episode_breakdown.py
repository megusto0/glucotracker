"""One episode taken apart: window, anchors, crossings, cause, frequency."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from glucotracker.domain.entities import MealSource, MealStatus
from glucotracker.infra.db.models import (
    Meal,
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)

NIGHT = datetime(2026, 8, 6)

# The trace behind mockup screen H, as (minutes past midnight, mmol/L). Glucose
# falls off a correction given at 00:18, bottoms at 01:05, is answered with
# juice, rebounds — and then climbs again on a snack at 02:20, which is the rise
# the breakdown must *not* attribute to the juice.
CURVE: list[tuple[int, float]] = [
    (-30, 7.4),
    (0, 6.8),
    (18, 6.1),
    (42, 4.8),
    (60, 3.7),
    (65, 3.6),
    (84, 4.4),
    (102, 6.3),
    (114, 7.5),
    (123, 7.9),
    (140, 7.2),
    (162, 7.8),
    (186, 8.3),
    (210, 7.6),
    (240, 6.6),
    (276, 6.1),
    (330, 5.8),
]


def _at(minutes: int) -> datetime:
    return NIGHT + timedelta(minutes=minutes)


def _interpolated() -> list[tuple[datetime, float]]:
    """The curve resampled every five minutes, the way a sensor reports it."""
    points: list[tuple[datetime, float]] = []
    for index in range(len(CURVE) - 1):
        (start_min, start_value), (end_min, end_value) = CURVE[index], CURVE[index + 1]
        step = start_min
        while step < end_min:
            share = (step - start_min) / (end_min - start_min)
            points.append((_at(step), start_value + (end_value - start_value) * share))
            step += 5
    points.append((_at(CURVE[-1][0]), CURVE[-1][1]))
    return points


def _seed_night(session: Session, owner_id: UUID) -> None:
    for at, value in _interpolated():
        session.add(
            NightscoutGlucoseEntry(
                owner_id=owner_id,
                source_key=f"breakdown-cgm-{at.isoformat()}",
                timestamp=at,
                value_mmol_l=round(value, 1),
                value_mg_dl=round(value * 18.0182),
                source="CGM",
            )
        )
    session.add(
        NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key="breakdown-correction",
            nightscout_id="breakdown-correction",
            timestamp=_at(18),
            insulin_units=3.0,
            event_type="Correction Bolus",
            entered_by="Nightscout",
        )
    )
    session.add(
        Meal(
            owner_id=owner_id,
            eaten_at=_at(65),
            title="Сок яблочный",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=12,
            total_protein_g=0,
            total_fat_g=0,
            total_kcal=48,
            ai_categories={"taste_profile": "drink_sweet"},
            derived_categories={"meal_role": "drink"},
        )
    )
    session.add(
        Meal(
            owner_id=owner_id,
            eaten_at=_at(140),
            title="Печенье",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=53,
            total_protein_g=6,
            total_fat_g=18,
            total_kcal=420,
        )
    )
    session.add(
        NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key="breakdown-meal-bolus",
            nightscout_id="breakdown-meal-bolus",
            timestamp=_at(193),
            insulin_units=2.0,
            event_type="Meal Bolus",
            entered_by="Nightscout",
        )
    )
    session.add(
        NightscoutInsulinEvent(
            owner_id=owner_id,
            source_key="breakdown-meal-catch-up",
            nightscout_id="breakdown-meal-catch-up",
            timestamp=_at(213),
            insulin_units=2.0,
            event_type="Meal Bolus",
            entered_by="Nightscout",
        )
    )


def _rescue(api_client: TestClient) -> dict:
    response = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-06T00:00:00", "to": "2026-08-07T00:00:00"},
    )
    assert response.status_code == 200
    episodes = response.json()["episodes"]
    rescue = next(
        episode
        for episode in episodes
        if episode["therapy"]["classification"] == "carb_correction"
    )
    detail = api_client.get(
        "/glucose/episodes/breakdown",
        params={
            "key": rescue["key"],
            "from": "2026-08-06T00:00:00",
            "to": "2026-08-07T00:00:00",
        },
    )
    assert detail.status_code == 200, detail.text
    return detail.json()


def test_breakdown_reads_the_rescue_from_its_trough(
    api_client: TestClient,
) -> None:
    """Trough, rebound and the per-gram figure, all from the calibrated trace."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        _seed_night(session, owner_id)
        session.commit()

    body = _rescue(api_client)

    assert body["classification"] == "carb_correction"
    assert body["title"] == "Сок яблочный"
    assert body["subtitle"] == "12 г"
    anchors = {anchor["role"]: anchor for anchor in body["anchors"]}
    assert anchors["trough"]["value"] == 3.6
    assert anchors["trough"]["label"] == "Минимум перед приёмом"
    # The window opens two hours before the plate and the points are sent one by
    # one, so the sheet can draw density and gaps rather than a smoothed line.
    assert body["points"]
    assert any(point["is_low"] for point in body["points"])
    assert body["low_threshold"] == 3.9


def test_breakdown_stops_at_the_next_episode(api_client: TestClient) -> None:
    """The snack's rise is the snack's, however much higher it goes.

    Glucose reaches 8.3 at 03:06 on a 53 g biscuit eaten at 02:20. A peak search
    that ran a flat 150 minutes would hand that number to twelve grams of juice
    and derive a carbohydrate sensitivity almost half again too steep.
    """
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        _seed_night(session, owner_id)
        session.commit()

    episodes = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-06T00:00:00", "to": "2026-08-07T00:00:00"},
    ).json()["episodes"]
    rescue = next(
        episode
        for episode in episodes
        if episode["therapy"]["classification"] == "carb_correction"
    )
    assert rescue["outcome"] == {
        "status": "complete",
        "kind": "recovery",
        "start_value": 3.6,
        "result_value": 7.9,
        "delta_mmol_l": 4.3,
        "is_low": False,
    }

    body = _rescue(api_client)

    anchors = {anchor["role"]: anchor for anchor in body["anchors"]}
    assert anchors["peak"]["value"] == 7.9
    assert anchors["peak"]["at"].endswith("02:03:00")

    derived = {item["code"]: item for item in body["derived"]}
    rise = derived["rise_per_carb"]
    assert rise["value"] == 4.3
    assert rise["per_value"] == 0.36
    assert rise["per_unit"] == "ммоль/л на г"


def test_breakdown_names_the_dose_as_the_cause(api_client: TestClient) -> None:
    """A rescue's cause is upstream of the rescue — here, insulin 47 min back."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        _seed_night(session, owner_id)
        session.commit()

    body = _rescue(api_client)

    assert body["cause"]["code"] == "insulin_correction_before"
    assert "Не еда — доза" in body["cause"]["text"]

    crossings = {crossing["kind"]: crossing for crossing in body["crossings"]}
    assert crossings["insulin"]["offset_minutes"] == -47
    assert "Коррекция инсулином" in crossings["insulin"]["label"]
    assert crossings["episode"]["offset_minutes"] == 75
    assert body["frequency"]["days"] == 30


def test_food_breakdown_reports_observation_without_claiming_bolus_causality(
    api_client: TestClient,
) -> None:
    """One trace cannot prove what the same meal would do without its bolus."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    with api_client.app_state["session_factory"]() as session:
        _seed_night(session, owner_id)
        session.commit()

    episodes = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-06T00:00:00", "to": "2026-08-07T00:00:00"},
    ).json()["episodes"]
    food = next(
        episode
        for episode in episodes
        if episode["therapy"]["classification"] in {"meal", "mixed"}
    )
    response = api_client.get(
        "/glucose/episodes/breakdown",
        params={
            "key": food["key"],
            "from": "2026-08-06T00:00:00",
            "to": "2026-08-07T00:00:00",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Печенье"
    assert body["subtitle"] == "53 г · 4,0 ЕД"
    assert body["cause"]["code"] == "bolus_late"
    assert body["cause"]["text"].startswith("До пика болюса не было:")
    assert "Первый введён через 53 мин после еды." in body["cause"]["text"]
    assert "На фоне болюса" not in body["cause"]["text"]
    assert "удержал" not in body["cause"]["text"]
    assert "не удержал" not in body["cause"]["text"]
    own_insulin = [
        crossing
        for crossing in body["crossings"]
        if crossing["label"] == "Инсулин 2,0 ЕД"
    ]
    assert [crossing["offset_minutes"] for crossing in own_insulin] == [53, 73]
    assert [crossing["detail"] for crossing in own_insulin] == [
        "через 53 мин после еды",
        "через 73 мин после еды",
    ]


def test_food_breakdown_follows_a_rise_past_the_standard_peak_window(
    api_client: TestClient,
) -> None:
    """A boundary sample is not a peak while the same meal rise continues."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    start = datetime(2026, 8, 6, 13, 44)
    curve = [
        (-5, 6.4),
        (60, 7.4),
        (120, 8.9),
        (135, 9.8),
        (145, 10.5),
        (165, 11.4),
        (190, 12.2),
        (220, 9.1),
        (230, 13.0),
        (240, 7.2),
    ]

    with api_client.app_state["session_factory"]() as session:
        for minutes, value in curve:
            at = start + timedelta(minutes=minutes)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"delayed-peak-{minutes}",
                    timestamp=at,
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        meal = Meal(
            owner_id=owner_id,
            eaten_at=start,
            title="Delayed meal",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=117,
            total_protein_g=20,
            total_fat_g=30,
            total_kcal=800,
        )
        session.add(meal)
        session.add(
            NightscoutInsulinEvent(
                owner_id=owner_id,
                source_key="delayed-peak-bolus",
                nightscout_id="delayed-peak-bolus",
                timestamp=start + timedelta(minutes=53),
                insulin_units=11.6,
                event_type="Meal Bolus",
                entered_by="Nightscout",
            )
        )
        session.commit()
        meal_id = meal.id

    episodes = api_client.get(
        "/glucose/episodes",
        params={"from": "2026-08-06T00:00:00", "to": "2026-08-07T00:00:00"},
    ).json()["episodes"]
    delayed_episode = next(
        episode for episode in episodes if f"m:{meal_id}" in episode["key"]
    )
    episode_key = delayed_episode["key"]
    assert delayed_episode["outcome"]["result_value"] == 12.2

    response = api_client.get(
        "/glucose/episodes/breakdown",
        params={
            "key": episode_key,
            "from": "2026-08-06T00:00:00",
            "to": "2026-08-07T00:00:00",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    anchors = {anchor["role"]: anchor for anchor in body["anchors"]}
    assert anchors["peak"]["value"] == 12.2
    assert anchors["peak"]["minutes_from_start"] == 190
    assert body["cause"]["text"].startswith(
        "Подъём начался без болюса: первый введён через 53 мин после еды."
    )


def test_food_breakdown_does_not_claim_a_later_rise_after_the_peak_settled(
    api_client: TestClient,
) -> None:
    """A separate late fluctuation stays context once the meal already crested."""
    owner_id = UUID(str(api_client.app_state["current_user_id"]))
    start = datetime(2026, 8, 6, 10, 0)
    curve = [
        (0, 6.0),
        (60, 9.0),
        (120, 7.0),
        (145, 6.5),
        (180, 10.0),
        (220, 8.0),
    ]

    with api_client.app_state["session_factory"]() as session:
        for minutes, value in curve:
            at = start + timedelta(minutes=minutes)
            session.add(
                NightscoutGlucoseEntry(
                    owner_id=owner_id,
                    source_key=f"settled-peak-{minutes}",
                    timestamp=at,
                    value_mmol_l=value,
                    value_mg_dl=round(value * 18.0182),
                    source="CGM",
                )
            )
        meal = Meal(
            owner_id=owner_id,
            eaten_at=start,
            title="Settled meal",
            source=MealSource.manual,
            status=MealStatus.accepted,
            total_carbs_g=60,
            total_protein_g=20,
            total_fat_g=15,
            total_kcal=500,
        )
        session.add(meal)
        session.commit()
        meal_id = meal.id

    response = api_client.get(
        "/glucose/episodes/breakdown",
        params={
            "key": f"m:{meal_id}",
            "from": "2026-08-06T00:00:00",
            "to": "2026-08-07T00:00:00",
        },
    )

    assert response.status_code == 200, response.text
    anchors = {anchor["role"]: anchor for anchor in response.json()["anchors"]}
    assert anchors["peak"]["value"] == 9.0
    assert anchors["peak"]["minutes_from_start"] == 60


def test_breakdown_rejects_a_key_outside_the_range(api_client: TestClient) -> None:
    response = api_client.get(
        "/glucose/episodes/breakdown",
        params={
            "key": "m:00000000-0000-0000-0000-000000000000",
            "from": "2026-08-06T00:00:00",
            "to": "2026-08-07T00:00:00",
        },
    )

    assert response.status_code == 404
