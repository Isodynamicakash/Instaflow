"""
InstaFlow — Engagement Agent (FIXED)
- Handles both comments AND DMs
- LangGraph state machine
- Intent classification with Claude
- Auto-reply logic
"""
import logging
from typing import TypedDict, Literal
from anthropic import Anthropic

logger = logging.getLogger(__name__)

# ==================== STATE ====================

class EngagementState(TypedDict):
    """LangGraph state - DO NOT add extra fields!"""
    message_id: str
    message_text: str
    sender_id: str
    sender_username: str
    is_dm: bool
    conversation_id: str
    timestamp: str
    intent: str
    escalate: bool
    response_text: str
    action_taken: str

# ==================== KEYWORDS ====================

DEMO_KEYWORDS = ["demo", "demo link", "link", "trial", "try"]
TRIGGER_KEYWORDS = ["help", "support", "issue", "problem", "bug", "error"]
ESCALATION_KEYWORDS = ["complaint", "angry", "unhappy", "frustrated", "bad", "worst"]
SPAM_KEYWORDS = ["viagra", "casino", "forex", "crypto", "buy now", "click here"]

# ==================== ENGAGEMENT AGENT ====================

async def run_engagement_agent(
    message_id: str,
    message_text: str,
    sender_id: str,
    sender_username: str,
    is_dm: bool,
    conversation_id: str,
    timestamp: str
) -> dict:
    """
    Main engagement agent function
    Runs the full intent classification → decision → response flow
    
    Returns:
    {
        "action_taken": "demo_reply" | "trigger_reply" | "replied" | "escalated_to_support" | "spam" | "none",
        "response_text": "...",
        "intent": "demo" | "trigger" | "complaint" | "spam" | "other"
    }
    """
    
    # Initialize state
    state = EngagementState(
        message_id=message_id,
        message_text=message_text,
        sender_id=sender_id,
        sender_username=sender_username,
        is_dm=is_dm,
        conversation_id=conversation_id,
        timestamp=timestamp,
        intent="unknown",
        escalate=False,
        response_text="",
        action_taken="none"
    )
    
    try:
        # Step 1: Check for demo keywords
        logger.info("🔍 Step 1: Checking for demo keywords...")
        if any(keyword in message_text.lower() for keyword in DEMO_KEYWORDS):
            logger.info(f"   ✅ Demo keyword found!")
            return handle_demo_request(state)
        
        # Step 2: Check for trigger keywords
        logger.info("🔍 Step 2: Checking for trigger keywords...")
        if any(keyword in message_text.lower() for keyword in TRIGGER_KEYWORDS):
            logger.info(f"   ✅ Trigger keyword found!")
            return handle_trigger(state)
        
        # Step 3: Check for spam
        logger.info("🔍 Step 3: Checking for spam...")
        if any(keyword in message_text.lower() for keyword in SPAM_KEYWORDS):
            logger.info(f"   ✅ Spam detected!")
            return handle_spam(state)
        
        # Step 4: Classify intent with Claude
        logger.info("🔍 Step 4: Classifying intent with Claude...")
        state = await classify_intent(state)
        
        # Step 5: Route based on classification
        if state["escalate"]:
            logger.info(f"   ⚠️ Escalation needed (intent: {state['intent']})")
            return handle_escalation(state)
        elif state["intent"] == "other":
            logger.info(f"   💬 Regular reply")
            return await handle_reply(state)
        else:
            logger.info(f"   ⏭️ No action needed")
            return handle_none(state)
    
    except Exception as e:
        logger.error(f"❌ Agent error: {e}")
        raise

# ==================== INTENT CLASSIFICATION ====================

async def classify_intent(state: EngagementState) -> EngagementState:
    """Use Claude to classify message intent"""
    try:
        client = Anthropic()
        
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            system="""You are an engagement agent. Classify the message intent as ONE of:
- complaint: unhappy, problem, issue
- serious: urgent, important
- spam: promotional, suspicious
- other: normal

Also decide: escalate? (true/false) for complaint/serious messages.

Respond ONLY in JSON: {"intent": "...", "escalate": true/false}""",
            messages=[
                {
                    "role": "user",
                    "content": f"Message: {state['message_text']}"
                }
            ]
        )
        
        response_text = message.content[0].text
        logger.info(f"🤖 Claude response: {response_text}")
        
        # Parse response
        import json
        try:
            result = json.loads(response_text)
            state["intent"] = result.get("intent", "other")
            state["escalate"] = result.get("escalate", False)
        except:
            state["intent"] = "other"
            state["escalate"] = False
        
        logger.info(f"   Intent: {state['intent']}")
        logger.info(f"   Escalate: {state['escalate']}")
        
        return state
    
    except Exception as e:
        logger.error(f"❌ Classification error: {e}")
        state["intent"] = "other"
        state["escalate"] = False
        return state

# ==================== HANDLERS ====================

def handle_demo_request(state: EngagementState) -> dict:
    """Handle demo/link requests"""
    logger.info("⚠️ Handling demo request...")
    
    response = "Thanks for your interest! 🎉\n\nHere's your demo link: https://demo.instaflow.ai\n\nOur team will reach out shortly to help you get started!"
    
    return {
        "action_taken": "demo_reply",
        "response_text": response,
        "intent": "demo"
    }

def handle_trigger(state: EngagementState) -> dict:
    """Handle trigger/support requests"""
    logger.info("⚠️ Handling trigger...")
    
    response = "Thanks for reaching out! 👋\n\nOur support team will assist you shortly. We're here to help!"
    
    return {
        "action_taken": "trigger_reply",
        "response_text": response,
        "intent": "trigger"
    }

def handle_spam(state: EngagementState) -> dict:
    """Ignore spam"""
    logger.info("🚫 Spam detected, ignoring...")
    
    return {
        "action_taken": "spam",
        "response_text": "",
        "intent": "spam"
    }

def handle_escalation(state: EngagementState) -> dict:
    """Handle escalated messages (complaints, serious issues)"""
    logger.info("⚠️ Handling escalation (serious/complaint)...")
    
    holding_reply = "Thanks for reaching out! Our team will get back to you shortly 🙏"
    
    logger.info(f"   Holding reply: {holding_reply}")
    logger.info(f"   Status: ESCALATED to support team")
    
    # Return WITHOUT 'status' field (it's not in EngagementState schema)
    return {
        "action_taken": "escalated_to_support",
        "response_text": holding_reply,
        "intent": state["intent"]
    }

async def handle_reply(state: EngagementState) -> dict:
    """Generate contextual reply with Claude"""
    logger.info("💬 Generating contextual reply...")
    
    try:
        client = Anthropic()
        
        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=200,
            system="""You are a friendly Instagram/DM responder.
Write a SHORT, natural reply (1-2 sentences max).
Be helpful and human-like. Don't mention being an AI.""",
            messages=[
                {
                    "role": "user",
                    "content": f"Reply to: {state['message_text']}"
                }
            ]
        )
        
        response = message.content[0].text
        logger.info(f"   Generated: {response[:50]}...")
        
        return {
            "action_taken": "replied",
            "response_text": response,
            "intent": "other"
        }
    
    except Exception as e:
        logger.error(f"❌ Reply generation error: {e}")
        return {
            "action_taken": "none",
            "response_text": "",
            "intent": "other"
        }

def handle_none(state: EngagementState) -> dict:
    """No action needed"""
    logger.info("⏭️ No action needed")
    
    return {
        "action_taken": "none",
        "response_text": "",
        "intent": state["intent"]
    }

# ==================== BACKWARDS COMPATIBILITY ====================

# Keep old function for compatibility if needed elsewhere
async def run_agent(
    message_id: str,
    message_text: str,
    sender_id: str,
    sender_username: str,
    is_dm: bool = False,
    conversation_id: str = None,
    timestamp: str = None
) -> dict:
    """Backwards compatible wrapper"""
    return await run_engagement_agent(
        message_id=message_id,
        message_text=message_text,
        sender_id=sender_id,
        sender_username=sender_username,
        is_dm=is_dm,
        conversation_id=conversation_id or "",
        timestamp=timestamp or ""
        )
