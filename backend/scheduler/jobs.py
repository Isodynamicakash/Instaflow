"""
Scheduled background jobs — metrics refresh, content gen, digests.
"""

from backend.services import supabase_client as db
from backend.services.instagram_api import InstagramAPI
from backend.services.token_manager import get_token


async def refresh_all_metrics():
    """Fetch latest post insights for all active users. Runs every 6 hours."""
    print("📊 Refreshing metrics for all users...")
    users = await db.list_users()
    for user in users:
        try:
            token = await get_token(user["ig_user_id"])
            if not token:
                continue
            api = InstagramAPI(token, user["ig_user_id"])
            posts = await api.get_media(limit=20)
            for post in posts:
                insights = await api.get_media_insights(post["id"], post.get("media_type", "IMAGE"))
                if insights:
                    await db.upsert_metric({
                        "post_id": post["id"],
                        **insights,
                        "likes_count": post.get("like_count", 0),
                        "comments_count": post.get("comments_count", 0),
                    })
        except Exception as e:
            print(f"  ⚠️ Metrics refresh failed for {user.get('ig_username')}: {e}")
    print("✅ Metrics refresh complete")


async def refresh_intelligence():
    """Re-run intelligence analysis for all users. Updates brand voice,
    top hashtags, best posting times, content themes. Runs weekly."""
    print("🧠 Refreshing intelligence for all users...")
    from backend.agents.intelligence import build_intelligence_graph

    users = await db.list_users()
    graph = build_intelligence_graph()

    for user in users:
        try:
            token = await get_token(user["ig_user_id"])
            if not token:
                continue

            result = await graph.ainvoke(
                {
                    "user_id": user["id"],
                    "access_token": token,
                    "ig_user_id": user["ig_user_id"],
                    "profile": {},
                    "posts": [],
                    "metrics": [],
                    "analysis": {},
                    "report": "",
                    "error": None,
                },
                config={"configurable": {
                    "thread_id": f"intel-refresh-{user['ig_user_id']}"
                }},
            )

            # Update user's brand voice and analysis
            analysis = result.get("analysis", {})
            if analysis.get("writing_style"):
                await db.upsert_user({
                    "id": user["id"],
                    "ig_user_id": user["ig_user_id"],
                    "brand_voice": analysis["writing_style"],
                    "latest_analysis": analysis,
                })
            print(f"  ✅ Intelligence updated for @{user.get('ig_username')}")
        except Exception as e:
            print(f"  ⚠️ Intelligence refresh failed for {user.get('ig_username')}: {e}")

    print("✅ Intelligence refresh complete")


async def update_posting_analytics():
    """Analyze best posting times from historical data. Runs daily."""
    print("📅 Updating posting analytics...")
    users = await db.list_users()

    for user in users:
        try:
            token = await get_token(user["ig_user_id"])
            if not token:
                continue

            api = InstagramAPI(token, user["ig_user_id"])
            posts = await api.get_media(limit=50)

            # Group by day and hour
            from collections import defaultdict
            time_slots = defaultdict(lambda: {"total_engagement": 0, "count": 0})

            for post in posts:
                ts = post.get("timestamp", "")
                if not ts:
                    continue
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(ts.replace("+0000", "+00:00"))
                    key = (dt.weekday(), dt.hour)
                    engagement = (post.get("like_count", 0) or 0) + (post.get("comments_count", 0) or 0)
                    time_slots[key]["total_engagement"] += engagement
                    time_slots[key]["count"] += 1
                except Exception:
                    continue

            # Store best times
            for (day, hour), stats in time_slots.items():
                if stats["count"] > 0:
                    await db.upsert_posting_analytics({
                        "user_id": user["id"],
                        "day_of_week": day,
                        "hour_of_day": hour,
                        "avg_engagement": stats["total_engagement"] / stats["count"],
                        "sample_count": stats["count"],
                    })

            print(f"  ✅ Posting analytics updated for @{user.get('ig_username')}")
        except Exception as e:
            print(f"  ⚠️ Posting analytics failed for {user.get('ig_username')}: {e}")

    print("✅ Posting analytics complete")


async def weekly_digest():
    """Send weekly performance summary. Phase 2: via WhatsApp."""
    print("📈 Weekly digest — Phase 2 (WhatsApp)")