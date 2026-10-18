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
    from tools.customer_data_tools import list_existing_jars, query_beneficiaries
    from tools.investment_tools import project_investment_growth
    from tools.market_news_tools import read_market_article, search_market_news
    from tools.msb_knowledge_tools import search_msb_knowledge

    text = _text()
    for tool in (
        list_existing_jars,
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


def test_investment_guidance_decides_first_and_looks_up_only_when_needed():
    skill = _skill()
    assert "QUYẾT ĐỊNH TRƯỚC, TRA CỨU SAU" in skill
    assert "Không tra tin, không tra sản phẩm MSB" in skill
    assert "**1** `search_msb_knowledge`" in skill
    assert "không lặp search bằng từ khoá khác" in skill


def test_investment_guidance_answers_in_four_to_five_sentences_without_scenario_tables():
    skill = _skill()
    assert "4–5 câu" in skill
    assert "Không bảng, không tiêu đề, không emoji, không danh sách" in skill
    assert "tối đa ~120 từ" in skill
    assert "không bảng kịch bản" in skill
    assert "Ngoài ra bạn có thể cân nhắc" in skill  # alternative + required amount live in the conclusion
    assert "**Biểu đồ:** mặc định KHÔNG" in skill


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
    assert "4–5 câu văn xuôi" in text
    assert "Tra cứu ngoài phải cần thiết và mới nhất" in text
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
