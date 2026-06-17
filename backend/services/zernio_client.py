"""
InstaFlow — Zernio API Client
Wrapper around Zernio API for Instagram operations.

Zernio is a unified social media API that handles:
- Comment posting/replies
- Post publishing
- Message sending
- Account management
- Analytics

Base URL: https://api.zernio.com/v1
Authentication: Bearer token (ZERNIO_API_KEY)
"""

import httpx
import json
from typing import Optional, Dict, Any
from backend.config import settings


class ZernioAPIClient:
    """
    Async Zernio API client for Instagram operations.
    
    Handles all interactions with Zernio API endpoints.
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize Zernio API client.
        
        Args:
            api_key: Zernio API key (defaults to ZERNIO_API_KEY from config)
        """
        self.api_key = api_key or settings.ZERNIO_API_KEY
        self.base_url = "https://api.zernio.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.timeout = 30
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Dict[str, Any]:
        """
        Make an async HTTP request to Zernio API.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., /comments/123/replies)
            data: Request body (for POST/PUT)
            params: Query parameters
        
        Returns:
            Response JSON
        
        Raises:
            HTTPException if request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                if method == "GET":
                    response = await client.get(url, headers=self.headers, params=params)
                
                elif method == "POST":
                    response = await client.post(url, headers=self.headers, json=data, params=params)
                
                elif method == "PUT":
                    response = await client.put(url, headers=self.headers, json=data, params=params)
                
                elif method == "DELETE":
                    response = await client.delete(url, headers=self.headers, params=params)
                
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                # Handle response
                if response.status_code >= 400:
                    print(f"❌ Zernio API Error: {response.status_code}")
                    print(f"   Response: {response.text[:200]}")
                    return {
                        "error": True,
                        "status_code": response.status_code,
                        "message": response.text
                    }
                
                return response.json()
            
            except httpx.TimeoutException:
                print(f"⏱️  Zernio API timeout")
                return {"error": True, "message": "Request timeout"}
            
            except Exception as e:
                print(f"❌ Zernio API request failed: {str(e)}")
                return {"error": True, "message": str(e)}
    
    # ── COMMENT OPERATIONS ──
    
    async def post_comment_reply(
        self,
        comment_id: str,
        text: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Post a reply to an Instagram comment.
        
        Args:
            comment_id: Instagram comment ID
            text: Reply message text
            account_id: (Optional) Account ID to post from
        
        Returns:
            Response with reply ID
        
        Example:
            response = await zernio.post_comment_reply(
                comment_id="18093196763253678",
                text="Thanks for the comment! 🙏"
            )
        """
        print(f"📤 Posting comment reply...")
        
        data = {
            "text": text
        }
        
        if account_id:
            data["accountId"] = account_id
        
        response = await self._request(
            "POST",
            f"/comments/{comment_id}/replies",
            data=data
        )
        
        if not response.get("error"):
            reply_id = response.get("id", "unknown")
            print(f"✅ Reply posted! ID: {reply_id}")
        
        return response
    
    async def delete_comment_reply(self, reply_id: str) -> Dict[str, Any]:
        """
        Delete a comment reply.
        
        Args:
            reply_id: Reply ID to delete
        
        Returns:
            Response confirming deletion
        """
        return await self._request("DELETE", f"/comments/{reply_id}")
    
    # ── POST OPERATIONS ──
    
    async def publish_post(
        self,
        text: str,
        media_urls: list = None,
        account_id: Optional[str] = None,
        platform: str = "instagram"
    ) -> Dict[str, Any]:
        """
        Publish a post to Instagram.
        
        Args:
            text: Post caption/text
            media_urls: List of image/video URLs
            account_id: (Optional) Account ID to post from
            platform: Platform (default: instagram)
        
        Returns:
            Response with post ID
        
        Example:
            response = await zernio.publish_post(
                text="Beautiful sunset! 🌅 #photography",
                media_urls=["https://example.com/image.jpg"]
            )
        """
        print(f"📤 Publishing post to {platform}...")
        
        data = {
            "text": text,
            "platforms": [platform]
        }
        
        if media_urls:
            data["mediaItems"] = [
                {"type": "image", "url": url} if url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))
                else {"type": "video", "url": url}
                for url in media_urls
            ]
        
        if account_id:
            data["accountId"] = account_id
        
        response = await self._request(
            "POST",
            "/posts",
            data=data
        )
        
        if not response.get("error"):
            post_id = response.get("id", "unknown")
            print(f"✅ Post published! ID: {post_id}")
        
        return response
    
    async def schedule_post(
        self,
        text: str,
        scheduled_for: str,
        media_urls: list = None,
        account_id: Optional[str] = None,
        platform: str = "instagram"
    ) -> Dict[str, Any]:
        """
        Schedule a post for future publication.
        
        Args:
            text: Post caption/text
            scheduled_for: ISO 8601 timestamp (e.g., "2026-06-20T10:00:00Z")
            media_urls: List of image/video URLs
            account_id: (Optional) Account ID to post from
            platform: Platform (default: instagram)
        
        Returns:
            Response with scheduled post ID
        
        Example:
            response = await zernio.schedule_post(
                text="Tomorrow's post! 📸",
                scheduled_for="2026-06-20T10:00:00Z",
                media_urls=["https://example.com/image.jpg"]
            )
        """
        print(f"📅 Scheduling post for {platform}...")
        
        data = {
            "text": text,
            "scheduledFor": scheduled_for,
            "platforms": [platform]
        }
        
        if media_urls:
            data["mediaItems"] = [
                {"type": "image", "url": url} if url.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))
                else {"type": "video", "url": url}
                for url in media_urls
            ]
        
        if account_id:
            data["accountId"] = account_id
        
        response = await self._request(
            "POST",
            "/posts",
            data=data
        )
        
        if not response.get("error"):
            post_id = response.get("id", "unknown")
            print(f"✅ Post scheduled! ID: {post_id}")
        
        return response
    
    # ── MESSAGE OPERATIONS ──
    
    async def send_dm(
        self,
        recipient_id: str,
        text: str,
        account_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a direct message.
        
        Args:
            recipient_id: Recipient user ID
            text: Message text
            account_id: (Optional) Account ID to send from
        
        Returns:
            Response with message ID
        """
        print(f"💌 Sending DM...")
        
        data = {
            "text": text,
            "recipientId": recipient_id
        }
        
        if account_id:
            data["accountId"] = account_id
        
        response = await self._request(
            "POST",
            "/messages",
            data=data
        )
        
        if not response.get("error"):
            message_id = response.get("id", "unknown")
            print(f"✅ DM sent! ID: {message_id}")
        
        return response
    
    # ── INBOX OPERATIONS ──
    
    async def get_conversations(
        self,
        account_id: str,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get inbox conversations for an account.
        
        Args:
            account_id: Account ID
            limit: Number of conversations (default: 50)
        
        Returns:
            List of conversations
        """
        return await self._request(
            "GET",
            f"/inbox/accounts/{account_id}/conversations",
            params={"limit": limit}
        )
    
    async def get_messages(
        self,
        conversation_id: str,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get messages in a conversation.
        
        Args:
            conversation_id: Conversation ID
            limit: Number of messages (default: 50)
        
        Returns:
            List of messages
        """
        return await self._request(
            "GET",
            f"/inbox/conversations/{conversation_id}/messages",
            params={"limit": limit}
        )
    
    # ── ACCOUNT OPERATIONS ──
    
    async def get_account_profile(self, account_id: str) -> Dict[str, Any]:
        """
        Get account profile information.
        
        Args:
            account_id: Account ID
        
        Returns:
            Account profile data
        """
        return await self._request("GET", f"/accounts/{account_id}")
    
    async def get_accounts(self) -> Dict[str, Any]:
        """
        Get all connected accounts.
        
        Returns:
            List of accounts
        """
        return await self._request("GET", "/accounts")
    
    # ── ANALYTICS OPERATIONS ──
    
    async def get_post_analytics(
        self,
        post_id: str,
        metrics: list = None
    ) -> Dict[str, Any]:
        """
        Get analytics for a post.
        
        Args:
            post_id: Post ID
            metrics: List of metrics to fetch (e.g., ["reach", "impressions", "engagement"])
        
        Returns:
            Analytics data
        """
        params = {}
        if metrics:
            params["metrics"] = ",".join(metrics)
        
        return await self._request(
            "GET",
            f"/analytics/posts/{post_id}",
            params=params
        )
    
    async def get_account_analytics(
        self,
        account_id: str,
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, Any]:
        """
        Get analytics for an account.
        
        Args:
            account_id: Account ID
            start_date: Start date (ISO 8601)
            end_date: End date (ISO 8601)
        
        Returns:
            Analytics data
        """
        params = {}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        
        return await self._request(
            "GET",
            f"/analytics/accounts/{account_id}",
            params=params
        )


# Create global client instance
zernio_client = ZernioAPIClient()