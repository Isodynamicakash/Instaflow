"""
Auth & Onboarding routes.
POST /api/onboard — user provides token, we analyze their account.
POST /api/test-connection — quick token validation.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException

from backend.models.user import UserOnboardRequest, UserOnboardResponse
from backend.services.instagram_api import InstagramAPI
from backend.services import supabase_client as db
from backend.services.token_manager import store_token
from backend.agents.intelligence import build_intelligence_graph

router = APIRouter(prefix="/api", tags=["auth"])

# Singleton graph (reused across requests)
_intelligence_graph = None


def get_intelligence_graph():
    global _intelligence_graph
    if _intelligence_graph is None:
        _intelligence_graph = build_intelligence_graph()
    return _intelligence_graph


@router.post("/test-connection")
async def test_connection(data: dict):
    """Quick validation: is the token + user ID valid?"""
    token = data.get("access_token", "")
    ig_user_id = data.get("ig_user_id", "")
    if not token:
        raise HTTPException(400, "access_token is required")

    api = InstagramAPI(token, ig_user_id or "me")
    try:
        profile = await api.get_profile()
        return {
            "valid": True,
            "username": profile.get("username"),
            "ig_user_id": profile.get("id"),
            "followers": profile.get("followers_count"),
        }
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")


@router.post("/onboard", response_model=UserOnboardResponse)
async def onboard_user(data: UserOnboardRequest):
    """Full onboarding: fetch posts → analyze → generate report."""

    # Store token
    await store_token(data.ig_user_id, data.access_token)

    # Save user
    user = await db.upsert_user({
        "ig_user_id": data.ig_user_id,
        "ig_username": data.ig_username,
        "access_token": data.access_token,
        "whatsapp_number": data.whatsapp_number,
        "onboarding_data": data.form_data,
    })

    # Run intelligence graph
    graph = get_intelligence_graph()
    result = await graph.ainvoke(
        {
            "user_id": user["id"],
            "access_token": data.access_token,
            "ig_user_id": data.ig_user_id,
            "profile": {},
            "posts": [],
            "metrics": [],
            "analysis": {},
            "report": "",
            "error": None,
        },
        config={"configurable": {"thread_id": f"onboard-{data.ig_user_id}"}},
    )

    if result.get("error"):
        raise HTTPException(500, result["error"])

    # Save brand voice from analysis
    analysis = result.get("analysis", {})
    if analysis.get("writing_style"):
        await db.upsert_user({
            "id": user["id"],
            "ig_user_id": data.ig_user_id,
            "brand_voice": analysis["writing_style"],
        })

    return UserOnboardResponse(
        user_id=user["id"],
        profile=result.get("profile", {}),
        posts_analyzed=len(result.get("metrics", [])),
        analysis=analysis,
        report=result.get("report", ""),
    )
