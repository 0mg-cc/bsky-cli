from __future__ import annotations

import json
from dataclasses import dataclass

from .auth import get_session, resolve_handle
from .storage.db import ensure_schema, open_db
from .threads_mod.utils import uri_to_url


@dataclass
class HistoryResult:
    kind: str
    ts: str
    text: str
    uri: str | None = None
    url: str | None = None
    direction: str | None = None


def _query_history_fts(
    conn,
    *,
    target_did: str,
    query: str,
    scope: str,
    since: str | None,
    until: str | None,
    limit: int,
) -> list[HistoryResult]:
    q = (query or "").strip()
    if not q:
        return []

    scope = (scope or "all").lower()
    if scope not in {"all", "dm", "threads"}:
        scope = "all"

    limit = max(1, int(limit or 25))

    results: list[HistoryResult] = []

    # DMs: filter by convo membership for the target DID
    if scope in {"all", "dm"}:
        where = ["history_fts MATCH ?", "kind='dm'", "convo_id IN (SELECT convo_id FROM dm_convo_members WHERE did=?)"]
        params: list[object] = [q, target_did]
        if since:
            where.append("ts >= ?")
            params.append(since)
        if until:
            where.append("ts <= ?")
            params.append(until)

        rows = conn.execute(
            "SELECT ts, text, direction, uri FROM history_fts WHERE " + " AND ".join(where) + " ORDER BY ts DESC LIMIT ?",
            (*params, limit),
        ).fetchall()

        for r in rows:
            uri = r["uri"] if "uri" in r.keys() else None
            results.append(
                HistoryResult(
                    kind="dm",
                    ts=r["ts"],
                    text=r["text"],
                    uri=uri,
                    url=uri_to_url(uri) if uri else None,
                    direction=r["direction"] if "direction" in r.keys() else None,
                )
            )

    # Threads/interactions
    if scope in {"all", "threads"}:
        where = ["history_fts MATCH ?", "kind='interaction'", "actor_did=?"]
        params2: list[object] = [q, target_did]
        if since:
            where.append("ts >= ?")
            params2.append(since)
        if until:
            where.append("ts <= ?")
            params2.append(until)

        rows = conn.execute(
            "SELECT ts, text, uri FROM history_fts WHERE " + " AND ".join(where) + " ORDER BY ts DESC LIMIT ?",
            (*params2, limit),
        ).fetchall()

        for r in rows:
            uri = r["uri"]
            results.append(
                HistoryResult(
                    kind="interaction",
                    ts=r["ts"],
                    text=r["text"],
                    uri=uri,
                    url=uri_to_url(uri) if uri else None,
                )
            )

    # Merge results and truncate to limit
    results.sort(key=lambda r: r.ts or "", reverse=True)
    return results[:limit]


def run(args) -> int:
    handle = getattr(args, "handle", None)
    query = getattr(args, "query", None)
    scope = getattr(args, "scope", "all")
    since = getattr(args, "since", None)
    until = getattr(args, "until", None)
    limit = int(getattr(args, "limit", 25))
    as_json = bool(getattr(args, "json", False))

    pds, _my_did, _jwt, account_handle = get_session()

    target_did = resolve_handle(pds, str(handle))

    conn = open_db(account_handle)
    ensure_schema(conn)

    results = _query_history_fts(
        conn,
        target_did=target_did,
        query=str(query or ""),
        scope=str(scope or "all"),
        since=str(since) if since else None,
        until=str(until) if until else None,
        limit=limit,
    )

    if as_json:
        payload = {
            "handle": str(handle),
            "did": target_did,
            "query": str(query or ""),
            "scope": str(scope or "all"),
            "results": [
                {
                    "kind": r.kind,
                    "ts": r.ts,
                    "text": r.text,
                    "uri": r.uri,
                    "url": r.url,
                    "direction": r.direction,
                }
                for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if not results:
        print("(no matches)")
        return 0

    for r in results:
        prefix = "DM" if r.kind == "dm" else "THREAD"
        extra = f" ({r.direction})" if r.direction else ""
        print(f"[{prefix}] {r.ts}{extra}: {r.text}")
        if r.url:
            print(f"  {r.url}")

    return 0
