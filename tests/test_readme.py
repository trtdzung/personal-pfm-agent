from pathlib import Path

README = Path(__file__).resolve().parents[1] / "README.md"


def test_readme_describes_personal_card_agent():
    text = README.read_text(encoding="utf-8")
    assert "personal-card-agent" in text
    assert "research-assistant" not in text


def test_readme_lists_the_two_jar_endpoints_and_points_at_the_jars_docs():
    text = README.read_text(encoding="utf-8")
    assert "POST /jar-distribute" in text and "POST /jar-rebalance" in text and "docs/jars/endpoints.md" in text
    assert '"mode"' not in text  # the single two-mode endpoint is gone
    for old in ("docs/jar-rebalance-endpoint.md", "docs/jar-rebalance.md", "docs/spending-jar.md", "docs/jar.md"):
        assert old not in text, old


def test_readme_says_the_api_key_guards_every_endpoint_not_only_chat():
    text = README.read_text(encoding="utf-8")
    line = next(ln for ln in text.splitlines() if ln.startswith("- `SERVER_API_KEY`"))
    block = text[text.index(line): text.index(line) + 400]
    assert "/jar-rebalance" in block and "/chat/history" in block and "GET /health" in block


def test_readme_project_tree_lists_the_files_of_the_jar_endpoint_and_its_checks():
    text = README.read_text(encoding="utf-8")
    for entry in ("jar_endpoint.py", "jar_checks.py", "ui_guard.py", "llm.py", "prompts/", "jar_rebalance.md", "jar_distribute.md",
                  "customer_data_tools.py", "distribute-amount/", "spending-jar/"):
        assert entry in text, entry


def test_readme_mentions_the_content_filter_503():
    # a 503 here is the provider's own content-safety filter rejecting the model's output (production log:
    # GreenNode/VNG Cloud MaaS 403 ModelArts.81011) -- worth documenting so a frontend knows to retry
    text = README.read_text(encoding="utf-8")
    assert "503" in text
