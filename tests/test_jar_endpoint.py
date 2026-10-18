"""The two jar endpoints, no chat: `POST /jar-distribute` (unallocated money into jars -> `distribute_amount`) and
`POST /jar-rebalance` (one jar gives money to one or more other jars -> `rebalance_jars`).

The model only proposes and writes the sentence for the customer. Everything true -- what the pool holds, what the
giving jar can give, whether a proposal is allowed -- comes from code, against the jar-summary the server itself read
(jar_checks.py). Both prompts also carry each jar's spending of the last 3 months."""

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


def _jar(id, label, limit, spent, balance):
    # the jar-summary shape since 2026-09-23 (backend_docs): `limit` (plan) and `balance` (money) are independent
    return {"id": id, "label": label, "categoryIds": [], "limit": limit, "spent": spent, "balance": balance,
            "spendable": None if balance is None else max(0, balance), "overLimit": limit is not None and spent > limit}


def _summary(unallocated=13044000, jars=None):
    return {"month": "2026-09", "casaBalance": 18000000, "unallocated": unallocated, "allocationHeadroom": unallocated,
            "jars": jars if jars is not None else [
                _jar("food", "Ăn uống", 4000000, 2187000, 1813000),
                _jar("lifestyle", "Hưởng thụ", 2500000, 1204000, 1296000),
                _jar("move", "Di chuyển", 1000000, 204000, 796000),
                _jar("savings", "Tiết kiệm", None, 0, None),
            ]}


SPENDING = {
    "food": {"2026-08": {"total_vnd": 2900000, "by_category_vnd": {"Ăn uống ngoài": 2900000}}},
    "lifestyle": {"2026-08": {"total_vnd": 1500000, "by_category_vnd": {"Mua sắm": 1500000}}},
    "move": {"2026-08": {"total_vnd": 300000, "by_category_vnd": {"Di chuyển": 300000}}},
    "savings": {},
}


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


def _dist_reply(allocations, answer="Mình đề xuất chia 1.000.000đ vào các hũ.", reason="Ưu tiên hũ chi nhiều"):
    return _reply("DistributeDraft", answer=answer, allocations=allocations, reason=reason)


def _reb_reply(allocations, answer="Mình đề xuất chuyển 500.000đ từ hũ Ăn uống.", reason="Hũ Ăn uống còn nhiều tiền"):
    return _reply("RebalanceDraft", answer=answer, allocations=allocations, reason=reason)


DIST_BODY = {"user_id": "CIF_0001", "amount": 1000000}
REB_BODY = {"user_id": "CIF_0001", "from_jar_id": "food", "amount": 500000}
GOOD_DIST = [{"to_jar_id": "food", "amount": 600000}, {"to_jar_id": "move", "amount": 400000}]
GOOD_REB = [{"to_jar_id": "move", "amount": 300000}, {"to_jar_id": "savings", "amount": 200000}]


@pytest.fixture
def api(monkeypatch):
    """`call(path, replies, summary=..., body=..., spending=...)`: the model plays `replies` in order and records what
    it saw. `spending=None` makes the spending read fail (pfm down); a dict is what the read returns."""

    def call(path, replies, summary=None, body=None, headers=HEADERS, spending=SPENDING):
        _FakeModel.seen = []
        script = iter(replies)
        monkeypatch.setattr(jar_endpoint, "fetch_jar_summary", lambda customer_id, month="": summary or _summary())

        def _spending(customer_id, summ, today=None):
            if spending is None:
                raise httpx.ConnectError("pfm down")
            return spending

        monkeypatch.setattr(jar_endpoint, "fetch_jar_spending", _spending)
        monkeypatch.setattr(jar_endpoint, "_model", lambda: _FakeModel(messages=script))
        default = DIST_BODY if path == "/jar-distribute" else REB_BODY
        return TestClient(server.app).post(path, json={**default, **(body or {})}, headers=headers)

    call.model_calls = lambda: len(_FakeModel.seen)
    call.dist = lambda replies, **kw: call("/jar-distribute", replies, **kw)
    call.reb = lambda replies, **kw: call("/jar-rebalance", replies, **kw)
    return call


def _shown(index=0) -> str:
    return " ".join(str(m.content) for m in _FakeModel.seen[index])


# --- wiring, auth, request shape ----------------------------------------------------------------------------


def test_both_routes_are_part_of_the_same_server_and_guarded_like_chat():
    client = TestClient(server.app)
    # 401 (not 404) without a key: the routes exist
    assert client.post("/jar-distribute", json=DIST_BODY).status_code == 401
    assert client.post("/jar-rebalance", json=REB_BODY).status_code == 401
    assert client.post("/chat", json={"message": "hi", "user_id": "CIF_0001"}).status_code == 401


def test_they_need_the_same_api_key_as_chat(api):
    for call in (api.dist, api.reb):
        assert call([], headers={}).status_code == 401
        assert call([], headers={"X-API-Key": "wrong"}).status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"amount": 0}, {"amount": -1}, {"amount": None},
        {"jar_ids": []}, {"jar_ids": ["food", "food"]}, {"jar_ids": "food"},
        {"mode": "distribute"},  # the old `mode` field is gone
    ],
)
def test_a_malformed_distribute_request_is_rejected_before_anything_is_read(api, body):
    assert api.dist([], body=body).status_code == 422
    assert api.model_calls() == 0


@pytest.mark.parametrize(
    "body",
    [
        {"amount": 0}, {"amount": -1}, {"amount": None},
        {"from_jar_id": ""}, {"from_jar_id": None},
        {"to_jar_ids": []}, {"to_jar_ids": ["move", "move"]},
        {"to_jar_ids": ["food"]},  # the giving jar cannot be a destination
        {"mode": "cover"}, {"target_jar_id": "food"}, {"spend_amount": 5},  # the old request fields are gone: refuse, do not ignore
    ],
)
def test_a_malformed_rebalance_request_is_rejected_before_anything_is_read(api, body):
    assert api.reb([], body=body).status_code == 422
    assert api.model_calls() == 0


def test_the_customer_id_comes_from_the_request_and_is_what_pfm_is_asked_for(api, monkeypatch):
    asked = []
    monkeypatch.setattr(jar_endpoint, "fetch_jar_summary", lambda customer_id, month="": asked.append(customer_id) or _summary())
    monkeypatch.setattr(jar_endpoint, "fetch_jar_spending", lambda customer_id, summ, today=None: asked.append(customer_id) or SPENDING)
    script = iter([_dist_reply(GOOD_DIST)])
    monkeypatch.setattr(jar_endpoint, "_model", lambda: _FakeModel(messages=script))
    TestClient(server.app).post("/jar-distribute", json={"user_id": "CIF_0003", "amount": 1000000}, headers=HEADERS)
    assert asked == ["CIF_0003", "CIF_0003"]  # the jar summary and the spending, both for that customer


@pytest.mark.parametrize("path", ["/jar-distribute", "/jar-rebalance"])
def test_a_pfm_failure_reading_the_jars_is_a_502_not_an_empty_answer(monkeypatch, path):
    def _fail(customer_id, month=""):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(jar_endpoint, "fetch_jar_summary", _fail)
    body = DIST_BODY if path == "/jar-distribute" else REB_BODY
    assert TestClient(server.app).post(path, json=body, headers=HEADERS).status_code == 502


def test_an_unknown_jar_in_the_request_is_a_404_without_a_model_call(api):
    assert api.dist([], body={"jar_ids": ["khong-co"]}).status_code == 404
    assert api.reb([], body={"from_jar_id": "khong-co"}).status_code == 404
    assert api.reb([], body={"to_jar_ids": ["khong-co"]}).status_code == 404
    assert api.model_calls() == 0


# --- distribute: unallocated money into jars ---------------------------------------------------------------------


def test_distribute_returns_a_distribute_amount_ui(api):
    body = api.dist([_dist_reply(GOOD_DIST)]).json()
    assert body["ui"] == {"type": "distribute_amount", "allocations": GOOD_DIST, "reason": "Ưu tiên hũ chi nhiều"}
    assert body["answer"] == "Mình đề xuất chia 1.000.000đ vào các hũ."
    assert api.model_calls() == 1


def test_distribute_shows_the_model_the_amount_the_jars_and_each_jars_spending(api):
    api.dist([_dist_reply(GOOD_DIST)])
    shown = _shown()
    assert "1000000" in shown or "1.000.000" in shown
    assert "id: food" in shown and "id: savings" in shown  # every jar can receive, even one with no balance yet
    assert "balance: chưa có số dư" in shown
    assert "Ăn uống ngoài" in shown and "2026-08: 2.900.000đ" in shown  # the food jar's spending, by month and category
    assert "chưa có chi tiêu" in shown  # the savings jar has none
    assert "chưa nêu" in shown or "không chỉ định" in shown  # the customer named no jar: the agent picks


def test_distribute_only_offers_the_jars_the_customer_named(api):
    api.dist([_dist_reply([{"to_jar_id": "move", "amount": 1000000}])], body={"jar_ids": ["move", "food"]})
    shown = _shown()
    assert "id: move" in shown and "id: food" in shown
    assert "id: lifestyle" not in shown and "id: savings" not in shown


def test_distribute_to_a_jar_the_customer_did_not_name_is_never_returned(api):
    outside = _dist_reply([{"to_jar_id": "lifestyle", "amount": 1000000}])
    body = api.dist([outside, outside], body={"jar_ids": ["move", "food"]}).json()
    assert body["ui"] is None and "thử lại" in body["answer"]


def test_distribute_goes_on_without_the_spending_when_pfm_cannot_give_it(api):
    response = api.dist([_dist_reply(GOOD_DIST)], spending=None)
    assert response.status_code == 200 and response.json()["ui"]["allocations"] == GOOD_DIST
    assert "chưa đọc được chi tiêu" in _shown().lower()  # the model is told, so it splits by balance


def test_the_money_comes_only_from_the_unallocated_pool_so_a_bigger_amount_needs_no_model_call(api):
    body = api.dist([], summary=_summary(unallocated=700000)).json()  # 1.000.000 asked, 700.000 unallocated
    assert body["ui"] is None and "700.000đ" in body["answer"] and "chưa phân bổ" in body["answer"]
    assert api.model_calls() == 0


def test_an_empty_pool_needs_no_model_call(api):
    for unallocated in (0, -500000, None):
        body = api.dist([], summary=_summary(unallocated=unallocated)).json()
        assert body["ui"] is None and "chưa phân bổ" in body["answer"]
    assert api.model_calls() == 0


def test_distribute_with_no_jar_at_all_needs_no_model_call(api):
    body = api.dist([], summary=_summary(jars=[])).json()
    assert body["ui"] is None and "chưa có hũ nào" in body["answer"]
    assert api.model_calls() == 0


def test_giving_out_more_than_the_amount_is_never_returned(api):
    too_much = _dist_reply([{"to_jar_id": "food", "amount": 1000001}])
    body = api.dist([too_much, too_much]).json()
    assert body["ui"] is None and "1.000.001" not in body["answer"]  # a generic sentence, not the model's claim
    assert api.model_calls() == 2


def test_distribute_that_leaves_money_over_is_retried_then_accepted(api):
    partial = _dist_reply([{"to_jar_id": "food", "amount": 300000}])
    body = api.dist([partial, partial]).json()
    assert body["ui"]["allocations"] == [{"to_jar_id": "food", "amount": 300000}]  # only a soft error: nothing forbidden
    assert api.model_calls() == 2


def test_distribute_to_a_jar_that_does_not_exist_is_never_returned(api):
    bad = _dist_reply([{"to_jar_id": "du-lich", "amount": 1000000}])
    assert api.dist([bad, bad]).json()["ui"] is None


def test_a_hard_error_on_the_first_try_can_be_fixed_by_the_retry(api):
    bad = _dist_reply([{"to_jar_id": "du-lich", "amount": 1000000}])
    assert api.dist([bad, _dist_reply(GOOD_DIST)]).json()["ui"]["allocations"] == GOOD_DIST
    assert "không nằm trong jar-summary" in _shown(1)  # the retry message states what was wrong


# --- rebalance: one jar gives money to one or more other jars ----------------------------------------------------


def test_rebalance_returns_a_rebalance_jars_ui_whose_giver_comes_from_the_request(api):
    body = api.reb([_reb_reply(GOOD_REB)]).json()
    assert body["ui"] == {"type": "rebalance_jars", "from_jar_id": "food", "allocations": GOOD_REB, "reason": "Hũ Ăn uống còn nhiều tiền"}
    assert body["answer"] == "Mình đề xuất chuyển 500.000đ từ hũ Ăn uống."
    assert api.model_calls() == 1


def test_rebalance_shows_the_model_the_giver_the_amount_the_candidates_and_their_spending(api):
    api.reb([_reb_reply(GOOD_REB)])
    shown = _shown()
    assert "Ăn uống (id: food)" in shown
    assert "500000" in shown or "500.000" in shown
    assert "id: move" in shown and "id: lifestyle" in shown and "id: savings" in shown  # every other jar can receive
    assert "Mua sắm" in shown and "2026-08: 1.500.000đ" in shown  # the candidates' spending
    assert "không chỉ định" in shown or "chưa nêu" in shown


def test_rebalance_only_offers_the_destinations_the_customer_named(api):
    api.reb([_reb_reply([{"to_jar_id": "move", "amount": 500000}])], body={"to_jar_ids": ["move"]})
    shown = _shown()
    assert "id: move" in shown and "id: lifestyle" not in shown and "id: savings" not in shown


def test_rebalance_to_a_jar_the_customer_did_not_name_is_never_returned(api):
    outside = _reb_reply([{"to_jar_id": "lifestyle", "amount": 500000}])
    body = api.reb([outside, outside], body={"to_jar_ids": ["move"]}).json()
    assert body["ui"] is None and "thử lại" in body["answer"]


def test_a_giver_with_no_balance_yet_is_explained_without_a_model_call(api):
    body = api.reb([], body={"from_jar_id": "savings"}).json()
    assert body["ui"] is None and "chưa có số dư" in body["answer"] and "Tiết kiệm" in body["answer"]
    assert api.model_calls() == 0


def test_a_giver_that_has_less_than_the_amount_is_reported_without_a_model_call(api):
    body = api.reb([], body={"amount": 2000000}).json()  # food has 1.813.000
    assert body["ui"] is None and "1.813.000đ" in body["answer"] and "Ăn uống" in body["answer"]
    assert api.model_calls() == 0


def test_a_giver_with_nothing_left_is_reported_without_a_model_call(api):
    summary = _summary(jars=[_jar("food", "Ăn uống", 4000000, 4400000, -400000), _jar("move", "Di chuyển", 1000000, 204000, 796000)])
    body = api.reb([], summary=summary).json()
    assert body["ui"] is None and "hết số dư" in body["answer"]
    assert api.model_calls() == 0


def test_a_single_jar_has_nowhere_to_give_to(api):
    body = api.reb([], summary=_summary(jars=[_jar("food", "Ăn uống", 4000000, 2187000, 1813000)])).json()
    assert body["ui"] is None and "hũ khác" in body["answer"]
    assert api.model_calls() == 0


def test_a_giver_that_gives_more_than_it_has_is_never_returned(api):
    too_much = _reb_reply([{"to_jar_id": "move", "amount": 1813001}])
    body = api.reb([too_much, too_much], body={"amount": 1813000}).json()
    assert body["ui"] is None
    assert api.model_calls() == 2


def test_rebalance_that_moves_more_than_the_amount_is_never_returned(api):
    too_much = _reb_reply([{"to_jar_id": "move", "amount": 600000}])
    assert api.reb([too_much, too_much]).json()["ui"] is None


def test_rebalance_that_moves_less_than_the_amount_is_retried_then_accepted(api):
    partial = _reb_reply([{"to_jar_id": "move", "amount": 200000}])
    body = api.reb([partial, partial]).json()
    assert body["ui"]["allocations"] == [{"to_jar_id": "move", "amount": 200000}]
    assert api.model_calls() == 2


def test_rebalance_to_itself_or_to_an_invented_jar_is_never_returned(api):
    for bad_target in ("food", "du-lich", "pool"):
        bad = _reb_reply([{"to_jar_id": bad_target, "amount": 500000}])
        assert api.reb([bad, bad]).json()["ui"] is None, bad_target


def test_rebalance_goes_on_without_the_spending_when_pfm_cannot_give_it(api):
    response = api.reb([_reb_reply(GOOD_REB)], spending=None)
    assert response.status_code == 200 and response.json()["ui"]["allocations"] == GOOD_REB
    assert "chưa đọc được chi tiêu" in _shown().lower()


# --- what the customer reads ----------------------------------------------------------------------------------


def test_foreign_script_glitches_are_stripped_from_the_answer(api):
    body = api.dist([_dist_reply(GOOD_DIST, answer="Mình đề xuất chia，远远 vào các hũ.")]).json()
    assert "远" not in body["answer"] and "vào các hũ" in body["answer"]


def test_internal_words_in_the_reason_get_one_retry_that_names_them(api):
    jargon = _reb_reply(GOOD_REB, reason="Tổng amount đúng bằng balance; hũ có spendable lớn nhất.")
    body = api.reb([jargon, _reb_reply(GOOD_REB)]).json()
    assert body["ui"]["reason"] == "Hũ Ăn uống còn nhiều tiền"
    feedback = _shown(1)
    assert "balance" in feedback and "spendable" in feedback


def test_jargon_that_stays_is_still_returned_because_the_proposal_itself_is_right(api):
    jargon = _dist_reply(GOOD_DIST, reason="Hũ có spendable lớn nhất.")
    body = api.dist([jargon, jargon]).json()
    assert body["ui"]["allocations"] == GOOD_DIST  # a wording slip must not throw away a correct proposal


def test_the_sentences_of_the_answer_are_separated_by_a_blank_line(api):
    body = api.dist([_dist_reply(GOOD_DIST, answer="Câu một.\nCâu hai.\n\n\nCâu ba.")]).json()
    assert body["answer"] == "Câu một.\n\nCâu hai.\n\nCâu ba."


# --- a failing retry must not throw away an acceptable first proposal ----------------------------------------------


def test_a_retry_that_fails_keeps_the_acceptable_first_proposal(api):
    jargon = _dist_reply(GOOD_DIST, reason="Hũ có spendable lớn nhất.")
    body = api.dist([jargon]).json()  # the script ends: the retry call fails (as a dropped connection would)
    assert body["ui"]["allocations"] == GOOD_DIST
    assert api.model_calls() == 2


def test_a_first_try_with_a_broken_rule_and_a_failing_retry_returns_nothing(api):
    bad = _reb_reply([{"to_jar_id": "du-lich", "amount": 500000}])
    body = api.reb([bad]).json()
    assert body["ui"] is None and "thử lại" in body["answer"]


# --- an unreachable model is an infrastructure error, not "no proposal" --------------------------------------------


def test_when_every_model_call_fails_the_answer_is_a_503(api):
    assert api.dist([]).status_code == 503  # the script is empty: every call fails
    assert api.reb([]).status_code == 503
