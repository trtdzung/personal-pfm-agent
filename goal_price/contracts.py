"""POST /goal-price-estimates contract. Two calls share one endpoint: without `answers` the agent returns a form to tick,
with `answers` it researches the market and proposes a price."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

MAX_QUESTIONS = 6
MAX_CHOSEN = 8


class PriceEstimateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    # pfm goal template id: car, house, travel, education, wedding, retirement, emergency, other.
    template: str = Field(min_length=1, max_length=32)
    description: str | None = Field(default=None, max_length=200)
    # Question id -> options the customer ticked. Present: research the price. Absent: return the form.
    answers: dict[str, list[str]] | None = None
    # "Chạy lại": do not reuse earlier search results.
    refresh: bool = False

    @field_validator("answers")
    @classmethod
    def _sane_answers(cls, value: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        if value is None:
            return None
        if len(value) > MAX_QUESTIONS:
            raise ValueError("too many answers")
        for qid, chosen in value.items():
            if len(qid) > 32 or len(chosen) > MAX_CHOSEN or any(not isinstance(c, str) or len(c) > 80 for c in chosen):
                raise ValueError("answer too long")
        return value


class Question(BaseModel):
    id: str
    title: str
    options: list[str]
    # True: the customer may tick several options.
    multi: bool = False


class Source(BaseModel):
    title: str
    url: str


class Estimate(BaseModel):
    # Proposed goal amount in VND (the middle of what the sources say), and the range around it.
    amount: int
    low: int
    high: int
    summary: str
    sources: list[Source]


class PriceEstimateResponse(BaseModel):
    questions: list[Question] | None = None
    estimate: Estimate | None = None
    # Why there is nothing to show (not enough prices found, search or model down).
    reason: str | None = None
    degraded: bool = False
