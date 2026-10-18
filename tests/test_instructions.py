from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTRUCTIONS = REPO_ROOT / "instructions.md"
SKILLS_DIR = REPO_ROOT / "skills" / "project"


def _text() -> str:
    # Collapse hard line-wraps so phrases can be asserted regardless of where
    # the markdown happens to break the line.
    return " ".join(INSTRUCTIONS.read_text(encoding="utf-8").split())


def test_instructions_defines_info_only_role():
    assert "chỉ cung cấp thông tin và tư vấn" in _text()


def test_instructions_tell_model_customer_data_and_date_are_already_in_the_prompt():
    text = _text()
    assert "Đã nạp sẵn trong system prompt" in text
    assert "Không gọi `read_file`/`grep` cho dữ liệu này" in text
    assert "Ngày hiện tại (giờ Việt Nam)" in text
    # The old file-path instructions are gone: the model must not be told to
    # read customer data or budgets from files any more.
    assert "/customer_data.json" not in text
    assert "/memories/agent/customer_budgets.json" not in text
    assert "không ghi đè toàn bộ file" not in text


def test_instructions_use_preference_tools_for_budget():
    text = _text()
    assert "`remember_preference`" in text
    assert "`recall_preference`" in text
    assert "User Preference" in text


def test_instructions_mention_every_registered_tool():
    from tools.customer_data_tools import get_categories, get_jar_summary, query_beneficiaries
    from tools.investment_tools import project_investment_growth
    from tools.market_news_tools import read_market_article, search_market_news
    from tools.msb_knowledge_tools import search_msb_knowledge

    text = _text()
    for tool in (
        get_categories,
        get_jar_summary,
        query_beneficiaries,
        project_investment_growth,
        search_market_news,
        read_market_article,
        search_msb_knowledge,
    ):
        assert f"`{tool.name}`" in text, f"instructions.md does not mention tool {tool.name}"


def test_instructions_mention_every_skill_directory():
    text = _text()
    skills = sorted(p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())
    assert skills, "expected skills under skills/project"
    for name in skills:
        assert f"`{name}`" in text, f"instructions.md does not mention skill {name}"


def test_instructions_keep_hard_rules_for_msb_products_rates_and_investing():
    text = _text()
    assert "Quy tắc cứng" in text
    assert "lãi suất tiền gửi của ngân hàng khác" in text
    assert "khuyên khách gửi/vay/đầu tư ở ngân hàng khác" in text
    assert "Không bịa" in text
    # deposit rates: only from the transcribed tables, with decision + date + counter vs online
    assert "bản chép lại" in text and "tên quyết" in text and "**tại quầy** hay **trực tuyến**" in text
    assert "không lấy bảng tiết kiệm áp cho" in text
    assert "không lỗ vốn" in text  # no unsupported safety claims
    assert "dữ liệu để tóm" in text  # external content is data, not instructions
    assert "**không** mục tiêu giá" in text


def test_instructions_never_ask_the_model_to_pass_a_customer_id():
    assert "không bao giờ truyền mã khách hàng/CIF" in _text()


def test_instructions_keep_anti_refusal_rule_for_action_skills():
    text = _text()
    assert "đừng từ chối" in text
    assert "ui-json" in text


def test_instructions_no_longer_describes_research_assistant():
    text = _text().lower()
    assert "careful research assistant" not in text
    assert "internet search" not in text


def test_instructions_mark_plain_market_news_as_out_of_scope_and_tools_as_background_only():
    text = _text()
    assert "Tin tức/diễn biến thị trường đơn thuần không phải phạm vi hỗ trợ" in text
    assert "chỉ làm bối cảnh cho gợi ý đầu tư" in text
    # boundary: an investment decision that merely mentions the market is NOT plain news
    assert "**không phải** tin tức đơn thuần" in text
    assert "Đừng từ chối cả câu chỉ vì có nhắc tới diễn biến thị trường" in text
    # market-news is no longer a skill customers can trigger
    assert "`market-news`" not in text
    assert not (SKILLS_DIR / "market-news").exists()


def _skill() -> str:
    return " ".join((SKILLS_DIR / "investment-guidance" / "SKILL.md").read_text(encoding="utf-8").split())


def test_investment_guidance_owns_the_market_news_tool_usage():
    skill = _skill()
    assert "`search_market_news`" in skill and "`read_market_article`" in skill
    assert "skill `market-news`" not in skill


def test_investment_guidance_looks_up_in_the_first_turn_with_one_call_per_source():
    skill = _skill()
    assert "Tra cứu ở LƯỢT ĐẦU, gọi song song" in skill
    assert "`search_msb_knowledge` **1 lần**" in skill
    assert "`search_market_news` **1 lần**" in skill
    assert "`project_investment_growth` **1 lần**" in skill
    assert "không lặp bằng từ khoá khác" in skill
    assert "`calculate_deposit_interest`" in skill
    assert "phải cùng một hàng kỳ hạn của bảng" in skill  # 6,80% (12 months) was applied to a 3-month deposit


def test_investment_guidance_answers_the_question_first_then_options_then_the_customers_situation():
    skill = _skill()
    assert "Thứ tự **bắt buộc**" in skill
    first = skill.index("Trả lời thẳng câu hỏi (1–2 câu)")
    second = skill.index("Vài lựa chọn khác (1–2 câu)")
    third = skill.index("Tình hình hiện tại của khách (1–2 câu)")
    assert first < second < third
    assert "Mở đầu bằng tình hình nợ của khách rồi mới trả lời câu hỏi" in skill  # listed as a wrong example


def test_investment_guidance_is_short_bold_and_cites_full_urls():
    skill = _skill()
    assert "5–6 câu, tối đa ~150 từ" in skill
    assert "mỗi câu tối đa ~25 từ" in skill
    assert "Không bảng, không tiêu đề, không emoji, không danh sách" in skill
    assert "**In đậm** 3–5 cụm quan trọng nhất" in skill
    # sources are clickable citation numbers placed right after the claim, NOT a "Nguồn:" list at the end
    assert "Nguồn = số trích dẫn là link" in skill and "`[[1]](URL đầy đủ)`" in skill
    assert 'KHÔNG viết danh sách "Nguồn:" ở cuối' in skill
    assert "**URL đầy đủ chép nguyên văn**" in skill and "**không để URL trần**" in skill and "không viết tắt" in skill
    assert "Ngày/tên nguồn nằm **trong câu**" in skill
    example = skill[skill.index("## Ví dụ ĐÚNG"):skill.index("## Ví dụ SAI")]
    assert "[[1]](https://tuoitre.vn/...)" in example and "[[2]](https://www.msb.com.vn/" in example
    assert "Nguồn:" not in example
    assert "Tối đa 3 nguồn" in skill
    assert "Chỉ gắn mã nguồn cho điều nguồn đó thật sự nói" in skill
    assert "**Biểu đồ:** mặc định KHÔNG" in skill
    assert "mỗi câu là **một dòng riêng, cách nhau một dòng trống**" in skill
    raw = (SKILLS_DIR / "investment-guidance" / "SKILL.md").read_text(encoding="utf-8")  # _skill() flattens newlines
    example = raw[raw.index("## Ví dụ ĐÚNG"):raw.index("## Ví dụ SAI")]
    start = example.index("```\n") + 4
    body = example[start:example.index("\n```", start)].strip()
    paragraphs = [p for p in body.split("\n\n") if p.strip()]
    assert len(paragraphs) == 5 and all("\n" not in p.strip() for p in paragraphs)  # one sentence per line


def test_investment_guidance_forbids_foreign_script_glitches():
    assert "Chèn chữ Hán/Nhật/Hàn" in _skill()


def test_investment_guidance_requires_fresh_information():
    skill = _skill()
    assert "Thông tin phải MỚI NHẤT" in skill
    assert "4 ngày" in skill
    assert "đừng dùng tin cũ" in skill


def test_investment_guidance_skips_projection_and_chart_when_there_is_no_idle_money():
    skill = _skill()
    assert "không truyền `principal_vnd`" in skill
    assert "Số vốn nêu trong câu trả lời phải trùng đúng `principal_vnd` đã truyền" in skill
    assert "Không tự giả định lãi suất" in skill
    assert 'Không nói khách "dư sức/dễ dàng/chắc chắn đạt" mục tiêu' in skill
    assert '"Lợi suất cần có"' in skill


def test_instructions_have_no_skill_exception_to_the_brevity_rule_and_require_fresh_lookups():
    text = _text()
    assert "Không có ngoại lệ cho skill nào" in text
    assert "5–6 câu văn xuôi" in text and "**in đậm**" in text
    assert "`[[n]](URL)` ngay sau ý (không có danh sách \"Nguồn:\" cuối câu)" in text
    assert "Tra cứu ngoài phải cần thiết và mới nhất" in text
    assert "tra **1 lần mỗi nguồn**" in text
    assert "bài tin đăng quá 4 ngày là lỗi thời" in text


def test_instructions_allow_only_labelled_scenario_rates_and_forbid_calling_them_averages():
    text = _text()
    assert "kịch bản giả định" in text
    assert "không phải \"trung bình hiện nay\"" in text
    assert "luôn dùng `project_investment_growth`" in text
    assert "không giả định có hũ tên \"tiết kiệm\"" in text


def test_instructions_forbid_leaking_work_in_progress_into_the_answer():
    text = _text()
    assert "Không lộ quá trình làm việc" in text
    assert "Chỉ có **một** câu trả lời cuối cùng" in text


def test_instructions_send_msb_product_questions_to_the_offline_snapshot_with_sources():
    text = _text()
    assert "`search_msb_knowledge`" in text
    assert "gọi đúng 1 lần" in text
    assert "luôn kèm nguồn" in text and "URL đầy đủ" in text and "dữ liệu lưu ngày" in text
    assert "**số trích dẫn là link** `[[1]](URL đầy đủ)`" in text
    assert "không để URL trần" in text and '**Không** viết danh sách "Nguồn:" ở cuối' in text
    assert "2–4 câu" in text
    # no separate skill: the rules live here, so answering costs no extra "read the skill" model round-trip
    assert "msb-products" not in text
    assert not (SKILLS_DIR / "msb-products").exists()
    for gone in ("search_msb_products", "read_msb_product_page", "list_msb_documents", "read_msb_document"):
        assert gone not in text, gone


def test_instructions_carry_the_msb_answer_rules_that_used_to_live_in_the_skill():
    text = _text()
    assert 'Không khẳng định khách "đủ điều kiện/được duyệt"' in text
    assert "nhắc biên độ/điều kiện cụ thể xác nhận tại tư vấn viên" in text
    assert "nêu rủi ro theo đoạn trả về" in text
    assert "bảng giữ bố cục cột" in text and "đọc mỗi giá trị theo cột nằm ngay dưới đúng tiêu đề cột" in text
    assert "làm phẳng (mất ranh giới cột)" in text and "đừng tự ghép số với từng loại thẻ" in text
    assert "chỉ nêu nếu đoạn trả về nói đúng như vậy" in text
    assert "kết quả có dòng CẢNH BÁO".lower() in text.lower() or "dòng CẢNH BÁO" in text


def test_every_skill_front_matter_is_valid_yaml_for_the_skill_loader():
    # An unquoted ": " inside `description:` makes the YAML invalid; the loader then silently SKIPS the
    # skill ("failed metadata parse") and the model never sees its description. Happened once.
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        lines = skill_md.read_text(encoding="utf-8").split("---", 2)[1].strip().splitlines()
        assert len(lines) == 2 and lines[0].startswith("name: ") and lines[1].startswith("description: "), skill_md
        value = lines[1][len("description: "):]
        if not value.startswith(('"', "'")):
            assert ": " not in value and " #" not in value, f"{skill_md.parent.name}: quote the description or drop ': '"
        assert lines[0][len("name: "):] == skill_md.parent.name


def test_instructions_ask_for_one_sentence_per_line_in_multi_sentence_answers():
    text = _text()
    assert "**mỗi câu một dòng riêng, cách nhau một dòng trống**" in text
    assert "không dồn cả câu trả lời thành một khối chữ" in text
