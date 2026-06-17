"""
Instagram API client using Zernio as middleware for DMs
"""

import httpx
from backend.config import settings
import logging

logger = logging.getLogger(__name__)


class InstagramAPI:
    """Instagram API client - uses Zernio for DMs"""

    def __init__(self, access_token: str, ig_user_id: str):
        self.access_token = access_token
        self.ig_user_id = ig_user_id
        self.ig_api_base = settings.IG_API_BASE
        self.zernio_api_base = "https://zernio.com/api/v1"
        self.zernio_api_key = settings.ZERNIO_API_KEY
        self.zernio_account_id = settings.ZERNIO_ACCOUNT_ID
        self.http_client = httpx.AsyncClient()

    async def reply_to_comment(self, comment_id: str, reply_text: str) -> dict:
        """
        Reply to a comment on Instagram
        Uses Instagram Graph API directly
        """
        try:
            url = f"{self.ig_api_base}/{comment_id}/replies"
            payload = {
                "message": reply_text,
                "access_token": self.access_token,
            }
            
            response = await self.http_client.post(url, json=payload)
            response.raise_for_status()
            
            logger.info(f"✅ Reply posted: {response.json()}")
            return response.json()
        except Exception as e:
            logger.error(f"❌ Failed to reply: {e}")
            raise

    async def send_dm(self, user_id: str, message_text: str) -> dict:
        """
        Send DM to user via Zernio SEND MESSAGE endpoint
        For Instagram DMs - uses existing conversation
        """
        try:
            # For Instagram: conversationId = user's Instagram ID
            conversation_id = user_id
            
            url = f"{self.zernio_api_base}/inbox/conversations/{conversation_id}/messages"
            
            headers = {
                "Authorization": f"Bearer {self.zernio_api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "accountId": self.zernio_account_id,  # Use correct Zernio account ID!
                "message": message_text,
            }
            
            logger.info(f"📤 Sending DM via Zernio to {user_id}...")
            logger.info(f"   Message: {message_text}")
            
            response = await self.http_client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            
            logger.info(f"✅ DM sent via Zernio: {response.json()}")
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Zernio API error: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"❌ Failed to send DM: {e}")
            raise

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
