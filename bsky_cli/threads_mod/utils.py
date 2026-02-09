import re


def uri_to_url(uri: str) -> str:
    m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri)
    if m:
        return f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}"
    return uri
