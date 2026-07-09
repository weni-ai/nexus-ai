# Feature Specification: Project Guardrails Category Configuration

**Feature Branch**: `001-project-guardrails-config`

**Created**: 2026-07-06

**Status**: Draft

**Input**: FDD V2 — Configuração de tópicos de guardrails por projeto (Jade Castro, 2026-06-23)

**Scope**: Nexus backend only — persistence, API, validation, runtime injection, cache. No frontend or UI work in this feature.

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

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Read and update category blocked states (Priority: P1)

As an authenticated admin API consumer, I need to read and update per-category blocked states for a project so guardrail behavior can be controlled without engineering intervention.

**Independent Test**: `GET` config, `PATCH` one category from blocked to unblocked with confirmation, verify runtime payload reflects change.

**Acceptance Scenarios**:

1. **Given** valid project UUID and auth, **When** `GET /guardrails-config/`, **Then** response lists all fixed catalog categories with `slug`, `name`, `description`, and `blocked`.
2. **Given** category blocked, **When** PATCH unblocks without `confirm_disable`, **Then** `409` with `confirmation_type: disable_category`.
3. **Given** PATCH unblock with `confirm_disable: true`, **Then** persists and runtime reflects unblocked category.
4. **Given** category unblocked, **When** PATCH blocks without confirmation, **Then** persists immediately.
5. **Given** PATCH unblocks all categories without `confirm_disable`, **Then** `409` with `confirmation_type: disable_all`.
6. **Given** PATCH unblocks all with `confirm_disable: true`, **Then** all categories unblocked.

---

### User Story 2 - Configure blocking message (Priority: P2)

As an authenticated admin API consumer, I need to persist a project blocking message for customer-facing refusals.

**Independent Test**: PATCH message ≤240 chars; runtime uses exact message on block.

**Acceptance Scenarios**:

1. **Given** no custom message, **When** GET, **Then** `blocking_message` is platform default from settings and `blocking_message_is_custom: false`.
2. **Given** category blocked, **When** customer message triggers guardrail at runtime, **Then** router returns project blocking message.
3. **Given** PATCH message ≤240 chars, **When** saved, **Then** GET and runtime use custom message.
4. **Given** PATCH message >240 chars, **When** validated, **Then** `400`.

---

### User Story 3 - Uniform runtime application (Priority: P1)

As the platform, guardrails config MUST apply uniformly to all agents in the project.

**Independent Test**: `GuardrailsUsecase` payload identical for all agents; updates after PATCH + cache invalidation.

**Acceptance Scenarios**:

1. **Given** new project, **When** first GET lazy init, **Then** all categories blocked + platform default message.
2. **Given** existing project, **When** first GET lazy init, **Then** all categories unblocked + platform default message.
3. **Given** PATCH applied, **When** next message processed, **Then** new payload used; prior responses unchanged.

---

### Edge Cases

- Multiple blocked categories match one message → single blocking message (not per-category).
- Empty/whitespace `blocking_message` while any category blocked → `400`.
- Config changed mid-conversation → applies after save only.
- New catalog slug in deploy → merged on GET with project-type default.
- Non-admin PATCH → `403`; GET returns `writable: false`.
- Concurrent PATCH → last write wins.

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
- **FR-012**: Runtime exposes `categories` map + `blocking_message` in guardrails payload.
- **FR-013**: Changes apply only to messages after successful PATCH.
- **FR-014**: GET merges new catalog slugs with project-type defaults.
- **FR-015**: GET returns platform default blocking message from settings when no custom message stored.
- **FR-016**: Custom blocking messages stored without auto-translation.
- **FR-017**: No operator CRUD on catalog category definitions.
- **FR-018**: No per-agent guardrails config in this release.
- **FR-019**: No per-category blocking messages in this release.

### Key Entities

- **Guardrail category (catalog entry)**: Platform slug + English label/description; not mutable via API.
- **Project guardrails configuration**: One-to-one with project; `category_states` + optional custom blocking message.

## Success Criteria *(mandatory)*

- **SC-001**: Admin can GET/PATCH all 11 categories + message in one API session.
- **SC-002**: 100% of over-limit message PATCH attempts return `400`.
- **SC-003**: After PATCH, runtime payload reflects new states on next cache fetch.
- **SC-004**: 100% of non-admin PATCH return `403`.
- **SC-005**: First GET: new projects all blocked; existing all unblocked.
- **SC-006**: 100% of unconfirmed disable PATCH return `409` with typed metadata.

## Assumptions

- Conversation **Topics** (`Topics` model, lambda classifier) are a separate domain — no shared tables or APIs.
- Catalog labels in API are **English strings** from `GUARDRAIL_CATEGORY_CATALOG` (display localization is out of backend scope).
- Models team consumes `categories` map from runtime payload.

## Out of Scope

- Conversation topic classification
- Per-agent guardrails, custom categories, per-category messages, auto-translation
- Frontend/UI, API `Accept-Language`, backend locale modules

## API References

| Method | Route |
|--------|-------|
| GET | `/api/v1/projects/{project_uuid}/guardrails-config/` |
| PATCH | `/api/v1/projects/{project_uuid}/guardrails-config/` |

## Dependencies

| Dependency | Owner |
|------------|-------|
| Category refusal at inference | AI Models team |
| Persistence & injection | Nexus backend |
