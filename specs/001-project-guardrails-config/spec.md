# Feature Specification: Project Guardrails Category Configuration

**Feature Branch**: `001-project-guardrails-config`

**Created**: 2026-07-06

**Status**: Draft

**Input**: FDD V2 — Configuração de tópicos de guardrails por projeto (Jade Castro, 2026-06-23)

**Scope**: Nexus backend only — persistence, API, validation, Bedrock Guardrail **pool** (lazy create by category combination), `ApplyGuardrail` on user input preprocess, cache. No frontend or UI work in this feature.

**Terminology**: Use **guardrail category** (not *topic*) to avoid collision with conversation `Topics` (`nexus.intelligences.models.Topics`, lambda classifier). Use **category** (not *instruction*) to avoid collision with agent/content-base instructions.

## Clarifications

### Session 2026-07-06

- Q: Who may write guardrails configuration via API? → A: Project **moderator** or **organization admin** only.
- Q: New vs existing project defaults? → A: `GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT` + lazy init on first GET.
- Q: Default blocking message? → A: `settings.GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` until custom message is saved; custom stored verbatim, no auto-translation.
- Q: PATCH confirmation? → A: **Frontend-only** (FDD modal). Backend persists unblock immediately; no `confirm_disable` / `409` handshake.
- Q: New catalog entries? → A: Merge on GET; missing slugs inherit project-type default.

### Session 2026-07-06

- Q: Rename away from *topic*? → A: **guardrail category** / `category_states` / `GUARDRAIL_CATEGORY_CATALOG`. Rejects *instruction* (conflicts with existing Instructions domain) and *topic* (conflicts with conversation Topics).
- Q: Backend i18n for catalog labels? → A: **Out of scope.** API returns only `slug` + `blocked`; frontend owns `name`/`description` via translation files keyed by slug. No `Accept-Language`, no locale module. Default blocking message is a single settings string.

### Session 2026-07-16

- Q: Where does the refusal check run? → A: **`ApplyGuardrail` in Nexus preprocess**, before each user input. Not via conversation/guardrails Lambda.
- Q: Blocking message source? → A: **Option A** — on `GUARDRAIL_INTERVENED`, Nexus **ignores** Bedrock canned text and returns the project custom message or `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE`. Message-only PATCH does **not** require Bedrock Create/Update.
- Q: INPUT and/or OUTPUT? → A: **INPUT only** (`source=INPUT`).
- Q: OpenAI vs Bedrock backends? → A: Reuse the existing preprocess/`invoke` path for both; do not invent a parallel pipeline.

### Session 2026-07-22

- Q: One Bedrock Guardrail per project? → A: **Superseded.** Use **hybrid pool** (Models guidance): one Bedrock Guardrail per **combination** of `blocked=true` catalog categories; projects with the same subset **share** that Guardrail. Nexus creates pools **lazily** via API (not pre-created in AWS console).
- Q: Pool key includes project language? → A: **No.** Key = subset of blocked category slugs only. Custom message is always applied outside Bedrock (Option A).
- Q: Can operators create new Guardrails/topics? → A: **No** (FDD). Operators only toggle the fixed catalog + blocking message.
- Q: System prompt injection of denied topics / OUTPUT ApplyGuardrail? → A: **Out of scope** for this release (phase 2 if needed after hard path is stable).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read and update category blocked states (Priority: P1)

As an authenticated admin API consumer, I need to read and update per-category blocked states for a project so guardrail behavior can be controlled without engineering intervention.

**Independent Test**: `GET` config, `PATCH` one category from blocked to unblocked, verify the project is reassigned to the pool for the new combination and the next input no longer blocks that category.

**Acceptance Scenarios**:

1. **Given** valid project UUID and auth, **When** `GET /guardrails-config/`, **Then** response lists all fixed catalog categories with `slug` and `blocked` (no `name`/`description`).
2. **Given** category blocked, **When** PATCH unblocks it, **Then** persists immediately, resolves/assigns the Bedrock pool for the new combination (lazy create if missing), and runtime no longer blocks that category.
3. **Given** category unblocked, **When** PATCH blocks it, **Then** persists immediately and assigns the pool that includes that category.
4. **Given** PATCH unblocks all categories, **Then** all categories unblocked and runtime skips `ApplyGuardrail` (or never intervenes).
5. **Given** operator wants UX confirmation before unblocking, **When** Agent Builder shows a modal, **Then** FE calls PATCH once after confirm (backend does not enforce a two-step handshake).
6. **Given** two projects with the same `blocked=true` subset, **Then** both persist the same Bedrock `identifier`/`version` (shared pool).

---

### User Story 2 - Configure blocking message (Priority: P2)

As an authenticated admin API consumer, I need to persist a project blocking message for customer-facing refusals.

**Independent Test**: PATCH message ≤240 chars; on `ApplyGuardrail` intervene, response uses project message (not Bedrock canned text).

**Acceptance Scenarios**:

1. **Given** no custom message, **When** GET, **Then** `blocking_message` is platform default from settings and `blocking_message_is_custom: false`.
2. **Given** category blocked, **When** customer message triggers `ApplyGuardrail` at preprocess, **Then** Nexus returns project blocking message (Option A).
3. **Given** PATCH message ≤240 chars, **When** saved, **Then** GET reflects custom message; next intervene uses it **without** Bedrock Create/Update (shared pool unchanged).
4. **Given** PATCH message >240 chars, **When** validated, **Then** `400`.

---

### User Story 3 - Uniform runtime application (Priority: P1)

As the platform, guardrails config MUST apply uniformly to all agents in the project via a single pre-input check.

**Independent Test**: Project’s assigned pool id/version + project message used in preprocess for every agent/backend path that shares `invoke` preprocess; updates after category PATCH + pool resolve + cache invalidation.

**Acceptance Scenarios**:

1. **Given** new project, **When** first GET lazy init, **Then** all categories blocked + platform default message; Bedrock pool for the full blocked set is created/assigned on first category sync need (lazy).
2. **Given** existing project, **When** first GET lazy init, **Then** all categories unblocked + platform default message (no ApplyGuardrail until something is blocked).
3. **Given** category PATCH applied and pool resolved, **When** next user input is processed, **Then** `ApplyGuardrail` uses the assigned pool identifier/version; prior responses unchanged.

---

### Edge Cases

- Multiple blocked categories match one message → single project blocking message (not per-category).
- Empty/whitespace `blocking_message` while any category blocked → `400`.
- Config changed mid-conversation → applies after successful PATCH (+ pool resolve when categories change) only.
- New catalog slug in deploy → merged on GET with project-type default; pool keys that include the new slug are new combinations (lazy create when first needed).
- Non-admin PATCH → `403`; GET returns `writable: false`.
- Concurrent PATCH → last write wins.
- Bedrock pool create/resolve failure on category PATCH → PATCH MUST NOT leave local config and Bedrock assignment permanently inconsistent without a defined error path (fail the request; do not silently succeed).
- All categories unblocked → do not call `ApplyGuardrail` (clear or ignore pool pointer as implemented).
- Same category subset across projects → **must** reuse one Bedrock Guardrail pool (no 1:1 create).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: API MUST expose GET/PATCH with full fixed **guardrail category** catalog (`slug`, `blocked`). Display labels are frontend-owned.
- **FR-002**: `blocked: true` = category refused; `blocked: false` = allowed.
- **FR-003**: PATCH persists `category_states` at project level for admin only.
- **FR-004**: PATCH returns `403` for non-admin.
- **FR-005**: One blocking message per project for all blocked categories and agents.
- **FR-006**: Reject blocking messages >240 characters.
- **FR-007**: Reject empty/whitespace blocking message when any category blocked.
- **FR-008**: Lazy init defaults all categories blocked (new) or unblocked (existing).
- **FR-009**: PATCH unblocking categories persists immediately (confirmation UX is frontend-only).
- **FR-010**: PATCH may unblock all categories in one request.
- **FR-011**: PATCH blocking and unblocking categories use the same request shape (`category_states`).
- **FR-012**: Runtime MUST evaluate each user input with Bedrock `ApplyGuardrail` (`source=INPUT`) using the project's assigned pool identifier/version **before** agent processing, reusing the existing preprocess/`invoke` path (no dedicated OpenAI-only pipeline; no `GUARDRAILS_LAYER_LAMBDA` for this flow).
- **FR-013**: Changes apply only to messages after successful PATCH (and successful pool resolve when categories change).
- **FR-014**: GET merges new catalog slugs with project-type defaults.
- **FR-015**: GET returns platform default blocking message from settings when no custom message stored.
- **FR-016**: Custom blocking messages stored without auto-translation.
- **FR-017**: No operator CRUD on catalog category definitions.
- **FR-018**: No per-agent guardrails config in this release.
- **FR-019**: No per-category blocking messages in this release.
- **FR-020**: Nexus MUST maintain a **registry of Bedrock Guardrail pools** keyed by the combination of `blocked=true` catalog slugs (no language in the key). Each project MUST persist the assigned pool `identifier`/`version`. Projects with the same combination MUST share the same pool.
- **FR-021**: On category-state PATCH, Nexus MUST resolve the pool for the new combination: reuse registry entry if present; otherwise **lazy** `CreateGuardrail` with Denied Topics = only `blocked=true` categories (plus platform baseline filters/PII when defined), then persist id/version on the project.
- **FR-022**: On `GUARDRAIL_INTERVENED`, Nexus MUST return the project effective blocking message and MUST NOT use Bedrock canned output text as the customer-facing reply (Option A).
- **FR-023**: Message-only PATCH MUST persist locally and MUST NOT Create/Update Bedrock Guardrail or change the project's pool assignment.
- **FR-024**: Guardrail evaluation is INPUT-only; OUTPUT evaluation is out of scope.
- **FR-025**: When no categories are blocked, runtime MUST skip `ApplyGuardrail` (or equivalent no intervention).

### Key Entities

- **Guardrail category (catalog entry)**: Platform slug (+ Bedrock denied-topic definition/examples as needed); display name/description are frontend i18n; not mutable via API.
- **Bedrock Guardrail pool**: One AWS Guardrail resource per unique blocked-category combination; owned by Nexus registry; created lazily.
- **Project guardrails configuration**: One-to-one with project; `category_states` + optional custom blocking message + assigned pool identifier/version.

## Success Criteria *(mandatory)*

- **SC-001**: Admin can GET/PATCH all 11 categories + message in one API session.
- **SC-002**: 100% of over-limit message PATCH attempts return `400`.
- **SC-003**: After category PATCH + pool resolve, the next user input is evaluated with the assigned pool; on intervene, customer receives the project effective message (Option A).
- **SC-004**: 100% of non-admin PATCH return `403`.
- **SC-005**: First GET: new projects all blocked; existing all unblocked.
- **SC-006**: Unblock PATCH persists immediately without a backend confirmation handshake.
- **SC-007**: Preprocess guardrail path does not invoke `GUARDRAILS_LAYER_LAMBDA` for this feature.
- **SC-008**: Two projects with identical blocked subsets share one Bedrock Guardrail identifier.

## Assumptions

- Conversation **Topics** (`Topics` model, lambda classifier) are a separate domain — no shared tables or APIs.
- Catalog display labels are frontend-owned (i18n by `slug`); API returns only `slug` + `blocked`.
- Bedrock Denied Topics (+ optional baseline content filters/PII) are the hard enforcement mechanism; Nexus owns pool registry, lazy create, `ApplyGuardrail`, and customer-facing message resolution.
- Fail-open vs fail-closed on Bedrock API errors during preprocess is an implementation decision to document in research/plan and cover with tests.
- IAM/quota for Bedrock Guardrails is provided by Platform/Cloud; pools are **not** pre-created in the AWS console.

## Out of Scope

- Conversation topic classification
- Per-agent guardrails, custom categories, per-category messages, auto-translation
- Frontend/UI, API `Accept-Language`, backend locale modules
- OUTPUT guardrail evaluation
- Injecting project denied topics into the manager system prompt (soft layer)
- Reintroducing Lambda-based guardrails complexity layer for this flow
- Pre-provisioning all pool combinations in AWS by hand

## API References

| Method | Route |
|--------|-------|
| GET | `/api/v1/projects/{project_uuid}/guardrails-config/` |
| PATCH | `/api/v1/projects/{project_uuid}/guardrails-config/` |

## Dependencies

| Dependency | Owner |
|------------|-------|
| Bedrock Guardrails lazy create + `ApplyGuardrail` | Nexus backend |
| Persistence, admin API, preprocess gate, cache, pool registry | Nexus backend |
| IAM / AWS account access + quota for Bedrock Guardrails | Platform / DevOps (Cloud) |
| Denied topic definition/examples + baseline filter policy content | AI Models (as needed) |
