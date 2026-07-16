# Feature Specification: Project Guardrails Category Configuration

**Feature Branch**: `001-project-guardrails-config`

**Created**: 2026-07-06

**Status**: Draft

**Input**: FDD V2 — Configuração de tópicos de guardrails por projeto (Jade Castro, 2026-06-23)

**Scope**: Nexus backend only — persistence, API, validation, Bedrock Guardrail sync (one per project), `ApplyGuardrail` on user input preprocess, cache. No frontend or UI work in this feature.

**Terminology**: Use **guardrail category** (not *topic*) to avoid collision with conversation `Topics` (`nexus.intelligences.models.Topics`, lambda classifier). Use **category** (not *instruction*) to avoid collision with agent/content-base instructions.

## Clarifications

### Session 2026-07-06

- Q: Who may write guardrails configuration via API? → A: Project **moderator** or **organization admin** only.
- Q: New vs existing project defaults? → A: `GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT` + lazy init on first GET.
- Q: Default blocking message? → A: `settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` until custom message is saved; custom stored verbatim, no auto-translation.
- Q: PATCH confirmation? → A: `confirm_disable: true` required when unblocking categories; `disable_all` when all unblocked.
- Q: New catalog entries? → A: Merge on GET; missing slugs inherit project-type default.

### Session 2026-07-06

- Q: Rename away from *topic*? → A: **guardrail category** / `category_states` / `GUARDRAIL_CATEGORY_CATALOG`. Rejects *instruction* (conflicts with existing Instructions domain) and *topic* (conflicts with conversation Topics).
- Q: Backend i18n for catalog labels? → A: **Out of scope.** API returns English `name`/`description` from code constant. No `Accept-Language`, no locale module. Default blocking message is a single settings string.

### Session 2026-07-16

- Q: Where does the refusal check run? → A: **`ApplyGuardrail` in Nexus preprocess**, before each user input. Not via conversation/guardrails Lambda.
- Q: One Bedrock guardrail per project? → A: **Yes.** Categories with `blocked=false` are **omitted** from the Bedrock Denied Topics policy (not passed as inactive entries).
- Q: Blocking message source? → A: **Option A** — on `GUARDRAIL_INTERVENED`, Nexus **ignores** Bedrock canned text and returns the project custom message or `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE`. Message-only PATCH does **not** require Bedrock UpdateGuardrail.
- Q: INPUT and/or OUTPUT? → A: **INPUT only** (`source=INPUT`).
- Q: OpenAI vs Bedrock backends? → A: Reuse the existing preprocess/`invoke` path for both; do not invent a parallel pipeline.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read and update category blocked states (Priority: P1)

As an authenticated admin API consumer, I need to read and update per-category blocked states for a project so guardrail behavior can be controlled without engineering intervention.

**Independent Test**: `GET` config, `PATCH` one category from blocked to unblocked with confirmation, verify Bedrock sync omits the unblocked category and the next input no longer blocks that category.

**Acceptance Scenarios**:

1. **Given** valid project UUID and auth, **When** `GET /guardrails-config/`, **Then** response lists all fixed catalog categories with `slug`, `name`, `description`, and `blocked`.
2. **Given** category blocked, **When** PATCH unblocks without `confirm_disable`, **Then** `409` with `confirmation_type: disable_category`.
3. **Given** PATCH unblock with `confirm_disable: true`, **Then** persists, syncs Bedrock guardrail without that category, and runtime no longer blocks it.
4. **Given** category unblocked, **When** PATCH blocks without confirmation, **Then** persists immediately and syncs Bedrock including that category.
5. **Given** PATCH unblocks all categories without `confirm_disable`, **Then** `409` with `confirmation_type: disable_all`.
6. **Given** PATCH unblocks all with `confirm_disable: true`, **Then** all categories unblocked and Bedrock sync reflects no denied categories (runtime skips `ApplyGuardrail` or never intervenes).

---

### User Story 2 - Configure blocking message (Priority: P2)

As an authenticated admin API consumer, I need to persist a project blocking message for customer-facing refusals.

**Independent Test**: PATCH message ≤240 chars; on `ApplyGuardrail` intervene, response uses project message (not Bedrock canned text).

**Acceptance Scenarios**:

1. **Given** no custom message, **When** GET, **Then** `blocking_message` is platform default from settings and `blocking_message_is_custom: false`.
2. **Given** category blocked, **When** customer message triggers `ApplyGuardrail` at preprocess, **Then** Nexus returns project blocking message (Option A).
3. **Given** PATCH message ≤240 chars, **When** saved, **Then** GET reflects custom message; next intervene uses it **without** Bedrock guardrail version bump for message-only change.
4. **Given** PATCH message >240 chars, **When** validated, **Then** `400`.

---

### User Story 3 - Uniform runtime application (Priority: P1)

As the platform, guardrails config MUST apply uniformly to all agents in the project via a single pre-input check.

**Independent Test**: Same project Bedrock guardrail + project message used in preprocess for every agent/backend path that shares `invoke` preprocess; updates after category PATCH + Bedrock sync + cache invalidation.

**Acceptance Scenarios**:

1. **Given** new project, **When** first GET lazy init, **Then** all categories blocked + platform default message + Bedrock guardrail created/synced with all catalog denied topics.
2. **Given** existing project, **When** first GET lazy init, **Then** all categories unblocked + platform default message (no denied topics on Bedrock / skip apply as defined).
3. **Given** category PATCH applied and synced, **When** next user input is processed, **Then** `ApplyGuardrail` uses the new guardrail version; prior responses unchanged.

---

### Edge Cases

- Multiple blocked categories match one message → single project blocking message (not per-category).
- Empty/whitespace `blocking_message` while any category blocked → `400`.
- Config changed mid-conversation → applies after successful PATCH (+ Bedrock sync when categories change) only.
- New catalog slug in deploy → merged on GET with project-type default; next category sync includes it when blocked.
- Non-admin PATCH → `403`; GET returns `writable: false`.
- Concurrent PATCH → last write wins.
- Bedrock sync failure on category PATCH → PATCH MUST NOT leave local config and Bedrock permanently inconsistent without a defined error path (fail the request or report sync error; do not silently succeed).
- All categories unblocked → do not call `ApplyGuardrail` (or equivalent no-op with empty denied topics).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: API MUST expose GET/PATCH with full fixed **guardrail category** catalog (`slug`, `name`, `description`, `blocked`).
- **FR-002**: `blocked: true` = category refused; `blocked: false` = allowed.
- **FR-003**: PATCH persists `category_states` at project level for admin only.
- **FR-004**: PATCH returns `403` for non-admin.
- **FR-005**: One blocking message per project for all blocked categories and agents.
- **FR-006**: Reject blocking messages >240 characters.
- **FR-007**: Reject empty/whitespace blocking message when any category blocked.
- **FR-008**: Lazy init defaults all categories blocked (new) or unblocked (existing).
- **FR-009**: PATCH unblocking categories requires `confirm_disable: true` or returns `409`.
- **FR-010**: PATCH unblocking all categories returns `409` with `disable_all` unless confirmed.
- **FR-011**: PATCH blocking categories does NOT require confirmation.
- **FR-012**: Runtime MUST evaluate each user input with Bedrock `ApplyGuardrail` (`source=INPUT`) using the project's guardrail identifier/version **before** agent processing, reusing the existing preprocess/`invoke` path (no dedicated OpenAI-only pipeline; no `GUARDRAILS_LAYER_LAMBDA` for this flow).
- **FR-013**: Changes apply only to messages after successful PATCH (and successful Bedrock sync when categories change).
- **FR-014**: GET merges new catalog slugs with project-type defaults.
- **FR-015**: GET returns platform default blocking message from settings when no custom message stored.
- **FR-016**: Custom blocking messages stored without auto-translation.
- **FR-017**: No operator CRUD on catalog category definitions.
- **FR-018**: No per-agent guardrails config in this release.
- **FR-019**: No per-category blocking messages in this release.
- **FR-020**: Each project MUST have at most one Bedrock Guardrail resource; identifier and version MUST be persisted with the project config.
- **FR-021**: On category-state PATCH, Nexus MUST sync Bedrock Denied Topics to include **only** categories with `blocked=true` (omit unblocked categories).
- **FR-022**: On `GUARDRAIL_INTERVENED`, Nexus MUST return the project effective blocking message and MUST NOT use Bedrock canned output text as the customer-facing reply (Option A).
- **FR-023**: Message-only PATCH MUST persist locally and MUST NOT require Bedrock UpdateGuardrail / version bump.
- **FR-024**: Guardrail evaluation is INPUT-only; OUTPUT evaluation is out of scope.
- **FR-025**: When no categories are blocked, runtime MUST skip `ApplyGuardrail` (or equivalent no intervention).

### Key Entities

- **Guardrail category (catalog entry)**: Platform slug + English label/description (+ Bedrock denied-topic definition/examples as needed); not mutable via API.
- **Project guardrails configuration**: One-to-one with project; `category_states` + optional custom blocking message + Bedrock guardrail identifier/version.

## Success Criteria *(mandatory)*

- **SC-001**: Admin can GET/PATCH all 11 categories + message in one API session.
- **SC-002**: 100% of over-limit message PATCH attempts return `400`.
- **SC-003**: After category PATCH + Bedrock sync, the next user input is evaluated with the updated denied-topic set; on intervene, customer receives the project effective message (Option A).
- **SC-004**: 100% of non-admin PATCH return `403`.
- **SC-005**: First GET: new projects all blocked; existing all unblocked.
- **SC-006**: 100% of unconfirmed disable PATCH return `409` with typed metadata.
- **SC-007**: Preprocess guardrail path does not invoke `GUARDRAILS_LAYER_LAMBDA` for this feature.

## Assumptions

- Conversation **Topics** (`Topics` model, lambda classifier) are a separate domain — no shared tables or APIs.
- Catalog labels in API are **English strings** from `GUARDRAIL_CATEGORY_CATALOG` (display localization is out of backend scope).
- Bedrock Denied Topics are the enforcement mechanism; Nexus owns sync + `ApplyGuardrail` + customer-facing message resolution.
- Fail-open vs fail-closed on Bedrock API errors during preprocess is an implementation decision to document in research/plan and cover with tests.

## Out of Scope

- Conversation topic classification
- Per-agent guardrails, custom categories, per-category messages, auto-translation
- Frontend/UI, API `Accept-Language`, backend locale modules
- OUTPUT guardrail evaluation
- Reintroducing Lambda-based guardrails complexity layer for this flow

## API References

| Method | Route |
|--------|-------|
| GET | `/api/v1/projects/{project_uuid}/guardrails-config/` |
| PATCH | `/api/v1/projects/{project_uuid}/guardrails-config/` |

## Dependencies

| Dependency | Owner |
|------------|-------|
| Bedrock Guardrails create/update/version + `ApplyGuardrail` | Nexus backend |
| Persistence, admin API, preprocess gate, cache | Nexus backend |
| IAM / AWS account access for Bedrock Guardrails | Platform / DevOps |
