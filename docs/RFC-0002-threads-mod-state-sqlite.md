# RFC-0002 — threads_mod state JSON → SQLite

Contexte : le module `bsky_cli.threads_mod` utilise encore un state JSON local (`~/personas/echo/data/bsky-threads-state.json`) via `load_threads_state()/save_threads_state()`.

Objectif (PR-007) : éliminer ce legacy et migrer ce state vers la DB SQLite par account (`~/.bsky-cli/accounts/<account>/bsky.db`).

## Ce qu’on doit préserver

Le state actuel (voir `bsky_cli/threads_mod/state.py`) contient :

- `threads` : mapping (root_uri → metadata)
- `evaluated_notifications` : liste (tail -500)
- `last_evaluation` : timestamp ISO

Et, côté config, la logique `watch/backoff` utilise :

- `BACKOFF_INTERVALS = [10, 20, 40, 80, 160, 240]`
- `DEFAULT_SILENCE_HOURS = 18`

## Proposition de schéma (migration DB v6)

### Table 1 — thread_watch_state

Une table par *account* (donc dans sa DB) :

- `root_uri TEXT NOT NULL`
- `actor_did TEXT NOT NULL` (nullable si inconnu/legacy ? à éviter)
- `status TEXT NOT NULL` (ex: 'watching'|'silenced'|'closed')
- `backoff_step INTEGER NOT NULL DEFAULT 0`
- `next_check_at TEXT` (ISO)
- `silence_until TEXT` (ISO)
- `last_checked_at TEXT` (ISO)
- `created_at TEXT NOT NULL DEFAULT now`
- `updated_at TEXT NOT NULL DEFAULT now`

PK : `(root_uri, actor_did)`

### Table 2 — evaluated_notifications

Stockage append-only avec pruning (ex: garder 500 derniers) :

- `notif_id TEXT PRIMARY KEY`
- `evaluated_at TEXT NOT NULL DEFAULT now`

Option : index sur `evaluated_at` + job de cleanup.

### Table 3 — threads_mod_meta

- `key TEXT PRIMARY KEY`
- `value TEXT NOT NULL`

Pour `last_evaluation` et autres flags.

## Migration one-shot

Nouvelle commande :

- `bsky threads migrate-state --from-json <path?> --account <handle?>`

Comportement :

1) Lire le JSON legacy
2) Mapper vers les nouvelles tables (best-effort)
3) Écrire en DB dans une transaction
4) Option `--dry-run` qui n’écrit pas
5) Option `--archive-json` qui renomme le JSON en `*.bak.<ts>`

## Anti-régression / tests

- Test que `migrate-state`:
  - crée bien les rows attendues
  - respecte le pruning (500)
  - est idempotent

## Notes

- Comme la DB est *par account*, on évite les collisions multi-agents.
- Les timestamps doivent rester ISO (même format que le reste du projet).
