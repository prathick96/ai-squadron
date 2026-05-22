"""
apps/orchestrator/nodes/all_nodes.py
──────────────────────────────────────
All 11 agent nodes.

Day 1–7: All nodes are Stubs — they pass state through unchanged.
Each stub is a fully-wired class inheriting from StubNode so the graph
compiles and runs end-to-end without any real API calls.

Replacement plan:
  Week 2:  CEO_NODE, PRODUCT_NODE (real Gemini calls)
  Week 3:  ENGINEERING_NODE (real Claude calls), QA_NODE (real Playwright)
  Week 4:  CONTENT_NODE (real ElevenLabs + Remotion)
  Week 5:  SECURITY_NODE, DEPLOYMENT_NODE
  Week 6:  MARKETING_NODE, GLOBAL_NODE, GROWTH_NODE
  Revenue Engine is a separate service — not in this graph.

To replace a stub with a real implementation:
  1. Create packages/agents/{agent_name}.py with the full logic
  2. Import it here and swap the class body
  3. The graph.py file does NOT change — nodes are hot-swappable
"""

from __future__ import annotations

from apps.orchestrator.nodes.base_node import StubNode


class CEONicheScoutNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 2):
    - Calls Gemini 2.5 Pro with Google Trends + Tavily + Reddit data
    - Produces a validated VentureBrief
    - Writes venture to Supabase ventures table
    - Sets state["venture_brief"]
    """
    agent_id = "CEO_NODE"
    model = "gemini-2.5-pro-preview-06-05"


class ProductTeamNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 2):
    - Calls Gemini 2.0 Flash with VentureBrief
    - Produces TechSpec (for MICRO_SAAS) or ContentStrategy (for MEDIA_CHANNEL)
    - Sets state["tech_spec"]
    """
    agent_id = "PRODUCT_NODE"
    model = "gemini-2.0-flash"


class EngineeringTeamNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 3):
    - Calls Claude Sonnet with TechSpec
    - Generates full React 19 + Vite project with vitest tests
    - Runs `vite build` and captures exit code + bundle size
    - On retry: reads critique_log from state, patches only failing modules
    - Sets state["build_artifact"]
    """
    agent_id = "ENGINEERING_NODE"
    model = "claude-sonnet-4-6"


class ContentTeamNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 4):
    - Calls Gemini Flash for script generation
    - Calls ElevenLabs for voiceover (human_likeness_score >= 0.85)
    - Runs Remotion + FFmpeg for video assembly
    - Calls fal.ai Flux for thumbnail generation
    - On retry: regenerates only the failed component
    - Sets state["content_package"]
    """
    agent_id = "CONTENT_NODE"
    model = "gemini-2.0-flash"


class QAAuditorNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 3):
    - Engineering path: Playwright headless tests, bundle size, API smoke test
    - Content path: AudD copyright scan, human_likeness threshold, metadata validation
    - Emits QA_PASSED → state["qa_report"]["is_passed"] = True
    - Emits QA_FAILED → state["qa_report"]["is_passed"] = False + critique_log
    - Increments state["qa_retry_count"] on failure
    - Sets state["qa_report"]

    CRITICAL: The conditional edge routing logic in graph.py depends on
    state["qa_report"]["is_passed"] and state["qa_retry_count"]. These
    fields MUST be set correctly even in stub mode for routing tests.
    This stub sets is_passed=True to allow the graph to flow to SECURITY_NODE.
    """
    agent_id = "QA_NODE"
    model = "claude-haiku-4-5-20251001"

    async def execute(self, state):
        """
        Override stub to inject a passing QA report so the conditional
        edge routes correctly during Day 1 end-to-end testing.
        """
        from packages.state.agent_state import append_event
        import logging
        logger = logging.getLogger(__name__)

        venture_id = state.get("venture_id", "unknown")
        logger.info("[QA_NODE:STUB] Injecting passing QA report for venture_id=%s", venture_id)

        # Inject a minimal passing QA report so qa_routing_edge works
        state["qa_report"] = {
            "venture_id": venture_id,
            "artifact_type": "BUILD",
            "is_passed": True,
            "checks_run": ["stub_passthrough"],
            "checks_passed": 1,
            "checks_failed": 0,
            "qa_report_path": f"/reports/{venture_id}_stub.json",
        }

        entry = self.make_log_entry(
            state=state,
            event_type="QA_PASSED",
            target_agent="SECURITY_NODE",
            payload_summary=f"[STUB] QA passed for venture_id={venture_id}",
        )
        state["event_log"] = state.get("event_log", []) + [entry]
        return state


class SecurityAgentNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 5):
    - Reads ToS snapshots from DB, validates artifact against current rules
    - Assigns proxy profile + fingerprint profile per platform account
    - Generates posting schedule with jitter
    - Sets state["security_clearance"]
    """
    agent_id = "SECURITY_NODE"
    model = "gemini-2.0-flash"


class DeploymentTeamNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 5):
    - Railway Deploy API: triggers deploy, polls for completion, captures URL
    - Platform APIs: YouTube Data API v3, TikTok Content Posting API, Instagram Graph API
    - Runs 5-minute post-deployment smoke test
    - Sets state["deployment_receipt"]
    """
    agent_id = "DEPLOYMENT_NODE"
    model = "none"


class MarketingTeamNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 6):
    - Programmatic SEO: generates 50–200 landing pages per SaaS product
    - Cross-platform repurposing: YouTube → TikTok + Instagram + X
    - Email drip: Resend API sequence setup
    - Sets state["campaign_plan"]
    """
    agent_id = "MARKETING_NODE"
    model = "gemini-2.0-flash"


class GlobalApproachNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 6):
    - Gemini Flash multilingual translation with cultural adaptation
    - Timezone-aware posting schedule per target region
    - Generates localized thumbnail variants
    - Sets state["localization_map"]
    """
    agent_id = "GLOBAL_NODE"
    model = "gemini-2.0-flash"


class GrowthTeamNode(StubNode):
    """
    REAL IMPLEMENTATION TARGET (Week 6):
    - Aggregates metrics from YouTube Analytics API, PostHog, GA4, Stripe
    - Computes retention curves, CTR by variant, SaaS conversion rates
    - Emits GROWTH_REPORT_READY back to CEO to close the feedback loop
    - Sets state["growth_signals"]
    """
    agent_id = "GROWTH_NODE"
    model = "gemini-2.0-flash"


class ManualReviewNode(StubNode):
    """
    Terminal node. Reached when qa_retry_count >= qa_max_retries.
    - Writes MANUAL_REVIEW_REQUIRED event to DB
    - Sends alert (Resend email / Slack webhook)
    - Sets venture status to 'manual_review' in DB
    - Pipeline ends here — human must intervene
    """
    agent_id = "MANUAL_REVIEW_NODE"
    model = "none"

    async def execute(self, state):
        from packages.state.agent_state import append_event
        import logging
        logger = logging.getLogger(__name__)

        venture_id = state.get("venture_id", "unknown")
        retry_count = state.get("qa_retry_count", 0)

        logger.warning(
            "[MANUAL_REVIEW_NODE] venture_id=%s escalated after %d QA failures. "
            "Human intervention required.",
            venture_id, retry_count,
        )

        entry = self.make_log_entry(
            state=state,
            event_type="MANUAL_REVIEW_REQUIRED",
            target_agent="BROADCAST",
            payload_summary=(
                f"venture_id={venture_id} escalated after {retry_count} QA failures. "
                "Manual review required."
            ),
            success=False,
        )
        state["event_log"] = state.get("event_log", []) + [entry]

        # TODO (Week 5): persist to DB + send Resend alert email
        return state
