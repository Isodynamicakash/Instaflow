"""
InstaFlow — Instagram Webhook Handler (AGENT DISABLED, ZERNIO HANDLES EVERYTHING NATIVELY)
Handles comment.received AND message.received events.

The conversational agent (Claude-based classify/reply) is off. All
keyword-triggered replies — comment/DM auto-reply, the follow-gate/verify
loop, everything — are owned entirely by Zernio's own comment-automations,
configured from the dashboard's Flows tab. This webhook's job is now just:
  1. Log every event so it shows up in the dashboard Inbox.
  2. Skip your own messages (loop prevention).
  3. Dedupe on event id (Zernio's own docs: delivery is at-least-once).
  4. If AGENT_ENABLED is flipped back to True, fall through to the old
     Claude-based agent for anything not already handled by a flow.

REMOVED (2026-09-03): a custom manual follow-check layer (live status
re-checks, a "check again" postback button, direct-send bypassing Zernio's
own gate) was built on top of this to work around observed inconsistencies
in Zernio's native audience gate. It introduced more bugs than it fixed
(false positives releasing gated content, double-sends from two systems
racing) and has been removed. Zernio's native gate is trusted as-is again.
If Zernio's native follower-gating proves unreliable in practice, that's
worth raising with Zernio support directly rather than re-building a
workaround here.
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
import logging
import httpx
import asyncio
import re
import time
from datetime import datetime

from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Flip to True to restore the old Claude-based auto-reply agent as a fallback
# for anything a Flow doesn't catch. Leave False while flows own everything.
AGENT_ENABLED = False

# ==================== EVENT DEDUP ====================
# Zernio's own docs: "Delivery is at-least-once — dedupe on the event id."
# In-memory only — fine for a single Railway instance; if this ever runs on
# multiple replicas, this needs to move to Redis/DB instead.
_seen_event_ids = {}
_EVENT_ID_TTL = 300  # 5 minutes is generous for Zernio's retry window

def is_duplicate_event(event_id: str) -> bool:
    if not event_id:
        return False
    now = time.monotonic()
    if len(_seen_event_ids) > 500:
        for k in list(_seen_event_ids.keys()):
            if now - _seen_event_ids[k] > _EVENT_ID_TTL:
                del _seen_event_ids[k]
    if event_id in _seen_event_ids and (now - _seen_event_ids[event_id]) < _EVENT_ID_TTL:
        return True
    _seen_event_ids[event_id] = now
    return False

# ==================== NON-FOLLOWER NUDGE (deliberately simple) ====================
# Fills the one real gap in Zernio's native automation: a CONFIRMED
# non-follower (isFollower === false on the webhook payload) gets silently
# skipped by Zernio's own audience gate — no message at all, ever, per
# Zernio's own docs (the verify/gate step only applies to UNRESOLVED status).
#
# DESIGN CHOICE, on purpose, after an earlier version of this caused real
# bugs: this reads ONLY the isFollower value already sitting in the
# incoming webhook payload. It does NOT make a separate live API call to
# re-check status — that separate call was the thing that returned a wrong
# answer in testing (a flaky True when the real answer was False), and
# caused gated content to leak to a non-follower. Trusting the payload's
# own embedded value, which comes from the same event Meta already
# resolved, avoided that failure mode in every test.
#
# It also NEVER sends the real content itself — only the "please follow"
# nudge for the confirmed-False case. The "confirmed follower" and
# "unresolved" cases are left entirely to Zernio's native flow, so there's
# no way for this to race or double-send against Zernio's own automation.
_automations_cache = {"data": None, "fetched_at": 0}
_AUTOMATIONS_CACHE_TTL = 30

async def get_active_automations() -> list:
    now = time.monotonic()
    if _automations_cache["data"] is not None and (now - _automations_cache["fetched_at"]) < _AUTOMATIONS_CACHE_TTL:
        return _automations_cache["data"]
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.ZERNIO_API_BASE}/v1/comment-automations",
                headers={"Authorization": f"Bearer {settings.ZERNIO_API_KEY}"},
                params={"profileId": settings.ZERNIO_PROFILE_ID, "accountId": settings.ZERNIO_ACCOUNT_ID},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()
            automations = data.get("automations") or data.get("data") or []
            _automations_cache["data"] = automations
            _automations_cache["fetched_at"] = now
            return automations
    except Exception as e:
        logger.error(f"❌ Failed to fetch automations for nudge check: {e}")
        return _automations_cache["data"] or []

def matches_automation_keywords(text: str, automation: dict) -> bool:
    text_lower = (text or "").lower()
    words = re.findall(r"\w+", text_lower)
    match_mode = automation.get("matchMode", "word")
    for kw in automation.get("keywords", []):
        kw = (kw or "").strip().lower()
        if not kw:
            continue
        if match_mode == "exact":
            if text_lower.strip() == kw:
                return True
        elif match_mode == "word":
            if kw in words:
                return True
        else:
            if kw in text_lower:
                return True
    return False

# Light dedup so a confirmed non-follower repeating the same keyword
# doesn't get spammed with the nudge on every single message. In-memory
# only — resets on redeploy, same as everything else in this file.
_nudged = set()

async def maybe_send_non_follower_nudge(message_text: str, sender_obj: dict, conversation_id: str, sender_id: str, account_id: str) -> bool:
    profile = sender_obj.get("instagramProfile") or {}
    if profile.get("isFollower") is not False:
        return False  # True or unresolved None — leave entirely to Zernio's native flow

    try:
        automations = await get_active_automations()
    except Exception as e:
        logger.error(f"❌ Could not load automations for nudge check: {e}")
        return False

    for auto in automations:
        if not auto.get("isActive"):
            continue
        if not auto.get("alsoMatchInDms"):
            continue  # DMs only for now
        audience = auto.get("audience") or {}
        if audience.get("followerStatus") != "follower":
            continue  # only relevant for flows that actually care about follow status
        gate = auto.get("followGate") or {}
        nudge_text = gate.get("notFollowingMessage") or gate.get("message")
        if not nudge_text:
            continue
        if not matches_automation_keywords(message_text, auto):
            continue

        automation_id = auto.get("id") or auto.get("_id")
        key = (sender_id, automation_id)
        if key in _nudged:
            logger.info(f"⏭️  Already nudged this person for '{auto.get('name')}' — skipping repeat")
            return True
        _nudged.add(key)

        logger.info(f"🔔 Confirmed non-follower matched '{auto.get('name')}' (Zernio would skip silently) — sending follow nudge")
        await send_dm_reply(
            conversation_id=conversation_id,
            message_text=nudge_text,
            sender_id=sender_id,
            account_id=account_id,
        )
        return True
    return False

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

        event_type = body.get("event", "unknown")
        message_obj = body.get("message", {})
        conversation_obj = body.get("conversation", {})
        account_obj = body.get("account", {})

        logger.info(f"🔍 WEBHOOK DEBUG:")
        logger.info(f"   event_type: {event_type}")
        logger.info(f"   message_obj keys: {list(message_obj.keys())}")
        logger.info(f"   message_obj: {message_obj}")

        # ==================== EVENT FILTERING ====================
        if event_type not in ["comment.received", "message.received"]:
            logger.info(f"⏭️  Ignoring event: {event_type}")
            return {"status": "ok", "event": event_type}

        is_dm = event_type == "message.received"

        # ==================== EXTRACT DATA FROM ZERNIO PAYLOAD ====================

        if is_dm:
            message_id = message_obj.get("id")
            message_text = message_obj.get("text", "")
            sender_obj = message_obj.get("sender", {})
            sender_id = sender_obj.get("id")
            sender_username = sender_obj.get("username", "Unknown")
            timestamp = message_obj.get("sentAt", "")
            conversation_id = message_obj.get("conversationId")
            account_id = account_obj.get("id")

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
            message_id = message_obj.get("id")
            message_text = message_obj.get("text", "")
            sender_obj = message_obj.get("sender", {})
            sender_id = sender_obj.get("id")
            sender_username = sender_obj.get("username", "Unknown")
            timestamp = message_obj.get("sentAt", "")
            account_id = account_obj.get("id")
            conversation_id = message_obj.get("conversationId")  # Post ID for comments

            logger.info("")
            logger.info("="*70)
            logger.info("💬 Comment Received")
            logger.info("="*70)
            logger.info(f"   ID: {message_id}")
            logger.info(f"   From: @{sender_username}")
            logger.info(f"   Text: {message_text[:50]}...")
            logger.info(f"   Account: @{account_obj.get('username', 'unknown')}")
            logger.info("="*70)

        # ==================== EVENT DEDUP ====================
        if is_duplicate_event(message_id):
            logger.info(f"⏭️  Duplicate event ({message_id}) — already processed, skipping")
            return {"status": "ok", "skipped": True, "reason": "duplicate_event"}

        # ==================== SKIP OWN COMMENTS ====================
        if sender_id == account_id or sender_username == account_obj.get("username"):
            logger.info(f"⏭️  OWN {'MESSAGE' if is_dm else 'COMMENT'} - SKIPPING (prevents infinite loop)")
            return {"status": "ok", "skipped": True, "reason": "own_message"}

        # ==================== NON-FOLLOWER NUDGE (DMs only) ====================
        # Fills the one gap Zernio's native gate leaves open — see the
        # function's docstring above for the full explanation and the
        # deliberately-simple design (payload only, no live re-check).
        if is_dm:
            try:
                nudged = await maybe_send_non_follower_nudge(
                    message_text=message_text,
                    sender_obj=sender_obj,
                    conversation_id=conversation_id,
                    sender_id=sender_id,
                    account_id=account_id,
                )
                if nudged:
                    return {"status": "ok", "event": event_type, "action": "non_follower_nudge_sent"}
            except Exception as e:
                logger.error(f"❌ Non-follower nudge check failed (continuing normally): {e}")

        # ==================== FLOWS OWN ALL TRIGGER REPLIES ====================
        # Zernio's comment-automations (configured in the dashboard's Flows tab)
        # already matched, follow-gated, and replied to this event on Zernio's
        # side before this webhook even fired — this handler is a parallel
        # notification stream, not the thing sending the reply. We just log it
        # so it shows up in the dashboard Inbox, and stop here.
        if not AGENT_ENABLED:
            logger.info("📥 Event logged for inbox — no auto-reply (agent disabled, Zernio's native flows own all triggers)")
            return {"status": "ok", "event": event_type, "action": "logged_only"}

        # ==================== CALL ENGAGEMENT AGENT (fallback path, off by default) ====================
        logger.info(f"🤖 Calling engagement agent...")

        try:
            from backend.agents.engagement import run_engagement_agent

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

        if action_taken in ["demo_reply", "trigger_reply", "replied"]:
            logger.info("="*70)
            logger.info("📤 Posting Reply to Instagram")
            logger.info("="*70)
            logger.info(f"   {'Comment' if not is_dm else 'Message'} ID: {message_id}")
            logger.info(f"   Reply: {response_text[:50]}...")
            logger.info("="*70)

            try:
                if is_dm:
                    success = await send_dm_reply(
                        conversation_id=conversation_id,
                        message_text=response_text,
                        sender_id=sender_id,
                        account_id=account_id
                    )
                else:
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
                    success = await send_dm_reply(
                        conversation_id=conversation_id,
                        message_text=response_text,
                        sender_id=sender_id,
                        account_id=account_id
                    )
                else:
                    success = await post_comment_reply(
                        comment_id=message_id,
                        reply_text=response_text
                    )

                if success:
                    logger.info(f"✅ Holding reply posted! ID: {success}")
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

# ==================== REPLY POSTING (fallback-path helpers, kept for AGENT_ENABLED=True) ====================

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

async def send_dm_reply(conversation_id: str, message_text: str, sender_id: str, account_id: str = None, buttons: list = None) -> str:
    """Send a DM reply via Zernio. Kept for the AGENT_ENABLED=True fallback
    path — not used by anything else now that Zernio's native automations
    own all trigger-based sending."""
    try:
        logger.info(f"📤 send_dm_reply called with:")
        logger.info(f"   account_id param: {account_id}")
        logger.info(f"   conversation_id: {conversation_id}")

        url = f"{settings.ZERNIO_API_BASE}/v1/inbox/conversations/{conversation_id}/messages"
        headers = {
            "Authorization": f"Bearer {settings.ZERNIO_API_KEY}",
            "Content-Type": "application/json"
        }

        if not account_id:
            logger.warning(f"⚠️ account_id is None, using fallback from settings")
            account_id = settings.ZERNIO_ACCOUNT_ID
            logger.info(f"   Fallback account_id: {account_id}")

        payload = {
            "message": message_text,
            "accountId": account_id
        }
        if buttons:
            payload["buttons"] = buttons[:3]

        logger.info(f"📤 Sending DM via Zernio")
        logger.info(f"   URL: {url}")
        logger.info(f"   Final accountId in payload: {payload.get('accountId')}")
        logger.info(f"   Payload: {payload}")

        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=10.0)
            response.raise_for_status()
            result = response.json()

            message_id = (
                result.get("id")
                or result.get("message_id")
                or result.get("data", {}).get("id")
                or result.get("message", {}).get("id")
                or "success"
            )

            logger.info(f"✅ DM sent successfully! Response: {result}")
            return message_id
    except Exception as e:
        logger.error(f"❌ Failed to send DM reply: {e}")
        logger.error(f"   Status: {response.status_code if 'response' in locals() else 'N/A'}")
        logger.error(f"   Response: {response.text if 'response' in locals() else 'N/A'}")
        return None
