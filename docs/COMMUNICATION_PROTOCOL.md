# Communication & Orchestration Protocol

## Design principles

1. **Event-first:** Every agent action emits a typed `EventEnvelope` to the bus and appends to `AgentState.event_log`.
2. **Async decoupling:** Engineering and Content can run in parallel in Phase 3; Phase 0 runs sequential post-deploy nodes to avoid LangGraph state races.
3. **Single source of truth:** `AgentState` is the pipeline memory; Supabase `events` table is the durable audit trail.
4. **Idempotent retries:** `correlation_id` ties retry attempts; `retry_count` increments on QA failures only.

## Event envelope (all messages)

```json
{
  "event_id": "uuid",
  "event_type": "QA_FAILED",
  "schema_version": "1.0.0",
  "source_agent": "QA_AUDITOR",
  "target_agent": "ENGINEERING_TEAM",
  "correlation_id": "uuid",
  "priority": "HIGH",
  "timestamp": "2026-05-19T12:00:00+00:00",
  "retry_count": 1,
  "payload": { },
  "metadata": {
    "run_id": "uuid",
    "venture_id": "ven_finance_001",
    "pipeline_stage": "QA_NODE",
    "token_cost": 420,
    "latency_ms": 1800
  }
}
```

Implementation: `packages/schemas/events.py` (`EventEnvelope`, `make_event()`).

## Transport layers

| Environment | Bus | Persistence |
|-------------|-----|-------------|
| Local dev | `asyncio.Queue` in-process | NullDB or local Postgres |
| Production | Redis Streams (`packages/bus/event_bus.py`) | Supabase Postgres |

Publish pattern:

```python
from packages.bus.event_bus import EventBus
from packages.schemas.events import make_event, EventType, AgentID

event = make_event(
    EventType.BUILD_COMPLETE,
    AgentID.ENGINEERING_TEAM,
    AgentID.QA_AUDITOR,
    payload,
    run_id, venture_id, "ENGINEERING_NODE",
)
await bus.publish(event)
```

## LangGraph vs bus

- **LangGraph** orchestrates node order, conditional edges, and QA retry loops (`apps/orchestrator/graph.py`).
- **Event bus** notifies external services (Revenue Engine, Command Center WebSocket, future workers).

The graph is authoritative for *when* a node runs; the bus is authoritative for *who else needs to know*.

## Conditional edges (critical paths)

### `go_decision_edge` (after CEO)
- `go_decision=true` → PRODUCT_NODE  
- else → END (venture never allocated engineering tokens)

### `product_routing_edge` (after Product)
- `MICRO_SAAS` → ENGINEERING_NODE  
- `MEDIA_CHANNEL` | `AFFILIATE_SITE` → CONTENT_NODE  

### `qa_routing_edge` (after QA)
```
passed? ──yes──► SECURITY_NODE
  │
  no
  ├─ retry_count >= max_retries ──► MANUAL_REVIEW_NODE
  └─ qa_target == engineering ──► ENGINEERING_NODE
      qa_target == content     ──► CONTENT_NODE
```

### Post-security chain
```
SECURITY → ACCOUNT_DISTRIBUTION → DEPLOYMENT → MARKETING → GLOBAL → GROWTH → END
```

## State artifact flow

```
venture_brief → tech_spec → build_artifact | content_package
              → qa_report → security_clearance → account_distribution_plan
              → deployment_receipt → campaign_plan → localization_map → growth_signals
```

Factory: `packages/state/agent_state.py` → `init_state()`.

## Revenue Engine integration

Revenue Engine does **not** mutate LangGraph mid-run. It:
1. Reads `revenue_ledger` + `ventures.status`
2. Publishes `REVENUE_SCALE_SIGNAL` or `REVENUE_KILL_SIGNAL`
3. Command Center displays signals; human or future Orchestrator agent applies kills

## Command Center subscriptions

Dashboard API (`apps/api`) polls:
- `agent_logs` — live grid
- `events` — recent bus activity
- `revenue_ledger` — MRR/ARR ticker
- `ventures` — 450-slot portfolio grid
- Mock trend overlay when external APIs not wired

WebSocket `/api/ws/live` pushes ticker + agent status deltas every 5s.

## Failure modes

| Failure | Behavior |
|---------|----------|
| LLM timeout | Tenacity retry 3x (`packages/tools/llm.py`) |
| QA fail | Critique back to origin agent, max 3 loops |
| Security violation | Pipeline stops; no deployment |
| Manual review | Human notification via dashboard CRITICAL alert |
| Kill signal | Venture status → KILLED; decommission Vercel project |

## Versioning

`schema_version` on every envelope. Breaking payload changes require bump + migration in `packages/schemas/events.py` and a one-time backfill script.
