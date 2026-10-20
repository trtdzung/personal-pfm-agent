from langchain_core.runnables.config import var_child_runnable_config

import tools.goal_price_tools as gpt
from goal_price import service
from goal_price.contracts import Estimate, Source

WEB = Estimate(
    amount=3_630_000_000, low=3_370_000_000, high=3_880_000_000,
    summary="Tham khảo 2 mức giá từ 1 nguồn trên web: khoảng 3,37 tỷ đồng đến 3,88 tỷ đồng.",
    sources=[Source(title="Top căn hộ Thủ Đức", url="https://a.vn/1")],
)
GUESS = Estimate(amount=600_000_000, low=500_000_000, high=750_000_000, summary="M-You chưa tra được giá trên web nên ước tính. Đây là ước tính, chưa có nguồn đối chiếu.", sources=[])


def call(args):
    token = var_child_runnable_config.set({"configurable": {"actor_id": "CIF_0001"}})
    try:
        return gpt.estimate_goal_price.invoke({"name": "estimate_goal_price", "args": args, "id": "1", "type": "tool_call"})
    finally:
        var_child_runnable_config.reset(token)


def stub(monkeypatch, estimate, reason=None, seen=None):
    monkeypatch.setattr(service, "generate_with_llm", lambda schema: None)

    def fake(req, generate, search, guess=None):
        if seen is not None:
            seen.append(req)
        return estimate, reason

    monkeypatch.setattr(service, "research_price", fake)


def test_the_chat_gets_a_price_the_range_and_the_sources(monkeypatch):
    seen = []
    stub(monkeypatch, WEB, seen=seen)
    result = call({"template": "house", "description": "căn hộ ở Thủ Đức", "details": ["Căn hộ chung cư", "50–70 m²"]})
    assert "3.630.000.000 VND" in result.content and "3.370.000.000 VND đến 3.880.000.000 VND" in result.content
    assert "https://a.vn/1" in result.content and "KHÔNG có nguồn" not in result.content
    assert result.artifact["amount"] == 3_630_000_000
    req = seen[0]
    assert req.template == "house" and req.description == "căn hộ ở Thủ Đức" and req.answers == {"q1": ["Căn hộ chung cư"], "q2": ["50–70 m²"]}


def test_a_model_estimate_without_sources_is_flagged_for_the_chat_to_say_so(monkeypatch):
    stub(monkeypatch, GUESS)
    result = call({"template": "car", "description": "xe nhỏ", "details": []})
    assert "KHÔNG có nguồn web" in result.content and "ước tính của M-You" in result.content and result.artifact["sources"] == []


def test_nothing_to_search_for_or_no_price_found_tells_the_chat_not_to_invent_one(monkeypatch):
    stub(monkeypatch, None, "not_enough_prices")
    assert "Thiếu mô tả sản phẩm" in call({"template": "house"}).content
    result = call({"template": "house", "description": "nhà"})
    assert "đừng tự bịa giá" in result.content and result.artifact == {"reason": "not_enough_prices"}


def test_an_unknown_template_becomes_other_and_inputs_are_trimmed(monkeypatch):
    seen = []
    stub(monkeypatch, WEB, seen=seen)
    call({"template": "yacht", "description": "x" * 500, "details": ["a" * 200, "", "  "]})
    assert seen[0].template == "other" and len(seen[0].description) == 200 and seen[0].answers == {"q1": ["a" * 80]}


def test_a_failing_research_never_breaks_the_turn(monkeypatch):
    monkeypatch.setattr(service, "generate_with_llm", lambda schema: None)

    def boom(*args, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(service, "research_price", boom)
    result = call({"template": "house", "description": "nhà"})
    assert "Chưa ước tính được giá lúc này" in result.content and result.artifact is None
