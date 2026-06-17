"""
Configuration management for InstaFlow
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Instagram API
    IG_USER_ID: str = Field(default="", description="Instagram User ID")
    IG_ACCESS_TOKEN: str = Field(default="", description="Instagram Access Token")
    IG_API_BASE: str = Field(
        default="https://graph.instagram.com/v21.0",
        description="Instagram Graph API base URL"
    )

    # Zernio Webhook
    ZERNIO_API_KEY: str = Field(default="", description="Zernio API key")
    ZERNIO_WEBHOOK_SECRET: str = Field(default="", description="Zernio webhook secret")

    # Anthropic
    ANTHROPIC_API_KEY: str = Field(default="", description="Anthropic API key")
    CLAUDE_MODEL: str = Field(
        default="claude-3-5-sonnet-20241022",
        description="Claude model to use"
    )

    # Environment
    ENV: str = Field(default="development", description="Environment (development/production)")
    DEBUG: bool = Field(default=False, description="Debug mode")

    class Config:
        env_file = ".env"
        case_sensitive = True

    @field_validator("ANTHROPIC_API_KEY", "IG_ACCESS_TOKEN", "ZERNIO_API_KEY", 
                     "ZERNIO_WEBHOOK_SECRET", mode="before")
    @classmethod
    def strip_whitespace(cls, v):
        """Strip leading/trailing whitespace from API keys."""
        if isinstance(v, str):
            return v.strip()
        return v


settings = Settings()
