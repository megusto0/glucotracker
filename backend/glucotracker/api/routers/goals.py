"""User goals endpoints."""

from fastapi import APIRouter
from sqlalchemy import select

from glucotracker.api.dependencies import CurrentUserDep, SessionDep
from glucotracker.api.schemas import UserGoalsResponse, UserGoalsUpdate
from glucotracker.infra.db.models import User

router = APIRouter(prefix="/me", tags=["users"])


@router.get(
    "/goals",
    response_model=UserGoalsResponse,
    operation_id="getMyGoals",
)
def get_my_goals(
    session: SessionDep,
    current_user: CurrentUserDep,
) -> UserGoalsResponse:
    user = session.scalar(select(User).where(User.id == current_user.id))
    return UserGoalsResponse(
        kcal_goal_per_day=user.kcal_goal_per_day,
        protein_goal_g_per_day=user.protein_goal_g_per_day,
        carb_goal_g_per_day=user.carb_goal_g_per_day,
        fat_goal_g_per_day=user.fat_goal_g_per_day,
        goals_setup_completed=user.goals_setup_completed,
    )


@router.put(
    "/goals",
    response_model=UserGoalsResponse,
    operation_id="updateMyGoals",
)
def update_my_goals(
    body: UserGoalsUpdate,
    session: SessionDep,
    current_user: CurrentUserDep,
) -> UserGoalsResponse:
    user = session.scalar(select(User).where(User.id == current_user.id))
    if body.kcal_goal_per_day is not None:
        user.kcal_goal_per_day = body.kcal_goal_per_day
    if body.protein_goal_g_per_day is not None:
        user.protein_goal_g_per_day = body.protein_goal_g_per_day
    if body.carb_goal_g_per_day is not None:
        user.carb_goal_g_per_day = body.carb_goal_g_per_day
    if body.fat_goal_g_per_day is not None:
        user.fat_goal_g_per_day = body.fat_goal_g_per_day
    if body.goals_setup_completed is not None:
        user.goals_setup_completed = body.goals_setup_completed
    session.flush()
    return UserGoalsResponse(
        kcal_goal_per_day=user.kcal_goal_per_day,
        protein_goal_g_per_day=user.protein_goal_g_per_day,
        carb_goal_g_per_day=user.carb_goal_g_per_day,
        fat_goal_g_per_day=user.fat_goal_g_per_day,
        goals_setup_completed=user.goals_setup_completed,
    )
