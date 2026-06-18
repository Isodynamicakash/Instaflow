# backend/webhooks/instagram.py
"""
Instagram Webhook Handler - Receives comments via Zernio, processes with agent, posts replies.
INTEGRATES with: engagement.py (agent), instagram_api.py (API client)
NO DATABASE - simple in-memory dedup
"""

import json
import hmac
import hashlib
import asyncio
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from typing import Optional
import logging

from backend.config import settings
from backend.agents.engagement import engagement_agent
from backend.services.instagram_api import InstagramAPI

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["instagram"])

# Simple in-memory cache for dedup (prevent duplicate replies)
processed_comments = set()
MAX_CACHE = 5000


def verify_signature(body: bytes, signature: str) -> bool:
    """Verify Zernio webhook signature"""
    expected = hmac.new(
        settings.ZERNIO_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@router.post("/instagram")
async def handle_instagram_webhook(request: Request):
    """
    Main webhook handler.
    Flow: Verify → Extract → Detect own comment → Call agent → Reply
    """
    
    # Get raw body for signature
    body = await request.body()
    signature = request.headers.get("X-Zernio-Signature", "")
    
    # Verify signature
    if not verify_signature(body, signature):
        logger.warning("❌ Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse JSON
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = payload.get("event", "unknown")
    
    # Only handle comments
    if event_type != "comment.received":
        logger.info(f"⏭️  Ignoring event: {event_type}")
        return {"status": "ok", "event": event_type}
    
    # Process comment
    return await handle_comment_received(payload)


async def handle_comment_received(payload: dict):
    """
    🎯 CORE: Process comment with engagement agent
    
    1. Extract comment data
    2. ✅ Own-comment detection (skip if own comment)
    3. Dedup check
    4. Call engagement agent (10s timeout)
    5. Post reply via Instagram API
    """
    
    try:
        # ========== STEP 1: Extract Data ==========
        comment_data = payload.get("comment", {})
        account_data = payload.get("account", {})
        post_data = payload.get("post", {})
        
        comment_id = comment_data.get("id")
        comment_text = comment_data.get("text", "")
        
        # Author
        author = comment_data.get("author", {})
        author_username = (author.get("username", "") or "").lower().strip()
        author_id = author.get("id")
        
        # Account
        account_username = (account_data.get("username", "") or "").lower().strip()
        account_id = account_data.get("id")
        post_permalink = post_data.get("permalink", "")
        
        logger.info(f"\n{'='*70}")
        logger.info(f"💬 Comment Received")
        logger.info(f"{'='*70}")
        logger.info(f"   ID: {comment_id}")
        logger.info(f"   From: @{author_username}")
        logger.info(f"   Text: {comment_text[:60]}...")
        logger.info(f"   Account: @{account_username}")
        logger.info(f"{'='*70}\n")
        
        # ========== STEP 2: Own-Comment Detection ✅ ==========
        if author_username == account_username:
            logger.info(f"⏭️  OWN COMMENT - SKIPPING (prevents infinite loop)\n")
            return {"status": "ok", "skipped": True, "reason": "own_comment"}
        
        # ========== STEP 3: Dedup Check ==========
        if comment_id in processed_comments:
            logger.info(f"⏭️  DUPLICATE - Already processed\n")
            return {"status": "ok", "skipped": True, "reason": "duplicate"}
        
        processed_comments.add(comment_id)
        if len(processed_comments) > MAX_CACHE:
            processed_comments.clear()
        
        # ========== STEP 4: Build State for Agent ==========
        state = {
            "text": comment_text,
            "event_type": "comment",
            "sender_username": author_username,
            "sender_id": author_id,
            "comment_id": comment_id,
            "post_permalink": post_permalink,
            "ig_user_id": settings.IG_USER_ID,
            "ig_username": account_username,
            "user_id": "system",
            "access_token": settings.IG_ACCESS_TOKEN,
            "brand_voice": "professional and friendly",
            "niche": "general",
            "rules": [],  # Add user rules here if you have them
        }
        
        # ========== STEP 5: Call Agent (WITH TIMEOUT) ==========
        logger.info(f"🤖 Calling engagement agent...")
        
        result = await asyncio.wait_for(
            engagement_agent.ainvoke(
                state,
                config={"configurable": {"thread_id": str(comment_id)}}
            ),
            timeout=10.0  # 10 second timeout
        )
        
        response_text = result.get("response_text", "")
        action_taken = result.get("action_taken", "unknown")
        
        logger.info(f"✅ Agent processed")
        logger.info(f"   Action: {action_taken}")
        logger.info(f"   Reply: {response_text[:80]}\n")
        
        # ========== STEP 6: Post Reply (if any) ==========
        if response_text and response_text.strip():
            await post_reply_to_comment(
                comment_id=comment_id,
                reply_text=response_text,
                author_id=author_id
            )
        
        return {
            "status": "success",
            "comment_id": comment_id,
            "action": action_taken,
            "reply": response_text
        }
    
    except asyncio.TimeoutError:
        logger.warning(f"⏱️  AGENT TIMEOUT (10s) - Skipping reply\n")
        return {
            "status": "timeout",
            "comment_id": comment_id,
            "message": "Agent processing timeout"
        }
    
    except Exception as e:
        logger.error(f"❌ ERROR: {str(e)}\n", exc_info=True)
        return {
            "status": "error",
            "comment_id": comment_id,
            "error": str(e)
        }


async def post_reply_to_comment(
    comment_id: str,
    reply_text: str,
    author_id: Optional[str] = None
):
    """
    Post reply to Instagram via Graph API
    """
    
    logger.info(f"{'='*70}")
    logger.info(f"📤 Posting Reply to Instagram")
    logger.info(f"{'='*70}")
    logger.info(f"   Comment ID: {comment_id}")
    logger.info(f"   Reply: {reply_text[:80]}...")
    logger.info(f"{'='*70}\n")
    
    try:
        api = InstagramAPI(settings.IG_ACCESS_TOKEN, settings.IG_USER_ID)
        
        response = await api.reply_to_comment(comment_id, reply_text)
        
        reply_id = response.get("id", "unknown")
        logger.info(f"✅ Reply posted successfully! ID: {reply_id}\n")
    
    except Exception as e:
        logger.error(f"❌ Failed to post reply: {e}\n", exc_info=True)


# Health check
@router.get("/instagram/health")
async def webhook_health():
    return {
        "status": "healthy",
        "webhook": "instagram",
        "environment": settings.ENV,
        "processed_comments_cached": len(processed_comments),
        "timestamp": datetime.utcnow().isoformat()
    }
