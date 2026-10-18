"""The jar forms (create_jar / edit_jar / rebalance_jars) live in three places that must agree:
the validators in `text_utils`, the model-facing skills, and the frontend docs. These tests read the
skills and docs and run their example payloads through the real validator, so an example can never
drift away from what the server accepts."""

import json
import re
from pathlib import Path

from text_utils import extract_ui_block

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills" / "project"
DOCS_DIR = REPO_ROOT / "docs"
JAR_TYPES = {"create_jar", "edit_jar", "rebalance_jars"}  # what the CHAT agent emits
# POST /jar-rebalance also answers with `distribute_amount`, which chat never emits (docs only)
DOC_TYPES = JAR_TYPES | {"distribute_amount"}
DOC_FILES = ("spending-jar.md", "jar-rebalance.md", "jar-rebalance-endpoint.md")
ENDPOINT_DOC = "jar-rebalance-endpoint.md"  # POST /jar-rebalance, kept apart from the chat docs

_FENCE_RE = re.compile(r"```(ui-json|json)\n(.*?)\n```", re.DOTALL)


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _skill(name: str) -> str:
    return _flat(SKILLS_DIR / name / "SKILL.md")


def _section(markdown: str, heading: str) -> str:
    """Text from the `## heading…` line up to the next `## ` heading."""
    start = markdown.index(f"\n## {heading}")
    end = markdown.find("\n## ", start + 1)
    return markdown[start : end if end != -1 else len(markdown)]


def _payloads(markdown: str) -> list[dict]:
    return [json.loads(body) for _, body in _FENCE_RE.findall(markdown)]


def _accepted(payload: dict) -> bool:
    text = "```ui-json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    return extract_ui_block(text)[1] == payload


# --- spending-jar: create_jar / edit_jar --------------------------------------------------------


def test_spending_jar_reads_jars_with_get_jar_summary_not_the_old_mock_tool():
    skill = _skill("spending-jar")
    assert "`get_jar_summary`" in skill
    assert "list_existing_jars" not in skill


def test_spending_jar_carries_the_contract_fields_and_headroom_rule():
    skill = _skill("spending-jar")
    assert "`category_ids`" in skill
    assert "`jar_id`" in skill
    assert "`allocation_amount` ≤ `allocationHeadroom`" in skill
    assert "chỉ thuộc đúng 1 hũ" in skill  # a category moves jars when it is reassigned
    assert "KHÔNG gửi `jar_id`" in skill  # create_jar: pfm generates the id
    assert "Không nói \"đã tạo" in skill or "KHÔNG khẳng định" in skill


def test_spending_jar_says_when_not_to_emit_a_ui_block():
    skill = _skill("spending-jar")
    assert "không trả `ui-json`" in skill.lower() or "KHÔNG chèn khối" in skill
    assert "trùng" in skill  # a new jar name that duplicates an existing label
    assert "`null`" in skill  # unknown numbers are never guessed


def test_spending_jar_correct_examples_are_accepted_by_the_validator():
    examples = _payloads(_section(_skill_raw("spending-jar"), "Ví dụ ĐÚNG"))
    assert {p["type"] for p in examples} == {"create_jar", "edit_jar"}
    assert all(_accepted(p) for p in examples), examples


# --- jar-rebalance: rebalance_jars ---------------------------------------------------------------


def test_jar_rebalance_skill_exists_and_is_for_rebalance_jars():
    skill = _skill("jar-rebalance")
    assert "`rebalance_jars`" in skill
    assert "`get_jar_summary`" in skill


def test_jar_rebalance_lists_the_hard_rules_pfm_rechecks():
    skill = _skill("jar-rebalance")
    assert "Σ `moves[].amount`" in skill and "`shortfall`" in skill
    assert "`spendable`" in skill  # a donor gives at most its spendable
    assert "`unallocated`" in skill  # the pool gives at most max(0, unallocated)
    assert "không lặp nguồn" in skill


def test_jar_rebalance_follows_the_donor_order_and_states_the_arithmetic():
    skill = _skill("jar-rebalance")
    assert "`pool` trước, rồi các hũ còn lại theo `spendable` giảm dần" in skill
    assert "không hũ nào được bảo vệ" in skill.lower()  # "Không hũ nào được bảo vệ — hũ không có vai trò"
    assert "min(spendable, phần còn thiếu)" in skill
    assert "`shortfall`" in skill and "−`remaining`" in skill  # case (b): jar already over its limit


def test_jar_rebalance_handles_one_jar_per_turn_and_no_ui_when_nothing_can_cover_it():
    skill = _skill("jar-rebalance")
    assert "1 hũ mỗi lượt" in skill
    assert "`remaining` âm nhất" in skill
    assert "không đủ" in skill and "KHÔNG trả `ui-json`" in skill


def test_jar_rebalance_never_claims_the_move_happened():
    skill = _skill("jar-rebalance")
    assert "KHÔNG nói \"đã chuyển" in skill


def test_jar_rebalance_correct_examples_are_accepted_by_the_validator():
    examples = _payloads(_section(_skill_raw("jar-rebalance"), "Ví dụ ĐÚNG"))
    assert examples and {p["type"] for p in examples} == {"rebalance_jars"}
    assert all(_accepted(p) for p in examples), examples


# --- instructions.md + transfer-form -------------------------------------------------------------


def test_instructions_route_each_jar_situation_to_one_form():
    text = _flat(REPO_ROOT / "instructions.md")
    assert "Khi nào trả form nào" in text
    for form in JAR_TYPES | {"transfer_form"}:
        assert f"`{form}`" in text, form
    assert "tối đa 1 khối `ui-json`" in text
    assert "gọi lại `get_jar_summary`" in text  # numbers change after the customer confirms a change


def test_transfer_form_skill_says_it_is_independent_of_the_jars():
    skill = _skill("transfer-form")
    assert "độc lập" in skill and "hũ" in skill


# --- docs/ ---------------------------------------------------------------------------------------


def test_docs_exist_for_every_jar_form_and_are_linked_from_the_api_doc():
    for name in DOC_FILES:
        assert (DOCS_DIR / name).is_file(), name
    api = (DOCS_DIR / "api.md").read_text(encoding="utf-8")
    for form in DOC_TYPES:
        assert f"`{form}`" in api or f'"{form}"' in api, form
    assert "jar-rebalance.md" in api
    assert "POST /jar-rebalance" in api
    assert ENDPOINT_DOC in api  # the endpoint links to its own doc


def test_every_jar_json_example_in_the_docs_is_accepted_by_the_validator():
    seen = set()
    for name in DOC_FILES:
        for payload in _payloads((DOCS_DIR / name).read_text(encoding="utf-8")):
            ui = payload.get("ui", payload)  # the docs show both a bare `ui` and a full /chat response
            if isinstance(ui, dict) and ui.get("type") in DOC_TYPES:
                seen.add(ui["type"])
                assert _accepted(ui), (name, ui)
    assert seen == DOC_TYPES


def _skill_raw(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


# --- what the customer reads: no internal names -------------------------------------------------------
# Found by running the real model: the answer said "`pfm` sẽ tạo hũ" and named the category `entertainment`,
# and a `reason` (shown to the customer on the form) quoted `allocationHeadroom`.

_INTERNAL_NAMES = ("allocationHeadroom", "spendable", "remaining", "budgetLimit", "unallocated", "pfm", "_id", "`")


def _reasons_in_skill_examples() -> list[tuple[str, str]]:
    found = []
    for name in ("spending-jar", "jar-rebalance"):
        for payload in _payloads(_section(_skill_raw(name), "Ví dụ ĐÚNG")):
            found.append((name, payload["reason"]))
    return found


def test_reasons_in_the_skill_examples_use_no_internal_names():
    reasons = _reasons_in_skill_examples()
    assert len(reasons) >= 4
    for name, reason in reasons:
        assert not [w for w in _INTERNAL_NAMES if w in reason], (name, reason)


def test_reasons_in_the_doc_examples_use_no_internal_names():
    checked = 0
    for name in DOC_FILES:
        for payload in _payloads((DOCS_DIR / name).read_text(encoding="utf-8")):
            ui = payload.get("ui", payload)
            if isinstance(ui, dict) and ui.get("type") in DOC_TYPES:
                checked += 1
                assert not [w for w in _INTERNAL_NAMES if w in ui["reason"]], (name, ui["reason"])
    assert checked >= 4


def test_both_jar_skills_and_the_instructions_say_not_to_show_internal_names_to_the_customer():
    for text in (_skill("spending-jar"), _skill("jar-rebalance"), _flat(REPO_ROOT / "instructions.md")):
        assert "không nhắc tên nội bộ" in text
        assert "`pfm`" in text  # the rule names the words to avoid


# --- arithmetic the model got wrong when run for real -----------------------------------------------------


def test_spending_jar_says_how_much_another_jar_must_shrink_to_make_room():
    # headroom -1.000.000 and a 2.000.000 jar: cutting another jar by 2.000.000 is NOT enough (needs 3.000.000)
    skill = _skill("spending-jar")
    assert "ít nhất `allocation_amount` − `allocationHeadroom`" in skill


# --- backend_docs 2026-09-21: jar roles and the protected goal jar are gone --------------------------------

_ROLE_WORDS = ("`role`", "goal", "buffer", "essential", "hũ mục tiêu")  # "không hũ nào được bảo vệ" is the rule itself


def test_no_skill_instruction_or_doc_talks_about_jar_roles_or_a_protected_jar():
    texts = {
        "spending-jar": _skill("spending-jar"),
        "jar-rebalance": _skill("jar-rebalance"),
        "instructions": _flat(REPO_ROOT / "instructions.md"),
        "docs/spending-jar.md": _flat(DOCS_DIR / "spending-jar.md"),
        "docs/jar-rebalance.md": _flat(DOCS_DIR / "jar-rebalance.md"),
    }
    for name, text in texts.items():
        assert not [w for w in _ROLE_WORDS if w in text], (name, [w for w in _ROLE_WORDS if w in text])


def test_rebalance_is_triggered_by_a_jar_that_needs_covering_not_by_over_limit():
    # `overLimit` (spent > budgetLimit) does not change when a jar is covered; `remaining < 0` is "cần bù"
    skill = _skill("jar-rebalance")
    assert "cần bù" in skill and "`remaining` < 0" in skill
    assert "`overLimit: có`" not in skill
    assert "`overLimit`" in skill  # ... but the model is told it is a different axis


def test_skills_tell_the_model_how_to_talk_about_a_jar_that_needs_covering():
    for name in ("jar-rebalance", "spending-jar"):
        skill = _skill(name)
        assert 'KHÔNG nói "số dư âm"' in skill, name
        assert "số dư 0, còn thiếu" in skill and "chưa được bù" in skill, name
        assert "đã vượt hạn mức" in skill, name  # only when overLimit is true
    assert 'KHÔNG nói "số dư âm"' in _flat(REPO_ROOT / "instructions.md")


def test_skills_forbid_an_invented_jar_id_and_a_jar_that_only_exists_in_the_conversation():
    for name in ("jar-rebalance", "spending-jar"):
        skill = _skill(name)
        assert "KHÔNG bao giờ bịa `id`" in skill, name
        assert "chưa tồn tại" in skill, name  # a jar proposed last turn is not confirmed, so it is not in the summary
        assert "`lien-thien`" in skill, name  # the real failure, named so the model recognises it


def test_spending_jar_moves_a_category_with_one_edit_of_the_receiving_jar():
    raw = _skill_raw("spending-jar")
    skill = _skill("spending-jar")
    assert "Chuyển danh mục giữa hai hũ" in skill
    assert "hũ nhận" in skill and "danh sách đầy đủ" in skill
    assert "KHÔNG trả `edit_jar` cho hũ cho" in skill  # editing the giving jar drops the category into "Khác"
    assert '"Khác"' in skill
    moves = [p for p in _payloads(_section(raw, "Ví dụ ĐÚNG")) if p["reason"].startswith("Chuyển danh mục")]
    assert len(moves) == 1
    assert moves[0]["type"] == "edit_jar" and moves[0]["jar_id"] == "food"  # the RECEIVING jar
    assert moves[0]["category_ids"] == ["dining", "groceries", "entertainment"]  # its own categories + the moved one


def test_categories_come_from_the_customers_own_list_not_a_fixed_ten():
    for name in ("spending-jar", "transfer-form"):
        skill = _skill(name)
        assert "`get_categories`" in skill, name
        assert "`c_<slug>`" in skill, name
        assert '`kind: "expense"`' in skill, name
    assert "không phải danh sách cố định" in _skill("spending-jar").lower()


def test_docs_describe_the_category_move_and_the_customers_own_categories():
    doc = _flat(DOCS_DIR / "spending-jar.md")
    assert "Chuyển danh mục giữa hai hũ" in doc
    assert "`c_<slug>`" in doc and "`GET /api/categories?cif=`" in doc
    assert "ui_guard" in doc or "`jar_id` không có trong" in doc  # the server drops an edit_jar for an unknown jar


# --- found by running the real model: it compared the sources with the spend, not with the shortfall ---------

def test_jar_rebalance_compares_the_sources_with_the_shortfall_not_with_the_spend():
    skill = _skill("jar-rebalance")
    assert "so với `shortfall`, KHÔNG so với số tiền khách định chi" in skill
    # a worked example where the sources (15.136.000) cover the shortfall (14.187.000) though not the 16.000.000 spend
    assert "14.187.000" in skill and "15.136.000" in skill
    assert "còn thiếu = `shortfall` − tổng đã lấy" in skill  # the running remainder, step by step


def test_jar_rebalance_has_a_correct_example_where_the_pool_and_the_largest_jar_cover_a_big_spend():
    examples = _payloads(_section(_skill_raw("jar-rebalance"), "Ví dụ ĐÚNG"))
    big = [p for p in examples if p["shortfall"] == 14187000]
    assert len(big) == 1
    assert big[0]["moves"] == [{"from_jar_id": "pool", "amount": 13044000}, {"from_jar_id": "lifestyle", "amount": 1143000}]


def test_jar_rebalance_writes_the_sorted_sources_down_before_choosing():
    # the real model took a 796.000 jar while a 1.813.000 jar was available
    assert "Viết ra danh sách nguồn đã sắp xếp" in _skill("jar-rebalance")


def test_skills_tell_the_model_not_to_narrate_its_lookups_to_the_customer():
    # the real model opened an answer with 'Danh mục Cà phê của bạn có id `c_cafe`...'
    for name in ("spending-jar", "jar-rebalance"):
        assert "Không kể lại việc tra cứu" in _skill(name), name


# --- POST /jar-rebalance: the endpoint and the distribute_amount contract, for the pfm frontend --------------------


def test_the_rebalance_doc_describes_the_endpoint_its_modes_and_its_errors():
    doc = _flat(DOCS_DIR / ENDPOINT_DOC)
    assert "POST /jar-rebalance" in doc
    assert '"mode": "cover"' in doc and '"mode": "distribute"' in doc
    for status in ("401", "404", "422", "502", "503"):
        assert status in doc, status
    assert "không gọi model" in doc  # the cases answered by code: nothing to cover, not enough, no jar can receive
    assert "X-API-Key" in doc and "user_id" in doc


def test_the_rebalance_doc_defines_distribute_amount_as_an_amount_shared_into_balances():
    doc = _flat(DOCS_DIR / ENDPOINT_DOC)
    assert "`distribute_amount`" in doc and "`allocations`" in doc and "`to_jar_id`" in doc
    assert "Σ `allocations[].amount` ≤ `amount`" in doc
    assert "không bị giới hạn bởi tiền chưa phân bổ" in doc  # the amount is the customer's own
    assert "chỉ cộng vào số dư" in doc and "không đổi `budgetLimit`" in doc.lower().replace("`budgetlimit`", "`budgetLimit`")
    assert "Chỉ hũ có `budgetLimit` mới nhận được" in doc  # a jar without a limit cannot receive
    assert "`amount` | **không được có** | bắt buộc" in doc  # the request table: required for distribute, absent for cover


def test_the_endpoint_prompts_state_the_same_rules_as_the_docs():
    cover = (REPO_ROOT / "prompts" / "jar_cover.md").read_text(encoding="utf-8")
    distribute = (REPO_ROOT / "prompts" / "jar_distribute.md").read_text(encoding="utf-8")
    assert "`pool` trước" in cover and "giảm dần" in cover and "dừng ngay khi còn thiếu = 0" in cover
    assert "so tổng nguồn với **shortfall**" in cover.replace("\n", " ")
    assert "hũ đang cần bù" in distribute.lower() and "chia **hết**" in distribute.lower()
    for prompt in (cover, distribute):
        assert 'Không nói "số dư âm"' in prompt and "không nhắc tên nội bộ" in prompt


def test_the_endpoint_doc_is_a_file_of_its_own_and_the_chat_rebalance_doc_only_links_to_it():
    chat_doc = _flat(DOCS_DIR / "jar-rebalance.md")
    assert ENDPOINT_DOC in chat_doc  # a pointer, so a reader of the chat form finds the endpoint
    assert "## Endpoint `POST /jar-rebalance`" not in (DOCS_DIR / "jar-rebalance.md").read_text(encoding="utf-8")
    # the definition of the new ui type and the request shape live only in the endpoint doc (the chat doc may name it)
    assert '"mode": "distribute"' not in chat_doc and "`allocations`" not in chat_doc and "`to_jar_id`" not in chat_doc
    endpoint_doc = _flat(DOCS_DIR / ENDPOINT_DOC)
    assert "jar-rebalance.md" in endpoint_doc  # and back: `rebalance_jars` is defined there, not repeated here


# --- found by running the chat for real: it read the jars, then skipped the pool ------------------------------------
# (took 1.000.000 from a jar although 1.932.889 of unallocated money was available). The fix lives in the skills.


def test_the_jar_skills_open_with_reading_the_jar_summary_before_anything_else():
    for name in ("jar-rebalance", "spending-jar"):
        skill = _skill(name)
        first = skill.index("việc ĐẦU TIÊN là gọi `get_jar_summary`")
        assert first < skill.index("Đọc dữ liệu" if name == "spending-jar" else "Khi nào dùng"), name  # at the top, not buried
        assert "trước khi viết bất kỳ câu nào" in skill, name
    instructions = _flat(REPO_ROOT / "instructions.md")
    assert "việc đầu tiên là gọi `get_jar_summary`" in instructions


def test_jar_rebalance_makes_the_pool_the_first_source_whenever_it_has_money():
    skill = _skill("jar-rebalance")
    assert "Nếu `unallocated` > 0 thì `pool` LUÔN là nguồn đầu tiên" in skill
    assert "kể cả khi 1 hũ khác đủ một mình" in skill
    assert "lấy từ 1 hũ khi `pool` còn tiền" in skill  # named as a mistake


def test_jar_rebalance_has_a_correct_example_where_the_pool_alone_covers_the_shortfall():
    examples = _payloads(_section(_skill_raw("jar-rebalance"), "Ví dụ ĐÚNG"))
    pool_only = [p for p in examples if [m["from_jar_id"] for m in p["moves"]] == ["pool"]]
    assert len(pool_only) == 1
    assert pool_only[0]["moves"][0]["amount"] == pool_only[0]["shortfall"]  # the pool alone gives all of it


def test_the_pool_first_rule_is_also_in_the_system_prompt_not_only_in_the_skill():
    # a skill arrives as a tool result (read_file), the instructions are always in the prompt: the real model skipped
    # the pool in 1 of 3 chat runs with the rule only in the skill
    instructions = _flat(REPO_ROOT / "instructions.md")
    assert "`pool` luôn là nguồn đầu tiên" in instructions
    assert "kể cả khi 1 hũ khác đủ một mình" in instructions
