"""
packages/agents/global_approach.py
Global Approach Node — regional localisation and timezone-aware scheduling
Model: gemini-2.0-flash (strong multilingual performance)
"""
from __future__ import annotations
import json, logging
from packages.db.client import log_agent_event
from packages.schemas.events import (AgentID, EventType, LocalizationCompletePayload,
                                      LocalizationEntry, make_event)
from packages.state.agent_state import AgentState, LocalizationMap, append_event, update_stage
from packages.tools.llm import call_llm
log = logging.getLogger(__name__)

_REGIONS = [
    {"region": "IN", "language": "hi", "post_time_local": "20:00 IST", "tz_offset": "+5:30"},
    {"region": "US", "language": "es", "post_time_local": "18:00 CST", "tz_offset": "-6:00"},
]

async def global_approach_node(state: AgentState) -> AgentState:
    run_id, venture_id = state["run_id"], state["venture_id"]
    log.info("[GLOBAL_NODE] Localising content | venture=%s", venture_id)
    log_agent_event(run_id, venture_id, "GLOBAL_TEAM", "RUNNING", "Generating localised variants")
    content = state.get("content_package") or {}
    seo     = content.get("seo_metadata") or {}
    title   = seo.get("title", "AI Tool Overview") if isinstance(seo, dict) else "AI Tool Overview"
    localizations: list[LocalizationEntry] = []
    for region_cfg in _REGIONS:
        try:
            resp = await call_llm(
                "GLOBAL_TEAM",
                "You translate and culturally adapt YouTube video titles. Output ONLY the adapted title string. No quotes, no explanation.",
                f"Translate this title to {region_cfg['language']} (region: {region_cfg['region']}): {title}",
                temperature=0.3)
            adapted_title = resp.text.strip()
        except Exception:
            adapted_title = title
        localizations.append(LocalizationEntry(
            region=region_cfg["region"], language=region_cfg["language"],
            platform="youtube", adapted_title=adapted_title,
            post_time_local=region_cfg["post_time_local"],
            deployment_status="SCHEDULED",
        ))
    payload = LocalizationCompletePayload(
        venture_id=venture_id, localizations=localizations,
        regions_covered=[r["region"] for r in _REGIONS],
        estimated_incremental_reach=500_000,
    )
    event = make_event(EventType.LOCALIZATION_COMPLETE, AgentID.GLOBAL_TEAM, AgentID.GROWTH_TEAM,
                       payload, run_id, venture_id, "GLOBAL_NODE")
    loc_map: LocalizationMap = payload.model_dump()  # type: ignore[assignment]
    log_agent_event(run_id, venture_id, "GLOBAL_TEAM", "SUCCESS")
    log.info("[GLOBAL_NODE] ✓ %d localisations ready", len(localizations))
    return append_event({**update_stage(state,"GROWTH_NODE"), "localization_map": loc_map}, event.model_dump())
