"""
Account Intelligence Graph — fetches all posts, analyzes patterns,
generates a performance report. Runs on onboarding + weekly refresh.
"""

import json
import asyncio
from datetime import datetime

from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from backend.config import settings
from backend.agents.states import IntelligenceState
from backend.agents.prompts import ANALYZER
from backend.services.instagram_api import InstagramAPI
from backend.services import supabase_client as db


def build_intelligence_graph():
    """Build and compile the account intelligence graph."""

    llm = ChatAnthropic(
        model=settings.CLAUDE_MODEL,
        api_key=settings.ANTHROPIC_API_KEY,
        temperature=0.3,
    )

    async def fetch_profile(state: IntelligenceState) -> dict:
        api = InstagramAPI(state["access_token"], state["ig_user_id"])
        try:
            profile = await api.get_profile()
            return {"profile": profile}
        except Exception as e:
            return {"error": f"Profile fetch failed: {e}"}

    async def fetch_all_posts(state: IntelligenceState) -> dict:
        if state.get("error"):
            return {}
        api = InstagramAPI(state["access_token"], state["ig_user_id"])
        try:
            posts = await api.get_media(limit=200)
            # Store in DB
            for p in posts:
                await db.upsert_post({
                    "user_id": state["user_id"],
                    "ig_media_id": p["id"],
                    "media_type": p.get("media_type", "IMAGE"),
                    "caption": p.get("caption", ""),
                    "permalink": p.get("permalink", ""),
                    "timestamp": p.get("timestamp", ""),
                })
            return {"posts": posts}
        except Exception as e:
            return {"error": f"Media fetch failed: {e}"}

    async def extract_metrics(state: IntelligenceState) -> dict:
        if state.get("error"):
            return {}
        api = InstagramAPI(state["access_token"], state["ig_user_id"])
        metrics = []

        for post in state["posts"]:
            try:
                insights = await api.get_media_insights(
                    post["id"], post.get("media_type", "IMAGE")
                )
                metric = {
                    "post_id": post["id"],
                    "caption": post.get("caption", ""),
                    "timestamp": post.get("timestamp", ""),
                    "media_type": post.get("media_type", ""),
                    "likes": post.get("like_count", 0),
                    "comments": post.get("comments_count", 0),
                    **insights,
                }
                metrics.append(metric)

                # Store metric
                await db.upsert_metric({
                    "post_id": post["id"],
                    **insights,
                    "likes_count": post.get("like_count", 0),
                    "comments_count": post.get("comments_count", 0),
                })
            except Exception:
                continue
            # Pace to respect rate limits
            await asyncio.sleep(0.5)

        return {"metrics": metrics}

    async def analyze_patterns(state: IntelligenceState) -> dict:
        if state.get("error"):
            return {}

        metrics_json = json.dumps(state["metrics"][:50], indent=2, default=str)

        response = await llm.ainvoke([
            SystemMessage(content=ANALYZER),
            HumanMessage(content=(
                f"Profile: {json.dumps(state['profile'], default=str)}\n\n"
                f"Post metrics (most recent 50):\n{metrics_json}"
            )),
        ])

        try:
            content = response.content
            start = content.find("{")
            end = content.rfind("}") + 1
            analysis = json.loads(content[start:end])
        except (json.JSONDecodeError, ValueError):
            analysis = {"error": "Failed to parse analysis", "raw": response.content[:500]}

        return {"analysis": analysis}

    async def generate_report(state: IntelligenceState) -> dict:
        if state.get("error"):
            return {"report": f"Error: {state['error']}"}

        a = state["analysis"]
        p = state["profile"]
        nl = "\n"

        hashtags = nl.join(f"- #{tag}" for tag in a.get("top_hashtags", [])[:10])
        times = nl.join(
            f"- {t['day']} at {t['hour']}:00 (avg engagement: {t.get('avg_engagement', '?')}%)"
            for t in a.get("best_posting_times", [])[:5]
        )
        themes = nl.join(f"- {t}" for t in a.get("content_themes", []))
        top_posts = nl.join(
            f"- {tp.get('caption_preview', '?')[:80]}... "
            f"(engagement: {tp.get('engagement_rate', '?')}%) — {tp.get('why', '')}"
            for tp in a.get("top_posts", [])[:5]
        )
        weak = nl.join(f"- {w}" for w in a.get("weak_spots", []))
        recs = nl.join(f"- {r}" for r in a.get("recommendations", []))

        report = f"""# Instagram Performance Report
## @{p.get('username', 'unknown')}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

### Account Overview
- Followers: {p.get('followers_count', 'N/A'):,}
- Following: {p.get('follows_count', 'N/A'):,}
- Total Posts: {p.get('media_count', 'N/A'):,}
- Posts Analyzed: {len(state['metrics'])}

### Top Performing Hashtags
{hashtags}

### Best Posting Times
{times}

### Content Themes Identified
{themes}

### Writing Style Profile
{a.get('writing_style', 'Not analyzed')}

### Top Posts & Why They Worked
{top_posts}

### Areas for Improvement
{weak}

### Recommendations
{recs}
"""
        return {"report": report}

    # Build and compile
    graph = StateGraph(IntelligenceState)
    graph.add_node("fetch_profile", fetch_profile)
    graph.add_node("fetch_all_posts", fetch_all_posts)
    graph.add_node("extract_metrics", extract_metrics)
    graph.add_node("analyze_patterns", analyze_patterns)
    graph.add_node("generate_report", generate_report)

    graph.add_edge(START, "fetch_profile")
    graph.add_edge("fetch_profile", "fetch_all_posts")
    graph.add_edge("fetch_all_posts", "extract_metrics")
    graph.add_edge("extract_metrics", "analyze_patterns")
    graph.add_edge("analyze_patterns", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile(checkpointer=MemorySaver())
