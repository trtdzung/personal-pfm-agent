from text_utils import extract_final_text


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
