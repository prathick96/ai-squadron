"""
packages/agents/growth_team.py
Growth Team Node — analytics aggregation, power-law filtering, feedback to CEO
Model: gemini-2.0-flash
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from packages.db.client import log_agent_event
from packages.schemas.events import (AgentID, EventType, GrowthReportPayload,
                                      PortfolioSummary, VenturePerformance, make_event)
from packages.state.agent_state import AgentState, GrowthSignals, append_event, update_stage
log = logging.getLogger(__name__)

async def growth_team_node(state: AgentState) -> AgentState:
    run_id, venture_id = state["run_id"], state["venture_id"]
    log.info("[GROWTH_NODE] Aggregating metrics | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "GROWTH_TEAM", "RUNNING", "Aggregating analytics")
    # Stub: replace with live YouTube Analytics + PostHog + Stripe pulls in Phase 3
    today = datetime.now(timezone.utc).date()
    period = f"{today.replace(day=1)}/{today}"
    payload = GrowthReportPayload(
        report_period=period,
        portfolio_summary=PortfolioSummary(
            total_ventures=1, live_ventures=1,
            total_mrr_usd=0.0, total_burn_usd=0.0, net_mrr_usd=0.0,
        ),
        top_performers=[VenturePerformance(
            venture_id=venture_id, mrr_usd=0.0, growth_rate_mom=0.0,
            primary_channel="youtube", signal="HOLD",
        )],
        bottom_performers=[],
        niche_recalibration={"boost_niches": [], "blacklist_niches": []},
        winning_content_formats={"youtube": "8-12min explainer"},
    )
    event = make_event(EventType.GROWTH_REPORT_READY, AgentID.GROWTH_TEAM, AgentID.CEO_NICHE_SCOUT,
                       payload, run_id, venture_id, "GROWTH_NODE")
    signals: GrowthSignals = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "GROWTH_TEAM", "SUCCESS")
    log.info("[GROWTH_NODE] ✓ Growth report ready")
    return append_event({**update_stage(state,"COMPLETE"), "growth_signals": signals}, event.model_dump())
