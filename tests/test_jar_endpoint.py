"""POST /jar-rebalance: one endpoint, two modes, no chat.

The model only proposes and writes the sentence for the customer. Everything true -- the shortfall, the pool,
whether a proposal is allowed -- comes from code, against the jar-summary the server itself read (jar_checks.py)."""

import os
from typing import ClassVar

os.environ["SERVER_API_KEY"] = "test-key-for-pytest"
os.environ["MEMORY_ID"] = "test-memory-id-for-pytest"
os.environ["USER_PREFERENCE_STRATEGY_ID"] = "test-strategy-id-for-pytest"
os.environ["AI_PLATFORM_API_KEY"] = "test-ai-platform-key-for-pytest"

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

import jar_endpoint  # noqa: E402
import server  # noqa: E402

HEADERS = {"X-API-Key": "test-key-for-pytest"}


def _jar(id, label, limit, spent, remaining):
    return {"id": id, "label": label, "categoryIds": [], "budgetLimit": limit, "spent": spent, "remaining": remaining,
            "spendable": None if remaining is None else max(0, remaining), "overLimit": limit is not None and spent > limit}


def _summary(unallocated=13044000, jars=None):
    return {"month": "2026-09", "casaBalance": 18000000, "unallocated": unallocated, "allocationHeadroom": 1000000,
            "jars": jars if jars is not None else [
                _jar("food", "Ăn uống", 4000000, 2187000, 1813000),
                _jar("lifestyle", "Hưởng thụ", 2500000, 1204000, 1296000),
                _jar("move", "Di chuyển", 1000000, 204000, 796000),
                _jar("savings", "Tiết kiệm", None, 0, None),
            ]}


class _FakeModel(GenericFakeChatModel):
    """Plays back scripted replies and records every conversation it was shown."""

    seen: ClassVar[list] = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        type(self).seen.append(messages)
        return super()._generate(messages, *args, **kwargs)


def _reply(tool_name: str, **args) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": tool_name, "args": args, "id": "call"}])


def _cover_reply(moves, answer="Hũ Ăn uống thiếu 14.187.000đ.", reason="Lấy từ tiền chưa phân bổ và hũ Hưởng thụ"):
    return _reply("CoverDraft", answer=answer, moves=moves, reason=reason)


GOOD_MOVES = [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "lifestyle", "amount": 1143000}]


@pytest.fixture
def api(monkeypatch):
    """Returns `call(replies, summary=..., **body)`; the model plays `replies` in order and records what it saw."""
    state = {"model_calls": 0}

    def _install(replies, summary=None):
        _FakeModel.seen = []
        script = iter(replies)
        monkeypatch.setattr(jar_endpoint, "fetch_jar_summary", lambda customer_id, month="": summary or _summary())
        monkeypatch.setattr(jar_endpoint, "_model", lambda: _FakeModel(messages=script))
        return TestClient(server.app)

    def call(replies, summary=None, body=None, headers=HEADERS):
        client = _install(replies, summary)
        payload = {"user_id": "CIF_0001", "mode": "cover", "target_jar_id": "food", "spend_amount": 16000000}
        payload.update(body or {})
        return client.post("/jar-rebalance", json=payload, headers=headers)

    call.model_calls = lambda: len(_FakeModel.seen)
    call.state = state
    return call


# --- wiring, auth, request shape ----------------------------------------------------------------------------


def test_the_endpoint_is_part_of_the_same_server_and_chat_is_untouched():
    client = TestClient(server.app)
    # 401 (not 404) without a key: the route exists, and it is guarded like /chat
    valid = {"user_id": "CIF_0001", "mode": "distribute", "amount": 1000}
    assert client.post("/jar-rebalance", json=valid).status_code == 401
    assert client.post("/chat", json={"message": "hi", "user_id": "CIF_0001"}).status_code == 401


def test_it_needs_the_same_api_key_as_chat(api):
    assert api([], headers={}).status_code == 401
    assert api([], headers={"X-API-Key": "wrong"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"mode": "sideways"},
        {"target_jar_id": None},  # cover needs a target
        {"spend_amount": 0},
        {"spend_amount": -1},
        {"mode": "distribute", "target_jar_id": "food", "spend_amount": None},  # distribute has no target
        {"mode": "distribute", "target_jar_id": None, "spend_amount": 5},  # ... and no planned spend
        {"mode": "distribute", "target_jar_id": None, "spend_amount": None, "amount": 0},
        {"mode": "distribute", "target_jar_id": None, "spend_amount": None, "amount": None},  # distribute needs the amount
        {"mode": "cover", "amount": 5},  # `amount` is for distribute only
    ],
)
def test_a_malformed_request_is_rejected_before_anything_is_read(api, body):
    assert api([], body=body).status_code == 422
    assert api.model_calls() == 0


def test_the_customer_id_comes_from_the_request_and_is_what_pfm_is_asked_for(api, monkeypatch):
    asked = []
    monkeypatch.setattr(jar_endpoint, "fetch_jar_summary", lambda customer_id, month="": asked.append(customer_id) or _summary())
    script = iter([_cover_reply(GOOD_MOVES)])
    monkeypatch.setattr(jar_endpoint, "_model", lambda: _FakeModel(messages=script))
    TestClient(server.app).post("/jar-rebalance", json={"user_id": "CIF_0003", "mode": "cover", "target_jar_id": "food", "spend_amount": 16000000}, headers=HEADERS)
    assert asked == ["CIF_0003"]


def test_a_pfm_failure_is_a_502_not_an_empty_answer(monkeypatch):
    def _fail(customer_id, month=""):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(jar_endpoint, "fetch_jar_summary", _fail)
    response = TestClient(server.app).post("/jar-rebalance", json={"user_id": "CIF_0001", "mode": "cover", "target_jar_id": "food", "spend_amount": 1}, headers=HEADERS)
    assert response.status_code == 502


# --- cover -----------------------------------------------------------------------------------------------------


def test_cover_returns_a_rebalance_jars_ui_whose_shortfall_was_computed_by_the_server(api):
    response = api([_cover_reply(GOOD_MOVES)])
    assert response.status_code == 200
    body = response.json()
    assert body["ui"] == {
        "type": "rebalance_jars", "target_jar_id": "food", "shortfall": 14187000,  # 16.000.000 - 1.813.000, not the model's
        "moves": GOOD_MOVES, "reason": "Lấy từ tiền chưa phân bổ và hũ Hưởng thụ",
    }
    assert body["answer"] == "Hũ Ăn uống thiếu 14.187.000đ."
    assert api.model_calls() == 1


def test_the_model_is_given_the_computed_shortfall_and_the_jars_it_must_use(api):
    api([_cover_reply(GOOD_MOVES)])
    shown = " ".join(str(m.content) for m in _FakeModel.seen[0])
    assert "14187000" in shown or "14.187.000" in shown
    assert "unallocated: 13.044.000đ" in shown and "id: lifestyle" in shown


def test_a_wrong_order_gets_one_retry_that_states_the_correct_plan(api):
    wrong = _cover_reply([{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "move", "amount": 796000}, {"from_jar_id": "lifestyle", "amount": 347000}])
    response = api([wrong, _cover_reply(GOOD_MOVES)])
    assert response.json()["ui"]["moves"] == GOOD_MOVES
    assert api.model_calls() == 2
    feedback = " ".join(str(m.content) for m in _FakeModel.seen[1])
    assert "lifestyle 1143000" in feedback  # the retry tells the model the right answer


def test_an_order_that_stays_wrong_is_still_returned_because_the_order_is_only_a_preference(api):
    wrong = [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "move", "amount": 796000}, {"from_jar_id": "lifestyle", "amount": 347000}]
    response = api([_cover_reply(wrong), _cover_reply(wrong)])
    assert response.json()["ui"]["moves"] == wrong  # every hard rule holds, pfm accepts it
    assert api.model_calls() == 2


def test_a_source_that_gives_more_than_it_has_is_never_returned(api):
    too_much = [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "move", "amount": 1143000}]  # move has 796.000
    response = api([_cover_reply(too_much), _cover_reply(too_much)])
    body = response.json()
    assert body["ui"] is None
    assert "thử lại" in body["answer"] and "1.143.000" not in body["answer"]  # a generic sentence, not the model's claim
    assert api.model_calls() == 2


def test_a_hard_error_on_the_first_try_can_be_fixed_by_the_retry(api):
    invented = _cover_reply([{"from_jar_id": "du-phong", "amount": 14187000}])
    assert api([invented, _cover_reply(GOOD_MOVES)]).json()["ui"]["moves"] == GOOD_MOVES


def test_a_jar_that_already_has_enough_needs_no_model_call(api):
    response = api([], body={"spend_amount": 1000000})
    body = response.json()
    assert body["ui"] is None and "đủ" in body["answer"] and "Ăn uống" in body["answer"]
    assert api.model_calls() == 0


def test_sources_that_cannot_cover_the_shortfall_are_reported_without_a_model_call(api):
    response = api([], summary=_summary(unallocated=0), body={"spend_amount": 16000000})
    body = response.json()
    assert body["ui"] is None and "chưa đủ" in body["answer"]
    assert "14.187.000đ" in body["answer"] and "2.092.000đ" in body["answer"]  # what is missing and what exists
    assert api.model_calls() == 0


def test_a_jar_that_needs_covering_is_covered_without_a_planned_spend(api):
    summary = _summary(unallocated=0, jars=[_jar("food", "Ăn uống", 4000000, 4400000, -400000), _jar("move", "Di chuyển", 1000000, 204000, 796000)])
    reply = _cover_reply([{"from_jar_id": "move", "amount": 400000}])
    body = api([reply], summary=summary, body={"spend_amount": None}).json()
    assert body["ui"]["shortfall"] == 400000 and body["ui"]["moves"] == [{"from_jar_id": "move", "amount": 400000}]


def test_an_unknown_target_is_a_404_and_a_jar_without_a_limit_gets_an_explanation(api):
    assert api([], body={"target_jar_id": "khong-co"}).status_code == 404
    body = api([], body={"target_jar_id": "savings"}).json()
    assert body["ui"] is None and "hạn mức" in body["answer"]
    assert api.model_calls() == 0


def test_foreign_script_glitches_are_stripped_from_the_answer(api):
    body = api([_cover_reply(GOOD_MOVES, answer="Hũ Ăn uống thiếu 14.187.000đ，远远 cần bù.")]).json()
    assert "远" not in body["answer"] and "cần bù" in body["answer"]


# --- distribute ---------------------------------------------------------------------------------------------------

DIST = {"mode": "distribute", "target_jar_id": None, "spend_amount": None, "amount": 1000000}


def _dist_reply(allocations, answer="Mình đề xuất chia 1.000.000đ vào các hũ.", reason="Ưu tiên hũ chi nhiều"):
    return _reply("DistributeDraft", answer=answer, allocations=allocations, reason=reason)


def test_distribute_returns_a_distribute_amount_ui(api):
    allocations = [{"to_jar_id": "food", "amount": 600000}, {"to_jar_id": "move", "amount": 400000}]
    body = api([_dist_reply(allocations)], body=DIST).json()
    assert body["ui"] == {"type": "distribute_amount", "allocations": allocations, "reason": "Ưu tiên hũ chi nhiều"}


def test_distribute_shows_the_model_the_amount_the_receiving_jars_and_the_customers_spending(api):
    api([_dist_reply([{"to_jar_id": "food", "amount": 1000000}])], body=DIST)
    shown = " ".join(str(m.content) for m in _FakeModel.seen[0])
    assert "1000000" in shown or "1.000.000" in shown
    assert "id: food" in shown and "id: savings" not in shown  # a jar without a limit cannot receive, so it is not offered
    assert "monthly_spending_summary" in shown  # the seeded customer data: what to base the split on


def test_the_amount_to_distribute_is_the_customers_own_and_not_limited_by_the_unallocated_money(api):
    summary = _summary(unallocated=0)  # nothing unallocated at all
    allocations = [{"to_jar_id": "food", "amount": 500000}, {"to_jar_id": "lifestyle", "amount": 200000}]
    body = api([_dist_reply(allocations)], summary=summary, body={**DIST, "amount": 700000}).json()
    assert body["ui"]["allocations"] == allocations
    assert api.model_calls() == 1


def test_giving_out_more_than_the_amount_is_never_returned(api):
    too_much = _dist_reply([{"to_jar_id": "food", "amount": 500000}])
    assert api([too_much, too_much], body={**DIST, "amount": 400000}).json()["ui"] is None


def test_distribute_that_leaves_money_over_is_retried_then_accepted(api):
    partial = _dist_reply([{"to_jar_id": "food", "amount": 300000}])
    body = api([partial, partial], body=DIST).json()
    assert body["ui"]["allocations"] == [{"to_jar_id": "food", "amount": 300000}]  # only a soft error: nothing forbidden
    assert api.model_calls() == 2


def test_distribute_to_a_jar_that_does_not_exist_is_never_returned(api):
    bad = _dist_reply([{"to_jar_id": "du-lich", "amount": 1000000}])
    assert api([bad, bad], body=DIST).json()["ui"] is None


def test_distribute_without_an_amount_is_rejected(api):
    assert api([], body={**DIST, "amount": None}).status_code == 422
    assert api.model_calls() == 0


def test_distribute_with_no_jar_that_can_receive_needs_no_model_call(api):
    only_unlimited = _summary(jars=[_jar("savings", "Tiết kiệm", None, 0, None)])
    body = api([], summary=only_unlimited, body=DIST).json()
    assert body["ui"] is None and "hạn mức" in body["answer"]
    assert api.model_calls() == 0


# --- what the customer reads ----------------------------------------------------------------------------------


def test_internal_words_in_the_reason_get_one_retry_that_names_them(api):
    jargon = _cover_reply(GOOD_MOVES, reason="Tổng amount đúng bằng shortfall; hũ có spendable lớn nhất.")
    body = api([jargon, _cover_reply(GOOD_MOVES)]).json()
    assert body["ui"]["reason"] == "Lấy từ tiền chưa phân bổ và hũ Hưởng thụ"
    feedback = " ".join(str(m.content) for m in _FakeModel.seen[1])
    assert "shortfall" in feedback and "spendable" in feedback


def test_jargon_that_stays_is_still_returned_because_the_proposal_itself_is_right(api):
    jargon = _cover_reply(GOOD_MOVES, reason="Hũ có spendable lớn nhất.")
    body = api([jargon, jargon]).json()
    assert body["ui"]["moves"] == GOOD_MOVES  # a wording slip must not throw away a correct proposal


def test_the_sentences_of_the_answer_are_separated_by_a_blank_line(api):
    body = api([_cover_reply(GOOD_MOVES, answer="Câu một.\nCâu hai.\n\n\nCâu ba.")]).json()
    assert body["answer"] == "Câu một.\n\nCâu hai.\n\nCâu ba."


# --- a failing retry must not throw away an acceptable first proposal ----------------------------------------------


def test_a_retry_that_fails_keeps_the_acceptable_first_proposal(api):
    jargon = _cover_reply(GOOD_MOVES, reason="Hũ có spendable lớn nhất.")
    body = api([jargon]).json()  # the script ends: the retry call fails (as a dropped connection would)
    assert body["ui"]["moves"] == GOOD_MOVES
    assert api.model_calls() == 2


def test_a_first_try_with_a_broken_rule_and_a_failing_retry_returns_nothing(api):
    invented = _cover_reply([{"from_jar_id": "du-phong", "amount": 14187000}])
    body = api([invented]).json()
    assert body["ui"] is None and "thử lại" in body["answer"]


# --- an unreachable model is an infrastructure error, not "no proposal" --------------------------------------------


def test_when_every_model_call_fails_the_answer_is_a_503(api):
    response = api([])  # the script is empty: every call fails
    assert response.status_code == 503
    assert api.model_calls() == 2  # the first try and the retry


def test_the_model_used_by_this_endpoint_has_a_short_timeout_and_no_hidden_retries(monkeypatch):
    seen = {}

    def _fake_default_model(api_key, **kwargs):
        seen.update(kwargs)
        return _FakeModel(messages=iter([]))

    monkeypatch.setattr(jar_endpoint, "default_model", _fake_default_model)
    jar_endpoint._model()
    assert seen == {"timeout": jar_endpoint.MODEL_TIMEOUT_SECONDS, "max_retries": 0}
    assert 0 < jar_endpoint.MODEL_TIMEOUT_SECONDS <= 60
