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
JAR_TYPES = {"create_jar", "edit_jar", "distribute_amount", "rebalance_jars"}  # what the CHAT agent emits
DOC_TYPES = JAR_TYPES  # the two endpoints answer with the same types
JARS_DIR = DOCS_DIR / "jars"  # every jar doc lives here; docs/api.md only points at it
DOC_FILES = ("create-edit-jar.md", "distribute-amount.md", "rebalance-jars.md", "endpoints.md")
OLD_DOCS = ("jar.md", "spending-jar.md", "jar-rebalance.md", "jar-rebalance-endpoint.md")  # folded into docs/jars/

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


def test_spending_jar_carries_the_contract_fields_and_the_balance_headroom_rule():
    skill = _skill("spending-jar")
    assert "`category_ids`" in skill
    assert "`jar_id`" in skill
    # since 2026-09-23 (backend_docs): the headroom caps the money put INTO a new jar, not the monthly limit
    assert "`initial_balance` ≤ `allocationHeadroom`" in skill
    assert "`allocation_amount` ≤ `allocationHeadroom`" not in skill
    assert "chỉ thuộc đúng 1 hũ" in skill  # a category moves jars when it is reassigned
    assert "KHÔNG gửi `jar_id`" in skill  # create_jar: pfm generates the id
    assert "Không nói \"đã tạo" in skill or "KHÔNG khẳng định" in skill


def test_spending_jar_requires_initial_balance_on_create_jar():
    skill = _skill("spending-jar")
    assert "`initial_balance`" in skill
    assert "≥ 0" in skill and "`0`" in skill  # zero is a valid opening balance
    # pfm drops a create_jar without it and never reads the gap as 0
    assert "thiếu" in skill and "pfm" in skill


def test_spending_jar_no_longer_caps_a_limit_increase_by_the_headroom():
    skill = _skill("spending-jar")
    for stale in (
        "`allocationHeadroom` còn đủ",  # old: "tăng hạn mức ... cần allocationHeadroom còn đủ"
        "đề xuất giảm hạn mức hũ khác",  # old: "make room by lowering another jar's limit"
        "lấy bớt hạn mức từ hũ khác",
        "còn được đặt thêm",  # old wording for allocationHeadroom ("phần hạn mức còn được đặt thêm")
    ):
        assert stale not in skill, stale
    assert "không cần `allocationHeadroom`" in skill or "không kiểm `allocationHeadroom`" in skill
    assert "không thêm tiền vào hũ" in skill  # a higher limit is a plan, not money


def test_spending_jar_reads_balance_and_limit_not_the_deprecated_remaining():
    skill = _skill("spending-jar")
    assert "`balance`" in skill and "`limit`" in skill
    assert "hũ chưa có số dư" in skill  # `balance: null` is "no balance yet", never 0
    assert "−`balance`" in skill  # a jar with a negative balance is short by −balance


def test_spending_jar_create_jar_examples_all_carry_initial_balance_and_one_is_zero():
    examples = _payloads(_section(_skill_raw("spending-jar"), "Ví dụ ĐÚNG"))
    creates = [p for p in examples if p["type"] == "create_jar"]
    assert creates and all("initial_balance" in p for p in creates)
    assert any(p["initial_balance"] == 0 for p in creates)  # no money waiting: still a create_jar


def test_spending_jar_wrong_examples_show_a_create_jar_without_initial_balance():
    raw = _skill_raw("spending-jar")
    wrong = raw[raw.index("## Ví dụ SAI") :]
    assert "thiếu initial_balance" in wrong


def test_spending_jar_says_when_not_to_emit_a_ui_block():
    skill = _skill("spending-jar")
    assert "không trả `ui-json`" in skill.lower() or "KHÔNG chèn khối" in skill
    assert "trùng" in skill  # a new jar name that duplicates an existing label
    assert "`null`" in skill  # unknown numbers are never guessed


def test_spending_jar_correct_examples_are_accepted_by_the_validator():
    examples = _payloads(_section(_skill_raw("spending-jar"), "Ví dụ ĐÚNG"))
    assert {p["type"] for p in examples} == {"create_jar", "edit_jar"}
    assert all(_accepted(p) for p in examples), examples


# --- distribute-amount skill = "chuyển tiền chưa phân bổ vào hũ" (distribute_amount) --------------------------------


def _rebalance_raw() -> str:
    return _skill_raw("distribute-amount")


def test_jar_rebalance_skill_is_about_putting_unallocated_money_into_jars():
    front = _rebalance_raw().split("---", 2)[1]
    assert "chuyển" in front and "tiền chưa phân bổ" in front
    skill = _skill("distribute-amount")
    assert "`distribute_amount`" in skill and "`get_jar_summary`" in skill


def test_jar_rebalance_takes_the_money_only_from_the_unallocated_pool_never_from_another_jar():
    skill = _skill("distribute-amount")
    assert "tiền chưa phân bổ" in skill and "`unallocated`" in skill
    assert "max(0, `unallocated`)" in skill  # the most that can be handed out
    assert "không lấy từ hũ khác" in skill
    # the old donor logic is gone with the rebalance_jars form
    for gone in ("`pool` trước", "`moves`", "`shortfall`", "min(spendable, phần còn thiếu)"):
        assert gone not in skill, gone
    assert "rebalance_jars" not in _section(_rebalance_raw(), "Ví dụ ĐÚNG")  # it may only appear as a WRONG example


def test_jar_rebalance_says_what_to_do_when_the_unallocated_money_is_not_enough():
    skill = _skill("distribute-amount")
    assert "KHÔNG trả `ui-json`" in skill
    assert "còn bao nhiêu" in skill  # tell the customer how much unallocated money there is


def test_a_jar_with_no_balance_yet_can_still_receive_money():
    skill = _skill("distribute-amount")
    assert "chưa có số dư" in skill and "vẫn nhận được" in skill  # the deposit is how a jar gets its first balance
    assert "phải có `balance`" not in skill


def test_jar_rebalance_handles_several_jars_in_one_form_each_jar_once():
    skill = _skill("distribute-amount")
    assert "nhiều hũ" in skill and "mỗi hũ một lần" in skill
    assert "Σ `allocations[].amount`" in skill


def test_jar_rebalance_covers_a_jar_that_needs_covering_by_putting_its_missing_amount_into_it():
    skill = _skill("distribute-amount")
    assert "`balance` < 0" in skill and "−`balance`" in skill


def test_jar_rebalance_never_claims_the_move_happened():
    skill = _skill("distribute-amount")
    assert "KHÔNG nói \"đã chuyển" in skill


def test_jar_rebalance_correct_examples_are_accepted_by_the_validator():
    examples = _payloads(_section(_rebalance_raw(), "Ví dụ ĐÚNG"))
    assert examples and {p["type"] for p in examples} == {"distribute_amount"}
    assert all(_accepted(p) for p in examples), examples
    assert any(len(p["allocations"]) >= 2 for p in examples)  # several jars in one form
    # "chuyển 300k vào hũ Tiết kiệm" when that jar has no balance yet
    assert any(p["allocations"] == [{"to_jar_id": "savings", "amount": 300000}] for p in examples)


def test_jar_rebalance_skill_is_short():
    # "tóm gọn": it used to be ~230 lines of donor ordering and arithmetic
    assert len(_rebalance_raw().splitlines()) <= 120


# --- instructions.md + transfer-form -------------------------------------------------------------


def test_instructions_route_each_jar_situation_to_one_form():
    text = _flat(REPO_ROOT / "instructions.md")
    assert "Khi nào trả form nào" in text
    for form in JAR_TYPES | {"transfer_form"}:
        assert f"`{form}`" in text, form
    assert "tiền chưa phân bổ" in text and "skill `rebalance-jars`" in text  # two skills, two forms
    assert "tối đa 1 khối `ui-json`" in text
    assert "gọi lại `get_jar_summary`" in text  # numbers change after the customer confirms a change


def test_transfer_form_skill_says_it_is_independent_of_the_jars():
    skill = _skill("transfer-form")
    assert "độc lập" in skill and "hũ" in skill


# --- docs/ ---------------------------------------------------------------------------------------


def test_jar_docs_live_in_one_folder_and_the_old_flat_docs_are_gone():
    assert (JARS_DIR / "README.md").is_file()
    for name in DOC_FILES:
        assert (JARS_DIR / name).is_file(), name
    for old in OLD_DOCS:
        assert not (DOCS_DIR / old).exists(), old  # merged into docs/jars/, not kept as a second copy


def test_the_api_doc_only_points_at_the_jar_docs_instead_of_repeating_them():
    api = (DOCS_DIR / "api.md").read_text(encoding="utf-8")
    for form in DOC_TYPES:
        assert f"`{form}`" in api or f'"{form}"' in api, form
    assert "docs/jars/" in api and "jars/endpoints.md" in api
    assert "POST /jar-distribute" in api and "POST /jar-rebalance" in api
    for detail in ("initial_balance", "allocations", "from_jar_id", "shortfall", "`moves`"):
        assert detail not in api, detail  # the field-level contract is defined once, in docs/jars/
    for old in OLD_DOCS:
        assert old not in api, old


def test_every_jar_json_example_in_the_docs_is_accepted_by_the_validator():
    seen = set()
    for name in DOC_FILES:
        for payload in _payloads((JARS_DIR / name).read_text(encoding="utf-8")):
            ui = payload.get("ui", payload)  # the docs show both a bare `ui` and a full /chat (or endpoint) response
            if isinstance(ui, dict) and ui.get("type") in DOC_TYPES:
                seen.add(ui["type"])
                assert _accepted(ui), (name, ui)
    assert seen == DOC_TYPES


def test_the_rebalance_doc_shows_the_new_shape_and_no_old_one():
    text = (JARS_DIR / "rebalance-jars.md").read_text(encoding="utf-8")
    shown = [p.get("ui", p) for p in _payloads(text) if p.get("ui", p).get("type") == "rebalance_jars"]
    assert len(shown) >= 2 and all("from_jar_id" in u and "allocations" in u for u in shown)
    assert any(len(u["allocations"]) >= 2 for u in shown)
    for u in shown:
        assert not {"target_jar_id", "shortfall", "moves"} & set(u), u


def _skill_raw(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


# --- what the customer reads: no internal names -------------------------------------------------------
# Found by running the real model: the answer said "`pfm` sẽ tạo hũ" and named the category `entertainment`,
# and a `reason` (shown to the customer on the form) quoted `allocationHeadroom`.

_INTERNAL_NAMES = ("allocationHeadroom", "spendable", "remaining", "budgetLimit", "unallocated", "pfm", "_id", "`")


def _reasons_in_skill_examples() -> list[tuple[str, str]]:
    found = []
    for name in ("spending-jar", "distribute-amount"):
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
        for payload in _payloads((JARS_DIR / name).read_text(encoding="utf-8")):
            ui = payload.get("ui", payload)
            if isinstance(ui, dict) and ui.get("type") in DOC_TYPES:
                checked += 1
                assert not [w for w in _INTERNAL_NAMES if w in ui["reason"]], (name, ui["reason"])
    assert checked >= 4


def test_both_jar_skills_and_the_instructions_say_not_to_show_internal_names_to_the_customer():
    for text in (_skill("spending-jar"), _skill("distribute-amount"), _flat(REPO_ROOT / "instructions.md")):
        assert "không nhắc tên nội bộ" in text
        assert "`pfm`" in text  # the rule names the words to avoid


# --- backend_docs 2026-09-21: jar roles and the protected goal jar are gone --------------------------------

_ROLE_WORDS = ("`role`", "goal", "buffer", "essential", "hũ mục tiêu")  # "không hũ nào được bảo vệ" is the rule itself


def test_no_skill_instruction_or_doc_talks_about_jar_roles_or_a_protected_jar():
    texts = {
        "spending-jar": _skill("spending-jar"),
        "distribute-amount": _skill("distribute-amount"),
        "instructions": _flat(REPO_ROOT / "instructions.md"),
        **{f"docs/jars/{name}": _flat(JARS_DIR / name) for name in ("README.md", *DOC_FILES)},
    }
    for name, text in texts.items():
        assert not [w for w in _ROLE_WORDS if w in text], (name, [w for w in _ROLE_WORDS if w in text])


def test_rebalance_is_triggered_by_a_jar_that_needs_covering_not_by_over_limit():
    # `overLimit` (spent > limit) does not change when a jar is covered; `balance < 0` is "cần bù"
    skill = _skill("distribute-amount")
    assert "cần bù" in skill and "`balance` < 0" in skill
    assert "`overLimit: có`" not in skill
    assert "`overLimit`" in skill  # ... but the model is told it is a different axis


def test_skills_tell_the_model_how_to_talk_about_a_jar_that_needs_covering():
    for name in ("distribute-amount", "spending-jar"):
        skill = _skill(name)
        assert 'KHÔNG nói "số dư âm"' in skill, name
        assert "hết số dư, còn thiếu" in skill and "chưa được bù" in skill, name  # backend_docs "Cách nói với khách"
        assert "đã vượt hạn mức" in skill, name  # only when overLimit is true
    assert 'KHÔNG nói "số dư âm"' in _flat(REPO_ROOT / "instructions.md")


def test_skills_forbid_an_invented_jar_id_and_a_jar_that_only_exists_in_the_conversation():
    for name in ("distribute-amount", "spending-jar"):
        skill = _skill(name)
        assert "KHÔNG bao giờ bịa `id`" in skill, name
        assert "chưa tồn tại" in skill, name  # a jar proposed last turn is not confirmed, so it is not in the summary
        assert "`lien-thien`" in skill, name  # the real failure, named so the model recognises it


def test_spending_jar_moves_a_category_with_one_edit_of_the_receiving_jar():
    raw = _skill_raw("spending-jar")
    skill = _skill("spending-jar")
    assert "Chuyển danh mục giữa hai hũ" in skill
    assert "hũ nhận" in skill and "danh sách đầy đủ" in skill
    assert "KHÔNG trả `edit_jar` cho hũ cho" in skill  # editing the giving jar leaves the category in no jar
    assert "chưa xếp hũ" in skill
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
    doc = _flat(JARS_DIR / "create-edit-jar.md")
    assert "Chuyển danh mục giữa hai hũ" in doc
    assert "`c_<slug>`" in doc and "`GET /api/categories?cif=`" in doc
    assert "`ui_guard.py`" in doc and "`jar_id` có trong `jar-summary`" in doc  # the server drops an edit_jar for an unknown jar
    assert "chưa xếp hũ" in doc and not re.search(r'hũ "?Khác\b', doc)  # no auto-generated "Khác" jar any more


def test_skills_tell_the_model_not_to_narrate_its_lookups_to_the_customer():
    # the real model opened an answer with 'Danh mục Cà phê của bạn có id `c_cafe`...'
    for name in ("spending-jar", "distribute-amount"):
        assert "Không kể lại việc tra cứu" in _skill(name), name


# --- POST /jar-rebalance: the endpoint and the distribute_amount contract, for the pfm frontend --------------------


# --- found by running the chat for real: it read the jars, then skipped the pool ------------------------------------
# (took 1.000.000 from a jar although 1.932.889 of unallocated money was available). The fix lives in the skills.


def test_the_jar_skills_open_with_reading_the_jar_summary_before_anything_else():
    for name in ("distribute-amount", "spending-jar"):
        skill = _skill(name)
        first = skill.index("việc ĐẦU TIÊN là gọi `get_jar_summary`")
        assert first < skill.index("Đọc dữ liệu" if name == "spending-jar" else "Tiền lấy từ đâu"), name  # at the top, not buried
        assert "trước khi viết bất kỳ câu nào" in skill, name
    instructions = _flat(REPO_ROOT / "instructions.md")
    assert "việc đầu tiên là gọi `get_jar_summary`" in instructions


def test_instructions_say_chat_only_puts_unallocated_money_into_jars_and_never_takes_from_another_jar():
    # a skill arrives as a tool result (read_file), the instructions are always in the prompt
    instructions = _flat(REPO_ROOT / "instructions.md")
    assert "tiền chưa phân bổ" in instructions and "không lấy từ hũ khác" in instructions


# --- the two endpoint prompts: same vocabulary as the skills (backend_docs 2026-09-23) ---------------------------

ENDPOINT_PROMPTS = ("jar_distribute.md", "jar_rebalance.md")


def _prompt(name: str) -> str:
    return " ".join((REPO_ROOT / "prompts" / name).read_text(encoding="utf-8").split())


def test_the_old_cover_prompt_is_gone_and_the_rebalance_prompt_exists():
    assert not (REPO_ROOT / "prompts" / "jar_cover.md").exists()  # one target, many sources: the shape that was dropped
    assert (REPO_ROOT / "prompts" / "jar_rebalance.md").is_file()


def test_endpoint_prompts_read_balance_not_the_deprecated_remaining():
    for name in ENDPOINT_PROMPTS:
        text = _prompt(name)
        assert "`balance`" in text, name
        assert "`remaining`" not in text, name  # deprecated alias of `balance`
        assert "hết số dư, còn thiếu" in text, name


def test_endpoint_prompts_state_the_same_rules_as_the_docs():
    distribute, rebalance = (_prompt(name) for name in ENDPOINT_PROMPTS)
    assert "hũ đang cần bù" in distribute.lower() and "chia **hết**" in distribute.lower()
    assert "hũ đang cần bù" in rebalance.lower() and "chuyển **hết**" in rebalance.lower()
    assert "không chuyển cho chính hũ cho tiền" in rebalance and "Không** trả hũ cho tiền" in rebalance.replace("**Không** trả", "Không** trả")
    for prompt in (distribute, rebalance):
        assert "Chi tiêu 3 tháng gần nhất" in prompt or "chi tiêu 3 tháng gần nhất" in prompt.lower()
        assert 'Không nói "số dư âm"' in prompt and "không nhắc tên nội bộ" in prompt


def test_distribute_prompt_receivers_are_every_jar_including_one_with_no_balance_yet():
    text = _prompt("jar_distribute.md")
    assert "đã đặt hạn mức" not in text and "chỉ hũ đã có số dư" not in text
    assert "kể cả hũ chưa có số dư" in text
    assert "`limit`" in text  # still shown, to compare spending with the plan


def test_rebalance_prompt_receivers_are_every_other_jar_and_the_giver_is_not_the_models_choice():
    text = _prompt("jar_rebalance.md")
    assert "kể cả hũ chưa có số dư" in text
    assert "hệ thống đã biết" in text  # `from_jar_id` comes from the request, never from the model
    assert "`from_jar_id`" not in text and "`pool`" not in text


def test_endpoint_prompts_forbid_the_new_internal_field_names_in_customer_text():
    for name in ENDPOINT_PROMPTS:
        text = _prompt(name)
        assert "`balance`" in text.split("không nhắc tên nội bộ")[1], name


# --- docs/jars/: the limit/balance split and initial_balance (backend_docs 2026-09-23) ----------------------------


def test_create_edit_doc_documents_initial_balance_and_the_new_headroom_meaning():
    doc = _flat(JARS_DIR / "create-edit-jar.md")
    assert "2026-09-23" in doc and "`initial_balance`" in doc and "phải ≤ `allocationHeadroom`" in doc
    assert "không bị giới hạn bởi `allocationHeadroom`" in doc  # a limit needs no free room
    for stale in ("còn được đặt thêm", "≤ `allocationHeadroom` = `casaBalance − Σ budgetLimit`", "`remaining` có thể âm"):
        assert stale not in doc, stale


def test_overview_explains_limit_balance_and_the_headroom_meaning_once():
    doc = _flat(JARS_DIR / "README.md")
    for word in ("`limit`", "`balance`", "`spendable`", "`allocationHeadroom`", "`unallocated`", "`overLimit`"):
        assert word in doc, word
    assert "hạn mức không phải tiền" in doc.lower()
    assert "**nguồn duy nhất** của `distribute_amount`" in doc
    assert "`limit: null`" in doc and "chưa xếp hũ" in doc and not re.search(r'hũ "?Khác\b', doc)
    for name in DOC_FILES:  # the definitions are not copied into the per-form docs
        assert "| `allocationHeadroom` (= `unallocated`) |" not in _flat(JARS_DIR / name), name


def test_overview_covers_the_four_types_and_which_skill_or_endpoint_returns_each():
    doc = _flat(JARS_DIR / "README.md")
    for ui_type in ("create_jar", "edit_jar", "distribute_amount", "rebalance_jars"):
        assert f"`{ui_type}`" in doc, ui_type
    assert "skill `spending-jar`" in doc and "skill `distribute-amount`" in doc and "skill `rebalance-jars`" in doc
    assert "`POST /jar-distribute`" in doc and "`POST /jar-rebalance`" in doc


def test_overview_says_when_ui_is_null_who_checks_what_and_that_the_agent_only_proposes():
    doc = _flat(JARS_DIR / "README.md")
    assert "`ui = null`" in doc
    for layer in ("`ui_guard.py`", "`text_utils.py`", "`jar_checks.py`"):
        assert layer in doc, layer
    assert "tối đa 1" in doc  # one ui per turn
    assert "KHÔNG bao giờ nói" in doc and "đã tạo" in doc
    assert "Cần `pfm` xác nhận" in doc and "distribute_amount" in doc  # pfm has no distribute_amount card yet


def test_overview_links_every_doc_in_the_folder_and_each_link_resolves():
    doc = (JARS_DIR / "README.md").read_text(encoding="utf-8")
    for name in DOC_FILES:
        assert f"]({'./' + name})" in doc, name
    for target in re.findall(r"\]\((\.[^)#]*)\)", doc):
        assert (JARS_DIR / target).resolve().exists(), target


def test_every_jar_doc_link_resolves():
    for path in [JARS_DIR / n for n in DOC_FILES] + [DOCS_DIR / "api.md", DOCS_DIR / "transfer-form.md"]:
        for target in re.findall(r"\]\((\.[^)#]*)\)", path.read_text(encoding="utf-8")):
            assert (path.parent / target).resolve().exists(), (path.name, target)


# --- docs/jars/endpoints.md: two endpoints, no `mode` -----------------------------------------------------------


def test_endpoints_doc_describes_both_endpoints_their_bodies_and_their_errors():
    doc = _flat(JARS_DIR / "endpoints.md")
    assert "`POST /jar-distribute`" in doc and "`POST /jar-rebalance`" in doc
    assert '{ "user_id": "CIF_0001", "amount": 1000000 }' in doc
    assert '"from_jar_id": "food"' in doc and '"to_jar_ids": ["transport"]' in doc
    for status in ("401", "404", "422", "502", "503"):
        assert status in doc, status
    assert "không gọi model" in doc
    assert "X-API-Key" in doc and "user_id" in doc
    assert '"mode"' not in doc and "`target_jar_id`" in doc  # the old field is mentioned only as refused
    assert "bị từ chối `422`" in doc


def test_endpoints_doc_says_what_the_agent_is_handed_and_how_its_proposal_is_checked():
    doc = _flat(JARS_DIR / "endpoints.md")
    assert "3 tháng dương lịch gần nhất" in doc and "`jar-summary`" in doc
    assert "`jar_checks.py`" in doc and "thử lại **1 lần**" in doc
    assert "300 ký tự" in doc  # the soft rule on `reason`
    assert "Chưa tạo được đề xuất phù hợp lúc này" in doc


def test_endpoints_doc_lists_the_answers_given_by_code_for_both_endpoints():
    doc = _flat(JARS_DIR / "endpoints.md")
    section = doc[doc.index("## Trả lời ngay bằng code") : doc.index("## Mã lỗi")]
    assert section.count("| distribute |") >= 3 and section.count("| rebalance |") >= 3
    assert "chưa có số dư" in section and "hết số dư" in section


def test_endpoint_doc_has_no_mode_and_no_cover_flow_left_anywhere_in_the_docs():
    for path in [JARS_DIR / n for n in ("README.md", *DOC_FILES)] + [DOCS_DIR / "api.md"]:
        text = path.read_text(encoding="utf-8")
        assert '"mode"' not in text and "mode: \"cover\"" not in text and "mode `cover`" not in text, path.name


# --- docs/jars/: chat puts unallocated money into jars with distribute_amount (2026-09-24) -------------------------


def test_distribute_doc_defines_unallocated_money_as_the_only_source():
    doc = _flat(JARS_DIR / "distribute-amount.md")
    assert "max(0, `unallocated`)" in doc and "không lấy từ hũ khác" in doc
    assert "Mọi hũ nhận được" in doc and "kể cả hũ `balance: null`" in doc
    assert "không đổi hạn mức" in doc
    assert "rebalance-jars.md" in doc  # moving money out of a jar is the other form


def test_rebalance_doc_defines_one_giver_many_receivers_and_marks_the_old_shape_dropped():
    doc = _flat(JARS_DIR / "rebalance-jars.md")
    assert "`from_jar_id`" in doc and "`allocations`" in doc and "`to_jar_id`" in doc
    assert "Σ `allocations[].amount` ≤ `spendable`" in doc and "**không cho được**" in doc
    assert "mang sang tháng sau" in doc and "breaking" in doc
    assert "hết số dư, còn thiếu" not in doc or "chưa được bù" in doc  # the wording, when used, is the agreed one
    assert "`remaining` <" not in doc and "phải có `budgetLimit`" not in doc
    assert "distribute-amount.md" in doc


def test_create_edit_doc_points_at_the_other_forms_for_adding_money_to_a_jar():
    doc = _flat(JARS_DIR / "create-edit-jar.md")
    assert "distribute-amount.md" in doc and "rebalance-jars.md" in doc


def test_transfer_form_doc_links_the_rebalance_doc_in_the_jars_folder():
    assert "docs/jars/rebalance-jars.md" in _flat(DOCS_DIR / "transfer-form.md")


# --- skill rebalance-jars: ONE jar gives money to one or more other jars (rebalance_jars) -------------------------


def _rj_raw() -> str:
    return _skill_raw("rebalance-jars")


def test_rebalance_jars_skill_exists_with_a_front_matter_that_routes_jar_to_jar_requests():
    assert (SKILLS_DIR / "rebalance-jars" / "SKILL.md").is_file()
    front = _rj_raw().split("---", 2)[1]
    assert "name: rebalance-jars" in front
    assert "hũ này sang" in front and "rebalance_jars" in front
    assert "distribute-amount" in front  # says when the OTHER skill (unallocated money into a jar) applies instead
    assert ": " not in front.split("description:", 1)[1]  # an unquoted ': ' silently breaks skill loading


def test_the_distribute_skill_points_at_the_rebalance_skill_when_a_source_jar_is_named():
    front = _rj_raw().split("---", 2)[1]
    distribute = _skill_raw("distribute-amount").split("---", 2)[1]
    assert "rebalance-jars" in distribute and "hũ nguồn" in distribute
    assert "hũ nguồn" in front or "hũ cho" in front


def test_rebalance_jars_reads_the_summary_first_and_never_claims_the_move_happened():
    skill = _skill("rebalance-jars")
    assert "việc ĐẦU TIÊN là gọi `get_jar_summary`" in skill
    assert "KHÔNG nói \"đã chuyển" in skill


def test_rebalance_jars_has_one_giving_jar_and_one_or_more_receiving_jars():
    skill = _skill("rebalance-jars")
    assert "`from_jar_id`" in skill and "`allocations`" in skill and "`to_jar_id`" in skill
    assert "1 hũ nguồn" in skill and "1 hoặc nhiều hũ" in skill
    for gone in ("`moves`", "`shortfall`", "`target_jar_id`", "`pool` trước"):
        assert gone not in skill.replace("`pool`\"", ""), gone  # the old one-target-many-sources shape is gone


def test_rebalance_jars_lists_the_hard_rules_pfm_rechecks():
    skill = _skill("rebalance-jars")
    assert "Σ `allocations[].amount` ≤ `spendable`" in skill  # the giver gives at most what it has
    assert "`from_jar_id` ≠ `to_jar_id`" in skill and "mỗi hũ nhận một lần" in skill
    assert "không phải `\"pool\"`" in skill  # the pool is distribute-amount's source
    assert "chưa có số dư" in skill  # a giver with no balance yet has nothing to give


def test_rebalance_jars_uses_the_amounts_the_customer_states_and_splits_only_a_bare_total():
    skill = _skill("rebalance-jars")
    assert "đúng số khách nêu" in skill
    assert "hũ cần bù trước" in skill and "chia đều" in skill  # only a total for several jars: needy first, then evenly


def test_rebalance_jars_picks_one_giver_when_the_customer_names_none():
    skill = _skill("rebalance-jars")
    assert "không nêu hũ nguồn" in skill
    assert "`spendable` lớn nhất" in skill and "một mình" in skill  # the single giver that can cover it alone
    assert "−`balance`" in skill and "`balance` < 0" in skill  # a jar that needs covering is short by -balance


def test_rebalance_jars_says_when_not_to_return_a_form():
    skill = _skill("rebalance-jars")
    assert "KHÔNG trả `ui-json`" in skill and "chỉ còn bao nhiêu" in skill  # the giver has less than asked
    assert "KHÔNG bao giờ bịa `id`" in skill and "`lien-thien`" in skill and "chưa tồn tại" in skill


def test_rebalance_jars_talks_to_the_customer_without_internal_names():
    skill = _skill("rebalance-jars")
    assert 'KHÔNG nói "số dư âm"' in skill and "hết số dư, còn thiếu" in skill and "chưa được bù" in skill
    assert "không nhắc tên nội bộ" in skill and "`pfm`" in skill
    assert "Không kể lại việc tra cứu" in skill


def test_rebalance_jars_correct_examples_are_accepted_by_the_validator_and_show_the_shapes():
    examples = _payloads(_section(_rj_raw(), "Ví dụ ĐÚNG"))
    assert examples and {p["type"] for p in examples} == {"rebalance_jars"}
    assert all(_accepted(p) for p in examples), examples
    for p in examples:
        assert not [w for w in _INTERNAL_NAMES if w in p["reason"]], p["reason"]
        assert p["from_jar_id"] != "pool" and all(a["to_jar_id"] != p["from_jar_id"] for a in p["allocations"])
    assert any(len(p["allocations"]) == 1 for p in examples)  # one destination
    assert any(len(p["allocations"]) >= 2 for p in examples)  # several destinations from the same giver


def test_rebalance_jars_skill_is_short_and_free_of_role_words():
    raw = _rj_raw()
    assert len(raw.splitlines()) <= 130
    assert not [w for w in ("`role`", "goal", "buffer", "hũ mục tiêu") if w in raw]


def test_instructions_route_jar_to_jar_moves_to_the_rebalance_jars_skill():
    text = _flat(REPO_ROOT / "instructions.md")
    assert "`rebalance_jars` (skill `rebalance-jars`)" in text
    assert "`distribute_amount` (skill `distribute-amount`)" in text


def test_spending_jar_points_at_rebalance_jars_for_jar_to_jar_moves_and_distribute_amount_for_topping_up():
    skill = _skill("spending-jar")
    assert "skill `rebalance-jars`" in skill  # a short jar / moving balance between jars
    assert "skill `distribute-amount`" in skill  # putting unallocated money into a jar
    assert "skill `jar-rebalance`" not in skill and "skill jar-rebalance" not in skill  # old name is gone


def test_the_old_skill_name_is_gone_everywhere_the_agent_reads_it():
    assert not (SKILLS_DIR / "jar-rebalance").exists() and (SKILLS_DIR / "distribute-amount" / "SKILL.md").is_file()
    front = _skill_raw("distribute-amount").split("---", 2)[1]
    assert "name: distribute-amount" in front
    import re
    for path in [REPO_ROOT / "instructions.md", *SKILLS_DIR.glob("*/SKILL.md")]:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"(?<![/\w-])jar-rebalance(?![\w-]|\.md)", text), path


# --- backend_docs 2026-09-24: no auto-generated "Khác" jar; a jar may have limit null AND a balance -----------------


def test_spending_jar_knows_there_is_no_auto_generated_khac_jar_any_more():
    skill = _skill("spending-jar")
    assert "chưa xếp hũ" in skill
    import re

    assert not re.search(r'hũ "?Khác\b', skill) and "rơi về" not in skill  # "hũ Khách" (a customer) must not trip it


def test_spending_jar_does_not_infer_a_null_balance_from_a_null_limit():
    skill = _skill("spending-jar")
    assert "`limit` là `null`" in skill and "không suy ra" in skill and "`balance`" in skill
    assert "chưa đặt hạn mức" in skill  # the customer-facing way to say it
