"""Strict, bounded HTTP contracts. The rule engine retains all execution rights."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Level = Literal["green", "yellow", "red"]
ScanLevel = Literal["none", "suspicious", "danger"]
Scenario = Literal["BT1", "BT2", "BT3", "BT4", "BT5", "BT6", "BT7", "DH1", "DH2", "DH3", "DH3-2", "DH4", "DH5", "DH6", "DH7", "DH8", "DH-T5", "SC1", "SC2", "SC3", "SC4"]
Proposal = Literal["callback", "emergency_lock", "case", "none"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TraceEntry(StrictModel):
    tool: str = Field(min_length=1, max_length=80)
    elapsed_ms: int = Field(ge=0)
    result: Literal["ok", "no_data", "error"]


class InterveneRequest(StrictModel):
    intervention_id: str = Field(min_length=1, max_length=80)
    cif: str = Field(min_length=1, max_length=64)


class InterveneResponse(StrictModel):
    level: Level
    scenario: Scenario
    message: str = Field(min_length=1, max_length=1200)
    question: str | None = Field(default=None, max_length=400)
    chips: list[str] = Field(default_factory=list, max_length=8)
    matched_playbook: str | None = Field(default=None, max_length=80)
    trace: list[TraceEntry] = Field(default_factory=list, max_length=30)


class DiagnoseRequest(StrictModel):
    intervention_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=1000)


class DiagnoseResponse(StrictModel):
    next_question: str | None = Field(default=None, max_length=400)
    conclusion: str | None = Field(default=None, max_length=800)
    proposals: list[Proposal] = Field(default_factory=list, max_length=3)
    trace: list[TraceEntry] = Field(default_factory=list, max_length=30)


class ScanRule(StrictModel):
    level: ScanLevel
    reasons: list[str] = Field(default_factory=list, max_length=10)


class ScanRequest(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    rule: ScanRule


class ScanResponse(StrictModel):
    level: ScanLevel
    reasons: list[str] = Field(min_length=1, max_length=10)
    manipulation_signs: list[str] = Field(default_factory=list, max_length=10)
    trace: list[TraceEntry] = Field(default_factory=list, max_length=30)


class CaseRequest(StrictModel):
    case_id: str = Field(min_length=1, max_length=80)
    answer: str | None = Field(default=None, max_length=1000)


class CaseDossier(StrictModel):
    time: str = Field(max_length=500)
    amount: str = Field(max_length=100)
    recipient: str = Field(max_length=500)
    channel: str = Field(max_length=500)
    image: str = Field(max_length=120)


class CaseResponse(StrictModel):
    next_question: str | None = Field(default=None, max_length=400)
    dossier: CaseDossier | None = None
    guidance: str | None = Field(default=None, max_length=1000)
    trace: list[TraceEntry] = Field(default_factory=list, max_length=30)


EducateTrigger = Literal[
    "new_customer", "device_login", "warned_account", "warned_scan",
    "hub_first", "balance_up", "after_incident",
    "BT1", "BT2", "BT3", "BT4", "BT7", "SC4",
]


class EducateRequest(StrictModel):
    trigger: EducateTrigger
    cif: str = Field(min_length=1, max_length=64)


class EducateResponse(StrictModel):
    summary: list[str] = Field(min_length=3, max_length=3)
    article_id: str = Field(min_length=1, max_length=80)
    chips: list[str] = Field(default_factory=list, max_length=8)
    trace: list[TraceEntry] = Field(default_factory=list, max_length=30)


class ChatSignalRequest(StrictModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatSignalResponse(StrictModel):
    scam_in_progress: bool
    playbook: str | None = Field(default=None, max_length=80)
    suggest_sc1: bool
    trace: list[TraceEntry] = Field(default_factory=list, max_length=30)
