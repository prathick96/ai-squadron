# AI Squadron — Installation Guide

**Last Updated:** May 23, 2026  
**Python Version:** 3.11+ required  
**OS:** Windows (PowerShell), macOS (zsh/bash), Linux (bash)

---

## Quick Start (5 minutes)

### 1. Clone Repository

```bash
git clone https://github.com/prathick96/ai-squadron.git
cd ai-squadron
```

### 2. Create Virtual Environment

```powershell
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

**Option A: Full Install (Recommended)**
```bash
pip install -r requirements.txt
```

**Option B: Using pyproject.toml (Alternative)**
```bash
pip install -e ".[dev,api,revenue]"
```

**Option C: Minimal Install**
```bash
pip install -r requirements-core.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in:
#   GEMINI_API_KEY=aiz...
#   ANTHROPIC_API_KEY=sk-ant-...
```

### 5. Start Infrastructure

```bash
docker compose -f infra/docker-compose.yml up -d
# Waits for PostgreSQL, Redis, RedisInsight to be healthy
```

### 6. Validate Installation

```bash
# Dry-run (no API calls)
python -m apps.orchestrator.main --mode dry-run

# Run tests
pytest tests/ -v

# Run one pipeline
python -m apps.orchestrator.main --mode single
```

---

## Installation Options by Use Case

### Scenario 1: I want to run the orchestrator only

```bash
pip install -r requirements-core.txt
python -m apps.orchestrator.main --mode single
```

**Size:** ~200 MB  
**Time:** 2-3 minutes  
**Use Case:** Pipeline execution, event processing

---

### Scenario 2: I want to develop and test

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
ruff check packages/ apps/
mypy packages/ --strict
```

**Size:** ~250 MB  
**Time:** 3-5 minutes  
**Use Case:** Code changes, running unit tests, linting

---

### Scenario 3: I want the full Command Center dashboard

```bash
pip install -r requirements-api.txt
uvicorn apps.api.main:app --reload --port 8000

cd apps/command-center
npm install
npm run dev
# Open http://localhost:5173
```

**Size:** ~300 MB (Python) + ~500 MB (node_modules)  
**Time:** 5-7 minutes  
**Use Case:** Live dashboard, agent monitoring

---

### Scenario 4: I need Stripe integration (Week 8+)

```bash
pip install -r requirements-revenue.txt
python apps/revenue-engine/main.py --mode once
```

**Size:** ~210 MB  
**Time:** 2-3 minutes  
**Use Case:** Revenue sync, MRR tracking, confidence scoring

---

### Scenario 5: I want everything (full development)

```bash
pip install -r requirements.txt
pip install -e ".[dev,api,revenue]"

docker compose -f infra/docker-compose.yml up -d
python -m apps.orchestrator.main --mode dry-run
pytest tests/ -v
```

**Size:** ~500 MB  
**Time:** 10-15 minutes  
**Use Case:** Complete local development, all features available

---

## Dependency Breakdown

### Core (Always Required)

| Package | Version | Purpose | Size |
|---------|---------|---------|------|
| langgraph | >=0.2.0 | Graph orchestration | 15 MB |
| langchain-core | >=0.3.0 | Base abstractions | 8 MB |
| langchain-google-genai | >=2.0.0 | Gemini integration | 3 MB |
| anthropic | >=0.40.0 | Claude API client | 5 MB |
| google-generativeai | >=0.8.0 | Google AI Studio | 4 MB |
| google-genai | >=1.0.0 | Alternative Google client | 2 MB |
| pydantic | >=2.9.0 | Data validation | 12 MB |
| pydantic-settings | >=2.6.0 | Config management | 2 MB |
| redis | >=5.0.0 | Redis client | 3 MB |
| supabase | >=2.10.0 | Supabase Python SDK | 5 MB |
| httpx | >=0.27.0 | Async HTTP | 6 MB |
| tenacity | >=9.0.0 | Retry logic | 2 MB |
| structlog | >=24.4.0 | Structured logging | 3 MB |
| pytrends | >=4.9.2 | Google Trends API | 1 MB |
| tavily-python | >=0.5.0 | Tavily search API | 1 MB |
| python-dotenv | >=1.0.0 | .env parser | 1 MB |
| apscheduler | >=3.10.0 | Task scheduling | 2 MB |
| **Total Core** | — | — | **~99 MB** |

### API & Dashboard

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.115.0 | REST framework |
| uvicorn | >=0.32.0 | ASGI server |
| **Total API** | — | **~15 MB** |

### Development

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | >=8.0.0 | Test runner |
| pytest-asyncio | >=0.24.0 | Async test support |
| pytest-cov | >=6.0.0 | Coverage reporting |
| ruff | >=0.8.0 | Fast linter |
| mypy | >=1.13.0 | Type checker |
| **Total Dev** | — | **~50 MB** |

### Revenue (Optional)

| Package | Version | Purpose |
|---------|---------|---------|
| stripe | >=11.0.0 | Stripe API client |
| **Total Revenue** | — | **~10 MB** |

### Frontend (React Dashboard)

```bash
cd apps/command-center
npm install
# Installs: react, react-dom, recharts, vite, typescript, etc.
# Size: ~500 MB (node_modules)
```

---

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'langgraph'`

**Solution:**
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

### Issue: `redis.exceptions.ConnectionError`

**Solution:** Start Redis with Docker Compose:
```bash
docker compose -f infra/docker-compose.yml up -d redis
```

Or set `REDIS_URL` to skip Redis (dev mode falls back to asyncio.Queue):
```bash
export REDIS_URL=
python -m apps.orchestrator.main --mode single
```

---

### Issue: `supabase.exceptions.APIError: Unauthorized`

**Solution:** Check environment variables:
```bash
echo $SUPABASE_SERVICE_ROLE_KEY  # Should not be empty
# If empty, set in .env and reload:
source .env
```

Or disable Supabase for testing:
```bash
unset SUPABASE_URL
python -m apps.orchestrator.main --mode dry-run  # Uses NullDB fallback
```

---

### Issue: `pip install -r requirements.txt` hangs or fails

**Solution:** Update pip, setuptools, wheel:
```bash
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt --no-cache-dir
```

Or use pyproject.toml instead:
```bash
pip install -e .
pip install -e ".[dev,api]"
```

---

### Issue: `pytest` cannot find modules

**Solution:** Ensure you're in the repo root and .venv is activated:
```bash
cd /path/to/ai-squadron
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pytest tests/ -v
```

---

### Issue: `npm install` in command-center fails

**Solution:** Use Node.js 18+:
```bash
node --version  # Should be v18.0.0+
npm install --legacy-peer-deps
```

---

## Verification Checklist

After installation, verify each component:

```bash
# 1. Python environment
python --version              # Should be 3.11+
pip list | grep langgraph    # Should list langgraph

# 2. Core packages
python -c "import langgraph; print('✓ langgraph')"
python -c "import pydantic; print('✓ pydantic')"
python -c "import redis; print('✓ redis')"

# 3. LLM clients
python -c "import anthropic; print('✓ anthropic')"
python -c "import google.generativeai; print('✓ google-generativeai')"

# 4. Database
python -c "import supabase; print('✓ supabase')"

# 5. Graph compilation
python -m apps.orchestrator.main --mode dry-run

# 6. Tests
pytest tests/ -v --tb=short

# 7. API (optional)
python -c "import fastapi; print('✓ fastapi')"

# 8. Revenue (optional)
python -c "import stripe; print('✓ stripe')"
```

---

## Updating Dependencies

### Check for outdated packages

```bash
pip list --outdated
```

### Update all packages safely

```bash
pip install --upgrade -r requirements.txt
```

### Update specific package

```bash
pip install --upgrade langgraph
```

### Lock versions (for production)

```bash
pip freeze > requirements-frozen.txt
pip install -r requirements-frozen.txt
```

---

## Docker Alternative

If you prefer containerized installation:

```bash
docker build -t ai-squadron:latest .
docker run -it --env-file .env ai-squadron:latest python -m apps.orchestrator.main --mode single
```

*(Dockerfile not yet in repo; create if needed)*

---

## Platform-Specific Notes

### Windows (PowerShell)

```powershell
# Activate venv
.venv\Scripts\Activate.ps1

# If execution policy blocks script
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Run commands
python -m apps.orchestrator.main --mode single
```

### macOS (Intel vs Apple Silicon)

```bash
# Intel (x86_64)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Apple Silicon (arm64)
# Most packages have arm64 wheels; if not:
pip install --target .venv/lib/python3.11/site-packages --platform macosx_11_0_arm64 package-name
```

### Linux (Debian/Ubuntu)

```bash
# Install system dependencies
sudo apt-get install python3.11 python3.11-venv python3.11-dev libpq-dev

# Create venv with system Python
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Cost of Dependencies

| Category | Cost | Notes |
|----------|------|-------|
| Python packages | **$0** | All free/open source |
| Docker | **$0** | Free community edition |
| LLM APIs | **$0–100+/mo** | Depends on usage; free tier available |
| Supabase DB | **$0** | Free tier covers Phase 1 (500 MB) |
| Redis | **$0** | Self-hosted with Docker |
| **Total Setup** | **$0** | All software is free; only LLM APIs incur cost |

---

## Next Steps After Installation

1. **Configure .env** (see .env.example)
2. **Start infrastructure** (`docker compose up -d`)
3. **Run dry-run** (`python -m apps.orchestrator.main --mode dry-run`)
4. **Run tests** (`pytest tests/ -v`)
5. **Start Command Center** (`uvicorn apps.api.main:app --reload --port 8000`)
6. **Read docs** (see docs/AGENTS.md, docs/ROADMAP.md)

---

## Support

- **Questions?** Check docs/ folder
- **Errors?** Run `pytest tests/ -v` to identify failing tests
- **Installation issues?** See Troubleshooting section above

---

**Happy coding! 🚀**
