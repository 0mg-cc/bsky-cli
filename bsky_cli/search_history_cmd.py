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


def _fts_escape_query(q: str) -> str:
    """Escape a user query into a safer FTS5 MATCH expression.

    FTS5 parses MATCH input as an expression; punctuated literals like `did:plc:...`,
    `@handle`, or URLs can throw OperationalError unless quoted.

    Goals:
    - Keep phrase queries intact ("foo bar")
    - Quote punctuated literals to avoid syntax errors
    - Preserve common FTS operators/syntax (prefix `*`, unary `-`, parentheses)
    """

    q = (q or "").strip()
    if not q:
        return ""

    import shlex

    try:
        tokens = shlex.split(q)
    except ValueError:
        # Fallback if user has unmatched quotes
        tokens = q.split()

    def is_bare_word(s: str) -> bool:
        return bool(s) and all((c.isalnum() or c == "_") for c in s)

    out: list[str] = []
    for raw in tokens:
        tok = raw

        # Preserve parentheses as-is (basic grouping)
        if tok in {"(", ")"}:
            out.append(tok)
            continue

        # Preserve explicit boolean operators
        if tok.upper() in {"AND", "OR", "NOT"}:
            out.append(tok.upper())
            continue

        # Preserve NEAR (e.g. NEAR/5)
        if tok.upper().startswith("NEAR/") and tok[5:].isdigit():
            out.append(tok.upper())
            continue

        # Handle unary NOT prefix (-term)
        prefix = ""
        if tok.startswith("-") and len(tok) > 1:
            prefix = "-"
            tok = tok[1:]

        # Preserve prefix queries like foo*
        if tok.endswith("*") and is_bare_word(tok[:-1]):
            out.append(prefix + tok)
            continue

        # Quote tokens with punctuation/symbols (including ':' '/' '.' '@') OR spaces
        # to force literal/phrase match.
        if (" " in tok) or not is_bare_word(tok):
            tok = tok.replace('"', '""')
            out.append(prefix + f'"{tok}"')
        else:
            out.append(prefix + tok)

    return " ".join(out)


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
    q = _fts_escape_query(query)
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

    # Normalize date-only bounds to be inclusive.
    # Stored timestamps are full ISO strings (e.g. 2026-02-10T00:00:02Z).
    if isinstance(since, str) and len(since) == 10 and since.count("-") == 2:
        since = since + "T00:00:00Z"
    if isinstance(until, str) and len(until) == 10 and until.count("-") == 2:
        until = until + "T23:59:59Z"

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
