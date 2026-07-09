# Tasks: Project Guardrails Category Configuration

**Scope**: Nexus backend only

## Phase 1: Setup

- [ ] T001 Add `GUARDRAIL_CATEGORY_CATALOG`, `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE`, and `GUARDRAILS_CONFIG_FEATURE_DEPLOY_AT` to `nexus/settings.py`

## Phase 2: Foundational

- [ ] T002 Create `ProjectGuardrailsConfig` model in `nexus/projects/models.py` with `category_states` JSONField and `clean()`
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
- [ ] T012 [P] [US2] Message validation tests

## Phase 5: User Story 3 — Runtime (P1)

- [ ] T013 [US3] Extend `GuardrailsUsecase.get_guardrail_as_dict` with `categories` + `blocking_message`
- [ ] T014 [US3] Cache invalidation on PATCH
- [ ] T015 [US3] Verify router block path uses config message if needed
- [ ] T016 [P] [US3] Use case + catalog merge tests in `nexus/usecases/guardrails/tests/`

## Phase 6: Polish

- [ ] T017 [P] drf-spectacular annotations on view
- [ ] T018 Run `quickstart.md` scenarios
- [ ] T019 [P] Django admin read-only in `nexus/projects/admin.py`

---

**Removed**: former T002 i18n locale task — out of backend scope.

**MVP**: Phases 1–3 + T013.
