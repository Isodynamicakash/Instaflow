"""
Sentiment analysis for escalation detection.
Phase 1: keyword-based. Phase 2: LLM-based scoring.
"""

NEGATIVE_KEYWORDS = [
    "angry", "terrible", "worst", "scam", "fraud", "refund",
    "disappointed", "horrible", "disgusting", "unacceptable",
    "lawsuit", "report", "fake", "stolen", "broken", "never received",
    "still waiting", "no response", "where is my order",
]

PURCHASE_KEYWORDS = [
    "price", "cost", "how much", "wholesale", "bulk", "order",
    "invoice", "payment", "buy", "purchase", "units", "quantity",
    "quote", "shipping", "deliver", "available",
]


def detect_negative_sentiment(text: str) -> float:
    """Returns a 0-1 score. > 0.5 = likely negative."""
    text_lower = text.lower()
    hits = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
    return min(hits / 3.0, 1.0)


def detect_purchase_intent(text: str) -> float:
    """Returns a 0-1 score. > 0.5 = likely purchase intent."""
    text_lower = text.lower()
    hits = sum(1 for kw in PURCHASE_KEYWORDS if kw in text_lower)
    return min(hits / 2.0, 1.0)


def should_escalate(text: str, threshold: float = 0.5) -> tuple[bool, str]:
    """Check if message should be escalated to human."""
    neg = detect_negative_sentiment(text)
    purchase = detect_purchase_intent(text)

    if neg >= threshold:
        return True, f"negative_sentiment:{neg:.2f}"
    if purchase >= threshold:
        return True, f"purchase_intent:{purchase:.2f}"
    return False, "ok"
