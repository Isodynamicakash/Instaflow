"""
InstaFlow — Instagram Webhook Handler (FIXED)
Handles comment.received AND message.received events
Routes to engagement agent for auto-replies
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import logging
import httpx
import asyncio
from datetime import datetime

from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ==================== MODELS ====================

class WebhookPayload(BaseModel):
    event: str = None
    data: dict = None

class InstagramWebhookData(BaseModel):
    id: str = None
    text: str = None
    from_id: str = None
    from_username: str = None
    timestamp: str = None
    post_id: str = None
    account_id: str = None

# ==================== WEBHOOK VERIFICATION ====================

@router.get("/webhook/instagram")
async def verify_webhook(request: Request):
    """Instagram webhook verification (GET)"""
    try:
        verify_token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"🔐 Webhook verification attempt")
        logger.info(f"   Token: {verify_token}")
        
        if verify_token == settings.ZERNIO_WEBHOOK_SECRET or verify_token == "instaflow_test_token":
            logger.info(f"✅ Webhook verified!")
            return int(challenge)
        else:
            logger.warning(f"❌ Invalid verification token")
            raise HTTPException(status_code=403, detail="Invalid token")
    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== WEBHOOK HANDLER ====================

@router.post("/webhook/instagram")
async def handle_instagram_webhook(request: Request):
    """
    Handle Instagram webhooks
    - comment.received: Post comments
    - message.received: DM messages
    """
    try:
        body = await request.json()
        logger.info(f"📨 Webhook received")
        
        # Parse payload
        event_type = body.get("event", "unknown")
        data = body.get("data", {})
        
        # ==================== EVENT FILTERING ====================
        # Handle BOTH comments AND DMs (FIXED)
        if event_type not in ["comment.received", "message.received"]:
            logger.info(f"⏭️  Ignoring event: {event_type}")
            return {"status": "ok", "event": event_type}
        
        # Determine if it's a comment or DM
        is_dm = event_type == "message.received"
        
        # ==================== EXTRACT DATA ====================
        
        if is_dm:
            # For DMs: message.received
            message_id = data.get("message_id") or data.get("id")
            message_text = data.get("message", "") or data.get("text", "")
            sender_id = data.get("sender_id") or data.get("from_id")
            sender_username = data.get("sender_username") or data.get("from_username", "Unknown")
            timestamp = data.get("timestamp", "")
            account_id = data.get("account_id", settings.IG_USER_ID)
            conversation_id = data.get("conversation_id")
            
            logger.info("")
            logger.info("="*70)
            logger.info("💬 DM Received")
            logger.info("="*70)
            logger.info(f"   ID: {message_id}")
            logger.info(f"   From: @{sender_username}")
            logger.info(f"   Text: {message_text[:50]}...")
            logger.info(f"   Account: @{data.get('account_username', 'unknown')}")
            logger.info("="*70)
        else:
            # For comments: comment.received
            comment_id = data.get("comment_id") or data.get("id")
            comment_text = data.get("comment", "") or data.get("text", "")
            sender_id = data.get("commenter_id") or data.get("from_id")
            sender_username = data.get("commenter_username") or data.get("from_username", "Unknown")
            timestamp = data.get("timestamp", "")
            account_id = data.get("account_id", settings.IG_USER_ID)
            post_id = data.get("post_id")
            
            logger.info("")
            logger.info("="*70)
            logger.info("💬 Comment Received")
            logger.info("="*70)
            logger.info(f"   ID: {comment_id}")
            logger.info(f"   From: @{sender_username}")
            logger.info(f"   Text: {comment_text[:50]}...")
            logger.info(f"   Account: @{data.get('account_username', 'unknown')}")
            logger.info("="*70)
            
            message_id = comment_id
            message_text = comment_text
            conversation_id = post_id
        
        # ==================== SKIP OWN COMMENTS ====================
        # Prevent infinite loop if we reply to our own comment/DM
        if sender_id == account_id or sender_username == data.get("account_username"):
            logger.info(f"⏭️  OWN {'MESSAGE' if is_dm else 'COMMENT'} - SKIPPING (prevents infinite loop)")
            return {"status": "ok", "skipped": True, "reason": "own_message"}
        
        # ==================== CALL ENGAGEMENT AGENT ====================
        logger.info(f"🤖 Calling engagement agent...")
        
        try:
            # Import here to avoid circular imports
            from backend.agents.engagement import run_engagement_agent
            
            # Run async agent
            agent_result = await run_engagement_agent(
                message_id=message_id,
                message_text=message_text,
                sender_id=sender_id,
                sender_username=sender_username,
                is_dm=is_dm,
                conversation_id=conversation_id,
                timestamp=timestamp
            )
            
            action_taken = agent_result.get("action_taken", "none")
            response_text = agent_result.get("response_text", "")
            
            logger.info(f"✅ Agent processed")
            logger.info(f"   Action: {action_taken}")
            logger.info(f"   Reply: {response_text[:50]}...")
            
        except Exception as agent_error:
            logger.error(f"❌ Agent error: {agent_error}")
            return {
                "status": "error",
                "message": str(agent_error),
                "event": event_type
            }
        
        # ==================== POST REPLY ====================
        
        # If action is to reply, post it back
        if action_taken in ["demo_reply", "trigger_reply", "replied"]:
            logger.info("="*70)
            logger.info("📤 Posting Reply to Instagram")
            logger.info("="*70)
            logger.info(f"   {'Comment' if not is_dm else 'Message'} ID: {message_id}")
            logger.info(f"   Reply: {response_text[:50]}...")
            logger.info("="*70)
            
            try:
                if is_dm:
                    # Send DM reply via Zernio
                    success = await send_dm_reply(
                        conversation_id=conversation_id,
                        message_text=response_text,
                        sender_id=sender_id
                    )
                else:
                    # Post comment reply via Instagram API
                    success = await post_comment_reply(
                        comment_id=message_id,
                        reply_text=response_text
                    )
                
                if success:
                    logger.info(f"✅ Reply posted successfully! ID: {success}")
                    return {
                        "status": "success",
                        "event": event_type,
                        "action": action_taken,
                        "reply_id": success
                    }
                else:
                    logger.warning(f"⚠️  Reply posting failed")
                    return {
                        "status": "warning",
                        "event": event_type,
                        "action": action_taken,
                        "message": "Failed to post reply"
                    }
            except Exception as reply_error:
                logger.error(f"❌ Reply error: {reply_error}")
                return {
                    "status": "error",
                    "event": event_type,
                    "action": action_taken,
                    "error": str(reply_error)
                }
        
        elif action_taken == "escalated_to_support":
            logger.info("="*70)
            logger.info("⚠️  Message Escalated to Support")
            logger.info("="*70)
            logger.info(f"   {'Comment' if not is_dm else 'Message'} ID: {message_id}")
            logger.info(f"   From: @{sender_username}")
            logger.info(f"   Holding Reply: {response_text[:50]}...")
            logger.info("="*70)
            
            try:
                if is_dm:
                    # Send holding reply via Zernio
                    success = await send_dm_reply(
                        conversation_id=conversation_id,
                        message_text=response_text,
                        sender_id=sender_id
                    )
                else:
                    # Post holding reply via Instagram API
                    success = await post_comment_reply(
                        comment_id=message_id,
                        reply_text=response_text
                    )
                
                if success:
                    logger.info(f"✅ Holding reply posted! ID: {success}")
                    # TODO: Send to support queue/Slack
                    return {
                        "status": "escalated",
                        "event": event_type,
                        "action": action_taken,
                        "reply_id": success
                    }
                else:
                    return {
                        "status": "escalated",
                        "event": event_type,
                        "action": action_taken,
                        "message": "Escalated but reply posting failed"
                    }
            except Exception as escalation_error:
                logger.error(f"❌ Escalation error: {escalation_error}")
                return {
                    "status": "error",
                    "event": event_type,
                    "action": action_taken,
                    "error": str(escalation_error)
                }
        
        else:
            # No reply needed (spam, ignored, etc.)
            logger.info(f"⏭️  No reply needed (action: {action_taken})")
            return {
                "status": "ok",
                "event": event_type,
                "action": action_taken
            }
    
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e)
        }

# ==================== REPLY POSTING ====================

async def post_comment_reply(comment_id: str, reply_text: str) -> str:
    """Post a reply to an Instagram comment"""
    try:
        url = f"{settings.IG_API_BASE}/{comment_id}/replies"
        payload = {
            "message": reply_text,
            "access_token": settings.IG_ACCESS_TOKEN
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=payload, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            reply_id = result.get("id")
            
            logger.info(f"✅ Reply posted: {result}")
            return reply_id
    except Exception as e:
        logger.error(f"❌ Failed to post comment reply: {e}")
        return None

async def send_dm_reply(conversation_id: str, message_text: str, sender_id: str) -> str:
    """Send a DM reply via Zernio"""
    try:
        url = f"{settings.ZERNIO_API_BASE}/v1/inbox/conversations/{conversation_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.ZERNIO_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "message": message_text,
            "recipient_id": sender_id
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            message_id = result.get("id") or result.get("message_id")
            
            logger.info(f"✅ DM sent: {result}")
            return message_id
    except Exception as e:
        logger.error(f"❌ Failed to send DM reply: {e}")
        return None
