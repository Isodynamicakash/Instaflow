"""Analytics routes for the dashboard."""

from fastapi import APIRouter
from backend.services import supabase_client as db
from backend.guards.railguards import Railguards

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Shared railguard instance (imported by webhooks too)
guards = Railguards()


@router.get("/{user_id}")
async def get_analytics(user_id: str):
    log = await db.get_engagement_log(user_id, limit=50)
    summary = await db.get_engagement_summary(user_id)
    posting = await db.get_posting_analytics(user_id)
    guard_stats = guards.get_stats()

    return {
        "engagement_log": log,
        "summary": summary,
        "posting_analytics": posting,
        "guard_stats": guard_stats,
    }


@router.get("/{user_id}/log")
async def get_engagement_log(user_id: str, limit: int = 50):
    log = await db.get_engagement_log(user_id, limit=limit)
    return {"log": log}
