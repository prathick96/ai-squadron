"""
tests/test_pipeline_api.py
Week 5 — Run registry unit tests + pipeline API endpoint tests.

Run: pytest tests/test_pipeline_api.py -v
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from packages.orchestrator.runner import RunRecord, RunRegistry


# ---------------------------------------------------------------------------
# RunRegistry unit tests (no FastAPI required)
# ---------------------------------------------------------------------------

def test_registry_start_returns_record():
    reg = RunRegistry()
    rec = reg.start("run_001", "ven_001", "PRODUCT")
    assert isinstance(rec, RunRecord)
    assert rec.run_id == "run_001"
    assert rec.venture_id == "ven_001"
    assert rec.department == "PRODUCT"
    assert rec.status == "STARTED"
    assert rec.current_stage == "RESEARCH_NODE"
    assert rec.completed_at is None


def test_registry_update_stage():
    reg = RunRegistry()
    reg.start("r1", "v1", "AUTO")
    reg.update_stage("r1", "CEO_NODE")
    rec = reg.get("r1")
    assert rec.current_stage == "CEO_NODE"
    assert rec.status == "RUNNING"


def test_registry_complete_marks_done():
    reg = RunRegistry()
    reg.start("r2", "v2", "MEDIA")
    reg.complete("r2", "END", "COMPLETED")
    rec = reg.get("r2")
    assert rec.status == "COMPLETED"
    assert rec.completed_at is not None
    assert rec.last_error is None


def test_registry_complete_with_error():
    reg = RunRegistry()
    reg.start("r3", "v3", "PRODUCT")
    reg.complete("r3", "FAILED", "FAILED", "LLM timeout")
    rec = reg.get("r3")
    assert rec.status == "FAILED"
    assert rec.last_error == "LLM timeout"


def test_registry_append_event():
    reg = RunRegistry()
    reg.start("r4", "v4", "PRODUCT")
    reg.append_event("r4", {"event_type": "RESEARCH_DOSSIER_READY"})
    reg.append_event("r4", {"event_type": "VENTURE_BRIEF_READY"})
    rec = reg.get("r4")
    assert len(rec.recent_events) == 2
    assert rec.recent_events[0]["event_type"] == "RESEARCH_DOSSIER_READY"


def test_registry_event_cap():
    reg = RunRegistry()
    reg.start("r5", "v5", "AUTO")
    for i in range(60):
        reg.append_event("r5", {"seq": i})
    rec = reg.get("r5")
    assert len(rec.recent_events) == 50   # capped at _MAX_EVENTS_PER_RUN
    assert rec.recent_events[-1]["seq"] == 59   # newest kept


def test_registry_list_recent_newest_first():
    reg = RunRegistry()
    for i in range(5):
        reg.start(f"run_{i:03d}", f"ven_{i:03d}", "AUTO")
    runs = reg.list_recent(3)
    assert len(runs) == 3
    assert runs[0].run_id == "run_004"  # newest first
    assert runs[1].run_id == "run_003"


def test_registry_eviction():
    reg = RunRegistry()
    # Override max to keep test fast
    import packages.orchestrator.runner as r_mod
    original_max = r_mod._MAX_RUNS
    r_mod._MAX_RUNS = 3
    reg2 = RunRegistry()
    for i in range(5):
        reg2.start(f"ev_{i}", f"v_{i}", "AUTO")
    assert len(reg2._runs) == 3
    r_mod._MAX_RUNS = original_max


def test_registry_active_count():
    reg = RunRegistry()
    reg.start("a1", "v1", "PRODUCT")
    reg.start("a2", "v2", "MEDIA")
    reg.complete("a2", "END", "COMPLETED")
    assert reg.active_count() == 1


def test_registry_get_unknown_returns_none():
    reg = RunRegistry()
    assert reg.get("nonexistent") is None


def test_registry_noop_on_unknown_run_id():
    reg = RunRegistry()
    # These should not raise
    reg.update_stage("ghost", "CEO_NODE")
    reg.complete("ghost", "END", "COMPLETED")
    reg.append_event("ghost", {"x": 1})


# ---------------------------------------------------------------------------
# API endpoint tests (uses FastAPI TestClient)
# ---------------------------------------------------------------------------

from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app, raise_server_exceptions=False)


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "active_pipeline_runs" in body
    assert body["version"] == "0.4.0"


def test_pipeline_run_endpoint_returns_run_id():
    with patch("apps.api.main._run_pipeline_background", new=AsyncMock(return_value=None)):
        resp = client.post("/api/pipeline/run", json={"department": "PRODUCT"})
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body
    assert "venture_id" in body
    assert body["status"] == "STARTED"
    assert body["venture_id"].startswith("ven_")


def test_pipeline_run_media_department():
    with patch("apps.api.main._run_pipeline_background", new=AsyncMock(return_value=None)):
        resp = client.post("/api/pipeline/run", json={"department": "MEDIA"})
    assert resp.status_code == 200


def test_pipeline_run_with_explicit_venture_id():
    with patch("apps.api.main._run_pipeline_background", new=AsyncMock(return_value=None)):
        resp = client.post(
            "/api/pipeline/run",
            json={"department": "AUTO", "venture_id": "ven_explicit_001"},
        )
    assert resp.status_code == 200
    assert resp.json()["venture_id"] == "ven_explicit_001"


def test_pipeline_status_found():
    from packages.orchestrator.runner import registry
    registry.start("status_test_run", "ven_status_test", "PRODUCT")

    resp = client.get("/api/pipeline/status_test_run")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == "status_test_run"
    assert body["venture_id"] == "ven_status_test"
    assert body["department"] == "PRODUCT"
    assert "current_stage" in body
    assert "recent_events" in body
    assert "event_count" in body


def test_pipeline_status_not_found():
    resp = client.get("/api/pipeline/nonexistent_run_xyz")
    assert resp.status_code == 404


def test_pipeline_recent_returns_list():
    from packages.orchestrator.runner import registry
    registry.start("recent_test_001", "ven_recent_1", "AUTO")

    resp = client.get("/api/pipeline/recent")
    assert resp.status_code == 200
    body = resp.json()
    assert "runs" in body
    assert isinstance(body["runs"], list)
    assert body["count"] == len(body["runs"])


def test_pipeline_recent_newest_first():
    from packages.orchestrator.runner import registry
    registry.start("order_a", "ven_a", "PRODUCT")
    registry.start("order_b", "ven_b", "MEDIA")

    resp = client.get("/api/pipeline/recent")
    runs = resp.json()["runs"]
    # order_b was started last — should appear first
    run_ids = [r["run_id"] for r in runs]
    assert run_ids.index("order_b") < run_ids.index("order_a")


# ---------------------------------------------------------------------------
# ElevenLabs client unit tests (no real API calls)
# ---------------------------------------------------------------------------

def test_elevenlabs_available_false_when_no_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    from packages.tools.elevenlabs_client import elevenlabs_available
    assert elevenlabs_available() is False


def test_elevenlabs_available_false_for_placeholder(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "your_elevenlabs_key_here")
    from packages.tools import elevenlabs_client
    # Re-check (function reads env at call time)
    assert elevenlabs_client.elevenlabs_available() is False


def test_elevenlabs_available_true_for_real_key(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "a" * 32)
    from packages.tools import elevenlabs_client
    assert elevenlabs_client.elevenlabs_available() is True


# ---------------------------------------------------------------------------
# Deployment agent — railway_available() gating
# ---------------------------------------------------------------------------

def test_railway_available_false_when_no_token(monkeypatch):
    monkeypatch.delenv("RAILWAY_TOKEN", raising=False)
    from packages.agents.product.deployment_agent import railway_available
    assert railway_available() is False


def test_railway_available_true_for_real_token(monkeypatch):
    monkeypatch.setenv("RAILWAY_TOKEN", "tok_" + "x" * 30)
    from packages.agents.product import deployment_agent
    assert deployment_agent.railway_available() is True


@pytest.mark.asyncio
async def test_deployment_agent_uses_mock_when_no_token(monkeypatch):
    monkeypatch.delenv("RAILWAY_TOKEN", raising=False)
    from packages.agents.product.deployment_agent import deployment_agent_node
    from packages.state.agent_state import init_state

    state = {
        **init_state("ven_deploy_test"),
        "security_clearance": {"is_compliant": True},
        "legal_clearance": {"is_cleared": True, "platforms_reviewed": ["railway"]},
        "build_artifact": {"build_path": ""},
    }

    with patch("packages.db.client.log_agent_event", return_value=None):
        result = await deployment_agent_node(state)

    receipt = result.get("deployment_receipt") or {}
    deps = receipt.get("deployments", [])
    assert len(deps) == 1
    assert "railway.app" in deps[0].get("url", "")


@pytest.mark.asyncio
async def test_voice_agent_uses_mock_when_no_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    from packages.agents.media.voice_agent import voice_agent_node
    from packages.state.agent_state import init_state

    state = {
        **init_state("ven_voice_test"),
        "script_package": {
            "hook": "Test hook",
            "body_sections": ["Body text here"],
            "cta": "Subscribe now",
            "estimated_duration_sec": 120,
            "word_count": 50,
            "platform": "youtube",
        },
    }

    with patch("packages.db.client.log_agent_event", return_value=None):
        result = await voice_agent_node(state)

    vp = result.get("voice_package") or {}
    assert vp.get("duration_sec", 0) > 0
    assert vp.get("human_likeness_score", 0) >= 0.85
    assert vp.get("platform") == "youtube"
