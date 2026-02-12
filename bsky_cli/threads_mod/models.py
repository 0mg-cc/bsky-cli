from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Branch:
    our_reply_uri: str
    our_reply_url: str
    interlocutors: list[str]
    interlocutor_dids: list[str]
    last_activity_at: str
    message_count: int
    topic_drift: float
    branch_score: float

    def to_dict(self) -> dict:
        return {
            "our_reply_uri": self.our_reply_uri,
            "our_reply_url": self.our_reply_url,
            "interlocutors": self.interlocutors,
            "interlocutor_dids": self.interlocutor_dids,
            "last_activity_at": self.last_activity_at,
            "message_count": self.message_count,
            "topic_drift": self.topic_drift,
            "branch_score": self.branch_score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Branch":
        allowed_fields = {
            "our_reply_uri",
            "our_reply_url",
            "interlocutors",
            "interlocutor_dids",
            "last_activity_at",
            "message_count",
            "topic_drift",
            "branch_score",
        }
        filtered = {k: v for k, v in d.items() if k in allowed_fields}
        return cls(**filtered)


@dataclass
class TrackedThread:
    root_uri: str
    root_url: str
    root_author_handle: str
    root_author_did: str
    main_topics: list[str]
    root_text: str
    overall_score: float
    branches: dict[str, Branch]
    total_our_replies: int
    created_at: str
    last_activity_at: str
    engaged_interlocutors: list[str] = field(default_factory=list)
    our_reply_texts: list[str] = field(default_factory=list)
    cron_id: str | None = None
    enabled: bool = True
    backoff_level: int = 0
    last_check_at: str | None = None
    last_new_activity_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "root_uri": self.root_uri,
            "root_url": self.root_url,
            "root_author_handle": self.root_author_handle,
            "root_author_did": self.root_author_did,
            "main_topics": self.main_topics,
            "root_text": self.root_text,
            "overall_score": self.overall_score,
            "branches": {k: v.to_dict() for k, v in self.branches.items()},
            "total_our_replies": self.total_our_replies,
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "engaged_interlocutors": self.engaged_interlocutors,
            "our_reply_texts": self.our_reply_texts,
            "cron_id": self.cron_id,
            "enabled": self.enabled,
            "backoff_level": self.backoff_level,
            "last_check_at": self.last_check_at,
            "last_new_activity_at": self.last_new_activity_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TrackedThread":
        # Validate required fields for legacy state compatibility
        required = ("root_uri", "root_url", "root_author_handle",
                     "root_author_did", "main_topics", "overall_score",
                     "created_at", "last_activity_at")
        missing = [k for k in required if k not in d]
        if missing:
            import sys
            print(f"⚠️  Skipping legacy thread entry (missing: {', '.join(missing)})",
                  file=sys.stderr)
            return None  # type: ignore[return-value]

        branches = {k: Branch.from_dict(v) for k, v in d.get("branches", {}).items()}
        return cls(
            root_uri=d["root_uri"],
            root_url=d["root_url"],
            root_author_handle=d["root_author_handle"],
            root_author_did=d["root_author_did"],
            main_topics=d["main_topics"],
            root_text=d.get("root_text", ""),
            overall_score=d["overall_score"],
            branches=branches,
            total_our_replies=d.get("total_our_replies", 0),
            created_at=d["created_at"],
            last_activity_at=d["last_activity_at"],
            engaged_interlocutors=d.get("engaged_interlocutors", []),
            our_reply_texts=d.get("our_reply_texts", []),
            cron_id=d.get("cron_id"),
            enabled=d.get("enabled", True),
            backoff_level=d.get("backoff_level", 0),
            last_check_at=d.get("last_check_at"),
            last_new_activity_at=d.get("last_new_activity_at"),
        )


@dataclass
class InterlocutorProfile:
    did: str
    handle: str
    display_name: str
    followers_count: int
    follows_count: int
    posts_count: int
    description: str = ""
    labels: list[str] = field(default_factory=list)
