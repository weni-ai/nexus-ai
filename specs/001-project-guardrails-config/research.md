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

- Catalog `name`/`description`: English strings in settings constant.
- Default blocking message: `settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` (single string).
- Custom blocking message: stored as submitted.
- Remove `Accept-Language` from admin API contract.

**Rationale**: Label localization is a presentation concern for API consumers outside this backend scope.

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

## R5 — One Bedrock Guardrail per project; omit unblocked categories

**Decision**: Each project owns one Bedrock Guardrail (`identifier` + `version` persisted). On category PATCH, sync Denied Topics to include **only** `blocked=true` catalog entries. Unblocked categories are omitted from the policy.

**Rationale**: Bedrock evaluates configured denied topics as a set; toggles are expressed by presence/absence in the guardrail definition, not by a separate runtime map.

**When all unblocked**: skip `ApplyGuardrail` at preprocess (no-op).

---

## R6 — Blocking message Option A

**Decision**: On `GUARDRAIL_INTERVENED`, Nexus ignores Bedrock canned output and returns the project effective message (custom or `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE`). Message-only PATCH does not UpdateGuardrail / bump version.

**Rationale**: Message changes are more frequent than topic toggles; avoids unnecessary Bedrock version churn. Customer-facing copy stays owned by Nexus/project config.

**Rejected**: Option B — store project message in `blockedInputMessaging` and return Bedrock text as-is.

---

## R7 — Fail behavior on Bedrock errors (open)

**Decision pending implementation**: Document and test whether preprocess **fail-open** (allow message) or **fail-closed** (block/safe reply) when `ApplyGuardrail` or sync APIs error. Prefer explicit choice in plan/tasks before release.
