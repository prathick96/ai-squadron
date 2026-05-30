"""
tests/test_state.py
Unit tests for AgentState schema and helper functions.
Run: pytest tests/test_state.py -v
"""
from packages.state.agent_state import append_event, init_state, update_stage


def test_init_state_defaults():
    state = init_state()
    assert state["run_id"] is not None
    assert state["venture_id"].startswith("ven_")
    assert state["pipeline_stage"] == "RESEARCH_NODE"
    assert state["qa_retry_count"] == 0
    assert state["qa_max_retries"] == 3
    assert state["mrr_current"] == 0.0
    assert state["event_log"] == []
    assert state["venture_brief"] is None
    assert state["tech_spec"] is None


def test_init_state_with_venture_id():
    state = init_state("ven_finance_001")
    assert state["venture_id"] == "ven_finance_001"


def test_update_stage():
    state  = init_state()
    state2 = update_stage(state, "PRODUCT_NODE")
    assert state2["pipeline_stage"] == "PRODUCT_NODE"
    assert state["pipeline_stage"] == "RESEARCH_NODE"   # original not mutated


def test_append_event():
    state = init_state()
    event = {"event_type": "VENTURE_BRIEF_READY", "source_agent": "CEO_NICHE_SCOUT"}
    state2 = append_event(state, event)
    assert len(state2["event_log"]) == 1
    assert state2["event_log"][0]["event_type"] == "VENTURE_BRIEF_READY"
    assert "logged_at" in state2["event_log"][0]
    assert len(state["event_log"]) == 0  # original not mutated


def test_append_multiple_events():
    state = init_state()
    for i in range(5):
        state = append_event(state, {"seq": i, "event_type": f"EVENT_{i}"})
    assert len(state["event_log"]) == 5
    assert state["event_log"][4]["seq"] == 4


def test_qa_retry_counter():
    state = init_state()
    assert state["qa_retry_count"] == 0
    state = {**state, "qa_retry_count": state["qa_retry_count"] + 1}
    assert state["qa_retry_count"] == 1
    state = {**state, "qa_retry_count": state["qa_retry_count"] + 1}
    assert state["qa_retry_count"] == 2
    # Guard check
    assert state["qa_retry_count"] < state["qa_max_retries"] + 1


def test_state_immutability():
    """Verify state helpers return new dicts — never mutate in place."""
    original = init_state()
    original_id = id(original)
    modified = update_stage(original, "QA_NODE")
    assert id(modified) != original_id
    assert original["pipeline_stage"] == "RESEARCH_NODE"
