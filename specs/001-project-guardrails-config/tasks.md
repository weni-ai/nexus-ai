# Tasks: Project Guardrails Category Configuration

**Scope**: Nexus backend only

## Phase 1: Setup

- [ ] T001 Add `GUARDRAIL_CATEGORY_CATALOG` (incl. Bedrock definition/examples), `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE`, and `GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT` to `nexus/settings.py`

## Phase 2: Foundational

- [ ] T002 Create `ProjectGuardrailsConfig` model in `nexus/projects/models.py` with `category_states`, `blocking_message`, `bedrock_guardrail_identifier`, `bedrock_guardrail_version`, and `clean()`
- [ ] T003 Add migration in `nexus/projects/migrations/`
- [ ] T004 [P] Implement `ProjectGuardrailsConfigUseCase` in `nexus/usecases/guardrails/project_guardrails_config.py`
- [ ] T005 [P] Add `GuardrailsConfigAdminPermission` in `nexus/projects/api/permissions.py`

## Phase 3: User Story 1 — Category blocked states (P1)

- [ ] T006 [US1] Serializers in `nexus/projects/api/serializers.py` (`categories` in response, `category_states` in PATCH)
- [ ] T007 [US1] `ProjectGuardrailsConfigView` GET/PATCH in `nexus/projects/api/views.py`
- [ ] T008 [US1] Route in `nexus/projects/api/routers.py`
- [ ] T009 [US1] Confirmation logic (`409`, `disable_category`, `disable_all`) in use case
- [ ] T010 [P] [US1] Tests in `nexus/projects/api/tests/test_guardrails_config.py`

## Phase 4: User Story 2 — Blocking message (P2)

- [ ] T011 [US2] Message validation (240 chars, non-empty when blocked) in serializers
- [ ] T012 [P] [US2] Message validation tests (message-only PATCH does not call Bedrock update)

## Phase 5: Bedrock sync (P1)

- [ ] T013 [US1/US3] Implement Bedrock sync service (`create`/`update`/`version`) with Denied Topics = only `blocked=true` categories
- [ ] T014 [US1/US3] Wire category PATCH → sync; persist identifier/version; fail request on sync failure
- [ ] T015 [P] Sync unit tests (omit unblocked; all-unblocked; mock boto3)

## Phase 6: User Story 3 — Runtime ApplyGuardrail (P1)

- [ ] T016 [US3] Preprocess gate in `router/tasks/invoke.py`: `ApplyGuardrail` `source=INPUT`; skip when no categories blocked; **no** `GUARDRAILS_LAYER_LAMBDA`
- [ ] T017 [US3] On `GUARDRAIL_INTERVENED`, return project effective blocking message (Option A); reuse existing early-exit / `UnsafeMessageException` patterns
- [ ] T018 [US3] Cache id/version + effective message; invalidate on PATCH
- [ ] T019 [P] [US3] Router/usecase tests: intervene → project message; pass-through; skip when all unblocked; no Lambda invoke

## Phase 7: Polish

- [ ] T020 [P] drf-spectacular annotations on view
- [ ] T021 Run `quickstart.md` scenarios
- [ ] T022 [P] Django admin read-only in `nexus/projects/admin.py`

---

**Removed**: former i18n locale task — out of backend scope.

**Removed**: “extend runtime payload with `categories` map for Models” — replaced by ApplyGuardrail + Option A.

**MVP**: Phases 1–3 + Phase 5–6 (API + sync + preprocess gate).
