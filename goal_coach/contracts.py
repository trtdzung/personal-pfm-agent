"""Goal Coach HTTP contract (goal-coach/v1) and NLU output schema."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

VERSION = "goal-coach/v1"

SlotName = Literal["name", "target_amount", "horizon", "flexibility", "opening_amount"]
Flexibility = Literal["fixed", "flexible"]
Status = Literal["draft", "need_info", "out_of_scope"]
MessageCode = Literal[
    "draft_ready",
    "need_name",
    "need_amount",
    "need_horizon",
    "need_flexibility",
    "need_opening",
    "not_a_goal",
    "amount_unclear",
    "horizon_unclear",
]

MAX_AMOUNT_VND = 10**14
MAX_NAME_LEN = 80
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- request


class AnswerIn(_Strict):
    slot: SlotName
    value: str = Field(min_length=1, max_length=200)
    source: Literal["option", "text"]


class CoachRequest(_Strict):
    user_id: str = Field(min_length=1, max_length=64)
    request: str = Field(min_length=1, max_length=500)
    answers: list[AnswerIn] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _trim_request(self) -> "CoachRequest":
        self.request = self.request.strip()
        if not self.request:
            raise ValueError("request must not be blank")
        return self


# ---------------------------------------------------------------- horizon


class Horizon(_Strict):
    """Exactly one of `months` (1-600) or `target_month` (YYYY-MM)."""

    months: int | None = Field(default=None, ge=1, le=600)
    target_month: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "Horizon":
        if (self.months is None) == (self.target_month is None):
            raise ValueError("horizon needs exactly one of months / target_month")
        if self.target_month is not None and not _MONTH_RE.match(self.target_month):
            raise ValueError("target_month must be YYYY-MM")
        return self

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, int | str]:
        return self.to_wire()

    def to_wire(self) -> dict[str, int | str]:
        """Compact JSON form: only the field that is set."""
        if self.months is not None:
            return {"months": self.months}
        assert self.target_month is not None
        return {"target_month": self.target_month}


# ---------------------------------------------------------------- slots

SlotSource = Literal["request", "answer"]


class NameSlot(_Strict):
    value: str = Field(min_length=1, max_length=MAX_NAME_LEN)
    source: SlotSource
    evidence: str | None = Field(default=None, max_length=500)


class AmountSlot(_Strict):
    value: int = Field(ge=0, le=MAX_AMOUNT_VND)
    source: SlotSource
    evidence: str | None = Field(default=None, max_length=500)


class HorizonSlot(_Strict):
    value: Horizon
    source: SlotSource
    evidence: str | None = Field(default=None, max_length=500)


class FlexibilitySlot(_Strict):
    value: Flexibility
    source: SlotSource
    evidence: str | None = Field(default=None, max_length=500)


class Slots(_Strict):
    name: NameSlot | None = None
    target_amount: AmountSlot | None = None
    horizon: HorizonSlot | None = None
    flexibility: FlexibilitySlot | None = None
    opening_amount: AmountSlot | None = None


# ---------------------------------------------------------------- question / draft


class QuestionOption(_Strict):
    label: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=60)


class Question(_Strict):
    slot: SlotName
    code: MessageCode
    text: str = Field(min_length=1, max_length=200)
    options: list[QuestionOption] = Field(default_factory=list, max_length=6)
    allow_free_text: bool


class Draft(_Strict):
    name: str = Field(min_length=1, max_length=MAX_NAME_LEN)
    target_amount: int = Field(gt=0, le=MAX_AMOUNT_VND)
    horizon: Horizon
    flexibility: Flexibility
    opening_amount: int = Field(ge=0, le=MAX_AMOUNT_VND)


# ---------------------------------------------------------------- response


class CoachResponse(_Strict):
    version: Literal["goal-coach/v1"] = VERSION
    request_id: str = Field(min_length=1, max_length=40)
    status: Status
    slots: Slots
    draft: Draft | None = None
    question: Question | None = None
    message_code: MessageCode

    @model_validator(mode="after")
    def _status_shape(self) -> "CoachResponse":
        if self.status == "draft":
            ok = self.draft is not None and self.question is None
        elif self.status == "need_info":
            ok = self.draft is None and self.question is not None
        else:
            ok = self.draft is None and self.question is None
        if not ok:
            raise ValueError(f"draft/question do not match status={self.status}")
        return self


class ErrorBody(_Strict):
    error: Literal["unauthorized", "invalid_request", "model_unavailable"]
    detail: list[dict[str, object]] | None = None
    request_id: str | None = None


# ---------------------------------------------------------------- NLU output


class ExtractedName(_Strict):
    value: str
    evidence: str


class ExtractedAmount(_Strict):
    value_vnd: int
    evidence: str


class ExtractedHorizon(_Strict):
    months: int | None = None
    target_month: str | None = None
    evidence: str


class ExtractedFlexibility(_Strict):
    value: Flexibility
    evidence: str


class GoalExtraction(_Strict):
    """What the LLM may return: slots + verbatim evidence, nothing else."""

    is_savings_goal: bool
    name: ExtractedName | None = None
    target_amount: ExtractedAmount | None = None
    horizon: ExtractedHorizon | None = None
    flexibility: ExtractedFlexibility | None = None
    opening_amount: ExtractedAmount | None = None
