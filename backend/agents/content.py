"""
Content Generator Graph — analyzes performance, generates 4-5 post
options, sends for approval (WhatsApp in Phase 2, dashboard for now).
"""

import json
import asyncio
from datetime import datetime

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import settings
from backend.agents.states import ContentState
from backend.agents.prompts import CONTENT_GENERATOR
from backend.services.instagram_api import InstagramAPI
from backend.services import supabase_client as db


def build_content_graph():
    """Build and compile the content generator graph."""

    llm = ChatAnthropic(
        model=settings.CLAUDE_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=0.8,
    )

    async def analyze_performance(state: ContentState) -> dict:
        api = InstagramAPI(state["access_token"], state["ig_user_id"])
        try:
            posts = await api.get_media(limit=30)
        except Exception:
            posts = []

        metrics = []
        for post in posts:
            try:
                insights = await api.get_media_insights(
                    post["id"], post.get("media_type", "IMAGE")
                )
                metrics.append({
                    "caption": post.get("caption", "")[:200],
                    "likes": post.get("like_count", 0),
                    "comments": post.get("comments_count", 0),
                    "timestamp": post.get("timestamp", ""),
                    **insights,
                })
            except Exception:
                continue
            await asyncio.sleep(0.3)

        # LLM summary
        response = await llm.ainvoke([
            SystemMessage(content=(
                "Summarize this Instagram performance data in 3-4 bullet points. "
                "Focus on what content themes work, what doesn't, and timing patterns."
            )),
            HumanMessage(content=json.dumps(metrics[:20], default=str)),
        ])

        return {
            "recent_metrics": metrics,
            "performance_summary": response.content,
        }

    async def generate_options(state: ContentState) -> dict:
        prompt = CONTENT_GENERATOR.format(
            username=state.get("ig_username", ""),
            brand_voice=state.get("brand_voice", "friendly"),
            niche=state.get("niche", "general"),
            top_hashtags=", ".join(state.get("top_hashtags", [])),
            top_themes=", ".join(state.get("top_themes", [])),
            engagement_summary=state.get("performance_summary", ""),
        )

        response = await llm.ainvoke([
            SystemMessage(content=prompt),
            HumanMessage(content=(
                "Generate exactly 5 Instagram post options.\n"
                "Return ONLY a JSON array, no markdown fences:\n"
                '[\n  {\n    "caption": "full caption text with CTA",\n'
                '    "hashtags": ["hashtag1", "hashtag2"],\n'
                '    "content_type": "educational|behind_scenes|testimonial|promotional|lifestyle",\n'
                '    "best_time": "e.g. Tuesday 2pm",\n'
                '    "why": "brief reason this should perform well"\n  }\n]'
            )),
        ])

        try:
            content = response.content
            start = content.find("[")
            end = content.rfind("]") + 1
            options = json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            options = [{
                "caption": "Content generation encountered an issue. Retry.",
                "hashtags": [],
                "content_type": "unknown",
                "best_time": "N/A",
                "why": "Generation parse error",
            }]

        # Store in content queue
        await db.add_to_content_queue({
            "user_id": state["user_id"],
            "generated_captions": options[:5],
            "status": "pending",
        })

        return {"generated_options": options[:5], "approval_status": "pending"}

    # Build graph — for Phase 1, approval happens via dashboard, not WhatsApp
    graph = StateGraph(ContentState)
    graph.add_node("analyze_performance", analyze_performance)
    graph.add_node("generate_options", generate_options)

    graph.add_edge(START, "analyze_performance")
    graph.add_edge("analyze_performance", "generate_options")
    graph.add_edge("generate_options", END)

    return graph.compile(checkpointer=MemorySaver())
