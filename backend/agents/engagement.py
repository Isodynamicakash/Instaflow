"""
Engagement Monitor Graph — 24/7 agent that handles incoming comments.
Classifies intent, auto-replies, sends DMs, escalates serious messages.

FIXED: Uses Anthropic SDK directly (no langchain dependency hell)
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
import anthropic
from backend.config import settings
from backend.agents.states import EngagementState
from backend.agents.prompts import INTENT_CLASSIFIER, ENGAGEMENT_REPLY
from backend.services.instagram_api import InstagramAPI
import logging

logger = logging.getLogger(__name__)


def build_engagement_graph():
    """Build and compile the engagement monitor graph."""

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def classify_intent(state: EngagementState) -> dict:
        """
        Classify incoming comment: trigger word, praise, question, complaint, spam.
        
        Flow:
        1. Check trigger keywords (fast)
        2. LLM classification (accurate)
        """
        text_lower = state["text"].lower().strip()

        # Fast path: check trigger keywords first
        for rule in state.get("rules", []):
            if rule.get("rule_type") == "comment_trigger" and rule.get("is_active"):
                triggers = [t.lower() for t in rule.get("trigger_keywords", [])]
                if text_lower in triggers or any(t in text_lower for t in triggers):
                    logger.info(f"✅ Trigger keyword matched: {rule}")
                    return {"intent": "trigger_word", "matched_rule": rule}

        # LLM classification
        logger.info(f"🤖 Classifying intent with Claude...")
        
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=100,
            system=INTENT_CLASSIFIER,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Type: {state['event_type']}\n"
                        f"From: @{state['sender_username']}\n"
                        f"Message: {state['text']}"
                    ),
                }
            ],
        )

        intent = response.content[0].text.strip().lower().replace(" ", "_")
        valid = {"genuine_praise", "question", "serious_inquiry",
                 "complaint", "spam", "conversation"}
        if intent not in valid:
            intent = "conversation"

        should_escalate = intent in ("serious_inquiry", "complaint")
        
        logger.info(f"   Intent: {intent}")
        logger.info(f"   Escalate: {should_escalate}")
        
        return {"intent": intent, "should_escalate": should_escalate}

    def route_by_intent(state: EngagementState) -> str:
        """Route to the correct handler node based on intent."""
        if state["intent"] == "trigger_word":
            return "handle_trigger"
        elif state["intent"] == "spam":
            return "handle_spam"
        elif state.get("should_escalate"):
            return "handle_escalation"
        else:
            return "handle_reply"

    async def handle_trigger(state: EngagementState) -> dict:
        """
        Trigger word detected: reply publicly + send DM with link
        """
        logger.info(f"🎯 Handling trigger word...")
        
        rule = state["matched_rule"]
        api = InstagramAPI(state["access_token"], state["ig_user_id"])

        comment_reply = rule.get("comment_reply", "Check your DMs! 📩")
        dm_text = rule.get("dm_template", "Here's what you asked for!")

        # Substitute variables
        for key, value in rule.get("dm_payload", {}).items():
            dm_text = dm_text.replace(f"{{{key}}}", str(value))

        actions = []

        # Reply to comment
        if state.get("comment_id"):
            try:
                await api.reply_to_comment(state["comment_id"], comment_reply)
                actions.append("comment_replied")
                logger.info(f"   ✅ Comment replied")
            except Exception as e:
                logger.error(f"   ❌ Comment reply failed: {e}")

        # Send DM
        if state.get("sender_id"):
            try:
                await api.send_dm(state["sender_id"], dm_text)
                actions.append("dm_sent")
                logger.info(f"   ✅ DM sent")
            except Exception as e:
                logger.error(f"   ❌ DM failed: {e}")

        return {
            "response_text": comment_reply,
            "action_taken": "trigger_" + "_".join(actions),
        }

    async def handle_reply(state: EngagementState) -> dict:
        """
        Generate and post contextual AI reply for praise/questions/general comments
        """
        logger.info(f"💬 Generating contextual reply...")
        
        api = InstagramAPI(state["access_token"], state["ig_user_id"])

        # Build prompt
        prompt = ENGAGEMENT_REPLY.format(
            username=state.get("ig_username", ""),
            brand_voice=state.get("brand_voice", "friendly and professional"),
            niche=state.get("niche", "general"),
        )

        # Generate reply with Claude
        response = client.messages.create(
            model=settings.CLAUDE_MODEL,
            max_tokens=200,
            system=prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Someone said:\n"
                        f'"@{state["sender_username"]}: {state["text"]}"\n\n'
                        f"Write a natural, engaging reply. Just the reply text, no quotes."
                    ),
                }
            ],
        )

        reply_text = response.content[0].text.strip().strip('"').strip("'")
        logger.info(f"   Generated: {reply_text[:60]}...")

        # Post reply
        if state["event_type"] == "comment" and state.get("comment_id"):
            try:
                await api.reply_to_comment(state["comment_id"], reply_text)
                logger.info(f"   ✅ Posted to comment")
            except Exception as e:
                logger.error(f"   ❌ Failed to post: {e}")
        elif state["event_type"] == "dm" and state.get("sender_id"):
            try:
                await api.send_dm(state["sender_id"], reply_text)
                logger.info(f"   ✅ Sent as DM")
            except Exception as e:
                logger.error(f"   ❌ Failed to send DM: {e}")

        return {
            "response_text": reply_text,
            "action_taken": f"auto_reply_{state['event_type']}",
        }

    async def handle_escalation(state: EngagementState) -> dict:
        """
        Serious message detected: send holding reply.
        (In future: forward to WhatsApp)
        """
        logger.info(f"⚠️  Handling escalation (serious/complaint)...")
        
        api = InstagramAPI(state["access_token"], state["ig_user_id"])

        # Send holding reply
        holding = "Thanks for reaching out! Our team will get back to you shortly 🙏"
        
        if state["event_type"] == "comment" and state.get("comment_id"):
            try:
                await api.reply_to_comment(state["comment_id"], holding)
                logger.info(f"   ✅ Holding reply posted")
            except Exception as e:
                logger.error(f"   ❌ Failed to post holding reply: {e}")

        return {
            "response_text": holding,
            "action_taken": "escalated_to_support",
        }

    async def handle_spam(state: EngagementState) -> dict:
        """Spam detected: log and ignore"""
        logger.info(f"🚫 Spam detected - ignoring")
        return {
            "response_text": "",
            "action_taken": "blocked_spam",
        }

    # ========== Build Graph ==========
    graph = StateGraph(EngagementState)
    
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("handle_trigger", handle_trigger)
    graph.add_node("handle_reply", handle_reply)
    graph.add_node("handle_escalation", handle_escalation)
    graph.add_node("handle_spam", handle_spam)

    # ✅ Use set_entry_point instead of START (works with langgraph 0.0.21)
    graph.set_entry_point("classify_intent")
    
    graph.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "handle_trigger": "handle_trigger",
            "handle_reply": "handle_reply",
            "handle_escalation": "handle_escalation",
            "handle_spam": "handle_spam",
        },
    )
    graph.add_edge("handle_trigger", END)
    graph.add_edge("handle_reply", END)
    graph.add_edge("handle_escalation", END)
    graph.add_edge("handle_spam", END)

    return graph.compile(checkpointer=MemorySaver())


# ========== Build & Export ==========
engagement_agent = build_engagement_graph()
