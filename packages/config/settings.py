"""
packages/config/settings.py
Central settings object — reads from environment variables.
Import this anywhere instead of calling os.getenv() directly.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
load_dotenv()

class Settings:
    # LLMs
    GEMINI_API_KEY:           str  = os.getenv("GEMINI_API_KEY", "")
    ANTHROPIC_API_KEY:        str  = os.getenv("ANTHROPIC_API_KEY", "")

    # Supabase
    SUPABASE_URL:             str  = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY:        str  = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY:str  = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

    # Redis / Event Bus
    REDIS_URL:                str  = os.getenv("REDIS_URL", "redis://localhost:6379")
    REDIS_STREAM_NAME:        str  = os.getenv("REDIS_STREAM_NAME", "squadron:events")
    REDIS_CONSUMER_GROUP:     str  = os.getenv("REDIS_CONSUMER_GROUP", "squadron:workers")

    # Market Intelligence
    TAVILY_API_KEY:           str  = os.getenv("TAVILY_API_KEY", "")
    OPENROUTER_API_KEY:       str  = os.getenv("OPENROUTER_API_KEY", "")
    OPENROUTER_BASE_URL:      str  = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    DEEPINFRA_API_KEY:        str  = os.getenv("DEEPINFRA_API_KEY", "")
    DEEPINFRA_BASE_URL:       str  = os.getenv("DEEPINFRA_BASE_URL", "https://api.deepinfra.com/v1/openai")
    MOONSHOT_API_KEY:         str  = os.getenv("MOONSHOT_API_KEY", "")
    MOONSHOT_BASE_URL:        str  = os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.cn/v1")
    KIMI_MODEL:               str  = os.getenv("KIMI_MODEL", "moonshotai/kimi-k2.6")
    DATAFORSEO_LOGIN:         str  = os.getenv("DATAFORSEO_LOGIN", "")
    DATAFORSEO_PASSWORD:      str  = os.getenv("DATAFORSEO_PASSWORD", "")

    # Media APIs
    ELEVENLABS_API_KEY:       str  = os.getenv("ELEVENLABS_API_KEY", "")
    FAL_KEY:                  str  = os.getenv("FAL_KEY", "")

    # Infrastructure
    VERCEL_TOKEN:             str  = os.getenv("VERCEL_TOKEN", "")
    STRIPE_SECRET_KEY:        str  = os.getenv("STRIPE_SECRET_KEY", "")

    # App behaviour
    ENVIRONMENT:              str  = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL:                str  = os.getenv("LOG_LEVEL", "INFO")
    MAX_PARALLEL_PIPELINES:   int  = int(os.getenv("MAX_PARALLEL_PIPELINES", "5"))
    QA_MAX_RETRIES:           int  = int(os.getenv("QA_MAX_RETRIES", "3"))
    KILL_THRESHOLD_MRR:       float= float(os.getenv("KILL_THRESHOLD_MRR", "50.0"))
    KILL_THRESHOLD_DAYS:      int  = int(os.getenv("KILL_THRESHOLD_DAYS", "90"))
    SCALE_THRESHOLD_MRR:      float= float(os.getenv("SCALE_THRESHOLD_MRR", "200.0"))
    KILL_EARLY_DAYS:          int  = int(os.getenv("KILL_EARLY_DAYS", "60"))
    KILL_EARLY_VISITS:        int  = int(os.getenv("KILL_EARLY_VISITS", "100"))
    MONTHLY_BURN_USD:         float= float(os.getenv("MONTHLY_BURN_USD", "47.20"))
    ADSENSE_REPORT_CSV_PATH:  str  = os.getenv("ADSENSE_REPORT_CSV_PATH", "")
    POSTHOG_API_KEY:          str  = os.getenv("POSTHOG_API_KEY", "")

    def validate(self) -> list[str]:
        """Returns list of missing required keys. Empty list = ready to run."""
        missing = []
        if not self.GEMINI_API_KEY:    missing.append("GEMINI_API_KEY")
        if not self.ANTHROPIC_API_KEY: missing.append("ANTHROPIC_API_KEY")
        if not self.SUPABASE_URL:      missing.append("SUPABASE_URL (optional for Phase 0)")
        return missing

settings = Settings()
