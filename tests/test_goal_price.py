import asyncio

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from goal_price import api, research, service
from goal_price.contracts import PriceEstimateRequest

SNIPPETS = [
    research.Snippet("Top căn hộ Thủ Đức 2026", "https://a.vn/1", "Lavita Garden, 50,2 đến 55,5 triệu/m² tại Thủ Đức; Fresca 48,2 triệu/m²."),
    research.Snippet("Bán chung cư 70m2", "https://b.vn/2", "Căn hộ 70m2 tại TPHCM giá khoảng 2,4 tỷ đồng, thuê 15 triệu/tháng."),
    research.Snippet("Tin tức", "https://c.vn/3", "Thị trường ấm lên trong quý này."),
]


def fake_search(query, refresh=False):
    return SNIPPETS


def req(**over):
    base = {"user_id": "CIF_0001", "template": "house", "answers": {"q1": ["Căn hộ chung cư"], "q3": ["50–70 m²"]}}
    base.update(over)
    return PriceEstimateRequest(**base)


def extraction(points, area=60):
    return service._Extraction(area_m2=area, points=[service._Point(**p) for p in points])


GOOD_POINTS = [
    {"source": 1, "quote": "50,2 đến 55,5 triệu/m²", "value_vnd": 55_500_000, "per_m2": True},
    {"source": 1, "quote": "48,2 triệu/m²", "value_vnd": 48_200_000, "per_m2": True},
    {"source": 2, "quote": "giá khoảng 2,4 tỷ đồng", "value_vnd": 2_400_000_000},
]


def run(request, **kw):
    return asyncio.run(service.run(request, **kw))


def test_without_answers_the_agent_returns_a_form_to_tick():
    form = service._Form(questions=[service.Question(id="x", title="Khu vực", options=["Hà Nội", "Đà Nẵng"], multi=True), service.Question(id="y", title="Một lựa chọn", options=["chỉ một"])])
    resp = run(req(answers=None), form_generator=lambda system, human: form)
    assert [q.id for q in resp.questions] == ["q1"]  # a question with fewer than 2 options is dropped, ids are renumbered
    assert resp.questions[0].multi is True and resp.estimate is None and not resp.degraded


def test_a_broken_form_falls_back_to_the_fixed_one_for_the_template():
    def boom(system, human):
        raise RuntimeError("down")

    resp = run(req(answers=None), form_generator=boom)
    assert [q.title for q in resp.questions][:2] == ["Loại hình", "Khu vực"] and resp.reason.startswith("model_failed")
    assert run(req(answers=None, template="other"), form_generator=boom).questions


def test_the_price_is_computed_in_code_from_verified_quotes():
    resp = run(req(), extract_generator=lambda s, h: extraction(GOOD_POINTS), search=fake_search)
    est = resp.estimate
    # 55,5tr x 60 = 3.330.000.000; 48,2tr x 60 = 2.892.000.000; 2.400.000.000 -> median 2.892.000.000
    assert est.amount == 2_890_000_000 and est.low == 2_400_000_000 and est.high == 3_330_000_000
    assert "3 mức giá từ 2 nguồn" in est.summary and "2,4 tỷ đồng đến 3,33 tỷ đồng" in est.summary
    assert [s.url for s in est.sources] == ["https://a.vn/1", "https://b.vn/2"]


def test_points_the_snippet_does_not_support_are_dropped():
    invented = [
        {"source": 1, "quote": "giá 9 tỷ đồng", "value_vnd": 9_000_000_000},  # quote not in the snippet
        {"source": 2, "quote": "giá khoảng 2,4 tỷ đồng", "value_vnd": 2_000_000_000},  # number is not the one in the quote
        {"source": 2, "quote": "thuê 15 triệu/tháng", "value_vnd": 1_000},  # absurdly small
        {"source": 7, "quote": "x", "value_vnd": 10_000_000},  # no such snippet
    ]
    resp = run(req(), extract_generator=lambda s, h: extraction(invented + GOOD_POINTS[2:]), search=fake_search)
    assert resp.estimate is None and resp.degraded and resp.reason == "not_enough_prices"  # only one valid point left


def test_a_per_m2_price_needs_the_area():
    resp = run(req(), extract_generator=lambda s, h: extraction(GOOD_POINTS[:2], area=None), search=fake_search)
    assert resp.estimate is None and resp.reason == "not_enough_prices"


def test_search_or_model_trouble_is_degraded_not_an_error():
    def down(query, refresh=False):
        raise research.ResearchUnavailable("no_api_key")

    assert run(req(), extract_generator=lambda s, h: extraction([]), search=down).reason == "search_unavailable:no_api_key"
    assert run(req(), extract_generator=lambda s, h: extraction([]), search=lambda q, refresh=False: []).reason == "no_results"

    def boom(system, human):
        raise RuntimeError("down")

    resp = run(req(), extract_generator=boom, search=fake_search)
    assert resp.estimate is None and resp.degraded and resp.reason.startswith("model_failed")


def test_the_search_asks_for_what_the_customer_ticked_and_refresh_is_passed_on():
    seen = []

    def spy(query, refresh=False):
        seen.append((query, refresh))
        return SNIPPETS

    run(req(refresh=True), extract_generator=lambda s, h: extraction(GOOD_POINTS), search=spy)
    assert len(seen) == 2 and all("Căn hộ chung cư" in q and "50–70 m²" in q and r for q, r in seen)


def test_the_extraction_prompt_carries_the_request_and_numbered_snippets():
    humans = []

    def spy(system, human):
        humans.append((system, human))
        return extraction(GOOD_POINTS)

    run(req(description="gần metro"), extract_generator=spy, search=fake_search)
    system, human = humans[0]
    assert "chép nguyên văn" in system
    assert "Khách mô tả: gần metro" in human and "q3: 50–70 m²" in human and "[2] Bán chung cư 70m2:" in human


app = FastAPI()
app.include_router(api.router)
client = TestClient(app)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("SERVER_API_KEY", "test-key")


def test_endpoint_auth_validation_and_degraded_200(monkeypatch):
    body = {"user_id": "CIF_0001", "template": "house"}
    assert client.post("/goal-price-estimates", json=body).status_code == 401
    headers = {"X-API-Key": "test-key"}
    assert client.post("/goal-price-estimates", json={"template": "house"}, headers=headers).status_code == 422
    assert client.post("/goal-price-estimates", json={**body, "answers": {"q": ["x" * 90]}}, headers=headers).status_code == 422

    async def fake_run(request):
        return service.PriceEstimateResponse(reason="not_enough_prices", degraded=True)

    monkeypatch.setattr(api, "run", fake_run)
    resp = client.post("/goal-price-estimates", json={**body, "answers": {}}, headers=headers)
    assert resp.status_code == 200 and resp.json() == {"reason": "not_enough_prices", "degraded": True}
