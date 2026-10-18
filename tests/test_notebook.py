"""notebooks/try_agent.ipynb is how people try the agent by hand. It must stay valid, must not describe tools that no
longer exist, and must have a section for every flow worth trying -- including POST /jar-rebalance (Option J)."""

import json
from pathlib import Path

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "try_agent.ipynb"


def _cells() -> list[dict]:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


def _source(cell: dict) -> str:
    return "".join(cell["source"])


def _option(letter: str) -> tuple[str, str]:
    """The markdown cell of `## Option <letter>` and the code cell that follows it."""
    cells = _cells()
    for i, cell in enumerate(cells):
        if cell["cell_type"] == "markdown" and _source(cell).startswith(f"## Option {letter}"):
            assert cells[i + 1]["cell_type"] == "code", f"Option {letter} needs a code cell right after its description"
            return _source(cell), _source(cells[i + 1])
    raise AssertionError(f"no '## Option {letter}' section in the notebook")


def _option_j() -> tuple[str, str]:
    return _option("J")


def test_the_notebook_is_a_valid_notebook_with_unique_cell_ids():
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] >= 5
    ids = [c["id"] for c in nb["cells"]]
    assert len(ids) == len(set(ids)), "cell ids must be unique"
    for cell in nb["cells"]:
        assert cell["cell_type"] in {"markdown", "code"}
        if cell["cell_type"] == "code":
            assert "outputs" in cell and "execution_count" in cell


def test_every_code_cell_is_valid_python():
    for i, cell in enumerate(_cells()):
        if cell["cell_type"] != "code":
            continue
        lines = [ln for ln in _source(cell).splitlines() if not ln.lstrip().startswith(("%", "!"))]
        compile("\n".join(lines), f"cell {i}", "exec")


def test_no_cell_describes_a_tool_or_type_that_no_longer_exists():
    for i, cell in enumerate(_cells()):
        text = _source(cell)
        for gone in ("list_existing_jars", "distribute_pool", "actualAmount"):
            assert gone not in text, f"cell {i} still mentions {gone}"


def test_the_intro_lists_option_j_and_k():
    intro = _source(_cells()[0])
    assert "Option J" in intro and "Option K" in intro
    assert "/jar-distribute" in intro and "/jar-rebalance" in intro  # two endpoints now, no `mode`


def test_the_intro_lists_option_l():
    assert "Option L" in _source(_cells()[0])


def test_option_j_explains_both_endpoints_and_points_at_the_endpoint_doc():
    description, _ = _option_j()
    assert "POST /jar-distribute" in description and "POST /jar-rebalance" in description
    assert "docs/jars/endpoints.md" in description
    assert "mode" not in description.replace("model", "")  # the `mode` switch is gone
    assert "3 months" in description  # what the agent is handed besides the jar-summary


def test_option_j_calls_both_endpoints_and_checks_the_results_with_the_real_checks():
    _, code = _option_j()
    assert '"/jar-distribute"' in code and '"/jar-rebalance"' in code
    assert '"mode"' not in code and "target_jar_id" not in code and "check_cover" not in code
    assert '"from_jar_id"' in code and '"amount"' in code
    assert "fetch_jar_summary" in code  # the real jar-summary decides which jar to use, so the cell survives data changes
    assert "check_distribute" in code and "check_rebalance" in code and "hard == []" in code
    assert "SERVER_API_KEY" in code


def test_option_e_describes_the_current_jar_tools():
    e = next(_source(c) for c in _cells() if c["cell_type"] == "markdown" and _source(c).startswith("## Option E"))
    assert "get_jar_summary" in e and "get_categories" in e and "category_ids" in e


# --- Option K: the chat side of the jar flows --------------------------------------------------------------------


def test_option_k_explains_the_chat_jar_flows_and_the_guard():
    description, _ = _option("K")
    assert "POST /chat" in description
    for word in ("distribute_amount", "edit_jar", "ui_guard", "distribute-amount"):
        assert word in description, word
    assert "docs/jars/" in description and "docs/spending-jar.md" not in description


def test_option_k_goes_through_chat_so_the_validators_and_the_guard_run():
    _, code = _option("K")
    assert '"/chat"' in code and "InMemorySaver" in code  # the real endpoint, on a thread that starts fresh each run
    assert "server.agent" in code
    assert "fetch_jar_summary" in code  # real jars decide the questions, so the cell survives data changes


def test_option_k_covers_the_category_move_the_rebalance_and_the_jar_that_does_not_exist_yet():
    _, code = _option("K")
    # category move: one edit_jar for the RECEIVING jar with its full category list
    assert "edit_jar" in code and "category_ids" in code and "jar_id" in code
    # putting unallocated money into a jar in chat: same contract as the endpoint's distribute mode, same hard checks
    assert "distribute_amount" in code and "check_distribute" in code and "hard == []" in code
    # a jar proposed last turn is not confirmed, so it must not be editable: no ui
    assert "Liên thiên" in code and 'ui is None' in code


# --- Option L: the clarify_options skill -----------------------------------------------------------------


def test_option_l_explains_the_skill_and_the_no_backend_change_tap_mechanism():
    description, _ = _option("L")
    assert "clarify_options" in description and "clarify-options" in description
    assert "budgetLimit" in description or "options" in description  # what the buttons are built from


def test_option_l_uses_a_real_customer_and_real_tools_no_stubbing():
    # per explicit user request: no mocked/stubbed pfm data -- a real persona, real get_jar_summary call
    _, code = _option("L")
    for banned in ("STUBBED_SUMMARY", "_fake_get", "customer_data_tools.httpx", "monkeypatch"):
        assert banned not in code, banned
    assert "CIF_0001" in code


def test_option_l_invokes_the_agent_directly_like_the_earlier_options_not_the_endpoint():
    _, code = _option("L")
    assert "InMemorySaver" in code
    assert "build_agent" in code and ".invoke(" in code  # same style as Options C-I
    assert "TestClient" not in code and '"/chat"' not in code  # NOT the HTTP-endpoint style used in J/K


def test_option_l_asks_a_vague_question_that_does_not_lexically_match_any_real_jar_name():
    # CIF_0001's real jars (via pfm) are Thiết yếu/Ăn uống/Di chuyển/Hưởng thụ/Sức khỏe/Tiết kiệm -- none
    # named/collide by name with each other, so a hint-free question has to be SEMANTICALLY vague (not a
    # substring of any real label) for the model to have a genuine reason to ask at all.
    _, code = _option("L")
    assert "không rõ" not in code  # must not tip the model off
    for real_label in ("Thiết yếu", "Ăn uống", "Di chuyển", "Hưởng thụ", "Sức khỏe"):
        assert real_label not in code.split("question = ")[1].split("\n")[0]


def test_option_l_shows_the_clarify_options_ui_then_simulates_tapping_a_button():
    _, code = _option("L")
    assert "extract_ui_block" in code and "extract_final_text" in code
    assert "clarify_options" in code
    assert "options" in code and "[0]" in code  # picks one of the returned options
    assert code.count("config=config") >= 2 or code.count("config") >= 3  # same config/thread both turns


def test_option_l_does_not_hard_assert_the_widget_always_fires():
    # verified for real, twice: with no natural jar/card/beneficiary name collision in ANY demo persona,
    # the model sometimes lists every jar in an open question instead of clarify_options, and even once
    # leaked its own reasoning into the answer. A hard assert would make the notebook fail on an unlucky
    # (but not wrong) real run.
    _, code = _option("L")
    assert "assert ui" not in code.replace(" ", "")


def test_option_l_is_honest_about_the_real_ambiguity_it_relies_on():
    # CIF_0001 really has 6 jars, one more than the schema's 4-option cap -- so a fully unscoped "which
    # jar" question can't legally list all of them as buttons (the skill's own >4 rule forbids it). The
    # cell states the amount up front and names a jar description that matches none of the 6 real labels,
    # so the model must ask which real jar was meant, offering up to 4 -- not a stubbed collision.
    description, _ = _option("L")
    assert "CIF_0001" in description
    assert "6" in description and "4" in description


# --- Option M: put unallocated money into a jar in chat (distribute_amount), agent called directly -------------------


def test_the_intro_lists_option_m():
    assert "Option M" in _source(_cells()[0])


def test_option_m_explains_the_skill_the_source_of_the_money_and_who_executes_it():
    description, _ = _option("M")
    assert "distribute_amount" in description and "distribute-amount" in description
    assert "tiền chưa phân bổ" in description and "không lấy từ hũ khác" in description
    assert "pfm" in description  # the agent only proposes; pfm writes when the customer confirms


def test_option_m_asks_exactly_the_transfer_the_user_wants():
    _, code = _option("M")
    question = code.split("question = ")[1].split("\n")[0]
    assert "300 nghìn" in question and "Tiết kiệm" in question


def test_option_m_calls_the_agent_directly_not_through_an_endpoint_and_uses_real_data():
    _, code = _option("M")
    assert "InMemorySaver" in code and "build_agent" in code and ".invoke(" in code
    for banned in ("TestClient", '"/chat"', '"/jar-rebalance"', "STUBBED_SUMMARY", "_fake_get", "monkeypatch"):
        assert banned not in code, banned
    assert "CIF_0001" in code and "fetch_jar_summary" in code


def test_option_m_shows_the_unallocated_money_and_the_jar_and_checks_a_returned_proposal():
    _, code = _option("M")
    assert "unallocated" in code and "balance" in code  # printed BEFORE asking
    assert "check_distribute" in code and "extract_ui_block" in code


def test_option_m_does_not_hard_assert_the_model_returns_a_form():
    _, code = _option("M")
    assert "assert ui" not in code.replace(" ", "")


# --- Option N: move money from one jar to others in chat (rebalance_jars), agent called directly -------------------


def test_the_intro_lists_option_n():
    assert "Option N" in _source(_cells()[0])


def test_option_n_explains_the_skill_the_shape_and_that_the_money_comes_from_a_jar():
    description, _ = _option("N")
    assert "rebalance_jars" in description and "rebalance-jars" in description
    assert "from_jar_id" in description and "allocations" in description
    assert "docs/jars/rebalance-jars.md" in description
    assert "pfm" in description  # the agent only proposes


def test_option_n_asks_for_a_real_jar_to_jar_transfer_built_from_the_live_jars():
    _, code = _option("N")
    assert "fetch_jar_summary" in code and "CIF_0001" in code
    question = code.split("question = ")[1].split("\n")[0]
    assert "từ hũ" in question and "sang hũ" in question


def test_option_n_calls_the_agent_directly_and_checks_a_returned_proposal():
    _, code = _option("N")
    assert "InMemorySaver" in code and "build_agent" in code and ".invoke(" in code
    for banned in ("TestClient", '"/chat"', "STUBBED_SUMMARY", "_fake_get", "monkeypatch"):
        assert banned not in code, banned
    assert "check_rebalance" in code and "extract_ui_block" in code
    assert "assert ui" not in code.replace(" ", "")  # the model is non-deterministic: print, do not fail


# --- notebooks/try_jar_flows.ipynb: the six jar cases, side by side --------------------------------------------------

JAR_NOTEBOOK = NOTEBOOK.with_name("try_jar_flows.ipynb")


def _jar_cells() -> list[dict]:
    return json.loads(JAR_NOTEBOOK.read_text(encoding="utf-8"))["cells"]


def test_the_jar_notebook_is_valid_and_has_a_setup_cell_then_six_adjacent_case_cells():
    nb = json.loads(JAR_NOTEBOOK.read_text(encoding="utf-8"))
    assert nb["nbformat"] == 4 and nb["nbformat_minor"] >= 5
    cells = nb["cells"]
    assert len({c["id"] for c in cells}) == len(cells)
    kinds = [c["cell_type"] for c in cells]
    assert kinds[0] == "markdown" and kinds[1] == "code" and kinds[2:] == ["code"] * 6  # intro, setup, then 6 in a row
    for cell in cells:
        if cell["cell_type"] == "code":
            assert "outputs" in cell and "execution_count" in cell
            lines = [ln for ln in _source(cell).splitlines() if not ln.lstrip().startswith(("%", "!"))]
            compile("\n".join(lines), "jar cell", "exec")


def test_the_six_cases_cover_both_endpoints_and_the_chat_flows():
    cases = [_source(c) for c in _jar_cells()[2:]]
    assert '"/jar-distribute"' in cases[0] and "check_distribute" in cases[0]
    assert '"/jar-rebalance"' in cases[1] and "check_rebalance" in cases[1]
    assert "distribute_amount" in cases[2] and "Tiết kiệm" in cases[2] and "300 nghìn" in cases[2]
    assert "distribute_amount" in cases[3] and "600" in cases[3] and "400" in cases[3]
    assert "rebalance_jars" in cases[4] and "từ hũ" in cases[4] and "check_rebalance" in cases[4]
    assert "unallocated" in cases[5] and "ui is None" in cases[5]  # more than the unallocated money: no form
    for case in cases[2:]:
        assert '"mode"' not in case and "check_cover" not in case


def test_the_jar_notebook_uses_real_data_and_the_in_memory_chat_agent():
    setup = _source(_jar_cells()[1])
    assert "InMemorySaver" in setup and "TestClient" in setup and "fetch_jar_summary" in setup
    assert "SERVER_API_KEY" in setup and "CIF_0001" in setup
    for banned in ("STUBBED_SUMMARY", "_fake_get", "monkeypatch"):
        assert banned not in setup, banned
