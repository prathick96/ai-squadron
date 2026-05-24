"""
apps/orchestrator/main.py
Entry point for the AI Squadron orchestrator.

Run modes:
  python -m apps.orchestrator.main --mode single   # Run one pipeline end-to-end
  python -m apps.orchestrator.main --mode watch    # Watch event bus and run continuously
  python -m apps.orchestrator.main --mode dry-run  # Validate graph compiles, no LLM calls

Usage from repo root (with venv active):
  python -m apps.orchestrator.main --mode dry-run
  python -m apps.orchestrator.main --mode single --venture-id ven_finance_001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Ensure repo root is on the path when running directly
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv()

from apps.orchestrator.graph import build_squadron_graph
from typing import Literal
from packages.db.client import is_supabase_connected
from packages.db.pipeline import (
    begin_pipeline_run,
    complete_pipeline_run,
    persist_event_log,
)
from packages.state.agent_state import init_state

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("squadron.main")


# ---------------------------------------------------------------------------
# Run modes
# ---------------------------------------------------------------------------

async def run_single_pipeline(
    venture_id: str | None = None,
    department: Literal["PRODUCT", "MEDIA", "AUTO"] = "AUTO",
) -> dict:
    """
    Execute one complete pipeline run from Research → Growth.
    Returns the final state dict.
    """
    graph  = build_squadron_graph(department)
    state  = init_state(venture_id)

    log.info("━" * 60)
    log.info("PIPELINE START | run_id=%s | venture_id=%s", state["run_id"], state["venture_id"])
    if is_supabase_connected():
        log.info("Storage: Supabase (live persistence)")
    else:
        log.info("Storage: local fallback — set SUPABASE_* in .env for Day 3")
    log.info("━" * 60)

    begin_pipeline_run(state["run_id"], state["venture_id"])
    final_state: dict = state
    run_status = "COMPLETED"
    error_message: str | None = None

    try:
        final_state = await graph.ainvoke(state)
        stage = final_state.get("pipeline_stage", "UNKNOWN")
        if stage == "MANUAL_REVIEW":
            run_status = "MANUAL_REVIEW"
        elif final_state.get("last_error"):
            run_status = "FAILED"
            error_message = final_state.get("last_error")
    except Exception as exc:
        run_status = "FAILED"
        error_message = str(exc)
        final_state = {**state, "last_error": str(exc), "pipeline_stage": "FAILED"}
        log.exception("Pipeline failed: %s", exc)
        raise
    finally:
        stage = final_state.get("pipeline_stage", "FAILED")
        n_events = persist_event_log(final_state)
        if n_events:
            log.info("Persisted %d events to Supabase", n_events)
        complete_pipeline_run(
            final_state.get("run_id", state["run_id"]),
            final_state.get("venture_id", state["venture_id"]),
            stage,
            run_status,
            error_message,
        )

    log.info("━" * 60)
    log.info("PIPELINE COMPLETE | stage=%s | events=%d",
             final_state.get("pipeline_stage"), len(final_state.get("event_log", [])))

    _print_pipeline_summary(final_state)
    return final_state


async def run_watch_mode() -> None:
    """
    Continuously poll the event bus for REVENUE_SCALE_SIGNAL events
    and trigger new pipelines automatically.
    Phase 1 stub — replace with full bus consumer in Phase 3.
    """
    log.info("Watch mode started — polling for REVENUE_SCALE_SIGNAL events")
    log.info("Press Ctrl+C to stop")
    try:
        while True:
            await asyncio.sleep(30)
            log.info("[WATCH] Heartbeat — no scale signals received yet")
    except asyncio.CancelledError:
        log.info("Watch mode stopped")


def run_dry_run(department: str = "AUTO") -> None:
    """
    Validate that the graph compiles and all imports resolve.
    No LLM calls made.
    """
    log.info("Running dry-run validation (department=%s)...", department)
    try:
        graph = build_squadron_graph(department)  # type: ignore[arg-type]
        state = init_state()
        log.info("✓ Graph compiled successfully")
        log.info("✓ AgentState initialised: run_id=%s", state["run_id"])
        log.info("✓ All agent imports resolved")
        log.info("✓ Dry run PASSED — system is ready for live execution")

        product_nodes = [
            "RESEARCH_NODE", "CEO_NODE", "PRODUCT_VP_NODE", "PRODUCT_MANAGER_NODE",
            "ENGINEERING_NODE", "QA_TECHNICAL_NODE", "LEGAL_NODE", "SECURITY_NODE",
            "ACCOUNT_DISTRIBUTION_NODE", "DEPLOYMENT_NODE", "MARKETING_SEO_NODE",
            "PRODUCT_GROWTH_NODE", "MANUAL_REVIEW_NODE",
        ]
        media_nodes = [
            "RESEARCH_NODE", "CEO_NODE", "MEDIA_VP_NODE", "SCRIPT_NODE", "VOICE_NODE",
            "VIDEO_NODE", "THUMBNAIL_NODE", "SEO_METADATA_NODE", "QA_COMPLIANCE_NODE",
            "LEGAL_NODE", "SECURITY_NODE", "ACCOUNT_DISTRIBUTION_NODE", "PUBLISHING_NODE",
            "ANALYTICS_NODE", "ANTI_BAN_NODE", "MEDIA_GROWTH_NODE", "MANUAL_REVIEW_NODE",
        ]
        nodes = product_nodes if department == "PRODUCT" else (
            media_nodes if department == "MEDIA" else product_nodes + media_nodes
        )
        log.info("\nExpected node registry (%s):", department)
        for node_name in dict.fromkeys(nodes):  # deduplicate while preserving order
            log.info("  ✓ %s", node_name)

    except Exception as exc:
        log.error("✗ Dry run FAILED: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_pipeline_summary(state: dict) -> None:
    sep = "─" * 60
    print(f"\n{sep}")
    print("  AI SQUADRON — PIPELINE SUMMARY")
    print(sep)
    print(f"  Run ID       : {state.get('run_id', 'N/A')}")
    print(f"  Venture ID   : {state.get('venture_id', 'N/A')}")
    print(f"  Final Stage  : {state.get('pipeline_stage', 'N/A')}")
    print(f"  QA Retries   : {state.get('qa_retry_count', 0)} / {state.get('qa_max_retries', 3)}")
    print(f"  Events Logged: {len(state.get('event_log', []))}")

    dossier = state.get("research_dossier") or {}
    if dossier:
        print(f"\n  Research Council:")
        print(f"    Primary niche : {dossier.get('recommended_primary_niche', 'N/A')}")
        print(f"    Confidence  : {dossier.get('council_confidence', 0):.2f}")
        print(f"    Mode          : {dossier.get('research_mode', 'N/A')}")

    brief = state.get("venture_brief") or {}
    if brief:
        print(f"\n  Venture Brief:")
        print(f"    Niche        : {brief.get('niche', 'N/A')}")
        print(f"    Type         : {brief.get('venture_type', 'N/A')}")
        print(f"    Go Decision  : {'✓ YES' if brief.get('go_decision') else '✗ NO'}")
        print(f"    Feasibility  : {brief.get('feasibility_score', 0):.2f}")

    receipt = state.get("deployment_receipt") or {}
    if receipt:
        deployments = receipt.get("deployments", [])
        print(f"\n  Deployments  : {len(deployments)} live")
        for d in deployments:
            if isinstance(d, dict):
                print(f"    → [{d.get('type')}] {d.get('url', 'N/A')}")

    if state.get("last_error"):
        print(f"\n  ⚠ Last Error : {state['last_error']}")
    if state.get("manual_review_reason"):
        print(f"\n  ⚠ Manual Rev : {state['manual_review_reason']}")

    print(f"{sep}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AI Squadron Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m apps.orchestrator.main --mode dry-run
  python -m apps.orchestrator.main --mode single
  python -m apps.orchestrator.main --mode single --venture-id ven_finance_001
  python -m apps.orchestrator.main --mode watch
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["single", "watch", "dry-run"],
        default="dry-run",
        help="Execution mode (default: dry-run)",
    )
    parser.add_argument(
        "--department",
        choices=["PRODUCT", "MEDIA", "AUTO"],
        default="AUTO",
        help="Department pipeline to run (default: AUTO — CEO decides)",
    )
    parser.add_argument(
        "--venture-id",
        default=None,
        help="Optional venture ID override for single mode",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Write final state JSON to this file path",
    )
    args = parser.parse_args()

    if args.mode == "dry-run":
        run_dry_run(args.department)

    elif args.mode == "single":
        final = asyncio.run(run_single_pipeline(args.venture_id, args.department))
        if args.output_json:
            with open(args.output_json, "w") as f:
                # Serialize state — drop non-serializable items gracefully
                json.dump(
                    {k: v for k, v in final.items() if isinstance(v, (str, int, float, bool, list, dict, type(None)))},
                    f, indent=2, default=str
                )
            log.info("State written to %s", args.output_json)

    elif args.mode == "watch":
        asyncio.run(run_watch_mode())


if __name__ == "__main__":
    main()
