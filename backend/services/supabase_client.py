"""
In-Memory Data Store — replaces Supabase for Phase 1.
Drop-in replacement: swap this file for real supabase_client.py later.
All function signatures stay the same.
"""

import uuid
from datetime import datetime
from typing import Optional


# ── In-memory tables ──
_users: dict[str, dict] = {}
_posts: dict[str, dict] = {}
_metrics: dict[str, dict] = {}
_rules: dict[str, dict] = {}
_engagement_log: list[dict] = []
_content_queue: list[dict] = []
_posting_analytics: list[dict] = []


# ── Users ──

async def upsert_user(data: dict) -> dict:
    uid = data.get("id") or str(uuid.uuid4())
    data["id"] = uid
    data.setdefault("created_at", datetime.now().isoformat())
    _users[uid] = data
    return data


async def get_user_by_ig_id(ig_user_id: str) -> Optional[dict]:
    for u in _users.values():
        if u.get("ig_user_id") == ig_user_id:
            return u
    return None


async def get_user(user_id: str) -> Optional[dict]:
    return _users.get(user_id)


async def list_users() -> list[dict]:
    return list(_users.values())


# ── Posts ──

async def upsert_post(data: dict) -> dict:
    pid = data.get("id") or str(uuid.uuid4())
    data["id"] = pid
    _posts[data.get("ig_media_id", pid)] = data
    return data


async def get_posts_by_user(user_id: str, limit: int = 50) -> list[dict]:
    return [
        p for p in _posts.values()
        if p.get("user_id") == user_id
    ][:limit]


# ── Metrics ──

async def upsert_metric(data: dict) -> dict:
    mid = data.get("id") or str(uuid.uuid4())
    data["id"] = mid
    data.setdefault("measured_at", datetime.now().isoformat())
    _metrics[mid] = data
    return data


async def get_metrics_by_user(user_id: str, limit: int = 50) -> list[dict]:
    user_post_ids = {p["id"] for p in _posts.values() if p.get("user_id") == user_id}
    return [
        m for m in _metrics.values()
        if m.get("post_id") in user_post_ids
    ][:limit]


# ── Engagement Rules ──

async def create_rule(data: dict) -> dict:
    rid = data.get("id") or str(uuid.uuid4())
    data["id"] = rid
    data.setdefault("is_active", True)
    data.setdefault("created_at", datetime.now().isoformat())
    _rules[rid] = data
    return data


async def get_rules_by_user(user_id: str, active_only: bool = True) -> list[dict]:
    rules = [r for r in _rules.values() if r.get("user_id") == user_id]
    if active_only:
        rules = [r for r in rules if r.get("is_active")]
    return rules


async def update_rule(rule_id: str, updates: dict) -> Optional[dict]:
    if rule_id in _rules:
        _rules[rule_id].update(updates)
        return _rules[rule_id]
    return None


async def delete_rule(rule_id: str) -> bool:
    return _rules.pop(rule_id, None) is not None


# ── Engagement Log ──

async def log_engagement(data: dict) -> dict:
    data["id"] = str(uuid.uuid4())
    data.setdefault("created_at", datetime.now().isoformat())
    _engagement_log.append(data)
    # Keep last 1000
    if len(_engagement_log) > 1000:
        _engagement_log.pop(0)
    return data


async def get_engagement_log(user_id: str, limit: int = 50) -> list[dict]:
    return [
        e for e in reversed(_engagement_log)
        if e.get("user_id") == user_id
    ][:limit]


# ── Content Queue ──

async def add_to_content_queue(data: dict) -> dict:
    data["id"] = str(uuid.uuid4())
    data.setdefault("status", "pending")
    data.setdefault("created_at", datetime.now().isoformat())
    _content_queue.append(data)
    return data


async def get_content_queue(user_id: str) -> list[dict]:
    return [c for c in _content_queue if c.get("user_id") == user_id]


# ── Posting Analytics ──

async def upsert_posting_analytics(data: dict) -> dict:
    data.setdefault("updated_at", datetime.now().isoformat())
    _posting_analytics.append(data)
    return data


async def get_posting_analytics(user_id: str) -> list[dict]:
    return [a for a in _posting_analytics if a.get("user_id") == user_id]


# ── Summary Stats ──

async def get_engagement_summary(user_id: str) -> dict:
    log = [e for e in _engagement_log if e.get("user_id") == user_id]
    return {
        "total_auto_replies": sum(1 for e in log if "reply" in e.get("action_type", "")),
        "total_dms_sent": sum(1 for e in log if "dm" in e.get("action_type", "")),
        "total_escalations": sum(1 for e in log if "escalat" in e.get("action_type", "")),
        "total_blocked": sum(1 for e in log if "block" in e.get("action_type", "")),
        "total_events": len(log),
    }
