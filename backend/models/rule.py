"""Pydantic schemas for Engagement Rules."""
from pydantic import BaseModel
from typing import Optional


class RuleCreateRequest(BaseModel):
    user_id: str
    rule_type: str  # comment_trigger, welcome_dm, story_reply
    trigger_keywords: list[str] = []
    comment_reply: str = "Check your DMs! 📩"
    dm_template: str = ""
    dm_payload: dict = {}  # {link: "...", media_url: "..."}


class RuleUpdateRequest(BaseModel):
    trigger_keywords: Optional[list[str]] = None
    comment_reply: Optional[str] = None
    dm_template: Optional[str] = None
    dm_payload: Optional[dict] = None
    is_active: Optional[bool] = None


class RuleResponse(BaseModel):
    id: str
    user_id: str
    rule_type: str
    trigger_keywords: list[str]
    comment_reply: str
    dm_template: str
    dm_payload: dict
    is_active: bool
