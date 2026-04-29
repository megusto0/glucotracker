"""Endocrinologist report API tests."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi.testclient import TestClient

from glucotracker.infra.db.models import (
    NightscoutGlucoseEntry,
    NightscoutInsulinEvent,
)


def _manual_item(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": "Йогурт",
        "carbs_g": 10,
        "protein_g": 15,
        "fat_g": 4,
        "fiber_g": 0,
        "kcal": 136,
        "source_kind": "manual",
    }
    payload.update(overrides)
    return payload


def _create_meal(
    api_client: TestClient,
    *,
    eaten_at: str,
    carbs_g: float,
    title: str = "Завтрак",
) -> dict[str, Any]:
    response = api_client.post(
        "/meals",
        json={
            "eaten_at": eaten_at,
            "title": title,
            "source": "manual",
            "status": "accepted",
            "items": [_manual_item(carbs_g=carbs_g, kcal=carbs_g * 4)],
        },
    )
    assert response.status_code == 201
    return response.json()


def _seed_nightscout_context(api_client: TestClient) -> None:
    session_factory = api_client.app_state["session_factory"]
    with session_factory() as session:
        session.add_all(
            [
                NightscoutGlucoseEntry(
                    source_key="glucose-before",
                    timestamp=datetime.fromisoformat("2026-04-28T07:40:00"),
                    value_mmol_l=6.0,
                    value_mg_dl=108,
                    source="CGM",
                ),
                NightscoutGlucoseEntry(
                    source_key="glucose-after",
                    timestamp=datetime.fromisoformat("2026-04-28T10:00:00"),
                    value_mmol_l=8.0,
                    value_mg_dl=144,
                    source="CGM",
                ),
                NightscoutInsulinEvent(
                    source_key="insulin-linked",
                    nightscout_id="linked-1",
                    timestamp=datetime.fromisoformat("2026-04-28T08:05:00"),
                    insulin_units=4.0,
                    event_type="Meal Bolus",
                    entered_by="Nightscout",
                ),
                NightscoutInsulinEvent(
                    source_key="insulin-unlinked",
                    nightscout_id="unlinked-1",
                    timestamp=datetime.fromisoformat("2026-04-28T15:00:00"),
                    insulin_units=10.0,
                    event_type="Correction Bolus",
                    entered_by="Nightscout",
                ),
            ]
        )
        session.commit()


def test_endocrinologist_report_uses_episode_linked_insulin(
    api_client: TestClient,
) -> None:
    """Observed ratio uses linked insulin; daily insulin includes unlinked events."""
    _create_meal(
        api_client,
        eaten_at="2026-04-28T08:00:00",
        carbs_g=42,
    )
    _create_meal(
        api_client,
        eaten_at="2026-04-28T08:20:00",
        carbs_g=10,
    )
    _seed_nightscout_context(api_client)

    response = api_client.get(
        "/reports/endocrinologist",
        params={"from": "2026-04-28", "to": "2026-04-28"},
    )

    assert response.status_code == 200
    body = response.json()
    kpis = {row["label"]: row for row in body["kpis"]}
    assert kpis["НАБЛЮДАЕМЫЙ УК"]["value"] == "13,0"
    assert kpis["НАБЛЮДАЕМЫЙ УК"]["unit"] == "г/ЕД"
    assert kpis["ИНСУЛИН ЗАВТРАК"]["value"] == "4,0"
    assert kpis["ИНСУЛИН ЗА ДЕНЬ"]["value"] == "14,0"
    assert kpis["САХАР ДО ЕДЫ"]["value"] == "6,0"
    assert kpis["САХАР ПОСЛЕ ЕДЫ"]["value"] == "8,0"
    assert body["daily_rows"][0]["breakfast"] == "52г / 4Е"
    assert "рекомендуемый" not in body["footer"].lower()
    assert "медицинской рекомендацией" in body["footer"]


def test_endocrinologist_report_handles_empty_period(
    api_client: TestClient,
) -> None:
    """Empty report periods still return explicit missing-data states."""
    response = api_client.get(
        "/reports/endocrinologist",
        params={"from": "2026-04-28", "to": "2026-04-29"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["warning"] == "Данных мало: 0 дней с едой из 2 выбранных"
    assert "CGM нет за период" in body["notes"]
    assert "Инсулин не найден" in body["notes"]
    assert body["kpis"][0]["value"] == "—"
    assert body["daily_rows"][0]["date"] == str(date(2026, 4, 28))
