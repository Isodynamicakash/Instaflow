"""
Instagram Graph API client.
Handles all interactions with the Instagram Graph API v21.0.
"""

import asyncio
import httpx
from backend.config import settings


class InstagramAPI:
    """Async wrapper around Instagram Graph API endpoints."""

    def __init__(self, access_token: str, ig_user_id: str):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self.base = settings.IG_API_BASE

    def _params(self, extra: dict = None) -> dict:
        p = {"access_token": self.access_token}
        if extra:
            p.update(extra)
        return p

    # ── Profile ──

    async def get_profile(self) -> dict:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                f"{self.base}/{self.ig_user_id}",
                params=self._params({
                    "fields": "id,username,name,biography,followers_count,"
                              "follows_count,media_count,profile_picture_url,website"
                })
            )
            r.raise_for_status()
            return r.json()

    # ── Media ──

    async def get_media(self, limit: int = 50) -> list[dict]:
        """Fetch recent media with pagination."""
        all_media = []
        url = f"{self.base}/{self.ig_user_id}/media"
        params = self._params({
            "fields": "id,caption,media_type,media_url,thumbnail_url,"
                      "timestamp,permalink,like_count,comments_count",
            "limit": min(limit, 50),
        })

        async with httpx.AsyncClient(timeout=30) as c:
            while url and len(all_media) < limit:
                r = await c.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                all_media.extend(data.get("data", []))
                url = data.get("paging", {}).get("next")
                params = {}  # next URL has params baked in

        return all_media[:limit]

    async def get_media_insights(self, media_id: str, media_type: str = "IMAGE") -> dict:
        """Get insights for a single post (Instagram Login path metrics)."""
        # Instagram Login path uses different metric names than Facebook Login
        metrics = "reach,saved,shares,total_interactions,likes,comments"
        if media_type in ("VIDEO", "REEL"):
            metrics += ",views"

        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/{media_id}/insights",
                params=self._params({"metric": metrics})
            )
            if r.status_code == 200:
                raw = r.json().get("data", [])
                return {m["name"]: m["values"][0]["value"] for m in raw if m.get("values")}
            return {}

    # ── Comments ──

    async def get_comments(self, media_id: str, limit: int = 50) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/{media_id}/comments",
                params=self._params({
                    "fields": "id,text,username,timestamp,like_count,from",
                    "limit": limit,
                })
            )
            r.raise_for_status()
            return r.json().get("data", [])

    async def reply_to_comment(self, comment_id: str, message: str) -> dict:
        """Reply to a specific comment."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.base}/{comment_id}/replies",
                data={"message": message, "access_token": self.access_token}
            )
            r.raise_for_status()
            return r.json()

    # ── Direct Messages ──

    async def send_dm(self, recipient_id: str, message: str) -> dict:
        """Send a DM to a user (must be within 24hr messaging window)."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{self.base}/{self.ig_user_id}/messages",
                headers={"Content-Type": "application/json"},
                json={
                    "recipient": {"id": recipient_id},
                    "message": {"text": message},
                    "access_token": self.access_token,
                }
            )
            r.raise_for_status()
            return r.json()

    # ── Publishing ──

    async def publish_photo(self, image_url: str, caption: str) -> dict:
        """Two-step: create container → publish."""
        async with httpx.AsyncClient(timeout=30) as c:
            # Step 1: container
            container = await c.post(
                f"{self.base}/{self.ig_user_id}/media",
                data={
                    "image_url": image_url,
                    "caption": caption,
                    "access_token": self.access_token,
                }
            )
            container.raise_for_status()
            creation_id = container.json()["id"]
            import asyncio
            await asyncio.sleep(5)

            # Step 2: publish
            pub = await c.post(
                f"{self.base}/{self.ig_user_id}/media_publish",
                data={
                    "creation_id": creation_id,
                    "access_token": self.access_token,
                }
            )
            pub.raise_for_status()
            return pub.json()

    # ── Account Insights ──

    async def get_account_insights(self, period: str = "day") -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"{self.base}/{self.ig_user_id}/insights",
                params=self._params({
                    "metric": "reach,profile_views,accounts_engaged,total_interactions",
                    "period": period,
                })
            )
            if r.status_code == 200:
                data = r.json().get("data", [])
                return {
                    m["name"]: m["values"][-1]["value"]
                    for m in data if m.get("values")
                }
            return {}

    # ── Token Management ──

    async def exchange_for_long_lived_token(self, app_secret: str) -> dict:
        """Exchange short-lived token for a 60-day long-lived token."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": app_secret,
                    "access_token": self.access_token,
                }
            )
            r.raise_for_status()
            return r.json()

    async def refresh_token(self) -> dict:
        """Refresh a valid, non-expired long-lived token."""
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                "https://graph.instagram.com/refresh_access_token",
                params={
                    "grant_type": "ig_refresh_token",
                    "access_token": self.access_token,
                }
            )
            r.raise_for_status()
            return r.json()

    # ── Hashtag Search ──

    async def search_hashtag(self, query: str, limit: int = 5) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as c:
            # Get hashtag ID
            search = await c.get(
                f"{self.base}/ig_hashtag_search",
                params=self._params({"q": query, "user_id": self.ig_user_id})
            )
            search.raise_for_status()
            hashtags = search.json().get("data", [])
            if not hashtags:
                return []

            # Get top media
            hid = hashtags[0]["id"]
            top = await c.get(
                f"{self.base}/{hid}/top_media",
                params=self._params({
                    "user_id": self.ig_user_id,
                    "fields": "id,caption,media_type,like_count,comments_count,permalink",
                    "limit": limit,
                })
            )
            top.raise_for_status()
            return top.json().get("data", [])