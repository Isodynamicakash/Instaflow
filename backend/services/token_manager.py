"""
Token Manager — handles IG token refresh and basic encryption.
Phase 1: stores tokens in memory. Phase 2: encrypt at rest in Supabase.
"""

import hashlib
import base64
from datetime import datetime, timedelta
from backend.config import settings
from backend.services.instagram_api import InstagramAPI


# Simple in-memory token cache: ig_user_id → {token, refreshed_at, expires_at}
_token_cache: dict[str, dict] = {}


async def store_token(ig_user_id: str, access_token: str, expires_in: int = 5184000):
    """Store a token with its expiry (default 60 days)."""
    _token_cache[ig_user_id] = {
        "access_token": access_token,
        "refreshed_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
    }


async def get_token(ig_user_id: str) -> str | None:
    """Get a valid token, auto-refresh if near expiry."""
    entry = _token_cache.get(ig_user_id)
    if not entry:
        return None

    token = entry["access_token"]
    expires_at = datetime.fromisoformat(entry["expires_at"])

    # Refresh if within 7 days of expiry
    if datetime.now() > expires_at - timedelta(days=7):
        try:
            api = InstagramAPI(token, ig_user_id)
            result = await api.refresh_token()
            new_token = result.get("access_token", token)
            new_expires = result.get("expires_in", 5184000)
            await store_token(ig_user_id, new_token, new_expires)
            return new_token
        except Exception as e:
            print(f"Token refresh failed for {ig_user_id}: {e}")
            return token  # Return existing, may still work

    return token


async def exchange_short_token(ig_user_id: str, short_token: str) -> str:
    """Exchange a short-lived token (1hr) for long-lived (60 days)."""
    api = InstagramAPI(short_token, ig_user_id)
    result = await api.exchange_for_long_lived_token(settings.META_APP_SECRET)
    long_token = result["access_token"]
    expires_in = result.get("expires_in", 5184000)
    await store_token(ig_user_id, long_token, expires_in)
    return long_token
