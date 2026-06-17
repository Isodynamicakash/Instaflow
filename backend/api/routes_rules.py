"""
Engagement Rules routes.
CRUD for comment-to-DM triggers, welcome DMs, etc.
"""

from fastapi import APIRouter, HTTPException
from backend.models.rule import RuleCreateRequest, RuleUpdateRequest
from backend.services import supabase_client as db

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.post("")
async def create_rule(data: RuleCreateRequest):
    rule = await db.create_rule({
        "user_id": data.user_id,
        "rule_type": data.rule_type,
        "trigger_keywords": data.trigger_keywords,
        "comment_reply": data.comment_reply,
        "dm_template": data.dm_template,
        "dm_payload": data.dm_payload,
    })
    return {"status": "created", "rule": rule}


@router.get("/{user_id}")
async def get_rules(user_id: str, active_only: bool = True):
    rules = await db.get_rules_by_user(user_id, active_only=active_only)
    return {"rules": rules}


@router.patch("/{rule_id}")
async def update_rule(rule_id: str, data: RuleUpdateRequest):
    updates = data.model_dump(exclude_none=True)
    rule = await db.update_rule(rule_id, updates)
    if not rule:
        raise HTTPException(404, "Rule not found")
    return {"status": "updated", "rule": rule}


@router.delete("/{rule_id}")
async def delete_rule(rule_id: str):
    ok = await db.delete_rule(rule_id)
    if not ok:
        raise HTTPException(404, "Rule not found")
    return {"status": "deleted"}
