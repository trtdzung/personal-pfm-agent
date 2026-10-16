from pathlib import Path


def test_answer_file_exists_and_nonempty():
    answer = Path("answer.md")
    assert answer.exists(), "expected the agent to create answer.md"
    assert answer.read_text().strip(), "answer.md should not be empty"
