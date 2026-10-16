from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_describes_personal_card_agent():
    text = README.read_text(encoding="utf-8")
    assert "personal-card-agent" in text
    assert "research-assistant" not in text
