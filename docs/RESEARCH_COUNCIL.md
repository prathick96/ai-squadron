# Market Research Council (Kimi + CEO)

## Flow

```
RESEARCH_NODE
  ├── Trend snapshot (pytrends/Tavily — stub today)
  ├── Kimi Scout: Opportunity  ─┐
  ├── Kimi Scout: Skeptic      ─┼─ parallel
  ├── Kimi Scout: Execution    ─┘
  ├── Kimi Debate Synthesizer
  └── RESEARCH_DOSSIER_READY → CEO_NODE

CEO_NODE (Gemini 2.5 Pro)
  └── VENTURE_BRIEF_READY → PRODUCT_NODE → …
```

CEO is the **only** agent that sets `go_decision`.

## Configuration

```bash
# .env — get key from https://openrouter.ai/keys
OPENROUTER_API_KEY=sk-or-...
KIMI_MODEL=moonshotai/kimi-k2.5
```

Without `OPENROUTER_API_KEY`, the council runs in **mock mode** (deterministic dossier for dev/tests).

## Scout roles

| Scout | Lens |
|-------|------|
| Opportunity | RPM, growth, monetization fit |
| Skeptic | Saturation, policy, time-to-revenue risk |
| Execution | Build complexity, autonomous pipeline fit |

## Antigravity (developer only)

Use Antigravity to build integrations (Tavily, Stripe, etc.). It does **not** run inside the LangGraph pipeline.

## Commands

```bash
python -m apps.orchestrator.main --mode dry-run
python -m apps.orchestrator.main --mode single
pytest tests/test_market_research.py -v
```
