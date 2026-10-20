"""The three goal skills: frontmatter, the rules they must carry, and every example payload through the real validator."""

import json
import re
from pathlib import Path

import pytest

from text_utils import is_valid_ui

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills" / "project"
INSTRUCTIONS = (Path(__file__).resolve().parent.parent / "instructions.md").read_text(encoding="utf-8")
SKILLS = ("goal-manage", "goal-asset")
FORMS = {"goal-manage": {"create_goal", "edit_goal", "close_goal"}, "goal-asset": {"add_asset", "edit_asset"}}
# goal-manage also shows how to ask back with buttons (skill clarify-options)
EXTRA_BLOCKS = {"goal-manage": {"clarify_options"}}


def _text(skill: str) -> str:
    return (SKILLS_DIR / skill / "SKILL.md").read_text(encoding="utf-8")


def _ui_blocks(skill: str) -> list[dict]:
    return [json.loads(b) for b in re.findall(r"```ui-json\n(.*?)\n```", _text(skill), flags=re.DOTALL)]


@pytest.mark.parametrize("skill", SKILLS)
def test_frontmatter_names_the_skill_and_says_when_to_use_it(skill):
    head = _text(skill).split("---")[1]
    assert f"name: {skill}" in head and "description: Dùng khi" in head
    assert "Chỉ đề xuất, không thực thi" in head


@pytest.mark.parametrize("skill", SKILLS)
def test_every_ui_json_example_is_accepted_by_the_validator(skill):
    blocks = _ui_blocks(skill)
    assert blocks, "a skill without a valid example teaches nothing"
    for block in blocks:
        assert is_valid_ui(block), block
    assert {b["type"] for b in blocks} == FORMS[skill] | EXTRA_BLOCKS.get(skill, set())


def test_the_asset_examples_cover_every_group_and_every_change():
    blocks = _ui_blocks("goal-asset")
    adds = {b["category"] for b in blocks if b["type"] == "add_asset"}
    assert {"motorbike", "stock", "deposit"} <= adds
    assert {b["change"] for b in blocks if b["type"] == "edit_asset"} == {"revalue", "quantity", "remove"}


@pytest.mark.parametrize("skill", SKILLS)
def test_each_skill_reads_get_goals_first_and_only_proposes(skill):
    text = _text(skill)
    assert "việc ĐẦU TIÊN là gọi `get_goals`" in text
    assert "KHÔNG nói" in text and "đã " in text
    assert "KHÔNG bao giờ bịa" in text


@pytest.mark.parametrize("skill", SKILLS)
def test_dates_come_from_the_systems_today_not_the_real_date(skill):
    text = _text(skill)
    assert "`today`" in text and "get_goals" in text


def test_asset_skill_never_prices_things_itself_and_covers_msb_products_read_only():
    text = _text("goal-asset")
    assert "Không bao giờ tự định giá" in text and "get_goal_market" in text
    assert "chỉ xem" in text


def test_close_skill_warns_that_closing_cannot_be_undone():
    text = _text("goal-manage")
    assert "không hoàn tác" in text and "khoản vay" in text


@pytest.mark.parametrize("skill", SKILLS)
def test_the_reader_is_the_customer_so_no_internal_names_in_example_replies(skill):
    for line in re.findall(r'^Câu trả lời: "(.*)"$', _text(skill), flags=re.MULTILINE):
        assert not re.search(r"`|\bpfm\b|goal-\d|asset-\d|create_goal|edit_goal|add_asset", line), line


def test_instructions_list_the_tools_skills_and_forms():
    for needle in ("`get_goals`", "`get_goal_market`", "`goal-manage`", "`goal-asset`",
                   "`create_goal`", "`edit_goal`", "`close_goal`", "`add_asset`", "`edit_asset`"):
        assert needle in INSTRUCTIONS, needle


@pytest.mark.parametrize("skill", SKILLS)
def test_skills_tell_the_model_not_to_leak_ids_or_call_the_customer_khach(skill):
    # seen in a live run: "Khách đang có tài sản ... (asset-5)" and "Bạn có mục tiêu Mua xe (goal-1)"
    text = _text(skill)
    assert 'gọi khách là "Khách"' in text or 'không viết "Khách đang' in text
    assert "goal-1" in text  # named as an example of what not to write


def test_closing_a_goal_only_sells_msb_assets_not_the_customers_own():
    text = _text("goal-manage")
    assert "tài sản khách tự khai" in text and "không bị bán" in text


def test_asset_skill_says_when_to_ask_back_and_with_what():
    text = _text("goal-asset")
    assert "Khi nào hỏi lại, và hỏi bằng gì" in text
    assert "clarify_options" in text and "Câu hỏi bằng chữ" in text
    # a bare "I have N of X" must read get_goals first and decide between editing and adding
    assert "không nói là thêm hay sửa" in text and "gọi `get_goals` trước" in text
    assert "không bao giờ" in text.lower() and "add_asset" in text


def test_asset_skill_description_catches_a_bare_new_quantity():
    head = _text("goal-asset").split("---")[1]
    assert "giờ tôi có 1500 cổ phiếu ACB" in head


def test_asking_back_is_plain_talk_to_the_customer():
    text = _text("goal-asset")
    assert "Câu hỏi lại là lời nói thẳng với khách" in text
    assert "Gọi khách là **\"bạn\"**" in text and "Không** giải thích vì sao bạn hỏi" in text
    assert "Tôi cần hỏi lại khách" in text  # named as a mistake to avoid


def test_goal_manage_asks_for_a_missing_amount_or_date_with_buttons():
    text = _text("goal-manage")
    assert "Hỏi lại khi thiếu số tiền hoặc thời hạn" in text and "`clarify-options`" in text
    ask = [b for b in _ui_blocks("goal-manage") if b["type"] == "clarify_options"]
    assert ask, "the missing amount / date example must be a clarify_options block"
    questions = ask[0]["questions"]
    assert len(questions) == 2 and all(2 <= len(q["options"]) <= 4 for q in questions)
    assert "Không** hỏi bằng chữ" not in text  # no contradicting rule left
    assert "không hỏi bằng chữ tự do" in text


def test_goal_manage_reads_get_goals_again_after_the_button_and_keeps_replies_plain():
    text = _text("goal-manage")
    assert "Lượt sau khi khách bấm vẫn phải gọi `get_goals` TRƯỚC KHI trả `create_goal`" in text
    assert "bỏ luôn form" in text
    assert 'Gọi khách là **"bạn"**' in text and "Theo skill" in text  # the leak is named as a mistake


def test_goal_asset_reads_the_data_again_after_the_customer_answers_an_ask_back():
    text = _text("goal-asset")
    assert "Lượt sau khi khách trả lời câu hỏi lại" in text and "`get_goal_market`" in text and "bỏ luôn form" in text
    assert "Câu đầu tiên bạn viết ra là câu gửi cho khách" in text


def test_goal_manage_takes_the_monthly_amount_from_plan_monthly_not_from_its_own_division():
    text = _text("goal-manage")
    assert text.count("plan_monthly") >= 2 and "không tự chia" in text
