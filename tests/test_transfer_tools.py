from tools.transfer_tools import check_available_balance_or_credit


def test_check_available_balance_or_credit_reports_sufficient_card():
    # No LangGraph runnable context in a plain unit test -- falls back to
    # DEFAULT_CUSTOMER_ID ("CIF_0001"), which has 2 cards with
    # available_credit_vnd 45,500,000 and 30,000,000.
    result = check_available_balance_or_credit.invoke({"amount_vnd": 1_000_000})
    assert "Có ít nhất 1 thẻ đủ hạn mức khả dụng" in result
    assert "card_001" in result
    assert "card_002" in result


def test_check_available_balance_or_credit_reports_insufficient_for_all_cards():
    result = check_available_balance_or_credit.invoke({"amount_vnd": 999_000_000})
    assert "KHÔNG có thẻ nào đủ hạn mức khả dụng" in result
    assert "đừng đề xuất transfer_form" in result
