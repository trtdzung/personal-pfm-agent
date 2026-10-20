"""service.suggest: mock LLM — hợp lệ dùng lời model; lỗi/timeout/JSON hỏng → fallback + degraded."""

from __future__ import annotations

import asyncio
import time

from goal_suggest.contracts import GoalSuggestionsRequest
from goal_suggest.service import TIMEOUT_SECONDS, _LLMCard, assemble, suggest


def _req(**overrides) -> GoalSuggestionsRequest:
    base = {
        "user_id": "CIF_0001",
        "today": "2026-10-17",
        "customer": {
            "monthly_income": 20_000_000,
            "monthly_surplus": 3_000_000,
            "salary_day": 10,
            "risk_profile": "conservative",
        },
        "goals": [
            {
                "id": "g1",
                "name": "Du lịch",
                "status": "active",
                "phase": "build",
                "target_amount": 30_000_000,
                "target_date": "2027-06-01",
                "value": 5_000_000,
                "progress_pct": 16.7,
                "months_left": 8.0,
            }
        ],
        "signals": [
            {
                "id": "sig-1",
                "goal_id": "g1",
                "kind": "idle_cash",
                "rank": 2,
                "facts": {"main_casa_balance": 15_000_000, "salary_day": 10},
                "allowed_actions": [
                    {"id": "a0", "label": "Chuyển vào mục tiêu"},
                    {"id": "a1", "label": "Để sau"},
                ],
                "fallback": {
                    "title": "Lời viết sẵn",
                    "body": "Dùng số dư nhàn rỗi cho mục tiêu Du lịch.",
                },
            },
            {
                "id": "sig-0",
                "goal_id": None,
                "kind": "insufficient_data",
                "rank": 1,
                "facts": {"salary_day": 10},
                "allowed_actions": [{"id": "a0", "label": "Xem hướng dẫn"}],
                "fallback": {"title": "Fallback thiếu data", "body": "Cần thêm dữ liệu."},
            },
        ],
        "feedback": [],
    }
    base.update(overrides)
    return GoalSuggestionsRequest.model_validate(base)


def test_valid_llm_cards_used_degraded_false():
    def generate(req, signals):
        return [
            _LLMCard(
                signal_id="sig-0",
                title="Ngày lương 10",
                body="Bổ sung dữ liệu chi tiêu giúp gợi ý tốt hơn.",
                action_ids=["a0"],
            ),
            _LLMCard(
                signal_id="sig-1",
                title="Số dư 15000000",
                body="Chuyển một phần vào mục tiêu Du lịch.",
                action_ids=["a0"],
            ),
        ]

    out = asyncio.run(suggest(_req(), generate=generate))
    assert out.degraded is False
    assert [s.signal_id for s in out.suggestions] == ["sig-0", "sig-1"]  # theo rank
    assert out.suggestions[0].title == "Ngày lương 10"
    assert out.suggestions[1].title == "Số dư 15000000"
    assert out.suggestions[1].action_ids == ["a0"]


def test_llm_error_uses_all_fallbacks_degraded_true():
    def generate(req, signals):
        raise RuntimeError("provider down")

    out = asyncio.run(suggest(_req(), generate=generate))
    assert out.degraded is True
    assert len(out.suggestions) == 2
    assert out.suggestions[0].title == "Fallback thiếu data"
    assert out.suggestions[0].action_ids == ["a0"]
    assert out.suggestions[1].title == "Lời viết sẵn"
    assert out.suggestions[1].action_ids == ["a0", "a1"]  # D6: toàn bộ allowed_actions


def test_llm_timeout_uses_fallbacks_degraded_true():
    def generate(req, signals):
        time.sleep(0.2)
        return []

    out = asyncio.run(suggest(_req(), generate=generate, timeout=0.05))
    assert out.degraded is True
    assert out.suggestions[1].action_ids == ["a0", "a1"]


def test_broken_llm_payload_uses_fallbacks_degraded_true():
    def generate(req, signals):
        return [{"signal_id": "sig-1", "title": "thiếu body"}]  # không đủ schema _LLMCard

    out = asyncio.run(suggest(_req(), generate=generate))
    assert out.degraded is True
    assert all(s.title.startswith(("Fallback", "Lời")) for s in out.suggestions)


def test_guard_violation_uses_fallback_wording_and_all_actions():
    """Vi phạm guard → thẻ đó dùng fallback + toàn bộ action_ids (D6).

    Lưu ý: code hiện trả `degraded=false` khi chỉ một thẻ bị guard (khác bullet
    'degraded=true' trong prompt test). Không assert `degraded` ở đây — xem báo cáo.
    """

    def generate(req, signals):
        return [
            _LLMCard(
                signal_id="sig-0",
                title="Ngày lương 10",
                body="Ổn.",
                action_ids=["a0"],
            ),
            _LLMCard(
                signal_id="sig-1",
                title="Lãi 99%",  # số không có trong facts
                body="Cam kết sinh lời 99.",
                action_ids=["a0"],
            ),
        ]

    out = asyncio.run(suggest(_req(), generate=generate))
    by_id = {s.signal_id: s for s in out.suggestions}
    assert by_id["sig-0"].title == "Ngày lương 10"
    assert by_id["sig-1"].title == "Lời viết sẵn"
    assert by_id["sig-1"].body == "Dùng số dư nhàn rỗi cho mục tiêu Du lịch."
    assert by_id["sig-1"].action_ids == ["a0", "a1"]


def test_assemble_none_cards_sets_degraded():
    req = _req()
    out = assemble(sorted(req.signals, key=lambda s: s.rank), None)
    assert out.degraded is True
    assert out.suggestions[0].action_ids == ["a0"]


def test_default_timeout_is_20_seconds():
    assert TIMEOUT_SECONDS == 20.0


def test_empty_signals_returns_empty_not_degraded():
    def must_not_run(*_):
        raise RuntimeError("generate must not run when signals empty")

    out = asyncio.run(suggest(_req(signals=[]), generate=must_not_run))
    assert out.suggestions == []
    assert out.degraded is False
