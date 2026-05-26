"""Activity sync and user profile endpoints."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from datetime import date as date_type

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.config import get_settings
from glucotracker.domain.energy import kcal_balance, tdee_from_profile
from glucotracker.infra.db.models import DailyActivity, UserProfile

router = APIRouter(tags=["activity"])


class UserProfileResponse(BaseModel):
    weight_kg: float | None = None
    height_cm: float | None = None
    age_years: int | None = None
    sex: str | None = None
    activity_level: str = "moderate"


class UserProfileUpdate(BaseModel):
    weight_kg: float | None = None
    height_cm: float | None = None
    age_years: int | None = None
    sex: str | None = None
    activity_level: str | None = None


class ActivitySyncRequest(BaseModel):
    date: date_type
    steps: int = 0
    active_minutes: int = 0
    kcal_burned: float = 0
    heart_rate_avg: float | None = None
    heart_rate_rest: float | None = None
    source: str = "gadgetbridge"
    hr_samples: int = 0
    hr_active_minutes: int = 0
    kcal_hr_active: float = 0
    kcal_steps: float = 0
    kcal_no_move_hr: float = 0
    calorie_confidence: str = "none"


class ActivitySyncResponse(BaseModel):
    date: date_type
    steps: int
    active_minutes: int
    kcal_burned: float
    heart_rate_avg: float | None
    heart_rate_rest: float | None
    source: str
    synced_at: datetime


class KcalBalanceResponse(BaseModel):
    date: date_type
    kcal_in: float
    kcal_burned: float
    tdee: float | None = None
    net_balance: float | None = None
    steps: int = 0
    activity_source: str | None = None
    bmr_available: bool = False


class KcalBalanceDay(BaseModel):
    date: date_type
    kcal_in: float
    tdee: float | None = None
    net_balance: float | None = None
    steps: int = 0
    activity_source: str | None = None
    bmr_available: bool = False


class KcalBalanceRangeResponse(BaseModel):
    days: list[KcalBalanceDay]


def _get_or_create_profile(
    session: Session,
    current_user: CurrentUserDep,
) -> UserProfile:
    profile = session.scalar(
        select(UserProfile).where(UserProfile.owner_id == current_user.id)
    )
    if profile is None:
        profile = UserProfile(owner_id=current_user.id)
        session.add(profile)
        session.flush()
    return profile


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    operation_id="getUserProfile",
)
def get_profile(session: SessionDep, current_user: CurrentUserDep) -> UserProfile:
    return _get_or_create_profile(session, current_user)


@router.put(
    "/profile",
    response_model=UserProfileResponse,
    operation_id="updateUserProfile",
)
def update_profile(
    payload: UserProfileUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> UserProfile:
    profile = _get_or_create_profile(session, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    session.commit()
    session.refresh(profile)
    return profile


@router.post(
    "/activity/sync",
    response_model=ActivitySyncResponse,
    operation_id="syncActivity",
)
def sync_activity(
    payload: ActivitySyncRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> DailyActivity:
    existing = session.scalar(
        select(DailyActivity).where(
            DailyActivity.owner_id == current_user.id,
            DailyActivity.date == payload.date,
        )
    )
    action = "created" if existing is None else "updated"
    if existing is None:
        row = DailyActivity(
            owner_id=current_user.id,
            date=payload.date,
            steps=payload.steps,
            active_minutes=payload.active_minutes,
            kcal_burned=payload.kcal_burned,
            heart_rate_avg=payload.heart_rate_avg,
            heart_rate_rest=payload.heart_rate_rest,
            source=payload.source,
            hr_samples=payload.hr_samples,
            hr_active_minutes=payload.hr_active_minutes,
            kcal_hr_active=payload.kcal_hr_active,
            kcal_steps=payload.kcal_steps,
            kcal_no_move_hr=payload.kcal_no_move_hr,
            calorie_confidence=payload.calorie_confidence,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        _write_activity_sync_file(payload, row, action)
        return row

    existing.steps = payload.steps
    existing.active_minutes = payload.active_minutes
    existing.kcal_burned = payload.kcal_burned
    existing.heart_rate_avg = payload.heart_rate_avg
    existing.heart_rate_rest = payload.heart_rate_rest
    existing.source = payload.source
    existing.hr_samples = payload.hr_samples
    existing.hr_active_minutes = payload.hr_active_minutes
    existing.kcal_hr_active = payload.kcal_hr_active
    existing.kcal_steps = payload.kcal_steps
    existing.kcal_no_move_hr = payload.kcal_no_move_hr
    existing.calorie_confidence = payload.calorie_confidence
    session.commit()
    session.refresh(existing)
    _write_activity_sync_file(payload, existing, action)
    return existing


def _write_activity_sync_file(
    payload: ActivitySyncRequest,
    row: DailyActivity,
    action: str,
) -> None:
    """Append a readable local file entry for received activity payloads."""
    log_dir = get_settings().activity_log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"activity-{payload.date.isoformat()}.log"
    received_at = datetime.now(UTC).isoformat()
    raw_payload = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    entry = "\n".join(
        [
            "=" * 72,
            f"Received at: {received_at}",
            f"Action: {action}",
            f"Date: {payload.date.isoformat()}",
            f"Source: {payload.source}",
            "",
            "Readable summary:",
            f"  Steps: {payload.steps}",
            f"  Active minutes: {payload.active_minutes}",
            f"  Calories burned: {_format_number(payload.kcal_burned)} kcal",
            f"  Heart rate average: {_format_optional(payload.heart_rate_avg, ' bpm')}",
            f"  Heart rate rest: {_format_optional(payload.heart_rate_rest, ' bpm')}",
            f"  Heart-rate samples: {payload.hr_samples}",
            f"  Heart-rate active minutes: {payload.hr_active_minutes}",
            "  Calorie breakdown:",
            f"    Steps: {_format_number(payload.kcal_steps)} kcal",
            f"    Active HR: {_format_number(payload.kcal_hr_active)} kcal",
            f"    No-move HR: {_format_number(payload.kcal_no_move_hr)} kcal",
            f"  Calorie confidence: {payload.calorie_confidence}",
            "",
            "Stored row:",
            f"  Synced at: {row.synced_at.isoformat()}",
            f"  DB source: {row.source}",
            "",
            "Raw payload:",
            raw_payload,
            "",
        ]
    )
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)


def _format_optional(value: float | None, suffix: str) -> str:
    if value is None:
        return "not provided"
    return f"{_format_number(value)}{suffix}"


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.1f}"


@router.get(
    "/activity/balance",
    response_model=KcalBalanceResponse,
    operation_id="getKcalBalance",
)
def get_kcal_balance(
    day: date_type,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
    from glucotracker.infra.db.models import DailyTotal

    profile = _get_or_create_profile(session, current_user)
    total = session.scalar(
        select(DailyTotal).where(
            DailyTotal.owner_id == current_user.id,
            DailyTotal.date == day,
        )
    )
    activity = session.scalar(
        select(DailyActivity).where(
            DailyActivity.owner_id == current_user.id,
            DailyActivity.date == day,
        )
    )

    kcal_in = total.kcal if total else 0
    kcal_burned = activity.kcal_burned if activity else 0
    steps = activity.steps if activity else 0
    activity_source = activity.source if activity else None
    tdee = tdee_from_profile(profile, activity)
    net = kcal_balance(kcal_in, profile, activity)

    return {
        "date": day,
        "kcal_in": kcal_in,
        "kcal_burned": kcal_burned,
        "tdee": tdee,
        "net_balance": net,
        "steps": steps,
        "activity_source": activity_source,
        "bmr_available": tdee is not None,
    }


@router.get(
    "/activity/balance/range",
    response_model=KcalBalanceRangeResponse,
    operation_id="getKcalBalanceRange",
)
def get_kcal_balance_range(
    from_date: date_type,
    to_date: date_type,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> dict:
    from datetime import timedelta

    from glucotracker.infra.db.models import DailyTotal

    profile = _get_or_create_profile(session, current_user)

    days = []
    current = from_date
    while current <= to_date:
        total = session.scalar(
            select(DailyTotal).where(
                DailyTotal.owner_id == current_user.id,
                DailyTotal.date == current,
            )
        )
        activity = session.scalar(
            select(DailyActivity).where(
                DailyActivity.owner_id == current_user.id,
                DailyActivity.date == current,
            )
        )

        kcal_in = total.kcal if total else 0
        steps = activity.steps if activity else 0
        activity_source = activity.source if activity else None
        tdee = tdee_from_profile(profile, activity)
        net = kcal_balance(kcal_in, profile, activity)

        days.append(
            {
                "date": current,
                "kcal_in": kcal_in,
                "tdee": tdee,
                "net_balance": net,
                "steps": steps,
                "activity_source": activity_source,
                "bmr_available": tdee is not None,
            }
        )
        current += timedelta(days=1)

    return {"days": days}
