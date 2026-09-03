"""
InstaFlow — Instagram Webhook Handler (AGENT DISABLED)
Handles comment.received AND message.received events.

The conversational agent (Claude-based classify/reply) is now OFF by default.
All keyword-triggered replies — comment/DM auto-reply, the follow-gate loop —
are owned by Zernio comment-automations, configured from the dashboard's
Flows tab. This webhook's job now is just:
  1. Log every event so it shows up in the dashboard Inbox.
  2. Skip your own messages (loop prevention).
  3. Send a manual "please follow" nudge to CONFIRMED non-followers who
     match a follower-gated flow's keyword — Zernio's own automation
     silently skips this exact case (see NON-FOLLOWER NUDGE section below).
  4. If AGENT_ENABLED is flipped back to True, fall through to the old
     Claude-based agent for anything not already handled by a flow.
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

# ==================== NON-FOLLOWER NUDGE HELPERS ====================
# Zernio's own comment-automation, when audience.followerStatus == "follower",
# only shows the follow-gate/verify step to people whose status is UNRESOLVED
# (first-time senders). Once Meta has confirmed someone's status as False
# (they've messaged before, so consent exists, and the real answer is "not
# following"), Zernio silently SKIPS them — no message at all, not even
# notFollowingMessage. That's correct per Zernio's own docs, but if you want
# a nudge sent to known non-followers every time they trigger a keyword, that
# has to happen here, since Zernio's automation won't do it.

_automations_cache = {"data": None, "fetched_at": 0}
_AUTOMATIONS_CACHE_TTL = 30  # seconds — avoid hammering Zernio on bursty traffic

# ==================== EVENT DEDUP ====================
# Zernio's own docs: "Delivery is at-least-once — dedupe on the event id."
# In-memory only — fine for a single Railway instance; if this ever runs on
# multiple replicas, this needs to move to Redis/DB instead, since each
# replica would otherwise have its own blind spot.
_seen_event_ids = {}
_EVENT_ID_TTL = 300  # 5 minutes is generous for Zernio's retry window

def is_duplicate_event(event_id: str) -> bool:
    if not event_id:
        return False
    now = time.monotonic()
    # sweep occasionally so this dict doesn't grow unbounded
    if len(_seen_event_ids) > 500:
        for k in list(_seen_event_ids.keys()):
            if now - _seen_event_ids[k] > _EVENT_ID_TTL:
                del _seen_event_ids[k]
    if event_id in _seen_event_ids and (now - _seen_event_ids[event_id]) < _EVENT_ID_TTL:
        return True
    _seen_event_ids[event_id] = now
    return False

# ==================== PER-FLOW GATE STATE ====================
# Tracks, per (sender, automation) pair, whether this person has already
# been shown THIS flow's full "Gate message". First trigger of a given
# keyword/flow -> full gate message. Repeat triggers of the SAME flow ->
# "If still not following" instead. A DIFFERENT flow's keyword is a fresh
# pair, so it gets its own first-time gate message even for someone who's
# already seen a different flow's gate. In-memory only — same limitation
# as the automations cache: lost on restart, not shared across replicas.
_gate_shown_to = set()

def has_seen_gate(sender_id: str, automation_id: str) -> bool:
    return (sender_id, automation_id) in _gate_shown_to

def mark_gate_shown(sender_id: str, automation_id: str):
    _gate_shown_to.add((sender_id, automation_id))

async def get_active_automations() -> list:
    """Fetches the account's comment-automations from Zernio directly
    (raw shape, not the dashboard-reshaped version in api/automations.py),
    cached briefly to avoid a Zernio call on every single webhook event."""
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
    """Mirrors Zernio's matchMode semantics (contains/word/exact).
    NOTE: does not replicate typoTolerance — a known, minor gap versus
    Zernio's own matcher, acceptable since this only controls an extra
    manual nudge, not the primary automated reply."""
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
        else:  # contains
            if kw in text_lower:
                return True
    return False

async def check_live_follow_status(account_id: str, user_id: str):
    """Calls Zernio's on-demand follow-status endpoint for a fresh answer —
    used specifically at button-tap time, since the tap itself is new
    consent and may have resolved (or changed) since the original message.
    Returns True/False/None (None = still unresolved or the call failed)."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.ZERNIO_API_BASE}/v1/accounts/{account_id}/follow-status/{user_id}",
                headers={"Authorization": f"Bearer {settings.ZERNIO_API_KEY}"},
                timeout=10.0,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("isFollower")
    except Exception as e:
        logger.error(f"❌ follow-status check failed for user {user_id}: {e}")
        return None

async def find_automation_by_id(automation_id: str):
    automations = await get_active_automations()
    for auto in automations:
        if auto.get("id") == automation_id or auto.get("_id") == automation_id:
            return auto
    return None

FOLLOW_CHECK_PAYLOAD_PREFIX = "instaflow_followcheck:"

async def send_follow_check_prompt(conversation_id: str, sender_id: str, account_id: str, automation: dict, text: str = None):
    """Sends the nudge text with a postback button. Tapping it re-checks
    live follow status (see the postback handler in the webhook route) and
    either sends the real content or loops back to this same prompt."""
    gate = automation.get("followGate") or {}
    body = text or gate.get("notFollowingMessage") or "Looks like you're not following yet — follow, then tap below to try again."
    button_label = (gate.get("buttonLabel") or "I'm following ✅")[:20]  # Zernio caps button titles at 20 chars
    await send_dm_reply(
        conversation_id=conversation_id,
        message_text=body,
        sender_id=sender_id,
        account_id=account_id,
        buttons=[{
            "type": "postback",
            "title": button_label,
            "payload": f"{FOLLOW_CHECK_PAYLOAD_PREFIX}{automation.get('id') or automation.get('_id')}",
        }],
    )

async def maybe_send_non_follower_nudge(message_text: str, sender_obj: dict, conversation_id: str, sender_id: str, account_id: str):
    """If the sender is a CONFIRMED non-follower (isFollower is exactly
    False, not None/unresolved) and their message matches a keyword on an
    active, follower-gated flow, send the appropriate prompt WITH a
    check-again button. First trigger of THIS flow -> the full gate message;
    repeat triggers of the same flow -> the shorter notFollowingMessage.
    Returns True if sent."""
    profile = sender_obj.get("instagramProfile") or {}
    if profile.get("isFollower") is not False:
        return False  # True (is a follower), or None (unresolved — Zernio's own gate handles this case)

    try:
        automations = await get_active_automations()
    except Exception as e:
        logger.error(f"❌ Could not load automations for nudge check: {e}")
        return False

    for auto in automations:
        if not auto.get("isActive"):
            continue
        if not auto.get("alsoMatchInDms"):
            continue  # this nudge only covers the DM path currently
        audience = auto.get("audience") or {}
        if audience.get("followerStatus") != "follower":
            continue
        gate = auto.get("followGate") or {}
        gate_message = gate.get("message")
        not_following_message = gate.get("notFollowingMessage")
        if not gate_message and not not_following_message:
            continue  # nothing configured to send for this flow — skip it
        if matches_automation_keywords(message_text, auto):
            automation_id = auto.get("id") or auto.get("_id")
            first_time_for_this_flow = not has_seen_gate(sender_id, automation_id)
            text_to_send = (gate_message if first_time_for_this_flow and gate_message else None) or not_following_message
            logger.info(
                f"🔔 Confirmed non-follower matched flow '{auto.get('name')}' "
                f"({'first time on this flow — full gate message' if first_time_for_this_flow else 'repeat on this flow — short nudge'})"
            )
            mark_gate_shown(sender_id, automation_id)
            await send_follow_check_prompt(conversation_id, sender_id, account_id, auto, text=text_to_send)
            return True
    return False

async def handle_follow_check_postback(payload: str, conversation_id: str, sender_id: str, account_id: str) -> bool:
    """Handles a tap on the check-again button: re-checks live follow
    status and either sends the real content or loops the same prompt.
    Returns True if it handled the tap (caller should stop processing)."""
    if not payload.startswith(FOLLOW_CHECK_PAYLOAD_PREFIX):
        return False

    automation_id = payload[len(FOLLOW_CHECK_PAYLOAD_PREFIX):]
    automation = await find_automation_by_id(automation_id)
    if not automation:
        logger.warning(f"⚠️ Follow-check tap for unknown/deleted automation {automation_id} — ignoring")
        return True

    is_follower = await check_live_follow_status(account_id, sender_id)
    logger.info(f"🔁 Follow-check tap for '{automation.get('name')}' — live status: {is_follower}")

    if is_follower is True:
        real_message = automation.get("dmMessage", "")
        if real_message:
            await send_dm_reply(
                conversation_id=conversation_id,
                message_text=real_message,
                sender_id=sender_id,
                account_id=account_id,
            )
            logger.info("✅ Now following — sent real content")
    else:
        # Still not following (False) or Meta still can't resolve it (None) — loop the prompt
        await send_follow_check_prompt(conversation_id, sender_id, account_id, automation)
        logger.info("🔁 Still not confirmed as following — re-sent check-again prompt")
    return True


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
        # Handle BOTH comments AND DMs
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
            # For comments: Extract from message object
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
        # Zernio delivers at-least-once — the same event can legitimately
        # arrive twice. Without this, the "hee"/"first follow" duplicate-send
        # bug happens: two identical webhook deliveries for one real tap,
        # each independently triggering a send.
        if is_duplicate_event(message_id):
            logger.info(f"⏭️  Duplicate event ({message_id}) — already processed, skipping")
            return {"status": "ok", "skipped": True, "reason": "duplicate_event"}

        # ==================== SKIP OWN COMMENTS ====================
        # Prevent infinite loop if we reply to our own comment/DM
        if sender_id == account_id or sender_username == account_obj.get("username"):
            logger.info(f"⏭️  OWN {'MESSAGE' if is_dm else 'COMMENT'} - SKIPPING (prevents infinite loop)")
            return {"status": "ok", "skipped": True, "reason": "own_message"}

        # ==================== FOLLOW-CHECK BUTTON TAP (DMs only) ====================
        # A tap on the "I'm following ✅" button we sent arrives as an
        # ordinary message.received event, with the button's payload in
        # message_obj.metadata.postbackPayload. Handle it before any keyword
        # matching — the tap itself isn't a trigger word, it's a re-check.
        if is_dm:
            postback_payload = (message_obj.get("metadata") or {}).get("postbackPayload")
            if postback_payload:
                try:
                    handled = await handle_follow_check_postback(
                        payload=postback_payload,
                        conversation_id=conversation_id,
                        sender_id=sender_id,
                        account_id=account_id,
                    )
                    if handled:
                        return {"status": "ok", "event": event_type, "action": "follow_check_postback_handled"}
                except Exception as e:
                    logger.error(f"❌ Follow-check postback handling failed: {e}")

        # ==================== NON-FOLLOWER NUDGE (DMs only, fills a native gap) ====================
        # See the helper functions above for the full explanation: Zernio's own
        # audience gate silently skips CONFIRMED non-followers (isFollower ==
        # False) rather than sending notFollowingMessage, which only fires
        # during the unresolved/verify path. This catches that gap manually,
        # now with a check-again button instead of a dead-end text message.
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
            logger.info("📥 Event logged for inbox — no auto-reply (agent disabled, flows own all triggers)")
            return {"status": "ok", "event": event_type, "action": "logged_only"}

        # ==================== CALL ENGAGEMENT AGENT (fallback path, off by default) ====================
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
    """Send a DM reply via Zernio. Pass `buttons` (list of
    {type, title, payload/url}, max 3) to attach inline buttons —
    used by the follow-check prompt."""
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
        if buttons:
            payload["buttons"] = buttons[:3]  # Zernio caps inline buttons at 3

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
