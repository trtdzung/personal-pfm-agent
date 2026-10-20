import json
import re
from pathlib import Path

import yaml

from text_utils import is_valid_ui

SKILL = (Path(__file__).resolve().parent.parent / "skills" / "project" / "goal-plan" / "SKILL.md").read_text(encoding="utf-8")


def test_frontmatter_says_when_to_use_it_and_that_it_only_proposes():
    head = SKILL.split("---")[1]
    assert "name: goal-plan" in head and "description: Dùng khi" in head
    assert "Chỉ đề xuất, không thực thi" in head


def test_the_skill_carries_the_rules_the_card_flow_needs():
    for needle in (
        "build_goal_plan_card", "plan_roadmap", "quỹ dự phòng", "kịch bản gốc", "khẩu vị rủi ro", "trả vay", "get_goals",
        "search_msb_knowledge", "other_goals_monthly_vnd", "extra_assets_vnd", "Lộ trình luôn gắn với một mục tiêu đã có", "Chưa có mục tiêu khớp", "Có, mình có tài sản sẵn có", "từ **1 đến 3** phương án", "cần góp mỗi tháng", "12 đến 360", "tiền gửi online kỳ 12 tháng",
        "simulate_goal_plan", "create_goal", "edit_goal", "Mục tiêu → Vay", "goal_id",
        "không gửi tin nào về cho bạn", "không bao giờ", 'bấm "Chọn phương án này" để đặt lộ trình đó cho mục tiêu',
    ):
        assert needle in SKILL, needle
    assert "trả nợ" not in SKILL


def test_the_skill_forbids_a_clarify_options_block_in_the_same_reply():
    assert "Không kèm khối `clarify_options` trong cùng câu trả lời" in SKILL


def test_the_card_block_is_pasted_last_and_every_example_block_is_a_valid_plan_roadmap():
    heading = "## Khuôn câu trả lời (khối thẻ là phần cuối cùng)"
    assert heading in SKILL
    blocks = [json.loads(b) for b in re.findall(r"```ui-json\n(.*?)\n```", SKILL, flags=re.DOTALL)]
    assert blocks and all(b["type"] == "plan_roadmap" and is_valid_ui(b) for b in blocks)
    assert SKILL.index(heading) < SKILL.index("\n```ui-json\n")
    assert SKILL.count("\n```ui-json\n") == 1 and SKILL.rstrip().endswith("```") and "ví dụ về hình dạng" in SKILL.lower()


def test_frontmatter_is_valid_yaml_or_the_skill_is_silently_skipped():
    meta = yaml.safe_load(SKILL.split("---")[1])
    assert meta["name"] == "goal-plan" and meta["description"].startswith("Dùng khi")
