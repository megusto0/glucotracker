"""Deterministic parsing for CGM sensor GS1 Data Matrix payloads."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

GS = "\x1d"
_PARENTHESIZED_AI = re.compile(r"\((\d{2,4})\)")
_FIXED_LENGTH_AIS = {"01": 14, "11": 6, "17": 6}
_VARIABLE_LENGTH_AIS = {"10": 64, "21": 64}


class SensorCodeParseError(ValueError):
    """Raised when a scan is not a supported sensor GS1 Data Matrix payload."""


@dataclass(frozen=True)
class ParsedSensorCode:
    """Structured fields persisted for one scanned sensor."""

    raw_payload: str
    gtin: str
    manufactured_on: date | None
    expires_on: date | None
    lot_number: str | None
    serial_number: str


def parse_sensor_data_matrix(raw_payload: str) -> ParsedSensorCode:
    """Parse the GS1 fields used by sensor packaging."""
    payload = raw_payload.strip()
    if payload.startswith("]d2"):
        payload = payload[3:]
    if not payload:
        raise SensorCodeParseError("Data Matrix payload is empty.")

    fields = (
        _parse_parenthesized(payload)
        if _PARENTHESIZED_AI.search(payload)
        else _parse_compact(payload)
    )
    gtin = fields.get("01")
    serial = fields.get("21")
    if gtin is None or serial is None:
        raise SensorCodeParseError("Sensor code must contain GS1 fields 01 and 21.")
    if not _valid_gtin(gtin):
        raise SensorCodeParseError("GS1 field 01 contains an invalid GTIN.")

    manufactured_on = _parse_gs1_date(fields.get("11"), "11")
    expires_on = _parse_gs1_date(fields.get("17"), "17")
    if (
        manufactured_on is not None
        and expires_on is not None
        and expires_on < manufactured_on
    ):
        raise SensorCodeParseError("Sensor expiry precedes its manufacture date.")

    return ParsedSensorCode(
        raw_payload=payload,
        gtin=gtin,
        manufactured_on=manufactured_on,
        expires_on=expires_on,
        lot_number=fields.get("10"),
        serial_number=serial,
    )


def _parse_parenthesized(payload: str) -> dict[str, str]:
    matches = list(_PARENTHESIZED_AI.finditer(payload))
    fields: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(payload)
        value = payload[start:end].strip(GS)
        if value:
            fields[match.group(1)] = value
    return fields


def _parse_compact(payload: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    cursor = 0
    while cursor < len(payload):
        if payload[cursor] == GS:
            cursor += 1
            continue
        ai = payload[cursor : cursor + 2]
        cursor += 2
        fixed_length = _FIXED_LENGTH_AIS.get(ai)
        if fixed_length is not None:
            value = payload[cursor : cursor + fixed_length]
            if len(value) != fixed_length:
                raise SensorCodeParseError(f"GS1 field {ai} is truncated.")
            cursor += fixed_length
        elif ai in _VARIABLE_LENGTH_AIS:
            separator = payload.find(GS, cursor)
            if separator < 0:
                value = payload[cursor:]
                cursor = len(payload)
            else:
                value = payload[cursor:separator]
                cursor = separator + 1
            if len(value) > _VARIABLE_LENGTH_AIS[ai]:
                raise SensorCodeParseError(f"GS1 field {ai} is too long.")
        else:
            raise SensorCodeParseError(f"Unsupported GS1 application identifier {ai}.")
        if not value:
            raise SensorCodeParseError(f"GS1 field {ai} is empty.")
        fields[ai] = value
    return fields


def _parse_gs1_date(value: str | None, ai: str) -> date | None:
    if value is None:
        return None
    if len(value) != 6 or not value.isdigit():
        raise SensorCodeParseError(f"GS1 field {ai} must be YYMMDD.")
    year = 2000 + int(value[:2])
    month = int(value[2:4])
    day = int(value[4:6])
    if day == 0 and 1 <= month <= 12:
        day = calendar.monthrange(year, month)[1]
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise SensorCodeParseError(f"GS1 field {ai} contains an invalid date.") from exc


def _valid_gtin(value: str) -> bool:
    if len(value) != 14 or not value.isdigit():
        return False
    digits = [int(char) for char in value]
    total = sum(
        digit * (3 if index % 2 == 0 else 1)
        for index, digit in enumerate(digits[:-1])
    )
    return (10 - total % 10) % 10 == digits[-1]
