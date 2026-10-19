"""POST /goal-suggestions contract: pfm sends the fired signals with their facts, the agent words one card per signal."""

from __future__ import annotations

from pydantic import BaseModel, Field

FactValue = int | float | str


# ---------------------------------------------------------------- request


class Customer(BaseModel):
    monthly_income: int
    monthly_surplus: int | None = None
    salary_day: int
    risk_profile: str


class GoalIn(BaseModel):
    id: str
    name: str
    status: str
    phase: str
    target_amount: int
    target_date: str
    value: int
    progress_pct: float
    months_left: float


class AllowedAction(BaseModel):
    id: str
    label: str


class Fallback(BaseModel):
    """Pre-written wording from pfm; used as is whenever the model's wording is missing or rejected."""

    title: str
    body: str


class Signal(BaseModel):
    id: str
    goal_id: str | None = None  # null = customer-wide signal (insufficient_data, priority_conflict...)
    kind: str
    rank: int
    facts: dict[str, FactValue] = Field(default_factory=dict)
    allowed_actions: list[AllowedAction] = Field(default_factory=list)
    fallback: Fallback


class FeedbackIn(BaseModel):
    kind: str
    goal_id: str
    ignored_count: int


class GoalSuggestionsRequest(BaseModel):
    user_id: str = Field(min_length=1)
    today: str
    customer: Customer
    goals: list[GoalIn] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    feedback: list[FeedbackIn] = Field(default_factory=list)


# ---------------------------------------------------------------- response


class SuggestionOut(BaseModel):
    signal_id: str
    title: str
    body: str
    action_ids: list[str]


class GoalSuggestionsResponse(BaseModel):
    suggestions: list[SuggestionOut]
    degraded: bool = False  # true = model failed or timed out, every card is the signal's fallback
