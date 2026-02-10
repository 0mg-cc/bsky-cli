# Context v2 (BlueSky) — Plan d’implémentation en PRs

Objectif : contexte pertinent par handle (threads + DMs + notes) avec séparation HOT/COLD, stockage SQLite par account + FTS5, sans régression.

Règles :
- DMs sortants : **anglais**.
- Toujours utiliser des **richtext facets** (URLs / @handles / #hashtags cliquables).
- À chaque PR mergeable : ouvrir une PR GitHub pour review (Codex), mettre à jour ce plan, aviser Mathieu, attendre instructions.

---

## PR-001 — SQLite per-account + `bsky context` (v1) + `--focus`
**But** : poser la base DB + une commande `bsky context` utile immédiatement.

- [x] RFC initial (SQLite per-account, HOT/COLD, extraits)
- [x] DB + migrations v1
- [x] `bsky context` (10 derniers threads partagés + 3 extraits)
- [x] `bsky context --focus` : focus + path + branching answers
- [x] Tests smoke + doc `--help`

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/3 (**MERGED**)

---

## PR-002 — DM facets + DM poll correctness (skip self)
- [x] DMs sortants : facets (URLs/@/#)
- [x] DM poll : ignorer nos propres messages
- [x] Tests

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/4 (**MERGED**)

---

## PR-003 — Ingestion DMs → SQLite + DB-first pour HOT context
- [x] Tables DM + ingestion idempotente (convo_id,msg_id)
- [x] `bsky notify` : ingest best-effort (poller “ingest then decide” sera fait séparément côté scripts)
- [x] `bsky context` : HOT depuis DB, fallback live

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/5 (**MERGED**)

---

## Hotfix — DM newlines normalization
- [x] Normaliser par défaut les sauts de ligne en DM (join avec " — ")
- [x] Option `--raw` pour envoyer tel quel

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/7 (**MERGED**)

---

## PR-004 — Threads index DB + extraits fiables focus-aware par défaut
- [x] Index 10 threads “shared” depuis DB (source de vérité)
- [x] Extraits fiables : root + path + branches + last us/them (fallback focus)
- [x] Fallback focus robuste (dernier post d’interaction)

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/8 (**MERGED**)

---

## PR-005 — FTS5 + `bsky search-history`
- [ ] FTS5 sur DMs + threads/posts
- [ ] `bsky search-history "term" --handle ... --source dm|threads|all --since/--until`

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/11 (**OPEN**)

---

## PR-006 — People/notes v2 (DB) + enrich opt-in + drift prevention
- [ ] `bsky people` lit/écrit DB
- [ ] `people enrich` opt-in : résumés courts (2–4 phrases) + interests/tone
- [ ] Timestamps + (idéalement) versioning append-only

---

## PR-007 — Migration threads_mod state JSON → SQLite (fin du legacy)
- [ ] watch/backoff/state en DB
- [ ] commande de migration one-shot
