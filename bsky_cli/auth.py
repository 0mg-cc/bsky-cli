"""Common authentication and API utilities for BlueSky."""
from __future__ import annotations

import datetime as dt
import subprocess

import requests

PASS_PATH = "api/bsky-echo"


def load_from_pass(pass_path: str = PASS_PATH) -> dict | None:
    """Load credentials from pass."""
    try:
        result = subprocess.run(
            ["pass", "show", pass_path],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        out: dict[str, str] = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
        return out if out else None
    except Exception:
        return None


def load_credentials() -> dict:
    """Load credentials from pass, raise if missing."""
    env = load_from_pass()
    if not env:
        raise SystemExit("Cannot load credentials from pass api/bsky")
    return env


def create_session(pds: str, identifier: str, password: str) -> dict:
    """Create an authenticated session."""
    url = pds.rstrip("/") + "/xrpc/com.atproto.server.createSession"
    r = requests.post(url, json={"identifier": identifier, "password": password}, timeout=20)
    r.raise_for_status()
    return r.json()


def get_session() -> tuple[str, str, str, str]:
    """Get authenticated session. Returns (pds, did, access_jwt, handle)."""
    env = load_credentials()
    pds = env.get("BSKY_PDS", "https://bsky.social")
    handle = env.get("BSKY_HANDLE")
    email = env.get("BSKY_EMAIL")
    app_pw = env.get("BSKY_APP_PASSWORD")

    if not app_pw or not (handle or email):
        raise SystemExit("Missing BSKY_HANDLE/BSKY_EMAIL or BSKY_APP_PASSWORD")

    identifier = handle or email
    sess = create_session(pds, identifier, app_pw)
    return pds, sess["did"], sess["accessJwt"], handle or email


def utc_now_iso() -> str:
    """Return current UTC time in ISO format."""
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upload_blob(pds: str, jwt: str, data: bytes, mime_type: str) -> dict:
    """Upload a blob to the PDS."""
    r = requests.post(
        f"{pds}/xrpc/com.atproto.repo.uploadBlob",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": mime_type},
        data=data,
        timeout=60
    )
    r.raise_for_status()
    return r.json()["blob"]


def resolve_handle(pds: str, handle: str) -> str:
    """Resolve a handle to a DID."""
    if handle.startswith("did:"):
        return handle
    url = pds.rstrip("/") + "/xrpc/com.atproto.identity.resolveHandle"
    r = requests.get(url, params={"handle": handle}, timeout=10)
    r.raise_for_status()
    return r.json()["did"]
