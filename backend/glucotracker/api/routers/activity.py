"""Activity sync and user profile endpoints."""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from glucotracker.api.dependencies import SessionDep, verify_token
from glucotracker.domain.energy import kcal_balance, tdee_from_profile
from glucotracker.infra.db.models import DailyActivity, UserProfile

router = APIRouter(
    tags=["activity"],
    dependencies=[Depends(verify_token)],
)


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
    bmr_available: bool = False


class KcalBalanceDay(BaseModel):
    date: date_type
    kcal_in: float
    tdee: float | None = None
    net_balance: float | None = None
    steps: int = 0
    bmr_available: bool = False


class KcalBalanceRangeResponse(BaseModel):
    days: list[KcalBalanceDay]


def _get_or_create_profile(session: Session) -> UserProfile:
    profile = session.get(UserProfile, 1)
    if profile is None:
        profile = UserProfile(id=1)
        session.add(profile)
        session.flush()
    return profile


@router.get(
    "/profile",
    response_model=UserProfileResponse,
    operation_id="getUserProfile",
)
def get_profile(session: SessionDep) -> UserProfile:
    return _get_or_create_profile(session)


@router.put(
    "/profile",
    response_model=UserProfileResponse,
    operation_id="updateUserProfile",
)
def update_profile(
    payload: UserProfileUpdate,
    session: SessionDep,
) -> UserProfile:
    profile = _get_or_create_profile(session)
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
) -> DailyActivity:
    existing = session.get(DailyActivity, payload.date)
    if existing is None:
        row = DailyActivity(
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
    return existing


@router.get(
    "/activity/balance",
    response_model=KcalBalanceResponse,
    operation_id="getKcalBalance",
)
def get_kcal_balance(
    day: date_type,
    session: SessionDep,
) -> dict:
    from glucotracker.infra.db.models import DailyTotal

    profile = _get_or_create_profile(session)
    total = session.get(DailyTotal, day)
    activity = session.get(DailyActivity, day)

    kcal_in = total.kcal if total else 0
    kcal_burned = activity.kcal_burned if activity else 0
    steps = activity.steps if activity else 0
    tdee = tdee_from_profile(profile, activity)
    net = kcal_balance(kcal_in, profile, activity)

    return {
        "date": day,
        "kcal_in": kcal_in,
        "kcal_burned": kcal_burned,
        "tdee": tdee,
        "net_balance": net,
        "steps": steps,
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
) -> dict:
    from datetime import timedelta

    from glucotracker.infra.db.models import DailyTotal

    profile = _get_or_create_profile(session)

    days = []
    current = from_date
    while current <= to_date:
        total = session.get(DailyTotal, current)
        activity = session.get(DailyActivity, current)

        kcal_in = total.kcal if total else 0
        steps = activity.steps if activity else 0
        tdee = tdee_from_profile(profile, activity)
        net = kcal_balance(kcal_in, profile, activity)

        days.append(
            {
                "date": current,
                "kcal_in": kcal_in,
                "tdee": tdee,
                "net_balance": net,
                "steps": steps,
                "bmr_available": tdee is not None,
            }
        )
        current += timedelta(days=1)

    return {"days": days}
