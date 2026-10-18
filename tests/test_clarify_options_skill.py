"""clarify_options is a cross-cutting widget (skills/project/clarify-options/SKILL.md): instead of an
open-ended follow-up question, the agent offers 2-4 concrete, real-data-grounded choices as buttons.
Tapping one sends its exact label back as the customer's next chat message -- /chat itself is unchanged."""

import json
import re
from pathlib import Path

from text_utils import extract_ui_block

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills" / "project"
DOCS_DIR = REPO_ROOT / "docs"

_FENCE_RE = re.compile(r"```(ui-json|json)\n(.*?)\n```", re.DOTALL)


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


def _skill_raw(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def _skill(name: str) -> str:
    return _flat(SKILLS_DIR / name / "SKILL.md")


def _section(markdown: str, heading: str) -> str:
    start = markdown.index(f"\n## {heading}")
    end = markdown.find("\n## ", start + 1)
    return markdown[start : end if end != -1 else len(markdown)]


def _payloads(markdown: str) -> list[dict]:
    return [json.loads(body) for _, body in _FENCE_RE.findall(markdown)]


def _accepted(payload: dict) -> bool:
    text = "```ui-json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    return extract_ui_block(text)[1] == payload


# --- the skill itself -----------------------------------------------------------------------------------


def test_skill_directory_and_front_matter_exist():
    assert (SKILLS_DIR / "clarify-options" / "SKILL.md").is_file()
    front = _skill_raw("clarify-options").split("---", 2)[1]
    assert "name: clarify-options" in front


def test_skill_defines_the_schema():
    skill = _skill("clarify-options")
    assert "`clarify_options`" in skill and "`options`" in skill and "`question`" in skill
    assert "2" in skill and "4" in skill  # the 2-4 bound
    assert "mảng string" in skill or "danh sách string" in skill  # options is a plain list of strings


def test_skill_explains_how_a_tap_reaches_the_agent():
    skill = _skill("clarify-options")
    assert "tin nhắn tiếp theo" in skill  # the picked label becomes the next chat message
    assert "không đổi" in skill or "không cần" in skill  # /chat itself needs no new field


def test_skill_is_a_last_resort_not_a_shortcut_to_avoid_deciding():
    # this is the real regression risk: the model already over-asked before (see instructions.md rule 1
    # and transfer-form's auto-select-the-one-unpaid-card rule) -- the new skill must not reopen that
    skill = _skill("clarify-options")
    assert "TỰ quyết định" in skill or "tự quyết định" in skill.lower()
    assert "chỉ dùng khi" in skill.lower() or "CHỈ dùng" in skill
    assert "dữ liệu thật" in skill and "không bịa" in skill
    assert "2" in skill and "4" in skill


def test_skill_forbids_mixing_with_another_ui_block():
    skill = _skill("clarify-options")
    assert "1 khối `ui-json`" in skill or "1 khối" in skill


def test_skill_correct_examples_are_accepted_by_the_validator():
    examples = _payloads(_section(_skill_raw("clarify-options"), "Ví dụ ĐÚNG"))
    assert len(examples) >= 2
    assert all(p["type"] == "clarify_options" for p in examples)
    assert all(_accepted(p) for p in examples), examples


def test_skill_has_a_wrong_example_that_over_asks_instead_of_deciding():
    skill = _skill("clarify-options")
    assert "Ví dụ SAI" in skill
    wrong = _section(skill.replace(" ", " "), "Ví dụ SAI") if False else None  # placeholder, real check below
    raw = _skill_raw("clarify-options")
    wrong_section = raw[raw.index("## Ví dụ SAI"):]
    assert "chỉ có 1 thẻ" in wrong_section.lower() or "đã đủ để tự xác định" in wrong_section.lower()


# --- wired into instructions.md and existing flows -------------------------------------------------------


def test_instructions_mention_clarify_options():
    text = _flat(REPO_ROOT / "instructions.md")
    assert "`clarify_options`" in text
    assert "clarify-options" in text


def test_spending_jar_and_jar_rebalance_point_at_clarify_options_for_their_ask_again_cases():
    for name in ("spending-jar", "jar-rebalance"):
        skill = _skill(name)
        assert "clarify-options" in skill or "clarify_options" in skill, name


def test_transfer_form_uses_clarify_options_for_the_multi_card_case():
    skill = _skill("transfer-form")
    assert "clarify_options" in skill or "clarify-options" in skill


# --- docs/ ------------------------------------------------------------------------------------------------


def test_doc_file_exists_and_is_linked_from_api_doc():
    assert (DOCS_DIR / "clarify-options.md").is_file()
    api = (DOCS_DIR / "api.md").read_text(encoding="utf-8")
    assert "clarify_options" in api and "clarify-options.md" in api


def test_doc_examples_are_accepted_by_the_validator():
    checked = 0
    for payload in _payloads((DOCS_DIR / "clarify-options.md").read_text(encoding="utf-8")):
        ui = payload.get("ui", payload)
        if isinstance(ui, dict) and ui.get("type") == "clarify_options":
            checked += 1
            assert _accepted(ui), ui
    assert checked >= 1


def test_skill_warns_against_the_old_id_label_object_shape():
    # schema v2 (2026-09-23) dropped the old {id, label} object shape entirely -- `question` moved INTO
    # the ui block (no longer a mistake, it's required) and `options` became a plain list of strings. The
    # new pitfall is the model falling back to the old wrapped-object style out of habit.
    raw = _skill_raw("clarify-options")
    wrong = raw.split("## Ví dụ SAI", 1)[1]
    assert '{"label"' in wrong or "{'label'" in wrong  # the old object shape, shown as wrong
    assert "KHÔNG" in wrong.split('"label"')[0][-250:] or "KHÔNG" in raw.split("## Ví dụ SAI")[0][-400:]


def test_skill_warns_that_a_tapped_label_does_not_replace_reading_the_data_again():
    # real run: after the customer tapped a clarify_options button, the model treated the numbers already
    # quoted in the label as good enough and skipped re-calling get_jar_summary that turn -- ui_guard then
    # dropped the resulting edit_jar (no fresh read this turn), so the customer saw "xem lại rồi xác nhận"
    # with no form at all.
    skill = _skill("clarify-options")
    assert "label" in skill.lower() and "không thay thế" in skill
    assert "get_jar_summary" in skill or "đọc lại dữ liệu" in skill.lower()


def test_the_field_name_rule_is_stated_prominently_at_the_very_top_not_buried():
    # real runs kept repeating a field-naming mistake with the OLD schema even after a "Ví dụ SAI" was
    # added deep in the skill -- keep the loudest version of the current schema's rule at the very top.
    raw = _skill_raw("clarify-options")
    top = raw[: raw.index("## Khi nào dùng")]
    assert "QUAN TRỌNG NHẤT" in top
    assert "`question`" in top and "`options`" in top
    assert "mảng string" in top or "danh sách string" in top  # options is a plain list of strings, not objects
    assert "KHÔNG BAO GIỜ" in top or "TUYỆT ĐỐI KHÔNG" in top
    assert "lỗi thật" in top.lower()


def test_the_top_rule_pairs_with_the_exact_recurring_wrong_json_right_there():
    # a rule stated abstractly wasn't enough on its own with the old schema -- keep pairing the rule with
    # a concrete example right where the model reads it first, not scrolled away in "Ví dụ SAI". The
    # concrete pitfall now is the old wrapped-object options shape.
    raw = _skill_raw("clarify-options")
    top = raw[: raw.index("## Khi nào dùng")]
    assert '"question":' in top and '"options":' in top  # the correct shape, inline
    assert '{"label"' in top or "{'label'" in top  # the old, now-wrong object shape, inline for contrast


def test_the_top_rule_asks_the_model_to_self_check_before_answering():
    raw = _skill_raw("clarify-options")
    top = raw[: raw.index("## Khi nào dùng")]
    assert "Trước khi trả lời" in top or "trước khi trả lời" in top
    assert "chỉ có" in top.lower() or "đúng 2 field" in top


# --- broadened per user request 2026-09-23: "mọi câu hỏi cần agent hỏi lại user thì sẽ gọi skill này" ------


def test_skill_description_triggers_on_any_ask_again_not_only_multiple_choice():
    front = _skill_raw("clarify-options").split("---", 2)[1]
    assert "bất kỳ" in front.lower() or "BẤT KỲ" in front
    assert "text tự do" in front
    assert "CUỐI CÙNG" in front  # still the same guardrail, not a shortcut to avoid deciding


def test_skill_has_a_text_only_branch_for_when_there_is_no_fixed_option_set():
    raw = _skill_raw("clarify-options")
    branch_b = raw[raw.index("(B)"):]
    assert "hỏi bằng text" in branch_b.lower()
    assert "số dư" in branch_b  # the word-ambiguity example folded in from instructions.md rule 1
    assert "số tài khoản" in branch_b  # the free-text beneficiary example folded in from transfer-form
    assert "KHÔNG" in branch_b and "`ui-json`" in branch_b  # explicit: no button block for this branch


def test_instructions_routes_every_ask_again_moment_through_this_skill():
    text = _flat(REPO_ROOT / "instructions.md")
    assert "luôn đọc skill `clarify-options`" in text or "LUÔN đọc skill `clarify-options`" in text
    assert "text tự do" in text  # covers the free-text branch too, not just the button case


def test_instructions_rule_1_and_budget_section_point_at_clarify_options():
    text = _flat(REPO_ROOT / "instructions.md")
    assert "Không liệt kê mọi cách hiểu" in text  # unchanged substantive rule
    assert "chưa biết ngân sách và hỏi lại" in text  # unchanged substantive rule
    # both ask-again moments now point at the shared skill instead of freestanding advice
    rule1 = text[text.index("Không liệt kê mọi cách hiểu") :]
    rule1 = rule1[: rule1.index("Không hiện phép tính")]
    assert "clarify-options" in rule1
    budget = text[text.index("chưa biết ngân sách và hỏi lại") :]
    budget = budget[: budget.index("Khách nêu ngân sách")]
    assert "clarify-options" in budget


def test_transfer_form_free_text_spots_point_at_clarify_options():
    skill = _skill("transfer-form")
    # the two free-text "hỏi lại số tài khoản" spots (no beneficiary match, no card auto-decidable message)
    assert skill.count("clarify-options") >= 1


# --- broadened per user request 2026-09-23: preference/survey questions (e.g. investment intake) can use
# standard category options, not just real-entity data ------------------------------------------------------


def test_skill_description_covers_preference_survey_questions_not_just_real_entities():
    front = _skill_raw("clarify-options").split("---", 2)[1]
    assert "nhu cầu đầu tư" in front  # the exact real scenario that prompted this


def test_skill_has_a_branch_for_standard_category_options_not_tied_to_real_customer_data():
    raw = _skill_raw("clarify-options")
    assert "(A2)" in raw
    a2 = raw[raw.index("(A2)"): raw.index("### (B)")]
    assert "nhóm phân loại chuẩn" in a2 or "nhóm lựa chọn CHUẨN" in a2
    assert "không phải dữ liệu thật" in a2 or "không cần là dữ liệu thật" in a2
    # must not be a shortcut around a skill's own auto-decide rule (e.g. investment-guidance's principal calc)
    assert "investment-guidance" in a2


def test_skill_a2_example_is_accepted_by_the_validator_and_has_multiple_independent_questions():
    examples = _payloads(_section(_skill_raw("clarify-options"), "Ví dụ ĐÚNG"))
    a2_examples = [p for p in examples if len(p.get("questions", [])) > 2]
    assert a2_examples, "expected an A2 example with several independent preference questions"
    assert all(_accepted(p) for p in a2_examples)


def test_investment_guidance_points_at_clarify_options_for_the_ask_me_questions_case():
    skill = _skill("investment-guidance")
    assert "clarify-options" in skill
    assert "hỏi tôi các câu hỏi" in skill or "chủ động muốn được hỏi" in skill
