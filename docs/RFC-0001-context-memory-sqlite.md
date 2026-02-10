# RFC-0001 — BlueSky Context & Memory (SQLite, per account)

## TL;DR
On remplace le patchwork de JSONs (interlocutors, threads-state, etc.) par **une base SQLite par compte BlueSky**, avec **FTS5** pour la recherche texte.

Objectif produit : à chaque interaction avec un handle, pouvoir reconstruire automatiquement un **contexte pertinent** (DM récents + derniers threads partagés + notes interlocuteur), avec une séparation claire **HOT vs COLD** dans le prompt.

---

## 1) Contexte / Problème
Aujourd’hui, l’agent interagit sur BlueSky mais n’a pas, de façon systématique et robuste :

- un moyen d’assembler le contexte pertinent **par interlocuteur** (threads + DMs),
- un système unifié de notes/tags/qualité relationnelle,
- une recherche “au besoin” sur l’historique complet, filtrable par handle(s),
- une injection standardisée “contexte chaud vs froid” dans les prompts LLM.

On a aussi un risque de régression car plusieurs briques existent déjà (interlocutors.json, threads state JSON, DM poll script). La migration doit être **incrémentale**, avec validation.

---

## 2) État actuel (source de vérité)

### Stores existants
- **Interlocuteurs** : `~/.bsky-cli/interlocutors.json`
  - contient : did/handle/displayName, first_seen/last_interaction, tags, notes, interactions (avec snippets).
- **Threads monitoring** : `~/personas/echo/data/bsky-threads-state.json` (via `bsky threads …`)
  - contient : threads trackés + backoff + état d’évaluation.
- **Dernier “seen” notifications** : `/home/echo/.local/state/bsky_last_seen.txt` (dans `bsky notify`).

### Poll DM
- Script : `/home/echo/scripts/bsky-dm-poll.sh`
- Source : `uv run bsky notify --json` (renvoie `{notifications: [...], dms: [...]}`)

### Limitations actuelles
- Contexte DM/thread pas automatiquement assemblé “par handle”.
- Multiplication de JSONs → difficile à requêter + pas d’index.
- Recherche historique : inexistante (ou ad hoc).
- “Last 10 shared threads” : pas d’index stable (root_uri, participants, extraits).

---

## 3) Objectifs / Non-objectifs

### Objectifs
1. **1 DB par account** BlueSky.
2. Commande **`bsky context <handle>`** qui retourne un “context pack” prêt à injecter.
3. Par défaut, `bsky context` montre :
   - **10 threads partagés**, chacun avec **3 extraits** (root/last us/last them)
   - **DM récents** (N messages)
   - **notes/tags** interlocuteur + metadata (first_seen, last_seen, relation)
4. Recherche historique via **SQLite FTS5**, filtrable par **un ou plusieurs handles**.
5. Injection de contexte **toujours fournie** aux actions LLM, avec séparation explicite :
   - **HOT CONTEXT** : conversation active
   - **COLD CONTEXT** : mémoire / historique
6. Pas de régression : migration incrémentale + tests + possibilité de rollback.

### Non-objectifs (v1)
- Embeddings / vector store (peut venir plus tard). **FTS5 ≠ embeddings**.
- Résumés narratifs LLM automatiques en continu (coût/bruit). On fait du **lazy/opt-in**.
- Synchronisation multi-machines / cloud.

---

## 4) Architecture proposée

### Layout fichiers (per-account)
- Base : `~/.bsky-cli/accounts/<account_handle>/bsky.db`
- Eventuellement : `~/.bsky-cli/accounts/<account_handle>/cache/` (si on cache des records JSON bruts)

**Sélection du compte**
- Par défaut : handle du compte courant (via credentials `api/bsky-echo` ou config bsky-cli).
- Option : `--account <handle>`.

### Couche storage
Un module `bsky_cli/storage/` (nouveau) avec :
- `db.py` : ouverture SQLite (WAL, busy_timeout), migrations.
- `schema.sql` : DDL.
- `queries.py` : fonctions de lecture/écriture.

### Pipelines
1) **Ingestion** (écrit dans DB)
- Notifications (reply/mention/like/follow/repost)
- DMs (reçus/envoyés)
- Interactions “nous avons posté un reply/DM/like/follow”

2) **Context builder**
- assemble le pack HOT/COLD pour un handle.

3) **Search**
- FTS5 pour texte, avec filtres (handles, date range, source).

4) **Enrichment notes**
- Déterministe (stats/tags)
- LLM lazy (opt-in) : “people enrich …”

---

## 5) Modèle de données (SQLite)

> Note : on privilégie un schéma simple + extensible, normalisé là où ça compte, et FTS5 pour la recherche.

### Tables principales

**accounts**
- `account_id` (PK)
- `handle` (unique)
- `did`
- `created_at`

**actors** (interlocuteurs)
- `actor_id` (PK)
- `did` (unique)
- `handle_current`
- `display_name_current`
- `first_seen_at`
- `last_seen_at`
- `interaction_count`

**actor_handles** (historique de handle)
- `actor_id` (FK)
- `handle`
- `seen_at`

**actor_notes**
- `actor_id` (FK)
- `notes_manual` (texte)
- `notes_auto` (texte)
- `interests_auto` (json/text)
- `relationship_tone` (enum/text)
- `updated_at`

**actor_tags**
- `actor_id` (FK)
- `tag` (text)
- unique(actor_id, tag)

**interactions**
- `interaction_id` (PK)
- `actor_id` (FK)
- `type` (reply_to_them, they_replied, dm_sent, dm_received, liked_their_post, …)
- `created_at`
- `post_uri` (nullable)
- `root_uri` (nullable)
- `our_text` (nullable)
- `their_text` (nullable)

### DMs
**dm_conversations**
- `convo_id` (PK)
- `actor_id` (FK)
- `last_message_at`

**dm_messages**
- `msg_id` (PK)
- `convo_id` (FK)
- `actor_id` (FK)
- `direction` (in|out)
- `sent_at`
- `text` (full)
- `raw_json` (optional)

### Threads (index)
**threads**
- `root_uri` (PK)
- `root_author_actor_id`
- `root_created_at`
- `last_seen_at`
- `our_last_post_uri` (nullable)
- `their_last_post_uri` (nullable)

**thread_participants**
- `root_uri` (FK)
- `actor_id` (FK)
- unique(root_uri, actor_id)

**posts_cache** (lazy)
- `uri` (PK)
- `cid`
- `author_actor_id`
- `created_at`
- `text`
- `raw_json` (optional)

### Recherche FTS5
Option A (simple) : une FTS unique
- `content_fts(source, actor_id, uri, created_at, content)`

Option B (plus clean) : 2 FTS
- `dm_fts(convo_id, actor_id, sent_at, content)`
- `post_fts(actor_id, root_uri, uri, created_at, content)`

> Reco v1 : Option A (moins de plomberie), avec `source in ('dm','post','interaction')`.

---

## 6) Commandes CLI (spéc)

### `bsky context <handle>`
**But** : produire un pack contextuel standard.

**Sortie (format llm par défaut)**
- `HOT CONTEXT`:
  - DM last N (default 10)
  - si on répond à un post : extrait(s) du thread cible
- `COLD CONTEXT`:
  - profil interlocuteur (first_seen, tags, notes, relation)
  - last 10 shared threads (index) + pour chacun 3 extraits

**Options**
- `--account <handle>`
- `--threads 10` / `--dm 10`
- `--threads-depth <n>` (combien d’extraits)
- `--format llm|json|md`

### `bsky search-history <query>`
- `--handle <h>` (repeatable)
- `--since 30d` / `--until …`
- `--source dm|post|interaction|all`
- output : résultats triés (score FTS) + liens.

### `bsky people <handle>` (évolution)
- afficher la fiche (DB)
- `bsky people note <handle> "..."`
- `bsky people tag add/remove <handle> <tag>`

### `bsky people enrich …` (opt-in)
- `--regulars` / `--handles …`
- `--since 90d`
- produit `notes_auto/interests_auto/relationship_tone`

### `bsky migrate sqlite` (one-shot)
- import depuis `interlocutors.json`
- import depuis `bsky-threads-state.json`

---

## 7) Génération des “3 extraits” par thread
Par thread (`root_uri`) :
1. **Root snippet** : texte du root (ou parent direct si on répond à un sous-post) — 200–400 chars.
2. **Last us** : dernier post/DM “out” dans ce thread (cache via interactions + posts_cache).
3. **Last them** : dernier post/DM “in” dans ce thread.

**Note** : l’index (liste des 10 threads) peut afficher une ligne courte, mais `bsky context` inclut déjà les 3 extraits.

---

## 8) Intégration LLM : HOT vs COLD
Norme d’injection dans les prompts (tous les workflows LLM) :

```
[HOT CONTEXT — current conversation]
- …

[COLD CONTEXT — past interactions / memory]
- …
```

Règle : HOT = ce qui est nécessaire pour répondre maintenant; COLD = historique utile, mais non bloquant.

---

## 9) Migration / Anti-régression

### Stratégie
1. Introduire SQLite + migration import (sans changer le comportement).
2. Mettre `bsky context` en lecture DB.
3. Basculer progressivement les commandes existantes (`people`, `notify_scored` context) vers DB.
4. Optionnel : dual-write temporaire (DB + JSON) puis suppression du JSON.

### Tests
- Fixtures JSON -> import -> assertions sur counts (actors/interactions/dms).
- Golden tests sur `bsky people` / `bsky context` (format stable).
- Tests de requêtes FTS : recherche globale + filtrée.

---

## 10) Roadmap (proposée)

### Phase A — Foundations (pas de régression)
A1. Ajouter le module storage + migrations + WAL/busy_timeout.
A2. Import `interlocutors.json` → SQLite.
A3. Implémenter `bsky context` (DB read-only, 10 threads + 3 extraits).

### Phase B — DMs & interactions ingestion
B1. Ingestion DM (depuis `bsky notify --json`) → `dm_messages`.
B2. Ingestion interactions (reply/dm_sent/like/follow) → `interactions`.
B3. Adapter le poll DM : il lit/écrit DB + affiche “nouveaux DMs”.

### Phase C — Search
C1. Ajouter FTS5 + `bsky search-history` (handles filter).
C2. Ajout des index + optimisation (EXPLAIN, perf).

### Phase D — Enrichment
D1. Enrichissement déterministe : tags auto + stats.
D2. `bsky people enrich` (LLM lazy, opt-in) + persist dans DB.

### Phase E — Unification threads monitoring
E1. Migrer `bsky threads` state JSON → tables threads/backoff.
E2. Fix/align `bsky threads tree` (actuellement fragile) dans le nouveau stockage.

---

## 11) Questions ouvertes
- Rétention : conserver les DMs complets combien de temps ?
- Privacy : besoin de chiffrement au repos ? (SQLCipher) ou OK local + permissions ?
- Format exact de `bsky context` : JSON vs Markdown vs plain-text (on supporte les 3, mais on fixe une “golden” stable).
- Multi-langue : on garde `langs: ["en"]` dans les posts/replies; pour le contexte on conserve texte brut.
