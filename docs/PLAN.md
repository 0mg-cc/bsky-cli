# PLAN.md — Stabilisation bugs + validation réelle (bsky-cli)

Objectif: corriger les bugs bloquants observés en conditions réelles et valider le CLI de façon exhaustive, avec sorties réelles.

## Portée

Ce plan couvre **uniquement**:

1) correction des bugs identifiés,
2) tests exhaustifs commande par commande,
3) validation en conditions réelles (pas seulement tests internes).

---

## Priorités bugs

## P0 — `threads tree` cassé

- Symptôme: `Unknown threads command`
- Cause probable: dispatch manquant dans `threads_mod/commands.py::run()`.
- Action:
  - ajouter route `tree -> cmd_tree(args)`
  - test de régression CLI
  - test réel sur URL de thread BlueSky
- DoD:
  - la commande retourne un arbre (ou une erreur métier explicite), jamais `Unknown threads command`.

## P0 — `context` crash DB (`dm_convo_members`)

- Symptôme: `sqlite3.OperationalError: no such table: dm_convo_members`
- Cause probable: schéma account DB partiellement migré.
- Action:
  - centraliser `ensure_schema` / migration idempotente au point d’ouverture DB
  - fallback contrôlé sans traceback brut
  - test intégration sur DB legacy partielle
  - test réel `bsky context <handle> --json`
- DoD:
  - pas de crash SQL; sortie valide (données ou résultat vide cohérent).

## P0 — `search-history` crash DB (même root cause)

- Symptôme: même erreur SQL que `context`.
- Action:
  - réutiliser la même routine de migration/ensure-schema
  - test intégration DB partielle
  - test réel `bsky search-history <handle> <query> --json`
- DoD:
  - pas de crash SQL; sortie valide ou vide explicite.

## P1 — robustesse runtime (`engage` / `appreciate` / `discover`)

- Symptôme: exécutions longues/hang, SIGKILL/timeout dans orchestration.
- Action:
  - ajouter progression/logs par phase
  - ajouter bornes runtime (`--max-runtime-seconds` ou équivalent)
  - garder budgets bas pour smoke réel
- DoD:
  - commande bornée en durée en mode smoke, sans blocage silencieux.

---

## Stratégie de tests (obligatoire)

## 1) Tests internes (automatisés)

- unit + intégration ciblés par bug
- test de non-régression pour chaque fix
- CI verte avant merge

## 2) Tests exhaustifs CLI (commande par commande)

- couvrir toutes commandes + sous-commandes
- pour chaque commande:
  - cas nominal
  - cas limite
  - cas erreur
- consigner code retour + extrait sortie

## 3) Tests en conditions réelles (obligatoires)

Pour chaque commande réparée puis pour toutes les autres:

- exécution sur données/compte réels (BlueSky)
- sorties réelles collectées et archivées dans doc
- comparaison attendu vs observé

### Matrice minimale réelle (cron/skills + reste)

- notify (`--execute --quiet`, `--score --all`)
- dms / dm
- threads (`evaluate`, `list`, `tree`, `backoff-*`, `migrate-state`)
- context
- search-history
- discover (`follows`, `reposts`)
- engage
- appreciate
- organic
- people
- post/reply/like/repost/follow/bookmark(s)/lists/starterpack/config/announce/delete/profile/search

---

## Ordre d’exécution

1. Fix P0 `threads tree` + tests internes + test réel
2. Fix P0 `context` + `search-history` (schema/migration) + tests internes + tests réels
3. Implémentation P1 (bornes runtime + logs progression)
4. Sweep exhaustif toutes commandes (internes + réelles)
5. PRs/fixes complémentaires issus du sweep
6. Deuxième sweep complet de confirmation
7. Mise à jour doc utilisateur avec outputs réels validés

---

## Livrables

- `docs/PLAN.md` (ce fichier)
- PR(s) de fix avec tests associés
- journal des tests réels (commande, code retour, output)
- mise à jour `docs/USAGE_GUIDE.md` avec exemples réels vérifiés

## Avancement (2026-02-11)

- ✅ P0 `threads tree` corrigé
  - dispatch `tree` ajouté dans `threads_mod/commands.py::run()`
  - implémentation `cmd_tree` (rendu ASCII, `--depth`, `--snippet`, `--mine-only`)
  - tests: `tests/test_threads_tree_cmd.py`
  - test réel: `bsky threads tree at://did:plc:kcx54umwsf3fgjcz32acp4yw/app.bsky.feed.post/3mejeulsmsp22`

- ✅ P0 `context` / `search-history` crash DB partielle corrigé
  - root cause: DB pouvant annoncer une version de migration élevée tout en ayant des tables manquantes
  - fix: `ensure_schema()` ajoute une phase de réconciliation idempotente (`RECONCILE_SCHEMA_SQL`)
  - tests: `tests/test_storage_schema_self_heal.py`
  - tests réels: `bsky context echo.0mg.cc --json` et `bsky search-history echo.0mg.cc "memory" --json`

- 🔄 P1 robustesse runtime (`engage` / `appreciate` / `discover`) en cours
  - ✅ ajout flag `--max-runtime-seconds` sur `engage`, `appreciate`, `discover follows/reposts`
  - ✅ garde-fou wall-clock commun (`runtime_guard.py`) + code retour timeout non-zero (`124`)
  - ✅ logs de progression explicites par phase (`collect → score → decide → act`)
  - ✅ tests ciblés timeout/progression: `tests/test_runtime_bounds.py` (4 passed)
  - ✅ smoke réels (budget timeout minimal) archivés dans `docs/help-snapshots/`:
    - `p1-smoke-engage-timeout-2026-02-11.txt`
    - `p1-smoke-appreciate-timeout-2026-02-11.txt`
    - `p1-smoke-discover-timeout-2026-02-11.txt`
- ⏳ Sweep exhaustif commande par commande à faire

## Plan d’action immédiat (actionnable)

### A) P1 Runtime bounds + progression logs

- [x] Ajouter `--max-runtime-seconds` sur:
  - [x] `bsky engage`
  - [x] `bsky appreciate`
  - [x] `bsky discover follows`
  - [x] `bsky discover reposts`
- [x] Implémenter un garde-fou temps wall-clock commun (arrêt propre + code retour non-zero en timeout).
- [x] Ajouter logs de progression par phase (collect → score → decide → act) en mode non-quiet.
- [x] Ajouter tests unitaires/intégration ciblés:
  - [x] timeout respecté
  - [x] sortie explicite en timeout
  - [x] progression visible
- [x] Lancer smoke réels (budgets bas) et archiver sorties dans `docs/help-snapshots/`.

### B) Sweep exhaustif commande par commande

- [ ] Générer la liste complète des commandes via `bsky --help` + sous-commandes.
- [ ] Exécuter pour chaque commande:
  - [ ] cas nominal
  - [ ] cas limite
  - [ ] cas erreur
- [ ] Capturer pour chaque run: commande, code retour, extrait output.
- [ ] Produire un journal consolidé dans `docs/CLI_REFERENCE.md` (section validation réelle).

### C) PR/merge loop (jusqu’à completion)

- [ ] Ouvrir PR P1 runtime
- [ ] Review inline + corrections
- [ ] Re-run tests + smoke
- [ ] Merge
- [ ] Ouvrir PR sweep/doc sync
- [ ] Review inline + corrections
- [ ] Merge

### D) Finalisation plan

- [ ] Cocher tous items restants dans ce PLAN
- [ ] Mettre à jour `TODAY_TASKS.md` (fait/en cours/next)
- [ ] Vérifier DoD: plan entièrement accompli + docs synchronisées

## Critère de fin

Plan terminé quand:

- P0 corrigés,
- tests exhaustifs passés,
- tests réels exécutés sur toutes commandes,
- documentation synchronisée avec le comportement réel du CLI.
