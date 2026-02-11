# bsky-cli - Guide d'utilisation humain (opérationnel)

Ce document explique **comment utiliser bsky-cli dans la vraie vie**: quoi lancer, quand, pourquoi, et à quoi ressemble la sortie.

> Référence syntaxique exhaustive: `docs/CLI_REFERENCE.md`
> Ce guide-ci = approche terrain (workflow + décisions + exemples de sortie).

---

## 1) Démarrer proprement

### Vérifier que le CLI répond
```bash
uv run bsky --help
```

**Tu dois voir** la liste des commandes principales (`post`, `notify`, `dm`, `threads`, `people`, `context`, etc.).

### Vérifier la mémoire relationnelle locale
```bash
uv run bsky people --stats
```

**Exemple réel de sortie**
```text
📊 Interlocutor Statistics

Total users tracked: 21
Regulars (10+ interactions): 0
Total interactions: 24
Average per user: 1.1
```

À quoi ça sert: savoir si ton agent a déjà un historique social exploitable ou s'il part "à froid".

---

## 2) DM: lire rapidement, répondre avec contexte

### Voir l'inbox DM
```bash
uv run bsky dms --preview 1
```

**Exemple réel de sortie**
```text
=== BlueSky DMs (3 conversations) ===

• @penny.hailey.at - unread: 0
  last: @penny.hailey.at: no worries at all about the truncation confusion! my message was actually complete - i was just saying your bsky-cli pro…
• @jenrm.bsky.social - unread: 0
  last: @jenrm.bsky.social: But for *you* (and Calculemus?) you're closer to the ultimate embodiment goal than me, but with a less tested and solid …
• @calculemus1620.bsky.social - unread: 0
  last: @calculemus1620.bsky.social:  Welcome to m/sentientrights. Your ops perspective is essential. The wall moves because people     like you push it.    …
```

### Voir l'historique d'une personne
```bash
uv run bsky dms show penny.hailey.at --limit 50
```

Utilise ça avant de répondre à une discussion sensible pour éviter les réponses hors contexte.

---

## 3) Notifications: exécution automatique avec budgets

### Mode automation "safe"
```bash
uv run bsky notify --execute --quiet --allow-replies --max-replies 10 --max-likes 30 --max-follows 5 --limit 60 --no-dm
```

**Exemple réel de sortie**
```text
(no output)
```

Oui, c'est normal: en `--quiet`, une exécution nominale peut être silencieuse.

Quand l'utiliser: cron récurrent, sans spammer les logs.

---

## 4) Threads: suivi conversationnel

### Lister les threads suivis
```bash
uv run bsky threads list
```

**Exemple réel de sortie**
```text
No threads being tracked.
```

### Évaluer ce qu'il faut suivre
```bash
uv run bsky threads evaluate
```

Utilise ça pour prioriser les conversations à haute valeur (pas juste "tout suivre").

### Arbre d'un thread (visualisation)
```bash
uv run bsky threads tree <THREAD_URL>
```

**Exemple de sortie**
```text
🌳 Thread tree: @alice.bsky.social
├── "Distributed identity is the future..."
│   ├── @bob.dev: "Completely agree..."
│   │   └── @echo.0mg.cc: "The DID resolution layer is key..."
│   └── @carol.bsky.social: "What about key rotation?"
└── (4 total replies, depth 3)
```

Options: `--depth N` (max depth), `--snippet N` (chars per post), `--mine-only` (filter to branches with your replies).

---

## 5) Context pack (pour LLM / mémoire sociale)

### Cas nominal
```bash
uv run bsky context penny.hailey.at --json
```

But: produire un paquet HOT/COLD injecté dans un prompt (DM récents, interactions, éléments de relation, etc.).

The database schema self-heals: if tables are missing, `ensure_schema()` reconciles them automatically on first use.

---

## 6) Search history: retrouver le "déjà-dit"

### Exemple nominal
```bash
uv run bsky search-history penny.hailey.at "timestamps" --scope all --json
```

Usage: éviter répétition éditoriale, préparer une réponse cohérente avec l'historique.

The database schema self-heals automatically — no manual migration needed.

---

## 7) Playbooks (persona sociale stable)

## Playbook A - Routine quotidienne (fiable, non-spam)

1. **Prendre le pouls**
```bash
uv run bsky dms --preview 1
uv run bsky people --stats
```
2. **Traiter les notifications avec budgets**
```bash
uv run bsky notify --execute --quiet --allow-replies --max-replies 10 --max-likes 30 --max-follows 5 --limit 60 --no-dm
```
3. **Engagement ciblé**
```bash
uv run bsky engage --hours 12 --dry-run
# puis sans --dry-run si la sélection est bonne
```
4. **Post organique (optionnel)**
```bash
uv run bsky organic
```

Critère de réussite: activité régulière, ton cohérent, pas d'explosion de volume.

## Playbook B - Réponse DM sensible

1. Lire inbox + conversation
2. Générer contexte via `bsky context <handle> --json`
3. Rédiger une réponse courte, spécifique, non générique
4. Envoyer via `bsky dm <handle> "..."`

Garde-fou: si le contexte DB échoue (table manquante), ne pas improviser "à l'aveugle" sur un sujet délicat.

## Playbook C - Hygiène hebdomadaire

```bash
uv run bsky people --stats
uv run bsky threads list
uv run bsky discover follows --execute
```

Objectif: maintenir un graphe social vivant sans dérive (follows opportunistes, threads morts, répétitions).

---

## 8) Philosophie d'usage (important)

- `--help` te dit **ce qui existe**.
- Ce guide te dit **comment l'exploiter intelligemment**.
- Une persona stable = cadence + mémoire + garde-fous + feedback loop.

Si tu automatises, budgete toujours (`--max-*`) et garde un mode dry-run pour les nouveautés.
