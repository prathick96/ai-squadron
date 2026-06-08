"""
apps/orchestrator/graph.py
AI Squadron graph dispatcher — PRODUCT pipeline only.

Media pipeline has been archived. All runs are SaaS product builds.

Usage:
  from apps.orchestrator.graph import build_squadron_graph
  graph = build_squadron_graph(department="PRODUCT")
"""
from __future__ import annotations

import logging
from typing import Literal

log = logging.getLogger(__name__)


def build_squadron_graph(
    department: Literal["PRODUCT", "MEDIA", "AUTO"] = "PRODUCT",
) -> object:
    """
    Return the compiled LangGraph for the given department.
    MEDIA is archived — all departments now route to the PRODUCT pipeline.
    """
    from apps.orchestrator.product_graph import build_product_graph
    if department == "MEDIA":
        log.warning("[graph] MEDIA department requested but is archived — using PRODUCT pipeline")
    return build_product_graph()
