import asyncio
import copy
import json
from pathlib import Path

import pytest

from goal_suggest import digest, service
from goal_suggest.contracts import GoalSuggestionRequest

FIXTURE = json.loads((Path(__file__).parent / "data" / "goals_v2_world.json").read_text(encoding="utf-8"))
REQ = GoalSuggestionRequest(user_id="CIF_0001", goal_id="goal-1")


def collect(_cif):
    return {"snapshot": copy.deepcopy(FIXTURE), "jars": None, "accounts": None, "transactions": None, "categories": None, "preferences": None}


GOOD = {"observation": "Tài khoản mục tiêu có 5.000.000 VND nằm yên với lãi suất 0%/năm.",
        "suggestion": "Bạn có thể gửi tiết kiệm trực tuyến MSB 12 tháng, lãi 6,8%/năm, vẫn trước hạn mục tiêu.",
        "question": "Mình nên gửi tiết kiệm MSB kỳ hạn 12 tháng như thế nào để vẫn kịp hạn mục tiêu?"}


def run(generate, req=REQ):
    return asyncio.run(service.suggest(req, generate=generate, collect=collect))


def test_a_valid_wording_becomes_the_insight_of_the_requested_goal():
    seen = []

    def generate(messages):
        seen.append(messages)
        return GOOD

    resp = run(generate)
    assert resp.degraded is False and resp.reason is None
    assert resp.insight.goal_id == "goal-1" and resp.insight.goal_name == "Mua xe"
    assert resp.insight.observation == GOOD["observation"] and resp.insight.suggestion == GOOD["suggestion"]
    assert set(resp.insight.model_dump()) == {"goal_id", "goal_name", "observation", "suggestion", "question"}
    system, human = seen[0][0][1], seen[0][1][1]
    assert "M-You gợi ý theo đuổi mục tiêu" in system
    assert human.startswith("<du_lieu_khach_hang>") and "== MỤC TIÊU ĐANG XÉT ==" in human


def test_a_wording_with_an_invented_number_is_retried_once_with_the_reason():
    calls = []

    def generate(messages):
        calls.append(messages)
        return GOOD if len(calls) == 2 else {**GOOD, "suggestion": "Bạn nên gửi 999.000 VND vào quỹ."}

    resp = run(generate)
    assert resp.insight is not None and len(calls) == 2
    assert "number_not_in_data:999000" in calls[1][-1][1]


def test_too_long_wording_is_rejected_and_the_retry_names_the_limits():
    calls = []

    def generate(messages):
        calls.append(messages)
        return GOOD if len(calls) == 2 else {**GOOD, "observation": "Tài khoản mục tiêu " + "rất " * 100}

    assert run(generate).insight is not None
    assert "observation_too_long" in calls[1][-1][1] and "320" in calls[1][-1][1] and "140" in calls[1][-1][1]


def test_two_rejected_wordings_give_no_insight_and_say_why():
    resp = run(lambda m: {**GOOD, "suggestion": "Chắc chắn sinh lời."})
    assert resp.insight is None and resp.degraded is True and resp.reason == "promise"


def test_model_errors_never_raise():
    def boom(messages):
        raise RuntimeError("down")

    resp = run(boom)
    assert resp.insight is None and resp.degraded is True and resp.reason.startswith("đầu ra không đúng khuôn")
    assert run(lambda m: {"nonsense": 1}).insight is None


def test_wording_is_cleaned_of_extra_whitespace():
    resp = run(lambda m: {**GOOD, "observation": "  Tài khoản mục tiêu có 5.000.000 VND   nằm yên. "})
    assert resp.insight.observation == "Tài khoản mục tiêu có 5.000.000 VND nằm yên."


def test_an_unknown_goal_raises_instead_of_inventing_one():
    with pytest.raises(digest.GoalNotFound):
        run(lambda m: GOOD, GoalSuggestionRequest(user_id="CIF_0001", goal_name="Du lịch"))


def test_the_request_needs_a_goal():
    with pytest.raises(ValueError):
        GoalSuggestionRequest(user_id="CIF_0001")


def test_unwrap_reads_a_tool_call_or_a_json_answer_in_plain_text():
    class Msg:
        def __init__(self, content="", tool_calls=()):
            self.content, self.tool_calls = content, list(tool_calls)

    parsed = service.LLMOut.model_validate(GOOD)
    assert service._unwrap({"parsed": parsed, "raw": Msg()}) is parsed
    assert service._unwrap({"parsed": None, "raw": Msg(tool_calls=[{"name": "LLMOut", "args": GOOD}])}) == GOOD
    fenced = "```json\n" + json.dumps(GOOD, ensure_ascii=False) + "\n```"
    assert service._unwrap({"parsed": None, "raw": Msg(content=fenced)}) == GOOD
    with pytest.raises(ValueError):
        service._unwrap({"parsed": None, "raw": Msg(content="không có gì"), "parsing_error": None})


def test_a_matching_previous_fingerprint_skips_the_model():
    first = run(lambda m: GOOD)
    assert first.fingerprint and first.unchanged is False

    def never(_messages):
        raise AssertionError("model must not be called")

    again = run(never, GoalSuggestionRequest(user_id="CIF_0001", goal_id="goal-1", previous_fingerprint=first.fingerprint))
    assert again.insight is None and again.unchanged is True and again.degraded is False and again.fingerprint == first.fingerprint


def test_a_different_previous_fingerprint_regenerates_and_reports_the_new_one():
    resp = run(lambda m: GOOD, GoalSuggestionRequest(user_id="CIF_0001", goal_id="goal-1", previous_fingerprint="old"))
    assert resp.insight is not None and resp.unchanged is False and resp.fingerprint != "old"


def test_the_fingerprint_follows_the_plan_not_the_wording_of_a_drifting_percentage():
    world = copy.deepcopy(FIXTURE)
    base = digest.build_full({"snapshot": FIXTURE, "jars": None, "accounts": None, "transactions": None, "categories": None, "preferences": None}, "goal-1", None)[2]
    world["world"]["goals"][0]["targetAmount"] += 1_000_000
    changed = digest.build_full({"snapshot": world, "jars": None, "accounts": None, "transactions": None, "categories": None, "preferences": None}, "goal-1", None)[2]
    assert base != changed


def test_on_track_asks_the_model_with_the_on_track_note_and_accepts_the_fixed_wording():
    def on_track(_cif):
        raw = collect(_cif)
        goal = raw["snapshot"]["world"]["goals"][0]
        goal["targetDate"] = "2026-10-01"  # no deposit term fits
        goal["standingOrder"]["amount"] = 600_000_000
        return raw

    seen = []

    def generate(messages):
        seen.append(messages)
        return {"observation": "Đang đi đúng hướng.", "suggestion": "Hãy tiếp tục phát huy để đạt được mục tiêu.", "question": "Mình đang đi đúng hướng, có cách nào để đạt mục tiêu sớm hơn không?"}

    resp = asyncio.run(service.suggest(REQ, generate=generate, collect=on_track))
    assert digest.ON_TRACK_NOTE in seen[0][1][1] and "Đang đi đúng hướng." in seen[0][0][1]
    assert resp.insight.observation == "Đang đi đúng hướng." and resp.degraded is False


def test_a_question_that_is_not_a_question_is_retried_and_named():
    calls = []

    def generate(messages):
        calls.append(messages)
        return GOOD if len(calls) == 2 else {**GOOD, "question": "Hãy giải thích thêm giúp mình."}

    resp = run(generate)
    assert resp.insight.question == GOOD["question"] and "question_not_a_question" in calls[1][-1][1] and "200" in calls[1][-1][1]
