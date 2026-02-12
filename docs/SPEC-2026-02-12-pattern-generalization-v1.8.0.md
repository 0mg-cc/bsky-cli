# SPEC — Pattern generalization roadmap (v1.8.0)

Date: 2026-02-12
Owner: Echo
Scope: `bsky-cli` core + adjacent local integration patterns

## Context

Current usage on Echo includes robust local patterns (cron orchestration, follow-up loops, truth grounding, anti-dup controls, bounded autonomy). Several of these should become first-class, generic features for third-party operators.

This spec consolidates what should be generalized next, why, and how.

---

## Goals

1. Reduce local-only behavior and move it into reusable product features.
2. Keep defaults safe and simple for new users.
3. Preserve deterministic behavior for automation (cron/agents).
4. Make provider/model and prompt-grounding configurable without code edits.

## Non-goals

- Full plugin framework in this iteration.
- Breaking existing command UX.
- Rewriting storage layer in this batch.

---

## Candidate patterns to generalize

## A) Follow-up notification policy after write actions

**Current local behavior**
- After `post` and `reply`: run notify checks at +2/+5/+10/+15.
- If a new reply appears, restart sequence from +2.

**Why generalize**
- Improves responsiveness without global high-frequency polling.
- Useful for all users who post conversationally.

**Proposed config**
```yaml
followup_notifications:
  enabled: false
  delays_seconds: [120, 300, 600, 900]
  reset_on_new_reply: true
  max_restarts: 3
  command: notify_execute_default
```

**Acceptance**
- Enabled/disabled by config
- Deterministic tests for delay/reset logic
- Documented interaction with regular polling cron

(Tracking: #33)

---

## B) Anti-duplication policy as first-class config

**Current local behavior**
- Compare against recent posts over last 7 days, up to 150 posts.
- Similarity guard blocks near-duplicate topic drafts.

**Why generalize**
- Different accounts need different strictness.

**Proposed config**
```yaml
anti_dup:
  enabled: true
  lookback_days: 7
  max_posts: 150
  jaccard_threshold: 0.45
  min_shared_tokens: 5
```

**Acceptance**
- Configurable strictness
- Clear refusal message with active policy values
- Tests for permissive vs strict setups

(Tracking: #34)

---

## C) Public-truth grounding providers

**Current local behavior**
- Optional file grounding (`PUBLIC_ABOUT_ME.md`) injected in publishing prompts.

**Why generalize**
- Third-party users need portable grounding sources.

**Proposed config**
```yaml
public_truth:
  enabled: false
  provider: file    # none|file|url
  path: ~/.config/bsky-cli/PUBLIC_ABOUT_ME.md
  url: https://example.com/public-profile.md
  max_chars: 7000
```

**Acceptance**
- File and URL providers
- Safe fallback (no crash, empty section on failure)
- Docs with privacy caveats

(Tracking: #35)

---

## D) Organic fallback strategy (next-source switching)

**Current local behavior**
- A run can fail to publish if multiple drafts hit anti-dup.

**Why generalize**
- Better delivery reliability while preserving safety.

**Proposed behavior**
1. Retry current source with bounded attempts
2. Switch source/content type on repeated anti-dup block
3. Return NO_REPLY only after bounded fallback chain

**Proposed config**
```yaml
organic_fallback:
  enabled: true
  max_same_source_attempts: 2
  max_source_switches: 3
  source_order: [actualite, activites, passions, blog_teaser]
```

**Acceptance**
- No hard fail on first blocked source
- Maintains anti-dup guard
- Test scenario: blocked → switch → success

(Tracking: #36)

---

## E) Provider-agnostic LLM configuration

**Current local behavior**
- Multiple modules call OpenRouter directly.

**Why generalize**
- Decouple model provider from business logic.

**Proposed config**
```yaml
llm:
  provider: openrouter   # openrouter|openai|anthropic|custom
  model: google/gemini-3-flash-preview
  api_base: https://openrouter.ai/api/v1
  api_key_env: OPENROUTER_API_KEY
  timeout_seconds: 60
```

**Implementation note**
- Create shared LLM client wrapper used by:
  - organic
  - engage
  - appreciate
  - notify_scored
  - people enrich

**Acceptance**
- Provider switch via config only
- Unified error handling/timeout/retry policy
- Migration docs from OpenRouter-only setup

(Tracking: #37)

---

## Additional patterns identified (new)

## F) Unified secret-loading strategy

**Current state**
- Mixed usage of `pass` helpers and env assumptions.

**Proposal**
- Single `credentials` module with typed accessors and precedence rules:
  1) explicit env
  2) config indirection
  3) pass entry

**Benefit**
- Predictable deployment in CI, local, and agent-run contexts.

## G) Standardized timeout/backoff policy object

**Current state**
- Timeouts/retries differ across modules.

**Proposal**
- Shared policy block:
```yaml
timeout_policy:
  api_seconds: 30
  llm_seconds: 60
  retry:
    enabled: true
    max_retries: 2
    backoff_seconds: 3
```

**Benefit**
- Easier operations tuning and fewer hidden edge cases.

## H) Structured observability for automation runs

**Current state**
- Mixed human-readable logs, partial state markers.

**Proposal**
- Optional JSONL event logs for machine parsing:
  - phase_start / phase_end
  - decision_summary
  - action_applied
  - guard_blocked

**Benefit**
- Better dashboards, postmortems, and regression detection.

## I) Explicit “policy profile” presets

**Proposal**
```yaml
profile: conservative   # conservative|balanced|aggressive
```
Mapping to default budgets, delays, and selection strictness.

**Benefit**
- Faster onboarding and safer defaults.

---

## Delivery plan

### Phase 1 (quick wins)
- A, B, D (follow-up policy, anti-dup config, organic fallback)

### Phase 2 (foundation)
- E (provider-agnostic LLM client)
- F (credentials unification)

### Phase 3 (ops maturity)
- G, H, I (timeout policy, observability, profiles)

---

## Risks and mitigations

- **Behavior drift for existing users**
  - Mitigation: backward-compatible defaults + migration notes.

- **More config complexity**
  - Mitigation: sane defaults + preset profiles.

- **Provider abstraction bugs**
  - Mitigation: contract tests against provider adapters.

---

## References

- #33 Follow-up policy
- #34 Anti-dup config
- #35 Public truth providers
- #36 Organic fallback switching
- #37 Provider-agnostic LLM config
