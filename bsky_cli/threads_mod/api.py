from ..http import requests
from .models import InterlocutorProfile


def get_profile(pds: str, jwt: str, actor: str) -> InterlocutorProfile | None:
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.actor.getProfile",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"actor": actor},
            timeout=15,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        return InterlocutorProfile(
            did=data.get("did", ""),
            handle=data.get("handle", ""),
            display_name=data.get("displayName", ""),
            followers_count=data.get("followersCount", 0),
            follows_count=data.get("followsCount", 0),
            posts_count=data.get("postsCount", 0),
            description=data.get("description", ""),
            labels=[l.get("val", "") for l in data.get("labels", [])],
        )
    except Exception:
        return None


def get_thread(pds: str, jwt: str, uri: str, depth: int = 10) -> dict | None:
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.feed.getPostThread",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"uri": uri, "depth": depth, "parentHeight": 10},
            timeout=20,
        )
        if r.status_code != 200:
            return None
        return r.json().get("thread", {})
    except Exception:
        return None


def get_notifications(pds: str, jwt: str, limit: int = 50) -> list[dict]:
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.notification.listNotifications",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"limit": limit},
            timeout=20,
        )
        r.raise_for_status()
        return r.json().get("notifications", [])
    except Exception:
        return []
