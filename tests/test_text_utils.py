from text_utils import extract_final_text, extract_ui_block


def test_extract_final_text_returns_plain_string_unchanged():
    assert extract_final_text("hello") == "hello"


def test_extract_final_text_pulls_text_blocks_from_reasoning_model_output():
    content = [
        {
            "id": "rs_abc",
            "type": "reasoning",
            "summary": [],
            "content": [],
            "encrypted_content": "gAAAAA...",
        },
        {
            "type": "text",
            "text": "Câu trả lời cuối cùng.",
            "annotations": [],
            "id": "msg_xyz",
            "phase": "final_answer",
        },
    ]
    assert extract_final_text(content) == "Câu trả lời cuối cùng."


def test_extract_final_text_joins_multiple_text_blocks():
    content = [
        {"type": "text", "text": "Phần 1."},
        {"type": "text", "text": "Phần 2."},
    ]
    assert extract_final_text(content) == "Phần 1.\nPhần 2."


def test_extract_final_text_falls_back_to_str_for_unrecognized_shape():
    assert extract_final_text(42) == "42"


def test_extract_final_text_strips_complete_think_block():
    # GLM (via GreenNode's MaaS, OpenAI-compatible) sometimes leaves a raw
    # <think>...</think> reasoning block inline in message content instead
    # of a separate reasoning_content field.
    content = "trước <think>suy nghĩ nội bộ, không nên hiện ra</think> câu trả lời thật"
    assert extract_final_text(content) == "trước  câu trả lời thật"


def test_extract_final_text_strips_stray_closing_think_tags():
    # Observed in production: content starts with a stray "</think></think>"
    # with no matching opening tag/content (the reasoning itself was
    # presumably already split out elsewhere, leaving just the delimiter).
    content = "</think></think>Câu trả lời thật, không có suy nghĩ nội bộ nào cả."
    assert extract_final_text(content) == "Câu trả lời thật, không có suy nghĩ nội bộ nào cả."


def test_extract_ui_block_returns_text_unchanged_and_none_when_absent():
    text, ui = extract_ui_block("Tháng này bạn chi tiêu 4.250.000 VND.")
    assert text == "Tháng này bạn chi tiêu 4.250.000 VND."
    assert ui is None


def test_extract_ui_block_splits_out_valid_chart_block():
    text = (
        "Tháng này bạn chi nhiều nhất cho Mua sắm.\n\n"
        '```ui-json\n{"type": "chart", "chart_type": "pie", "title": "Chi tiêu theo danh mục", '
        '"labels": ["Mua sắm", "Ăn uống"], "series": [{"name": "VND", "data": [16280000, 10500000]}]}\n```'
    )
    cleaned, ui = extract_ui_block(text)
    assert cleaned == "Tháng này bạn chi nhiều nhất cho Mua sắm."
    assert ui == {
        "type": "chart",
        "chart_type": "pie",
        "title": "Chi tiêu theo danh mục",
        "labels": ["Mua sắm", "Ăn uống"],
        "series": [{"name": "VND", "data": [16280000, 10500000]}],
    }


def test_extract_ui_block_strips_block_even_when_json_is_malformed():
    # docs/chart-output-rules.md B.MUST-1 (generalized to every ui type): the
    # raw block must never leak into `answer`, whether or not it parses -- a
    # model formatting mistake should never break /chat, but it also must
    # never show raw JSON/dict syntax to a customer.
    text = 'Câu trả lời.\n```ui-json\n{not valid json}\n```'
    cleaned, ui = extract_ui_block(text)
    assert cleaned == "Câu trả lời."
    assert ui is None


def test_extract_ui_block_rejects_missing_type():
    # "type" is the dispatch key for every ui block -- absent means unknown,
    # rejected same as an unrecognized type.
    text = '```ui-json\n{"chart_type": "bar", "labels": ["A"], "series": [{"name": "x", "data": [1]}]}\n```'
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_unknown_type():
    text = '```ui-json\n{"type": "transfer_form", "recipient": "x", "amount": 1}\n```'
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_python_dict_repr():
    # docs/chart-output-rules.md "Ví dụ SAI 1" -- single-quoted Python dict
    # repr instead of real JSON.
    text = "```ui-json\n{'type': 'chart', 'chart_type': 'pie', 'labels': ['A'], 'series': [{'name': 'x', 'data': [1]}]}\n```"
    cleaned, ui = extract_ui_block(text)
    assert cleaned == ""
    assert ui is None


def test_extract_ui_block_rejects_series_data_length_mismatch():
    # docs/chart-output-rules.md "Ví dụ SAI 2" -- data.length (5) != labels.length (6).
    text = (
        '```ui-json\n{"type": "chart", "chart_type": "bar", "title": "t", '
        '"labels": ["A", "B", "C", "D", "E", "F"], '
        '"series": [{"name": "VND", "data": [1, 2, 3, 4, 5]}]}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_stringified_numbers_in_data():
    # docs/chart-output-rules.md "Ví dụ SAI 3" -- data as string numbers.
    text = (
        '```ui-json\n{"type": "chart", "chart_type": "bar", "title": "t", "labels": ["A", "B"], '
        '"series": [{"name": "VND", "data": ["5130000", "2870000"]}]}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_pie_with_multiple_series():
    # docs/chart-output-rules.md "Ví dụ SAI 4" -- pie is single-series by
    # definition. Validation only: a payload that violates this is dropped
    # entirely (ui: None), never silently trimmed to series[0] -- getting
    # the format right is the model's job (see SKILL.md), not the backend's
    # to patch up.
    text = (
        '```ui-json\n{"type": "chart", "chart_type": "pie", "title": "t", "labels": ["A", "B"], '
        '"series": [{"name": "s1", "data": [1, 2]}, {"name": "s2", "data": [3, 4]}]}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_invalid_chart_type():
    text = '```ui-json\n{"type": "chart", "chart_type": "scatter", "labels": ["A"], "series": [{"name": "x", "data": [1]}]}\n```'
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_empty_labels_or_series():
    text = '```ui-json\n{"type": "chart", "chart_type": "bar", "labels": [], "series": [{"name": "x", "data": []}]}\n```'
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_accepts_missing_title_unchanged():
    # title isn't in docs/chart-output-rules.md's B.MUST-2 validation list --
    # validation only, no normalizing a missing title, the payload is
    # returned as-is when the rest passes.
    text = '```ui-json\n{"type": "chart", "chart_type": "bar", "labels": ["A"], "series": [{"name": "x", "data": [1]}]}\n```'
    _, ui = extract_ui_block(text)
    assert ui == {"type": "chart", "chart_type": "bar", "labels": ["A"], "series": [{"name": "x", "data": [1]}]}


def test_extract_ui_block_strips_all_blocks_even_if_model_emits_more_than_one():
    # The model is instructed to emit at most 1 block, but B.MUST-1 says raw
    # JSON must never leak regardless -- defend against a model mistake here
    # instead of trusting Part A.
    text = (
        "Trả lời.\n"
        '```ui-json\n{"type": "chart", "chart_type": "bar", "labels": ["A"], "series": [{"name": "x", "data": [1]}]}\n```\n'
        '```ui-json\n{"type": "chart", "chart_type": "line", "labels": ["B"], "series": [{"name": "y", "data": [2]}]}\n```'
    )
    cleaned, ui = extract_ui_block(text)
    assert "```" not in cleaned
    assert ui is not None and ui["chart_type"] == "bar"


def test_extract_ui_block_splits_out_valid_transfer_form_block():
    text = (
        "Kỳ sao kê đến hạn 10/07, mức tối thiểu là 910.000đ.\n\n"
        '```ui-json\n{"type": "transfer_form", "recipient": "MSB Visa Signature", '
        '"account_number": "card_001", "amount": 910000, '
        '"note": "Thanh toan du no the ky sao ke den han 2026-07-10"}\n```'
    )
    cleaned, ui = extract_ui_block(text)
    assert cleaned == "Kỳ sao kê đến hạn 10/07, mức tối thiểu là 910.000đ."
    assert ui == {
        "type": "transfer_form",
        "recipient": "MSB Visa Signature",
        "account_number": "card_001",
        "amount": 910000,
        "note": "Thanh toan du no the ky sao ke den han 2026-07-10",
    }


def test_extract_ui_block_rejects_transfer_form_missing_note():
    # "note" is the actual bank transfer message/content -- required, not
    # just an optional comment, since the customer's real transfer needs it
    # filled in.
    text = (
        '```ui-json\n{"type": "transfer_form", "recipient": "MSB", '
        '"account_number": "card_001", "amount": 910000}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_transfer_form_with_empty_note():
    text = (
        '```ui-json\n{"type": "transfer_form", "recipient": "MSB", '
        '"account_number": "card_001", "amount": 910000, "note": ""}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_transfer_form_with_non_positive_amount():
    text = (
        '```ui-json\n{"type": "transfer_form", "recipient": "MSB", '
        '"account_number": "card_001", "amount": 0, "note": "x"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_transfer_form_with_stringified_amount():
    text = (
        '```ui-json\n{"type": "transfer_form", "recipient": "MSB", '
        '"account_number": "card_001", "amount": "910000", "note": "x"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_splits_out_valid_transfer_form_beneficiary_id_block():
    # New pfm-lookup shape (backend_docs/pfm-read-api.md) -- no
    # recipient/account_number, pfm looks those up from beneficiary_id.
    text = (
        "Mình đã điền sẵn form chuyển 500.000đ cho Nguyễn Thị Lan.\n\n"
        '```ui-json\n{"type": "transfer_form", "beneficiary_id": "b_stable_lan", '
        '"amount": 500000, "note": "Thanh toan tien an", "category": "dining"}\n```'
    )
    cleaned, ui = extract_ui_block(text)
    assert cleaned == "Mình đã điền sẵn form chuyển 500.000đ cho Nguyễn Thị Lan."
    assert ui == {
        "type": "transfer_form",
        "beneficiary_id": "b_stable_lan",
        "amount": 500000,
        "note": "Thanh toan tien an",
        "category": "dining",
    }


def test_extract_ui_block_rejects_transfer_form_beneficiary_id_missing_category():
    text = (
        '```ui-json\n{"type": "transfer_form", "beneficiary_id": "b_stable_lan", '
        '"amount": 500000, "note": "an trua"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_transfer_form_beneficiary_id_invalid_category():
    text = (
        '```ui-json\n{"type": "transfer_form", "beneficiary_id": "b_stable_lan", '
        '"amount": 500000, "note": "an trua", "category": "food"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_transfer_form_with_empty_beneficiary_id():
    text = (
        '```ui-json\n{"type": "transfer_form", "beneficiary_id": "", '
        '"amount": 500000, "note": "an trua", "category": "dining"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_transfer_form_mixing_both_schema_shapes():
    # beneficiary_id present alongside recipient/account_number -- must
    # never mix the two shapes in one block (SKILL.md's explicit rule).
    text = (
        '```ui-json\n{"type": "transfer_form", "beneficiary_id": "b_stable_lan", '
        '"recipient": "Nguyễn Thị Lan", "account_number": "19012345678901", '
        '"amount": 500000, "note": "an trua", "category": "dining"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_splits_out_valid_create_jar_block():
    text = (
        "Mình đề xuất hũ Ăn uống 3.000.000đ/tháng.\n\n"
        '```ui-json\n{"type": "create_jar", "jar_name": "Ăn uống", "allocation_amount": 3000000, '
        '"reason": "Trung bình chi tiêu Ăn uống 3 tháng gần nhất là ~3.045.000đ/tháng"}\n```'
    )
    cleaned, ui = extract_ui_block(text)
    assert cleaned == "Mình đề xuất hũ Ăn uống 3.000.000đ/tháng."
    assert ui == {
        "type": "create_jar",
        "jar_name": "Ăn uống",
        "allocation_amount": 3000000,
        "reason": "Trung bình chi tiêu Ăn uống 3 tháng gần nhất là ~3.045.000đ/tháng",
    }


def test_extract_ui_block_splits_out_valid_edit_jar_block():
    text = (
        '```ui-json\n{"type": "edit_jar", "jar_name": "Ăn uống", "allocation_amount": 4000000, '
        '"reason": "Khách hàng yêu cầu tăng hũ Ăn uống lên 4.000.000đ/tháng"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui == {
        "type": "edit_jar",
        "jar_name": "Ăn uống",
        "allocation_amount": 4000000,
        "reason": "Khách hàng yêu cầu tăng hũ Ăn uống lên 4.000.000đ/tháng",
    }


def test_extract_ui_block_rejects_jar_missing_reason():
    text = '```ui-json\n{"type": "create_jar", "jar_name": "Ăn uống", "allocation_amount": 3000000}\n```'
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_jar_with_non_positive_allocation_amount():
    text = '```ui-json\n{"type": "create_jar", "jar_name": "Ăn uống", "allocation_amount": 0, "reason": "x"}\n```'
    _, ui = extract_ui_block(text)
    assert ui is None


def test_extract_ui_block_rejects_jar_with_stringified_allocation_amount():
    text = (
        '```ui-json\n{"type": "edit_jar", "jar_name": "Ăn uống", "allocation_amount": "4000000", '
        '"reason": "x"}\n```'
    )
    _, ui = extract_ui_block(text)
    assert ui is None
