# Tasks: Project Guardrails Category Configuration

**Scope**: Nexus backend only

## Phase 1: Setup

- [x] T001 Add `GUARDRAIL_CATEGORY_CATALOG` (incl. Bedrock definition/examples), `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE`, and `GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT` to `nexus/settings.py`

## Phase 2: Foundational

- [x] T002 Create `ProjectGuardrailsConfig` model in `nexus/projects/models.py` with `category_states`, `blocking_message`, `bedrock_guardrail_identifier`, `bedrock_guardrail_version`, and `clean()`
- [x] T003 Add migration in `nexus/projects/migrations/`
- [x] T004 [P] Implement `ProjectGuardrailsConfigUseCase` in `nexus/usecases/guardrails/project_guardrails_config.py`
- [x] T005 [P] Add `GuardrailsConfigAdminPermission` in `nexus/projects/api/permissions.py`

## Phase 3: User Story 1 — Category blocked states (P1)

- [x] T006 [US1] Serializers in `nexus/projects/api/serializers.py` (`categories` in response, `category_states` in PATCH)
- [x] T007 [US1] `ProjectGuardrailsConfigView` GET/PATCH in `nexus/projects/api/views.py`
- [x] T008 [US1] Route in `nexus/projects/api/routers.py`
- [x] T009 [US1] Unblock persists immediately (no backend confirmation handshake)
- [x] T010 [P] [US1] Tests in `nexus/projects/api/tests/test_guardrails_config.py`

## Phase 4: User Story 2 — Blocking message (P2)

- [x] T011 [US2] Message validation (240 chars, non-empty when blocked) in serializers
- [x] T012 [P] [US2] Message validation tests (message-only PATCH does not call Bedrock update)

## Phase 5: Bedrock pool registry (P1) — NEXUS-5699

- [ ] T013 [US1/US3] `BedrockGuardrailPool` model/migration + combination key helper
- [ ] T014 [US1/US3] Pool service: get_or_create + lazy `CreateGuardrail` (Denied Topics = `blocked=true` only; baseline when available); reuse existing pool
- [ ] T015 [P] Pool unit tests (create, reuse, all-unblocked / no create; mock boto3)

## Phase 5b: Wire PATCH to pool (P1) — NEXUS-5725

- [ ] T015b [US1] Wire category PATCH → resolve pool → persist id/version on project; fail PATCH on resolve/create failure
- [ ] T015c [P] API/use case tests: assign, two projects share pool, message-only skips Bedrock, failure path

## Phase 6: User Story 3 — Runtime ApplyGuardrail (P1) — NEXUS-5644

- [ ] T016 [US3] Preprocess gate in `router/tasks/invoke.py`: `ApplyGuardrail` `source=INPUT`; skip when no categories blocked; **no** `GUARDRAILS_LAYER_LAMBDA`
- [ ] T017 [US3] On `GUARDRAIL_INTERVENED`, return project effective blocking message (Option A); reuse existing early-exit / `UnsafeMessageException` patterns
- [ ] T018 [US3] Cache id/version + effective message; invalidate on PATCH
- [ ] T019 [P] [US3] Router/usecase tests: intervene → project message; pass-through; skip when all unblocked; no Lambda invoke

## Phase 7: Polish — NEXUS-5645

- [ ] T020 [P] drf-spectacular annotations on view
- [ ] T021 Run `quickstart.md` scenarios
- [ ] T022 [P] Django admin read-only in `nexus/projects/admin.py`

---

**Removed**: former i18n locale task — out of backend scope.

**Removed**: “extend runtime payload with `categories` map for Models” — replaced by ApplyGuardrail + Option A.

**Superseded (2026-07-22)**: “one Guardrail per project + UpdateGuardrail on PATCH” → hybrid pool registry + lazy Create + shared assignment.

**Deferred**: system prompt denied-topics injection; OUTPUT ApplyGuardrail.

**MVP**: Phases 1–4 (done) + Phase 5–6 (pool + wire + preprocess gate).
