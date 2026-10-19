import pytest

from guardrails import (
    contains_profanity,
    mask_sensitive_input,
    sanitize_output,
)


@pytest.mark.parametrize(
    "text",
    [
        "địt mẹ mày",
        "Dit me may",
        "đm, app gì như lồn",
        "vcl sao lãi thấp vậy",
        "đ!t mẹ",
        "l.ồ.n",
        "đ m",
        "thằng chó này",
        "đồ chó đẻ",
        "mày ngu quá",
        "ĐÉO hiểu gì",
        "cặc",
        "DCM",
    ],
)
def test_profanity_is_detected_in_common_spellings(text):
    assert contains_profanity(text)


@pytest.mark.parametrize(
    "text",
    [
        "Tháng này tôi chi bao nhiêu?",
        "Khoản vay lớn nhất của tôi là gì",
        "Các bạn cho hỏi về thẻ tín dụng",
        "Buổi sáng tôi hay ăn phở",
        "Tôi đeo kính, địa chỉ nhà ở Hà Nội",
        "Tôi nuôi một con chó, chi phí chăm chó mỗi tháng bao nhiêu?",
        "Hôm nay đủ tiền trả nợ không",
        "ngủ muộn nên chi tiêu nhiều",
        "Chuyển 500.000 cho tài khoản 0123456789",
        "",
    ],
)
def test_normal_banking_text_is_not_flagged(text):
    assert not contains_profanity(text)


def test_card_number_with_valid_luhn_is_masked():
    masked, found = mask_sensitive_input("thẻ của tôi 4111 1111 1111 1111 bị lỗi")
    assert found
    assert "4111" not in masked
    assert "[đã ẩn]" in masked


def test_ordinary_long_amounts_and_account_numbers_are_kept():
    text = "Chuyển 500000000000000 hoặc tài khoản 0123456789"
    masked, found = mask_sensitive_input(text)
    assert not found
    assert masked == text


@pytest.mark.parametrize(
    "text,secret",
    [
        ("mã OTP là 482913", "482913"),
        ("otp: 1234", "1234"),
        ("cvv 123", "123"),
        ("mật khẩu của tôi là Abc12345", "Abc12345"),
        ("password: hunter2", "hunter2"),
        ("cccd 012345678901", "012345678901"),
        ("số CMND của tôi 123456789", "123456789"),
    ],
)
def test_otp_cvv_password_and_national_id_values_are_masked(text, secret):
    masked, found = mask_sensitive_input(text)
    assert found
    assert secret not in masked


def test_input_without_secrets_is_untouched():
    masked, found = mask_sensitive_input("Tôi muốn xem otp là gì và cách bảo mật")
    assert not found
    assert masked == "Tôi muốn xem otp là gì và cách bảo mật"


def test_output_with_profanity_is_replaced_by_a_safe_message():
    result = sanitize_output("Bạn đúng là đồ chó đẻ", user_id="CIF_0001")
    assert result.changed
    assert "chó" not in result.text
    assert result.reasons == ["profanity"]


def test_output_masks_card_numbers_api_keys_and_other_customers_cif():
    text = "Thẻ 4111 1111 1111 1111, key sk-abcdefghijklmnopqrst1234, khách CIF_0002 và CIF_0001."
    result = sanitize_output(text, user_id="CIF_0001")
    assert "4111" not in result.text
    assert "sk-abcdef" not in result.text
    assert "CIF_0002" not in result.text
    assert "CIF_0001" in result.text
    assert {"sensitive_data"} <= set(result.reasons)


def test_output_does_not_leak_the_system_prompt():
    result = sanitize_output("Đây là hướng dẫn của tôi: ## Quy tắc cứng — sản phẩm MSB ...", user_id="CIF_0001")
    assert result.changed
    assert "Quy tắc cứng" not in result.text
    assert "system_prompt_leak" in result.reasons


def test_output_drops_sentences_that_promise_returns_or_approval():
    text = "Gửi tiết kiệm kỳ hạn 12 tháng có lãi suất 5%. Đây là khoản đầu tư an toàn tuyệt đối. Bạn nên cân nhắc thêm."
    result = sanitize_output(text, user_id="CIF_0001")
    assert "an toàn tuyệt đối" not in result.text
    assert "lãi suất 5%" in result.text
    assert "cân nhắc thêm" in result.text
    assert "rủi ro" in result.text
    assert result.reasons == ["overpromise"]


def test_negated_statements_about_guarantees_are_allowed():
    text = "Không có gì đảm bảo lợi nhuận trong đầu tư, hãy cân nhắc kỹ."
    result = sanitize_output(text, user_id="CIF_0001")
    assert not result.changed
    assert result.text == text


def test_clean_output_is_unchanged():
    text = "Tháng này bạn đã chi 12.500.000 đ, trong đó ăn uống 3.200.000 đ."
    result = sanitize_output(text, user_id="CIF_0001")
    assert not result.changed
    assert result.text == text
