# Research: Project Guardrails Category Configuration

## R1 — Naming: category, not topic or instruction

**Decision**: Domain term **guardrail category**. Settings: `GUARDRAIL_CATEGORY_CATALOG`. Persistence: `category_states`. API: `categories`.

**Rationale**:

- **Topic** is taken: `Topics` model + `lambda_conversation_topics` classify *conversation content*, user-defined per project.
- **Instruction** is taken: content-base instructions, agent instructions, formatter instructions.
- **Category** matches FDD intent (fixed sensitive *subject categories*) without overloading existing nouns.

**Rejected**: `guardrails_instructions` — reads as prompt text, not a taxonomy of blocked subjects.

---

## R2 — i18n (backend scope)

**Decision**: **No i18n layer in Nexus for this feature.**

- Catalog `name`/`description`: English strings may remain in settings for Bedrock sync/docs; **API does not return them** — frontend i18n keys by `slug`.
- Default blocking message: `settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` (single string).
- Custom blocking message: stored as submitted.
- Remove `Accept-Language` from admin API contract.

**Rationale**: Label localization is a presentation concern owned by the frontend.

**Rejected**: locale module task — frontend/i18n pipeline pattern, not Nexus backend responsibility.

---

## R3 — Admin writes, lazy init, unblock

**Decision**: Moderator/org-admin PATCH only; `GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT` + lazy init on first GET; unblock persists immediately (confirmation UX is frontend-only); cache invalidation on PATCH.

Unchanged from 2026-07-06 product/API clarifications.

---

## R4 — Runtime: ApplyGuardrail in Nexus, not Lambda

**Decision**: Evaluate every user input with Bedrock Runtime **`ApplyGuardrail`** (`source=INPUT`) in the existing preprocess/`invoke` path. Do **not** use `GUARDRAILS_LAYER_LAMBDA` / conversation lambda for this feature.

**Rationale**: Guardrails run on every message; an extra Lambda hop adds latency (cold start + network). Decision from Roger Alexandre / John: implement Bedrock Guardrails SDK directly in Nexus.

**Rejected**: Re-enabling `guardrails_complexity_layer` Lambda invoke; injecting a `categories` map for Models team to enforce refusal.

---

## R5 — Hybrid Bedrock Guardrail pool (supersedes 1:1 per project)

**Decision (2026-07-22)**: Maintain a **pool registry** keyed by the combination of `blocked=true` catalog slugs (no language). On category PATCH, resolve the pool: **reuse** if the combination exists; otherwise **lazy `CreateGuardrail`** with Denied Topics for that subset (+ platform baseline content filters/PII when Models defines them). Persist assigned `identifier`/`version` on the project. Projects with the same subset share one AWS Guardrail.

**Rationale**: Operators cannot create custom topics (FDD) — combination space is finite. Models guidance: 1:1 per project does not scale operationally; temporary per-request Guardrails are impossible; custom messaging must stay outside Bedrock so pools can be shared (Option A).

**When all unblocked**: skip `ApplyGuardrail` at preprocess (no-op).

**Rejected**: One Bedrock Guardrail resource owned exclusively per project with UpdateGuardrail on every toggle (previous R5, 2026-07-16).

**Deferred**: Soft layer — inject denied topics into manager system prompt; OUTPUT `ApplyGuardrail`.

---

## R6 — Blocking message Option A

**Decision**: On `GUARDRAIL_INTERVENED`, Nexus ignores Bedrock canned output and returns the project effective message (custom or `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE`). Message-only PATCH does not Create/Update Guardrail or change pool assignment.

**Rationale**: Message changes are more frequent than topic toggles; pooling requires message outside the shared Guardrail. Customer-facing copy stays owned by Nexus/project config.

**Rejected**: Option B — store project message in `blockedInputMessaging` and return Bedrock text as-is (blocks pool sharing).

---

## R7 — Fail behavior on Bedrock errors (open)

**Decision pending implementation**: Document and test whether preprocess **fail-open** (allow message) or **fail-closed** (block/safe reply) when `ApplyGuardrail` or pool create/resolve APIs error. Prefer explicit choice in plan/tasks before release.
