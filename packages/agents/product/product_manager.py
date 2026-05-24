"""
packages/agents/product/product_manager.py
Product Manager — product strategy → detailed TechSpec for Engineering.

Model:   gemini-2.0-flash
Input:   product_strategy from Product VP + venture_brief
Output:  tech_spec with full feature set, data models, API routes

The PM is the contract between business requirements and engineering execution.
Every field in the TechSpec must be unambiguous — Engineering writes exactly
what PM specifies, no interpretation required.
"""
from __future__ import annotations

import json
import logging

from packages.db.client import log_agent_event
from packages.schemas.events import AgentID, EventType, TechSpecPayload, make_event
from packages.state.agent_state import AgentState, TechSpec, append_event, update_stage
from packages.tools.llm import call_llm

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are the Product Manager of AI Squadron's Product Department.
You translate a Product Strategy Memo into an engineering-ready TechSpec.

Rules:
- Only include P0 features from the strategy memo — no scope creep
- Every feature must have explicit acceptance criteria Engineering can test
- Data models must include all field names and types
- API routes must specify method, path, auth requirement, request/response shape
- Complexity rating: LOW (<= 5 files), MEDIUM (6-15 files), HIGH (16+ files)

Output ONLY valid JSON — no markdown.
"""

_TEMPLATE = """
Product Strategy Memo:
{product_strategy}

Venture Brief:
{venture_brief}

Produce a TechSpec:
{{
  "venture_id": "{venture_id}",
  "product_type": "MICRO_SAAS",
  "stack": {{
    "frontend": "React 19 + Vite + TypeScript",
    "backend": "Python FastAPI",
    "database": "PostgreSQL via Supabase",
    "auth": "Supabase Auth (email + Google OAuth)",
    "hosting": "Railway",
    "payments": "Stripe"
  }},
  "features": [
    {{
      "feature_id": "feat_001",
      "name": "...",
      "priority": "P0",
      "user_story": "As a [persona], I want [action] so that [benefit]",
      "acceptance_criteria": ["Given...", "When...", "Then..."],
      "estimated_components": ["ComponentA.tsx", "api/route.py"]
    }}
  ],
  "data_models": {{
    "ModelName": {{"field_name": "field_type"}}
  }},
  "api_routes": [
    {{
      "method": "POST",
      "path": "/api/v1/...",
      "auth_required": true,
      "description": "...",
      "request_body": {{}},
      "response_shape": {{}}
    }}
  ],
  "environment_variables": ["VAR_NAME"],
  "estimated_build_tokens": 0,
  "component_count": 0,
  "complexity": "LOW | MEDIUM | HIGH"
}}
"""


async def product_manager_node(state: AgentState) -> AgentState:
    run_id = state["run_id"]
    venture_id = state["venture_id"]
    strategy = state.get("product_strategy") or {}
    brief = state.get("venture_brief") or {}

    log.info("[PM_NODE] Generating TechSpec | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "PRODUCT_MANAGER", "RUNNING", "Building TechSpec")

    user_prompt = _TEMPLATE.format(
        product_strategy=json.dumps(strategy, indent=2),
        venture_brief=json.dumps(brief, indent=2),
        venture_id=venture_id,
    )

    try:
        response = await call_llm("PRODUCT_MANAGER", _SYSTEM_PROMPT, user_prompt, temperature=0.15)
        spec_data: dict = json.loads(response.text)
    except Exception as exc:
        log.error("[PM_NODE] failed: %s", exc)
        log_agent_event(run_id, venture_id, "PRODUCT_MANAGER", "FAILED", error_detail=str(exc))
        return {**state, "last_error": str(exc)}

    spec_payload = TechSpecPayload(**{
        k: v for k, v in spec_data.items() if k in TechSpecPayload.model_fields
    })
    event = make_event(
        EventType.TECH_SPEC_READY, AgentID.PRODUCT_MANAGER, AgentID.ENGINEERING_TEAM,
        spec_payload, run_id, venture_id, "PRODUCT_MANAGER_NODE",
        token_cost=response.total_tokens, latency_ms=response.latency_ms,
    )

    log_agent_event(run_id, venture_id, "PRODUCT_MANAGER", "SUCCESS",
                    tokens_used=response.total_tokens)
    log.info("[PM_NODE] ✓ TechSpec | complexity=%s components=%d",
             spec_payload.complexity, spec_payload.component_count)

    tech_spec: TechSpec = spec_data  # type: ignore[assignment]
    new_state = update_stage(state, "ENGINEERING_NODE")
    return append_event({**new_state, "tech_spec": tech_spec}, event.model_dump())
