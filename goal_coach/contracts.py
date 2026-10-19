"""Goal Coach HTTP contract (goal-coach/v1) and NLU output schema."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

VERSION = "goal-coach/v1"

SlotName = Literal["name", "target_amount", "horizon", "flexibility", "opening_amount"]
Flexibility = Literal["fixed", "flexible"]
Status = Literal["draft", "need_info", "out_of_scope", "adjust"]
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
    "adjust_ready",
    "adjust_unclear",
]

MAX_AMOUNT_VND = 10**14
MAX_NAME_LEN = 80
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
# Set by the caller to link the turns of one conversation in traces; never affects the answer.
CONVERSATION_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------- request


class AnswerIn(_Strict):
    slot: SlotName
    value: str = Field(min_length=1, max_length=200)
    source: Literal["option", "text"]


class CurrentDraft(_Strict):
    """The draft the customer is looking at; its presence turns the request into an adjustment."""

    target_amount: int = Field(gt=0, le=MAX_AMOUNT_VND)
    opening_amount: int = Field(default=0, ge=0, le=MAX_AMOUNT_VND)
    months: int | None = Field(default=None, ge=1, le=600)


class ContextJar(_Strict):
    id: str = Field(min_length=1, max_length=40)
    label: str = Field(min_length=1, max_length=40)
    spendable: int = Field(ge=0, le=MAX_AMOUNT_VND)


class CoachContext(_Strict):
    """Aggregated figures computed by pfm's engine; used by code to shape chips, never shown to the LLM."""

    surplus: int | None = Field(default=None, ge=-MAX_AMOUNT_VND, le=MAX_AMOUNT_VND)  # average monthly surplus
    savings_balance: int | None = Field(default=None, ge=0, le=MAX_AMOUNT_VND)
    jars: list[ContextJar] = Field(default_factory=list, max_length=8)
    missing: list[str] = Field(default_factory=list, max_length=8)  # what pfm could not compute


class CoachRequest(_Strict):
    user_id: str = Field(min_length=1, max_length=64)
    request: str = Field(min_length=1, max_length=500)
    answers: list[AnswerIn] = Field(default_factory=list, max_length=6)
    current_draft: CurrentDraft | None = None
    context: CoachContext | None = None
    conversation_id: str | None = Field(default=None, pattern=CONVERSATION_ID_PATTERN)

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


class QuestionHint(_Strict):
    """Code-decided early warning; pfm owns the wording."""

    code: Literal["far_beyond", "no_surplus"]
    months: int | None = Field(default=None, ge=1, le=100_000)


class Question(_Strict):
    slot: SlotName
    code: MessageCode
    text: str = Field(min_length=1, max_length=200)
    options: list[QuestionOption] = Field(default_factory=list, max_length=6)
    allow_free_text: bool
    hint: QuestionHint | None = None


AdjustKind = Literal["extend_months", "reduce_amount_to", "raise_saving_to", "use_savings_amount"]


class Adjustment(_Strict):
    """A normalised edit of the current draft.

    extend_months: months to ADD to the deadline; reduce_amount_to: the NEW target (VND);
    raise_saving_to: the monthly saving (VND/month); use_savings_amount: VND taken from savings as opening money.
    """

    kind: AdjustKind
    value: int = Field(gt=0, le=MAX_AMOUNT_VND)
    evidence: str | None = Field(default=None, max_length=500)


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
    adjustment: Adjustment | None = None

    @model_validator(mode="after")
    def _status_shape(self) -> "CoachResponse":
        if self.status == "draft":
            ok = self.draft is not None and self.question is None
        elif self.status == "need_info":
            ok = self.draft is None and self.question is not None
        else:
            ok = self.draft is None and self.question is None
        if (self.status == "adjust") != (self.adjustment is not None):
            ok = False
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


# ---------------------------------------------------------------- narration (G14)

Verdict = Literal["feasible", "stretch", "not_feasible", "unknown"]
PlanId = Literal["keep_deadline", "extend_deadline", "reduce_amount"]
DialogueAction = Literal[
    "ask_purpose", "ask_amount", "ask_horizon", "ask_opening",
    "reflect", "present_plans", "confirm", "handle_objection",
]
NarrateSource = Literal["llm", "template"]
FallbackReason = Literal["flag_off", "model_error", "invalid"]


class HistoryTurn(_Strict):
    role: Literal["customer", "coach"]
    text: str = Field(min_length=1, max_length=280)


class NarrateFacts(_Strict):
    """What is already known, never numbers."""

    goal_name: str | None = Field(default=None, max_length=40)


class NarrateRequest(_Strict):
    """No numbers anywhere: verdict and plan ids come from the engine, numbers are filled in by pfm."""

    user_id: str = Field(min_length=1, max_length=64)
    mode: Literal["explain", "converse"]
    verdict: Verdict | None = None
    plan_ids: list[PlanId] = Field(default_factory=list, max_length=3)
    category_names: list[str] = Field(default_factory=list, max_length=5)
    data_quality: Literal["ok", "partial", "unknown"] = "ok"
    action: DialogueAction | None = None
    facts: NarrateFacts = Field(default_factory=NarrateFacts)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=6)
    conversation_id: str | None = Field(default=None, pattern=CONVERSATION_ID_PATTERN)

    @model_validator(mode="after")
    def _mode_shape(self) -> "NarrateRequest":
        if self.mode == "explain" and (self.verdict is None or not self.plan_ids):
            raise ValueError("explain needs verdict and plan_ids")
        if self.mode == "converse" and self.action is None:
            raise ValueError("converse needs action")
        return self


class NarrateBlock(_Strict):
    id: str = Field(min_length=1, max_length=40)
    kind: Literal["verdict", "plan", "say"]
    plan_id: PlanId | None = None
    text: str = Field(min_length=1, max_length=280)


class NarrateResponse(_Strict):
    version: Literal["goal-coach/v1"] = VERSION
    request_id: str = Field(min_length=1, max_length=40)
    source: NarrateSource
    fallback_reason: FallbackReason | None = None
    blocks: list[NarrateBlock]


class AdjustExtraction(_Strict):
    """What the LLM may return for an edit sentence: kind + the number as written + verbatim evidence."""

    is_adjustment: bool
    kind: AdjustKind | None = None
    value: int | None = None
    is_delta: bool = False  # "giảm 100 triệu" (by) vs "giảm xuống 500 triệu" (to)
    evidence: str = ""
