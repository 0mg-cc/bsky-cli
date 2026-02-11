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
- [x] FTS5 sur DMs + threads/interactions
- [x] `bsky search-history <handle|did> <query> --scope dm|threads|all --since/--until`

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/11 (**MERGED**)

---

## PR-006 — People/notes v2 (DB) + enrich opt-in + drift prevention
- [x] `bsky people` lit/écrit DB (stats/list/single)
- [x] Notes/tags manuels en DB (`--set-note`, `--add-tag`, `--remove-tag`)
- [x] `bsky people --enrich` opt-in (dry-run par défaut) : notes_auto + interests_auto + tone
- [x] Drift prevention : cooldown `--min-age-hours` + `--force`
- [x] Versioning append-only : snapshots `actor_auto_notes` (notes/interests/tone)
- [x] Review Codex traitée + merge

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/14 (**MERGED**)

---

## PR-007 — Migration threads_mod state JSON → SQLite (fin du legacy)
- [x] watch/backoff/state en DB (tables `threads_mod_*` + DB-backed load/save)
- [x] commande de migration one-shot : `bsky threads migrate-state [--from-json] [--archive-json] [--dry-run]`
- [x] Review Codex + merge

**PR GitHub** : https://github.com/echo931/bsky-cli/pull/15 (**MERGED**)

---

## Hotfix plan (post-PR007) — bugs trouvés en tests manuels

### P0 — `bsky threads tree` cassé (`Unknown threads command`)
- **Symptôme**: `bsky threads tree <url>` retourne `Unknown threads command`.
- **Cause probable**: `tree` documenté dans le parser/help mais non routé dans `threads_mod/commands.py::run()` (branche manquante vers `cmd_tree`).
- **Fix immédiat**:
  1. Ajouter le dispatch `elif args.threads_command == "tree": return cmd_tree(args)`.
  2. Ajouter test CLI régression (commande `threads tree` route bien et n’échoue plus sur “Unknown threads command”).
  3. Vérifier output arbre sur un thread réel.

### P0 — `bsky context` échoue (DB schema)
- **Symptôme**: `sqlite3.OperationalError: no such table: dm_convo_members`.
- **Cause probable**: migration/schéma SQLite incomplet sur certaines DB account (tables DM membership absentes), code `context_cmd` suppose schéma complet.
- **Fix immédiat**:
  1. Garantir migration DM au startup/open DB (idempotent).
  2. Ajouter garde-fou: si table absente, fallback contrôlé + message actionnable (pas traceback brut).
  3. Test d’intégration: DB legacy partielle -> `bsky context ... --json` passe après auto-migration.

### P0 — `bsky search-history` échoue (même cause DB)
- **Symptôme**: même erreur `no such table: dm_convo_members`.
- **Cause probable**: requête FTS joint/filtre sur schéma attendu, mais DB pas migrée.
- **Fix immédiat**:
  1. Réutiliser la même stratégie migration/ensure-schema que `context`.
  2. Test d’intégration: DB partielle -> `search-history` retourne résultat vide ou hits, pas crash.

### P1 — Stabilité runtime `engage` / `appreciate` / `discover`
- **Symptôme**: appels parfois longs/hang en tests manuels, sessions interrompues par timeout/SIGKILL côté orchestration.
- **Cause probable**: latence réseau/LLM + absence d’output progressif + commandes non bornées.
- **Fix immédiat**:
  1. Ajouter timeout interne configurable + logs progressifs (phase fetch/select/generate/post).
  2. Ajouter mode `--max-runtime-seconds` (safe for cron/manual smoke).
  3. Tests smoke en CI avec budgets faibles et timeout court.

## Exécution immédiate (ordre)
1. Hotfix P0 `threads tree`.
2. Hotfix P0 migration/ensure-schema partagée pour `context` + `search-history`.
3. Re-run tests manuels (commandes cron + outputs réels) et coller sorties.
4. Stabilisation P1 timeouts/observabilité pour `engage`/`appreciate`/`discover`.
