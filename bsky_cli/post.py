"""Post command for BlueSky CLI."""
from __future__ import annotations

import re
from html.parser import HTMLParser

from .http import requests

from .auth import get_session, utc_now_iso, upload_blob


class OGParser(HTMLParser):
    """Parse Open Graph meta tags from HTML."""
    def __init__(self):
        super().__init__()
        self.og = {}
        self._in_title = False
        
    def handle_starttag(self, tag, attrs):
        if tag == "meta":
            attrs_dict = dict(attrs)
            prop = attrs_dict.get("property", attrs_dict.get("name", ""))
            content = attrs_dict.get("content", "")
            if prop.startswith("og:") and content:
                self.og[prop[3:]] = content
            elif prop == "description" and "description" not in self.og:
                self.og["description"] = content
        elif tag == "title" and "title" not in self.og:
            self._in_title = True
            
    def handle_data(self, data):
        if self._in_title:
            self.og["title"] = data.strip()
            self._in_title = False


def detect_facets(text: str) -> list[dict] | None:
    """Detect URLs and hashtags in text."""
    facets = []
    
    def char_to_byte(char_idx: int) -> int:
        return len(text[:char_idx].encode('utf-8'))
    
    # URLs
    for match in re.finditer(r'https?://[^\s<>\[\]()"\'\u200b]+', text):
        url = match.group(0).rstrip('.,;:!?)')
        byte_start = char_to_byte(match.start())
        byte_end = byte_start + len(url.encode('utf-8'))
        facets.append({
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]
        })
    
    # Hashtags
    for match in re.finditer(r'(?:^|\s)(#[^\d\s]\S{0,63})', text):
        tag = match.group(1).rstrip('.,;:!?)')
        byte_start = char_to_byte(match.start(1))
        byte_end = byte_start + len(tag.encode('utf-8'))
        facets.append({
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": tag[1:]}]
        })
    
    return facets if facets else None


def fetch_og_metadata(url: str) -> dict:
    """Fetch Open Graph metadata from URL."""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (compatible; Bsky-bot)"})
        r.raise_for_status()
        parser = OGParser()
        parser.feed(r.text[:50000])
        return parser.og
    except Exception:
        return {"title": url, "description": ""}


def compress_image(data: bytes, max_size: int = 950_000, max_dim: int = 1200) -> tuple[bytes, str]:
    """Compress image to fit BlueSky's 1MB limit."""
    from io import BytesIO
    try:
        from PIL import Image
    except ImportError:
        return data, "image/jpeg"
    
    img = Image.open(BytesIO(data))
    
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    
    for quality in [85, 75, 65, 55, 45]:
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() < max_size:
            return buf.getvalue(), "image/jpeg"
    
    img.thumbnail((800, 800), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=50, optimize=True)
    return buf.getvalue(), "image/jpeg"


def fetch_image(url: str) -> tuple[bytes, str] | None:
    """Fetch image and return (data, mime_type)."""
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if ct.startswith("image/"):
            data = r.content
            if len(data) > 900_000:
                data, ct = compress_image(data)
            return data, ct
    except Exception:
        pass
    return None


def create_external_embed(pds: str, jwt: str, url: str) -> dict:
    """Create external embed with link preview."""
    og = fetch_og_metadata(url)
    
    embed = {
        "$type": "app.bsky.embed.external",
        "external": {
            "uri": url,
            "title": og.get("title", url)[:300],
            "description": og.get("description", "")[:1000],
        }
    }
    
    img_url = og.get("image")
    if img_url:
        if img_url.startswith("/"):
            from urllib.parse import urljoin
            img_url = urljoin(url, img_url)
        img_data = fetch_image(img_url)
        if img_data:
            data, mime = img_data
            if len(data) < 1_000_000:
                blob = upload_blob(pds, jwt, data, mime)
                embed["external"]["thumb"] = blob
    
    return embed


def resolve_post(pds: str, jwt: str, url: str) -> tuple[str, str] | None:
    """
    Resolve a post URL to (uri, cid).
    Returns None if resolution fails.
    """
    import re
    
    # Parse URL: https://bsky.app/profile/HANDLE_OR_DID/post/RKEY
    m = re.match(r"https://bsky\.app/profile/([^/]+)/post/([^/]+)", url)
    if not m:
        return None
    
    actor, rkey = m.groups()
    
    # Resolve handle to DID if needed
    if not actor.startswith("did:"):
        try:
            r = requests.get(
                f"{pds}/xrpc/com.atproto.identity.resolveHandle",
                headers={"Authorization": f"Bearer {jwt}"},
                params={"handle": actor},
                timeout=10
            )
            r.raise_for_status()
            actor = r.json()["did"]
        except Exception:
            return None
    
    # Build URI and fetch post to get CID
    uri = f"at://{actor}/app.bsky.feed.post/{rkey}"
    
    try:
        r = requests.get(
            f"{pds}/xrpc/app.bsky.feed.getPosts",
            headers={"Authorization": f"Bearer {jwt}"},
            params={"uris": uri},
            timeout=15
        )
        r.raise_for_status()
        posts = r.json().get("posts", [])
        if posts:
            return uri, posts[0].get("cid")
    except Exception:
        pass
    
    return None


def create_quote_embed(uri: str, cid: str) -> dict:
    """Create a quote post embed."""
    return {
        "$type": "app.bsky.embed.record",
        "record": {
            "uri": uri,
            "cid": cid
        }
    }


def create_post(pds: str, jwt: str, did: str, text: str, facets=None, embed=None) -> dict:
    """Create a post."""
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": utc_now_iso(),
        "langs": ["en"],
    }
    if facets:
        record["facets"] = facets
    if embed:
        record["embed"] = embed
    
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {jwt}"},
        json={"repo": did, "collection": "app.bsky.feed.post", "record": record},
        timeout=20
    )
    r.raise_for_status()
    return r.json()


def run(args) -> int:
    """Execute post command."""
    if not args.text:
        print("Error: text is required")
        return 2

    text = args.text.strip()
    if len(text) > 300:
        raise SystemExit(f"Post too long ({len(text)} chars, max 300)")

    facets = detect_facets(text)
    quote_url = getattr(args, 'quote', None)

    if args.dry_run:
        print(f"DRY RUN\nText: {text}\nEmbed: {args.embed}\nQuote: {quote_url}")
        return 0

    pds, did, jwt, _ = get_session()

    embed = None
    
    # Quote post takes precedence over link embed
    if quote_url:
        resolved = resolve_post(pds, jwt, quote_url)
        if not resolved:
            raise SystemExit(f"Could not resolve post: {quote_url}")
        uri, cid = resolved
        embed = create_quote_embed(uri, cid)
        print(f"📝 Quoting: {quote_url}")
    elif args.embed:
        embed = create_external_embed(pds, jwt, args.embed)

    res = create_post(pds, jwt, did, text, facets=facets, embed=embed)
    
    uri = res.get("uri", "")
    m = re.match(r"^at://([^/]+)/app\.bsky\.feed\.post/([^/]+)$", uri)
    if m:
        print(f"https://bsky.app/profile/{m.group(1)}/post/{m.group(2)}")
    else:
        print(res)
    return 0
