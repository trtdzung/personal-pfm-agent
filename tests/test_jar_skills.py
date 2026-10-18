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
JAR_TYPES = {"create_jar", "edit_jar", "rebalance_jars"}

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
    assert "`role: \"goal\"`" in skill and "không được có trong `moves`" in skill
    assert "không lặp nguồn" in skill


def test_jar_rebalance_follows_the_donor_order_and_states_the_arithmetic():
    skill = _skill("jar-rebalance")
    assert "`pool` → `buffer` → `spending` → `essential`" in skill
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
    for name in ("spending-jar.md", "jar-rebalance.md"):
        assert (DOCS_DIR / name).is_file(), name
    api = (DOCS_DIR / "api.md").read_text(encoding="utf-8")
    for form in JAR_TYPES:
        assert f"`{form}`" in api or f'"{form}"' in api, form
    assert "jar-rebalance.md" in api


def test_every_jar_json_example_in_the_docs_is_accepted_by_the_validator():
    seen = set()
    for name in ("spending-jar.md", "jar-rebalance.md"):
        for payload in _payloads((DOCS_DIR / name).read_text(encoding="utf-8")):
            ui = payload.get("ui", payload)  # the docs show both a bare `ui` and a full /chat response
            if isinstance(ui, dict) and ui.get("type") in JAR_TYPES:
                seen.add(ui["type"])
                assert _accepted(ui), (name, ui)
    assert seen == JAR_TYPES


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
    for name in ("spending-jar.md", "jar-rebalance.md"):
        for payload in _payloads((DOCS_DIR / name).read_text(encoding="utf-8")):
            ui = payload.get("ui", payload)
            if isinstance(ui, dict) and ui.get("type") in JAR_TYPES:
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


def test_jar_rebalance_does_not_offer_to_raid_a_goal_jar():
    skill = _skill("jar-rebalance")
    assert "KHÔNG hứa" in skill and "`goal`" in skill
    # the rule sits in the hard rules (not only under an example), where the real model actually read it
    rules = skill[skill.index("## Quy tắc cứng"):skill.index("## Khi KHÔNG trả `ui-json`")]
    assert "KHÔNG hỏi khách có muốn lấy" in rules and "nêu sự thật rồi dừng" in rules
