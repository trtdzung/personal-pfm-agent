from goal_suggest import guard

DATA = "Cần góp mỗi tháng: 3.757.000 VND. Số đang góp: 3.600.000 VND. Thiếu 157.000 VND. Hạn 15/09/2028. Tăng 18%. Lãi 6,8%/năm."


def ok(observation="Bạn chi Ăn uống cao hơn 18%.", suggestion="Giảm bớt để bù 157.000 VND.", question="Mình nên giảm chi Ăn uống thế nào?"):
    return guard.check(observation, suggestion, question, data_text=DATA)


def test_wording_with_numbers_from_the_data_passes():
    assert ok() is None
    assert ok(suggestion="Tăng số góp lên 3.757.000 VND, hạn 15/09/2028, lãi 6,8%/năm.") is None


def test_millions_and_billions_are_compared_by_value():
    data = "Số dư 12.500.000 VND, mục tiêu 1.200.000.000 VND."
    check = lambda text: guard.check(text, "Giữ nhịp.", "Mình nên làm gì?", data_text=data)
    assert check("Có 12,5 triệu") is None and check("Mục tiêu 1,2 tỷ") is None
    assert check("Có 12,6 triệu").startswith("number_not_in_data")


def test_a_number_that_is_not_in_the_data_is_rejected():
    assert ok(suggestion="Giảm 300.000 VND mỗi tháng.").startswith("number_not_in_data")
    assert ok(observation="Bạn chi cao hơn 20%.").startswith("number_not_in_data")


def test_length_markup_and_promises_are_rejected():
    assert ok(observation="a" * (guard.MAX_OBSERVATION_LEN + 1)) == "observation_too_long"
    assert ok(observation="a" * guard.MAX_OBSERVATION_LEN) is None
    assert ok(suggestion="b" * (guard.MAX_SUGGESTION_LEN + 1)) == "suggestion_too_long"
    assert ok(suggestion="**Giảm** bớt") == "markup"
    assert ok(suggestion="Giảm bớt\nngay") == "markup"
    assert ok(suggestion="Chắc chắn sẽ kịp hạn.") == "promise"
    assert ok(suggestion="Cam kết sinh lời.") == "promise"


def test_empty_parts_are_rejected():
    assert ok(observation="  ") == "empty"
    assert ok(suggestion="") == "empty"


def test_the_question_must_be_short_a_question_and_obey_the_same_number_rules():
    assert ok(question="Mình nên giảm chi Ăn uống bao nhiêu để bù 157.000 VND mỗi tháng?") is None
    assert ok(question="q" * (guard.MAX_QUESTION_LEN - 1) + "?") is None
    assert ok(question="q" * guard.MAX_QUESTION_LEN + "?") == "question_too_long"
    assert ok(question="Hãy giải thích thêm giúp mình.") == "question_not_a_question"
    assert ok(question="Mình nên giảm 999.000 VND được không?").startswith("number_not_in_data")
    assert ok(question="Bạn đảm bảo được không?") == "promise"
    assert ok(question="  ") == "empty"
