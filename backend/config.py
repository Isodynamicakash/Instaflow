"""
Configuration management for InstaFlow
"""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Instagram API
    IG_USER_ID: str = os.getenv("IG_USER_ID", "").strip()
    IG_ACCESS_TOKEN: str = os.getenv("IG_ACCESS_TOKEN", "").strip()
    IG_API_BASE: str = os.getenv("IG_API_BASE", "https://graph.instagram.com/v21.0").strip()

    # Zernio Webhook
    ZERNIO_API_KEY: str = os.getenv("ZERNIO_API_KEY", "").strip()
    ZERNIO_ACCOUNT_ID: str = os.getenv("ZERNIO_ACCOUNT_ID", "").strip()
    ZERNIO_WEBHOOK_SECRET: str = os.getenv("ZERNIO_WEBHOOK_SECRET", "").strip()
    ZERNIO_API_BASE: str = os.getenv("ZERNIO_API_BASE", "https://api.zernio.com")

    # Anthropic
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-opus-4-1").strip()

    # Environment
    ENV: str = os.getenv("ENV", "development").strip()
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
