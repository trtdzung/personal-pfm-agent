"""POST /goal-suggestions contract: the caller names a customer and a goal, the agent reads the data itself."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class GoalSuggestionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    goal_id: str | None = Field(default=None, max_length=64)
    goal_name: str | None = Field(default=None, max_length=120)
    # `fingerprint` of the last card the caller holds; when nothing worth saying has changed the model is not called.
    previous_fingerprint: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _one_goal(self) -> "GoalSuggestionRequest":
        if not (self.goal_id or "").strip() and not (self.goal_name or "").strip():
            raise ValueError("goal_id or goal_name is required")
        return self


class Insight(BaseModel):
    """What the goal screen shows: the top box (`observation`) and the coloured box (`suggestion`), plus the `question` that "Chi tiết" sends to the chat."""

    goal_id: str
    goal_name: str
    observation: str
    suggestion: str
    # What the customer would ask M-You to learn more; the "Chi tiết" button sends it to the chat as their message.
    question: str


class GoalSuggestionResponse(BaseModel):
    insight: Insight | None
    # Id of what the card is about (send it back as `previous_fingerprint`). `unchanged`: it matches, so `insight` is null
    # on purpose and the caller keeps its stored card.
    fingerprint: str | None = None
    unchanged: bool = False
    # Why there is no insight: the model failed, or its wording broke a rule.
    reason: str | None = None
    degraded: bool = False
