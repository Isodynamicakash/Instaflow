"""
InstaFlow — Configuration
Loads all environment variables and provides app-wide settings.
Updated for Zernio API integration.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── Zernio (New - Primary) ──
    ZERNIO_API_KEY: str = os.getenv("ZERNIO_API_KEY", "")
    ZERNIO_WEBHOOK_SECRET: str = os.getenv("ZERNIO_WEBHOOK_SECRET", "instaflow_verify_2024")
    ZERNIO_API_BASE: str = "https://api.zernio.com/v1"

    # ── Instagram (Legacy - Graph API, kept for compatibility) ──
    IG_ACCESS_TOKEN: str = os.getenv("IG_ACCESS_TOKEN", "")
    IG_USER_ID: str = os.getenv("IG_USER_ID", "")
    META_APP_ID: str = os.getenv("META_APP_ID", "")
    META_APP_SECRET: str = os.getenv("META_APP_SECRET", "")
    IG_WEBHOOK_VERIFY_TOKEN: str = os.getenv("IG_WEBHOOK_VERIFY_TOKEN", "instaflow_verify_2024")

    # LLM
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # WhatsApp (Phase 2)
    WA_PHONE_NUMBER_ID: str = os.getenv("WA_PHONE_NUMBER_ID", "")
    WA_ACCESS_TOKEN: str = os.getenv("WA_ACCESS_TOKEN", "")
    WA_WEBHOOK_VERIFY_TOKEN: str = os.getenv("WA_WEBHOOK_VERIFY_TOKEN", "instaflow_wa_verify")

    # Supabase (Phase 2)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # Server
    PORT: int = int(os.getenv("PORT", "8000"))
    ENV: str = os.getenv("ENV", "development")

    # Instagram Graph API (Legacy)
    IG_API_BASE: str = "https://graph.instagram.com/v21.0"
    FB_API_BASE: str = "https://graph.facebook.com/v21.0"

    # Railguard defaults
    MAX_REPLIES_PER_HOUR: int = 30
    MIN_FOLLOWER_COUNT: int = 5
    COOLDOWN_MINUTES: int = 30
    SENTIMENT_ESCALATION_THRESHOLD: float = 0.7


settings = Settings()