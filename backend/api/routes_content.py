"""Content generation routes."""

from datetime import datetime
from fastapi import APIRouter, HTTPException
from backend.models.content import ContentGenerateRequest, ContentGenerateResponse
from backend.services import supabase_client as db
from backend.agents.content import build_content_graph

router = APIRouter(prefix="/api/content", tags=["content"])

_content_graph = None

def get_content_graph():
    global _content_graph
    if _content_graph is None:
        _content_graph = build_content_graph()
    return _content_graph


@router.post("/generate", response_model=ContentGenerateResponse)
async def generate_content(data: ContentGenerateRequest):
    user = await db.get_user(data.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    graph = get_content_graph()
    result = await graph.ainvoke(
        {
            "user_id": data.user_id,
            "access_token": user.get("access_token", ""),
            "ig_user_id": user.get("ig_user_id", ""),
            "ig_username": user.get("ig_username", ""),
            "brand_voice": user.get("brand_voice", "friendly"),
            "niche": user.get("onboarding_data", {}).get("niche", "general"),
            "whatsapp_number": user.get("whatsapp_number", ""),
            "recent_metrics": [],
            "performance_summary": "",
            "top_hashtags": data.top_hashtags,
            "top_themes": data.top_themes,
            "generated_options": [],
            "selected_option": None,
            "approval_status": "pending",
            "optimal_time": None,
            "posted": False,
        },
        config={"configurable": {
            "thread_id": f"content-{data.user_id}-{datetime.now().timestamp()}"
        }},
    )

    options = result.get("generated_options", [])
    return ContentGenerateResponse(
        options=[{"caption": o.get("caption",""), "hashtags": o.get("hashtags",[]),
                  "content_type": o.get("content_type",""), "best_time": o.get("best_time",""),
                  "why": o.get("why","")} for o in options],
        status=result.get("approval_status", "generated"),
    )


@router.get("/queue/{user_id}")
async def get_content_queue(user_id: str):
    queue = await db.get_content_queue(user_id)
    return {"queue": queue}
