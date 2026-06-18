"""
Engagement Monitor Graph — 24/7 agent that handles incoming comments AND DMs.
Classifies intent, auto-replies, sends DMs, escalates serious messages.

FEATURES:
- Auto-replies to comments
- Auto-replies to DMs with same intelligence
- Sends DMs for demo requests (hardcoded, no Claude)
- Escalates complaints/serious inquiries
- Intent-based routing
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

# Demo link and keywords
DEMO_LINK = "https://demo.a2gen.com/trial"
DEMO_KEYWORDS = ["link", "demo", "trial"]
DEMO_COMMENT_REPLY = "Check your DM 📩"
DEMO_DM_TEXT = f"🎯 Here's your demo link:\n\n{DEMO_LINK}\n\nTry it out and let us know what you think! 💪"


def build_engagement_graph():
    """Build and compile the engagement monitor graph."""

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def classify_intent(state: EngagementState) -> dict:
        """
        Classify incoming message (comment or DM):
        demo request, trigger word, praise, question, complaint, spam.
        
        Flow:
        1. Check demo keywords (hardcoded, no Claude)
        2. Check trigger keywords (fast)
        3. LLM classification (accurate)
        """
        text_lower = state["text"].lower().strip()

        # FIRST: Check for demo keywords (hardcoded, no Claude!)
        has_demo_keyword = any(kw in text_lower for kw in DEMO_KEYWORDS)
        if has_demo_keyword:
            logger.info(f"✅ Demo keyword detected: {state['text']}")
            return {"intent": "demo_request"}

        # SECOND: Check trigger keywords
        for rule in state.get("rules", []):
            if rule.get("rule_type") == "comment_trigger" and rule.get("is_active"):
                triggers = [t.lower() for t in rule.get("trigger_keywords", [])]
                if text_lower in triggers or any(t in text_lower for t in triggers):
                    logger.info(f"✅ Trigger keyword matched: {rule}")
                    return {"intent": "trigger_word", "matched_rule": rule}

        # THIRD: LLM classification
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
        if state["intent"] == "demo_request":
            return "handle_demo_request"
        elif state["intent"] == "trigger_word":
            return "handle_trigger"
        elif state["intent"] == "spam":
            return "handle_spam"
        elif state.get("should_escalate"):
            return "handle_escalation"
        else:
            return "handle_reply"

    async def handle_demo_request(state: EngagementState) -> dict:
        """
        Demo keyword detected: hardcoded reply + DM with link
        NO Claude involved!
        Works for both comments and DMs
        """
        logger.info(f"🎯 Demo request detected - sending link via DM...")
        
        api = InstagramAPI(state["access_token"], state["ig_user_id"])

        # Send DM with demo link
        if state.get("sender_id"):
            try:
                await api.send_dm(state["sender_id"], DEMO_DM_TEXT)
                logger.info(f"   ✅ Demo link sent via DM")
            except Exception as e:
                logger.error(f"   ❌ Demo DM failed: {e}")

        # Reply text differs based on event type
        reply_text = DEMO_COMMENT_REPLY if state["event_type"] == "comment" else "Check your DMs for the link 📩"

        return {
            "response_text": reply_text,
            "action_taken": "demo_request_handled",
        }

    async def handle_trigger(state: EngagementState) -> dict:
        """
        Trigger word detected: generate reply + send DM (if configured)
        Works for both comments and DMs
        """
        logger.info(f"🎯 Handling trigger word...")
        
        rule = state["matched_rule"]
        api = InstagramAPI(state["access_token"], state["ig_user_id"])

        comment_reply = rule.get("comment_reply", "Check your DMs! 📩")
        dm_text = rule.get("dm_template", "Here's what you asked for!")

        # Substitute variables
        for key, value in rule.get("dm_payload", {}).items():
            dm_text = dm_text.replace(f"{{{key}}}", str(value))

        logger.info(f"   Comment reply: {comment_reply}")

        # Send DM if applicable
        if state.get("sender_id"):
            try:
                await api.send_dm(state["sender_id"], dm_text)
                logger.info(f"   ✅ DM sent")
            except Exception as e:
                logger.error(f"   ❌ DM failed: {e}")

        return {
            "response_text": comment_reply,
            "action_taken": "trigger_matched",
        }

    async def handle_reply(state: EngagementState) -> dict:
        """
        Generate contextual AI reply for praise/questions/general comments
        Works for both comments and DMs
        """
        logger.info(f"💬 Generating contextual reply...")
        
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
                        f"Someone sent a {state['event_type']} and said:\n"
                        f'"@{state["sender_username"]}: {state["text"]}"\n\n'
                        f"Write a natural, engaging reply. Just the reply text, no quotes."
                    ),
                }
            ],
        )

        reply_text = response.content[0].text.strip().strip('"').strip("'")
        logger.info(f"   Generated: {reply_text[:60]}...")

        return {
            "response_text": reply_text,
            "action_taken": f"auto_reply_{state['event_type']}",
        }

    async def handle_escalation(state: EngagementState) -> dict:
        """
        Serious message detected: generate holding reply
        For complaints and serious inquiries (comments or DMs)
        Marks as escalated for dashboard review
        """
        logger.info(f"⚠️  Handling escalation (serious/complaint)...")

        holding = "Thanks for reaching out! Our team will get back to you shortly 🙏"
        logger.info(f"   Holding reply: {holding}")
        logger.info(f"   Status: ESCALATED to support team")

        return {
            "response_text": holding,
            "action_taken": "escalated_to_support",
            "status": "escalated",  # Mark as escalated in dashboard
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
    graph.add_node("handle_demo_request", handle_demo_request)
    graph.add_node("handle_trigger", handle_trigger)
    graph.add_node("handle_reply", handle_reply)
    graph.add_node("handle_escalation", handle_escalation)
    graph.add_node("handle_spam", handle_spam)

    graph.set_entry_point("classify_intent")
    
    graph.add_conditional_edges(
        "classify_intent",
        route_by_intent,
        {
            "handle_demo_request": "handle_demo_request",
            "handle_trigger": "handle_trigger",
            "handle_reply": "handle_reply",
            "handle_escalation": "handle_escalation",
            "handle_spam": "handle_spam",
        },
    )
    graph.add_edge("handle_demo_request", END)
    graph.add_edge("handle_trigger", END)
    graph.add_edge("handle_reply", END)
    graph.add_edge("handle_escalation", END)
    graph.add_edge("handle_spam", END)

    return graph.compile(checkpointer=MemorySaver())


# ========== Build & Export ==========
engagement_agent = build_engagement_graph()
