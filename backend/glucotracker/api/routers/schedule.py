"""User day-rhythm and schedule override endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.schemas import (
    DayAnchorHistoryResponse,
    DeleteResponse,
    NonTypicalPeriodCreate,
    NonTypicalPeriodResponse,
    ScheduleOverrideRequest,
    ScheduleResponse,
    ScheduleWindowResponse,
)
from glucotracker.application.categorization.window import (
    anchor_is_typical_morning,
    compute_user_anchors,
    recompute_and_persist_anchors,
    write_anchors_to_user,
)
from glucotracker.application.time import local_now
from glucotracker.domain.entities import AnchorBasis
from glucotracker.infra.db.models import DayAnchorHistory, NonTypicalPeriod, User

router = APIRouter(prefix="/me/schedule", tags=["schedule"])


@router.get(
    "",
    response_model=ScheduleResponse,
    operation_id="getMySchedule",
)
def get_my_schedule(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ScheduleResponse:
    """Return the user's current adaptive day rhythm."""
    user = _current_user_row(session, current_user.id)
    _refresh_learned_schedule_if_needed(session, user)
    return _schedule_response(session, user)


@router.put(
    "/override",
    response_model=ScheduleResponse,
    operation_id="putMyScheduleOverride",
)
def put_my_schedule_override(
    payload: ScheduleOverrideRequest,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ScheduleResponse:
    """Set a manual day-anchor override."""
    user = _current_user_row(session, current_user.id)
    user.day_anchor_user_override_minutes = payload.anchor_minutes
    write_anchors_to_user(
        session,
        current_user.id,
        payload.anchor_minutes,
        None,
        AnchorBasis.user_override,
    )
    session.commit()
    return _schedule_response(session, user)


@router.delete(
    "/override",
    response_model=ScheduleResponse,
    operation_id="deleteMyScheduleOverride",
)
def delete_my_schedule_override(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> ScheduleResponse:
    """Clear the manual day-anchor override and recompute the learned anchor."""
    user = _current_user_row(session, current_user.id)
    user.day_anchor_user_override_minutes = None
    weekday, weekend, basis = compute_user_anchors(session, current_user.id)
    write_anchors_to_user(session, current_user.id, weekday, weekend, basis)
    session.commit()
    return _schedule_response(session, user)


@router.post(
    "/non-typical-periods",
    response_model=NonTypicalPeriodResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createMyNonTypicalPeriod",
)
def create_my_non_typical_period(
    payload: NonTypicalPeriodCreate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> NonTypicalPeriod:
    """Add a date range excluded from automatic day-anchor learning."""
    if payload.start_date > payload.end_date:
        raise HTTPException(
            status_code=422,
            detail="start_date must be before end_date",
        )
    period = NonTypicalPeriod(
        user_id=current_user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        note=payload.note,
    )
    session.add(period)
    session.flush()
    recompute_and_persist_anchors(session, current_user.id)
    session.commit()
    session.refresh(period)
    return period


@router.delete(
    "/non-typical-periods/{period_id}",
    response_model=DeleteResponse,
    operation_id="deleteMyNonTypicalPeriod",
)
def delete_my_non_typical_period(
    period_id: UUID,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> DeleteResponse:
    """Remove one excluded schedule-learning period."""
    period = session.scalar(
        select(NonTypicalPeriod).where(
            NonTypicalPeriod.id == period_id,
            NonTypicalPeriod.user_id == current_user.id,
        )
    )
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")
    session.delete(period)
    session.flush()
    recompute_and_persist_anchors(session, current_user.id)
    session.commit()
    return DeleteResponse(deleted=True)


def _current_user_row(session: SessionDep, user_id: UUID) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _refresh_learned_schedule_if_needed(session: SessionDep, user: User) -> None:
    """Persist the current learned anchor when accepted meals have moved it."""
    if user.day_anchor_user_override_minutes is not None:
        return

    weekday, weekend, basis = compute_user_anchors(session, user.id)
    current = (
        user.day_anchor_weekday_minutes,
        user.day_anchor_weekend_minutes,
        user.day_anchor_basis,
    )
    computed = (weekday, weekend, basis.value)
    if current == computed:
        return

    write_anchors_to_user(session, user.id, weekday, weekend, basis)
    session.commit()
    session.refresh(user)


def _schedule_response(session: SessionDep, user: User) -> ScheduleResponse:
    effective = (
        user.day_anchor_user_override_minutes
        if user.day_anchor_user_override_minutes is not None
        else user.day_anchor_weekday_minutes
    )
    history = _history_response(session, user.id)
    periods = list(
        session.scalars(
            select(NonTypicalPeriod)
            .where(NonTypicalPeriod.user_id == user.id)
            .order_by(NonTypicalPeriod.start_date.desc())
        )
    )
    return ScheduleResponse(
        anchor_weekday_minutes=user.day_anchor_weekday_minutes,
        anchor_weekend_minutes=user.day_anchor_weekend_minutes,
        effective_anchor_minutes=effective,
        basis=user.day_anchor_basis,
        user_override_minutes=user.day_anchor_user_override_minutes,
        last_shift_at=user.day_anchor_last_shift_at,
        windows=_windows(effective),
        history=history,
        non_typical_periods=periods,
    )


def _history_response(
    session: SessionDep,
    user_id: UUID,
) -> list[DayAnchorHistoryResponse]:
    rows = list(
        session.scalars(
            select(DayAnchorHistory)
            .where(DayAnchorHistory.user_id == user_id)
            .order_by(DayAnchorHistory.effective_from.desc())
            .limit(12)
        )
    )
    rendered: list[DayAnchorHistoryResponse] = []
    previous_anchor: int | None = None
    for row in reversed(rows):
        current_anchor = row.anchor_weekday_minutes
        effective_to = row.effective_to or local_now().date()
        rendered.append(
            DayAnchorHistoryResponse(
                id=row.id,
                effective_from=row.effective_from,
                effective_to=row.effective_to,
                anchor_weekday_minutes=row.anchor_weekday_minutes,
                anchor_weekend_minutes=row.anchor_weekend_minutes,
                basis=row.basis,
                recorded_at=row.recorded_at,
                duration_days=(effective_to - row.effective_from).days + 1,
                shift_from_previous_minutes=(
                    None
                    if previous_anchor is None or current_anchor is None
                    else current_anchor - previous_anchor
                ),
            )
        )
        if current_anchor is not None:
            previous_anchor = current_anchor
    return list(reversed(rendered))


_WINDOW_LABELS_CLOCK: dict[str, str] = {
    "start": "1-й прием",
    "mid": "дневные",
    "late": "вечерние",
    "night_cap": "поздние ночные",
}
# Anchor-relative labels: truthful even when the learned day anchor is far
# from a conventional morning (e.g. first meal around midnight).
_WINDOW_LABELS_RELATIVE: dict[str, str] = {
    "start": "1-й прием",
    "mid": "середина дня",
    "late": "вторая половина",
    "night_cap": "конец дня",
}


def _windows(anchor_minutes: int | None) -> list[ScheduleWindowResponse]:
    labels = (
        _WINDOW_LABELS_CLOCK
        if anchor_is_typical_morning(anchor_minutes)
        else _WINDOW_LABELS_RELATIVE
    )
    if anchor_minutes is None:
        boundaries = [
            ("start", 5 * 60, 11 * 60),
            ("mid", 11 * 60, 16 * 60),
            ("late", 16 * 60, 22 * 60),
            ("night_cap", 22 * 60, 5 * 60),
        ]
    else:
        boundaries = [
            ("start", anchor_minutes, anchor_minutes + 3 * 60),
            ("mid", anchor_minutes + 3 * 60, anchor_minutes + 8 * 60),
            ("late", anchor_minutes + 8 * 60, anchor_minutes + 13 * 60),
            ("night_cap", anchor_minutes + 13 * 60, anchor_minutes + 24 * 60),
        ]
    return [
        ScheduleWindowResponse(
            key=key,
            label=labels[key],
            start_minute=start % (24 * 60),
            end_minute=end % (24 * 60),
        )
        for key, start, end in boundaries
    ]
