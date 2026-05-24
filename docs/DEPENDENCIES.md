# Dependencies Summary

**Last Updated:** May 23, 2026

## Single Requirements File

✅ **All dependencies consolidated into: `requirements.txt`**

This single file contains everything needed for AI Squadron:

### What's Included

1. **Core Dependencies (99 MB)**
   - LangGraph orchestration
   - LLM API clients (Anthropic, Google, OpenRouter)
   - Pydantic validation
   - Redis & Supabase
   - Tavily search & pytrends
   - APScheduler for cron jobs

2. **API & Dashboard (15 MB)**
   - FastAPI web framework
   - Uvicorn ASGI server

3. **Development Tools (50 MB)**
   - pytest (testing)
   - ruff (linting)
   - mypy (type checking)

4. **Revenue Integration (10 MB)**
   - Stripe payment processing

5. **Optional Future Integrations (commented out)**
   - ElevenLabs TTS (Phase 1 Week 5)
   - fal.ai Flux (Phase 1 Week 5)
   - YouTube Data API (Phase 1 Week 6)
   - TikTok API (Phase 2)
   - PostHog Analytics (Phase 2)
   - Playwright (Phase 2)

### Total Size
- **Current Phase 1:** ~174 MB
- **With Phase 2 optionals:** ~200+ MB

## Quick Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate          # Unix/macOS
.venv\Scripts\activate             # Windows PowerShell

# Upgrade pip
pip install --upgrade pip

# Install everything in one command
pip install -r requirements.txt
```

## Verification

After installation, verify with:

```bash
# Test dry-run (no API calls)
python -m apps.orchestrator.main --mode dry-run

# Run tests
pytest tests/ -v

# Run single pipeline
python -m apps.orchestrator.main --mode single
```

## What's NOT in requirements.txt

- **FFmpeg** (for Remotion video rendering)
  - macOS: `brew install ffmpeg`
  - Windows: `choco install ffmpeg`
  - Linux: `sudo apt-get install ffmpeg`

- **Node.js** (for Command Center React frontend)
  - Download from https://nodejs.org/ (v18+)
  - Then: `cd apps/command-center && npm install && npm run dev`

## Cost

- **Software:** $0 (all packages are free/open source)
- **APIs:** $0–100+/month (depends on usage; free tiers available)
- **Phase 1 total:** $0–10 (mostly free tier APIs)

## File Locations

```
ai-squadron/
├── requirements.txt          ← MAIN FILE (347 lines)
├── INSTALLATION.md           ← Detailed setup guide
├── PHASE_1_PROGRESS.md       ← Week-by-week checklist
├── PROJECT_OVERVIEW.md       ← Full architecture overview
├── pyproject.toml            ← Source of truth for dependencies
└── .env.example              ← Required environment variables
```

## Next Steps

1. ✅ Install: `pip install -r requirements.txt`
2. Configure `.env` file (copy from `.env.example`)
3. Start infrastructure: `docker compose -f infra/docker-compose.yml up -d`
4. Verify: `python -m apps.orchestrator.main --mode dry-run`
5. Run tests: `pytest tests/ -v`

---

**Note:** The modular `requirements-core.txt`, `requirements-dev.txt`, `requirements-api.txt`, and `requirements-revenue.txt` files have been removed in favor of this single consolidated file.
