"""
TypedDict state schemas for all LangGraph agent graphs.
"""

from typing import TypedDict, Optional


class IntelligenceState(TypedDict):
    """State for the Account Intelligence graph."""
    user_id: str
    access_token: str
    ig_user_id: str
    profile: dict
    posts: list[dict]
    metrics: list[dict]
    analysis: dict
    report: str
    error: Optional[str]


class EngagementState(TypedDict):
    """State for the Engagement Monitor graph."""
    # Incoming event
    event_type: str              # comment, dm, story_mention
    sender_id: str
    sender_username: str
    text: str
    media_id: Optional[str]
    comment_id: Optional[str]
    post_permalink: Optional[str]

    # User config
    user_id: str
    access_token: str
    ig_user_id: str
    ig_username: str
    brand_voice: str
    niche: str
    rules: list[dict]
    whatsapp_number: str

    # Processing
    intent: str
    matched_rule: Optional[dict]
    response_text: str
    action_taken: str
    should_escalate: bool


class ContentState(TypedDict):
    """State for the Content Generator graph."""
    user_id: str
    access_token: str
    ig_user_id: str
    ig_username: str
    brand_voice: str
    niche: str
    whatsapp_number: str

    # Analysis
    recent_metrics: list[dict]
    performance_summary: str
    top_hashtags: list[str]
    top_themes: list[str]

    # Generation
    generated_options: list[dict]
    selected_option: Optional[dict]
    approval_status: str

    # Scheduling
    optimal_time: Optional[str]
    posted: bool
