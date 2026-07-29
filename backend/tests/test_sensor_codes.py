"""GS1 sensor Data Matrix parsing tests."""

from datetime import date

import pytest

from glucotracker.domain.sensor_codes import (
    SensorCodeParseError,
    parse_sensor_data_matrix,
)

RAW_SENSOR_CODE = (
    "0106977641010009112606221727062110OCGL06/102SD2626.006"
    "\x1d21X12266291Y4R"
)


def test_parse_compact_sensor_data_matrix() -> None:
    parsed = parse_sensor_data_matrix(RAW_SENSOR_CODE)

    assert parsed.gtin == "06977641010009"
    assert parsed.manufactured_on == date(2026, 6, 22)
    assert parsed.expires_on == date(2027, 6, 21)
    assert parsed.lot_number == "OCGL06/102SD2626.006"
    assert parsed.serial_number == "X12266291Y4R"


def test_parse_parenthesized_sensor_data_matrix() -> None:
    parsed = parse_sensor_data_matrix(
        "(01)06977641010009(11)260622(17)270621"
        "(10)OCGL06/102SD2626.006(21)X12266291Y4R"
    )

    assert parsed.serial_number == "X12266291Y4R"
    assert parsed.lot_number == "OCGL06/102SD2626.006"


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "0106977641010008112606221727062121X12266291Y4R",
        "0106977641010009112606221725062121X12266291Y4R",
        "01069776410100091126062217270621",
    ],
)
def test_invalid_sensor_data_matrix_is_rejected(payload: str) -> None:
    with pytest.raises(SensorCodeParseError):
        parse_sensor_data_matrix(payload)
