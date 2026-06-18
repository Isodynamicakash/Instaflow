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
    Handle Instagram webhooks (Zernio format)
    - comment.received: Post comments
    - message.received: DM messages
    """
    try:
        body = await request.json()
        logger.info(f"📨 Webhook received")
        
        # Parse payload - Zernio sends message/conversation directly, not in "data"
        event_type = body.get("event", "unknown")
        message_obj = body.get("message", {})
        conversation_obj = body.get("conversation", {})
        account_obj = body.get("account", {})
        
        # SIMPLE DEBUG: Always log what we got
        logger.info(f"🔍 WEBHOOK DEBUG:")
        logger.info(f"   event_type: {event_type}")
        logger.info(f"   message_obj keys: {list(message_obj.keys())}")
        logger.info(f"   message_obj: {message_obj}")
        
        # ==================== EVENT FILTERING ====================
        # Handle BOTH comments AND DMs (FIXED)
        if event_type not in ["comment.received", "message.received"]:
            logger.info(f"⏭️  Ignoring event: {event_type}")
            return {"status": "ok", "event": event_type}
        
        # Determine if it's a comment or DM
        is_dm = event_type == "message.received"
        
        # ==================== EXTRACT DATA FROM ZERNIO PAYLOAD ====================
        
        if is_dm:
            # For DMs: Extract from message object
            message_id = message_obj.get("id")
            message_text = message_obj.get("text", "")
            sender_obj = message_obj.get("sender", {})
            sender_id = sender_obj.get("id")
            sender_username = sender_obj.get("username", "Unknown")
            timestamp = message_obj.get("sentAt", "")
            conversation_id = message_obj.get("conversationId")
            account_id = account_obj.get("id")
            
            # DEBUG: Log extracted values
            logger.info(f"🔍 DEBUG - Extracted fields:")
            logger.info(f"   account_id: {account_id}")
            logger.info(f"   account_obj: {account_obj}")
            logger.info(f"   conversation_id: {conversation_id}")
            
            logger.info("")
            logger.info("="*70)
            logger.info("💬 DM Received")
            logger.info("="*70)
            logger.info(f"   ID: {message_id}")
            logger.info(f"   From: @{sender_username}")
            logger.info(f"   Text: {message_text[:50]}...")
            logger.info(f"   Account: @{account_obj.get('username', 'unknown')}")
            logger.info("="*70)
       else:
           comment_obj = body.get("comment", {})
           post_obj = body.get("post", {})

           message_id = comment_obj.get("id")
           message_text = comment_obj.get("text", "")

           author_obj = comment_obj.get("author", {})

           sender_id = author_obj.get("id")
           sender_username = author_obj.get("username", "Unknown")

           timestamp = comment_obj.get("createdTime", "")
           account_id = account_obj.get("id")
   
           conversation_id = (
            post_obj.get("id")
           or comment_obj.get("postId")
           or None
           )

           logger.info("")
          logger.info("=" * 70)
          logger.info("💬 Comment Received")
          logger.info("=" * 70)
          logger.info(f"   ID: {message_id}")
          logger.info(f"   From: @{sender_username}")
          logger.info(f"   Text: {message_text[:50]}...")
          logger.info("=" * 70)
    
        
           
        
        # ==================== SKIP OWN COMMENTS ====================
        # Prevent infinite loop if we reply to our own comment/DM
        if sender_id == account_id or sender_username == account_obj.get("username"):
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
                    # Send DM reply via Zernio (with account_id)
                    success = await send_dm_reply(
                        conversation_id=conversation_id,
                        message_text=response_text,
                        sender_id=sender_id,
                        account_id=account_id
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
                    logger.warning(f"⚠️  Reply posting failed (no ID in response)")
                    return {
                        "status": "warning",
                        "event": event_type,
                        "action": action_taken,
                        "message": "Reply posted but no confirmation ID"
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
                    # Send holding reply via Zernio (with account_id)
                    success = await send_dm_reply(
                        conversation_id=conversation_id,
                        message_text=response_text,
                        sender_id=sender_id,
                        account_id=account_id
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

async def send_dm_reply(conversation_id: str, message_text: str, sender_id: str, account_id: str = None) -> str:
    """Send a DM reply via Zernio"""
    try:
        logger.info(f"📤 send_dm_reply called with:")
        logger.info(f"   account_id param: {account_id}")
        logger.info(f"   conversation_id: {conversation_id}")
        
        url = f"{settings.ZERNIO_API_BASE}/v1/inbox/conversations/{conversation_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.ZERNIO_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Zernio API requires accountId
        if not account_id:
            logger.warning(f"⚠️ account_id is None, using fallback from settings")
            account_id = settings.ZERNIO_ACCOUNT_ID
            logger.info(f"   Fallback account_id: {account_id}")
        
        # Correct Zernio payload format: {"message": "...", "accountId": "..."}
        payload = {
            "message": message_text,
            "accountId": account_id
        }
        
        logger.info(f"📤 Sending DM via Zernio")
        logger.info(f"   URL: {url}")
        logger.info(f"   Final accountId in payload: {payload.get('accountId')}")
        logger.info(f"   Payload: {payload}")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            result = response.json()
            
            # Extract ID from various possible response formats
            message_id = (
                result.get("id") 
                or result.get("message_id") 
                or result.get("data", {}).get("id")
                or result.get("message", {}).get("id")
                or "success"  # If no ID in response, return "success" indicator
            )
            
            logger.info(f"✅ DM sent successfully! Response: {result}")
            return message_id
    except Exception as e:
        logger.error(f"❌ Failed to send DM reply: {e}")
        logger.error(f"   Status: {response.status_code if 'response' in locals() else 'N/A'}")
        logger.error(f"   Response: {response.text if 'response' in locals() else 'N/A'}")
        return None
