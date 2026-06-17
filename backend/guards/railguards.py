"""
Railguards — safety checks applied before any auto-response.
Prevents spam, rate limit abuse, and ensures brand safety.
"""

from datetime import datetime, timedelta
from backend.config import settings


class Railguards:
    """Stateful guardrails: rate limit, blocklist, cooldown, anti-spam."""

    def __init__(self, config: dict = None):
        cfg = config or {}
        self.blocklist_words: list[str] = cfg.get("blocklist_words", [])
        self.max_replies_per_hour: int = cfg.get("max_replies_per_hour", settings.MAX_REPLIES_PER_HOUR)
        self.min_follower_count: int = cfg.get("min_follower_count", settings.MIN_FOLLOWER_COUNT)
        self.cooldown_minutes: int = cfg.get("cooldown_minutes", settings.COOLDOWN_MINUTES)
        self._reply_log: dict[str, list[datetime]] = {}

    def should_respond(
        self,
        sender_username: str,
        text: str,
        sender_followers: int = 100,
    ) -> tuple[bool, str]:
        """Check all guards. Returns (should_respond, reason)."""

        # 1. Blocklist
        text_lower = text.lower()
        for word in self.blocklist_words:
            if word.lower() in text_lower:
                return False, f"blocklist:{word}"

        # 2. Anti-spam: too few followers
        if sender_followers < self.min_follower_count:
            return False, "low_followers"

        # 3. Hourly rate limit (global)
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        total = sum(
            len([t for t in times if t > hour_ago])
            for times in self._reply_log.values()
        )
        if total >= self.max_replies_per_hour:
            return False, "rate_limit"

        # 4. Per-user cooldown
        user_replies = self._reply_log.get(sender_username, [])
        cooldown_ago = now - timedelta(minutes=self.cooldown_minutes)
        recent = [t for t in user_replies if t > cooldown_ago]
        if len(recent) >= 2:
            return False, f"cooldown:{sender_username}"

        return True, "ok"

    def log_reply(self, sender_username: str):
        """Record that we replied to this user."""
        if sender_username not in self._reply_log:
            self._reply_log[sender_username] = []
        self._reply_log[sender_username].append(datetime.now())

        # Cleanup: remove entries older than 2 hours
        cutoff = datetime.now() - timedelta(hours=2)
        self._reply_log[sender_username] = [
            t for t in self._reply_log[sender_username] if t > cutoff
        ]

    def add_blocklist_word(self, word: str):
        if word.lower() not in [w.lower() for w in self.blocklist_words]:
            self.blocklist_words.append(word)

    def remove_blocklist_word(self, word: str):
        self.blocklist_words = [w for w in self.blocklist_words if w.lower() != word.lower()]

    def get_stats(self) -> dict:
        now = datetime.now()
        hour_ago = now - timedelta(hours=1)
        total_last_hour = sum(
            len([t for t in times if t > hour_ago])
            for times in self._reply_log.values()
        )
        return {
            "replies_last_hour": total_last_hour,
            "max_per_hour": self.max_replies_per_hour,
            "remaining": self.max_replies_per_hour - total_last_hour,
            "blocklist_size": len(self.blocklist_words),
            "tracked_users": len(self._reply_log),
        }
