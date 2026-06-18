"""
InstaFlow — Instagram Webhook Handler (DEBUG VERSION)
Logs raw webhook payload to identify field names
"""
from fastapi import APIRouter, Request, HTTPException
import logging
import json

logger = logging.getLogger(__name__)
router = APIRouter()

from backend.config import settings

@router.get("/webhook/instagram")
async def verify_webhook(request: Request):
    """Instagram webhook verification (GET)"""
    try:
        verify_token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"🔐 Webhook verification attempt")
        
        if verify_token == settings.ZERNIO_WEBHOOK_SECRET or verify_token == "instaflow_test_token":
            logger.info(f"✅ Webhook verified!")
            return int(challenge)
        else:
            logger.warning(f"❌ Invalid verification token")
            raise HTTPException(status_code=403, detail="Invalid token")
    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webhook/instagram")
async def handle_instagram_webhook(request: Request):
    """
    DEBUG: Log the raw webhook payload to identify field structure
    """
    try:
        body = await request.json()
        
        # LOG THE ENTIRE PAYLOAD FOR DEBUGGING
        logger.info("="*70)
        logger.info("🔍 DEBUG: Raw Webhook Payload")
        logger.info("="*70)
        logger.info(json.dumps(body, indent=2))
        logger.info("="*70)
        
        # Extract what we can
        event_type = body.get("event", "unknown")
        data = body.get("data", {})
        
        logger.info(f"📨 Event Type: {event_type}")
        logger.info(f"📨 Data Keys: {list(data.keys())}")
        logger.info(f"📨 Data: {json.dumps(data, indent=2)}")
        
        # Try to find the message ID in different places
        logger.info("🔍 Searching for message ID in different fields...")
        possible_id_fields = ["message_id", "id", "comment_id", "dm_id", "conversation_id"]
        for field in possible_id_fields:
            if field in data:
                logger.info(f"   ✓ Found {field}: {data[field]}")
        
        # Try to find message text in different places
        logger.info("🔍 Searching for message text in different fields...")
        possible_text_fields = ["message", "text", "comment", "body", "content"]
        for field in possible_text_fields:
            if field in data:
                logger.info(f"   ✓ Found {field}: {data[field]}")
        
        # Try to find sender/user ID in different places
        logger.info("🔍 Searching for sender ID in different fields...")
        possible_user_fields = ["sender_id", "from_id", "user_id", "commenter_id", "from", "sender"]
        for field in possible_user_fields:
            if field in data:
                logger.info(f"   ✓ Found {field}: {data[field]}")
        
        # Try to find username in different places
        logger.info("🔍 Searching for username in different fields...")
        possible_username_fields = ["sender_username", "from_username", "username", "commenter_username", "user_name"]
        for field in possible_username_fields:
            if field in data:
                logger.info(f"   ✓ Found {field}: {data[field]}")
        
        # Check nested structures
        logger.info("🔍 Checking for nested objects...")
        if "from" in data and isinstance(data["from"], dict):
            logger.info(f"   'from' is an object: {data['from']}")
        if "sender" in data and isinstance(data["sender"], dict):
            logger.info(f"   'sender' is an object: {data['sender']}")
        if "user" in data and isinstance(data["user"], dict):
            logger.info(f"   'user' is an object: {data['user']}")
        if "message_data" in data and isinstance(data["message_data"], dict):
            logger.info(f"   'message_data' is an object: {data['message_data']}")
        
        return {
            "status": "ok",
            "debug": "Check logs for payload structure"
        }
    
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
