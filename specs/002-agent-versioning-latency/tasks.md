# Tasks: Agent Versioning — Production Latency & Cache Isolation

**Input**: Design documents from `/specs/002-agent-versioning-latency/`  
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/runtime-config-service.md, quickstart.md

**Dependency**: `ProjectRelease`, `Project.active_release`, and publish/rollback handlers are owned by sibling agent versioning work. Foundational tasks may use stubs until those land; phases 3–5 integrate when models exist.

**Tests**: Included — plan constitution requires service, invoke integration, and invalidation matrix coverage.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Maps to spec user stories US1–US4

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Constants, flag key, schema validation baseline

- [ ] T001 Register GrowthBook feature flag key `runtime_config_live_read` in `nexus/settings.py` (or shared flags config consumed by `nexus/feature_flags/`)
- [ ] T002 [P] Add `RUNTIME_CONFIG_LIVE_TTL` and Redis key builder helpers (`runtime_live_key`, `runtime_preview_key`) in `router/services/cache_service.py`
- [ ] T003 [P] Add schema validation test for `nexus/staticfiles/docs/versioning/schemas/runtime_config.v1.example.live.json` in `router/services/tests/test_runtime_config_schema.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Release resolver, adapter, service skeleton — **blocks all user stories**

**⚠️ CRITICAL**: No user story work until this phase completes (or sibling `ProjectRelease` models are available for integration)

- [ ] T004 Implement `resolve_release(release, *, runtime_mode)` in `nexus/projects/services/release_resolver.py` (prefetch team_members/versions; official agent live lookup per UC-01)
- [ ] T005 [P] Add `CachedProjectData.from_runtime_config` classmethod in `router/tasks/invocation_context.py`
- [ ] T006 [P] Implement `RuntimeConfigService` skeleton (`get_live`, `get_preview`, `warm_live`, `invalidate_preview`, `invalidate_live`) in `router/services/runtime_config_service.py`
- [ ] T007 [P] Unit tests for `resolve_release` output shape vs `runtime_config.v1.schema.json` in `nexus/projects/services/tests/test_release_resolver.py`
- [ ] T008 [P] Unit tests for `from_runtime_config` invoke-kwargs parity vs `from_pre_generation_data` in `router/tasks/tests/test_invocation_context_runtime_config.py`

**Checkpoint**: Resolver + adapter proven; service shell ready for story implementation

---

## Phase 3: User Story 1 — Customer messages stay fast in production (Priority: P1) 🎯 MVP

**Goal**: Production path loads one live cached snapshot with zero Postgres on cache hit

**Independent Test**: Warm `runtime:live`, send `preview=False` message, assert single cache read and `pre_generation` without DB queries (see quickstart §1)

### Implementation for User Story 1

- [ ] T009 [US1] Implement `RuntimeConfigService.get_live` cache hit path (Redis GET → `from_runtime_config`) in `router/services/runtime_config_service.py`
- [ ] T010 [US1] Implement `get_live` cache miss path (load `Project.active_release` → `resolve_release` → SET) in `router/services/runtime_config_service.py`
- [ ] T011 [US1] Wire feature-flag branch in `router/tasks/invoke.py` (`start_inline_agents` `PHASE_PRE_GENERATION`: flag on → `RuntimeConfigService.get_live`, off → `PreGenerationService`)
- [ ] T012 [P] [US1] Tests: cache hit performs zero Postgres config queries in `router/services/tests/test_runtime_config_service.py`
- [ ] T013 [P] [US1] Tests: invoke integration with warm live key in `router/tasks/tests/test_runtime_config_live.py`

**Checkpoint**: MVP — production can read consolidated live blob under feature flag

---

## Phase 4: User Story 2 — Editors draft without slowing live traffic (Priority: P1)

**Goal**: Draft edits refresh preview cache only; live key unchanged

**Independent Test**: Edit draft content, confirm live Redis key hash unchanged while preview rebuilds (quickstart §2)

### Implementation for User Story 2

- [ ] T014 [US2] Implement `RuntimeConfigService.get_preview` and `invalidate_preview` in `router/services/runtime_config_service.py`
- [ ] T015 [US2] Update instruction/content-base invalidation observers to call `invalidate_preview` only (not legacy live keys) when project has draft release in `router/services/cache_invalidation_observers.py`
- [ ] T016 [US2] Audit and update inline KB/instruction save paths (`InlineContentBaseTextViewset`, related views) in `nexus/intelligences/api/views.py` to use preview invalidation hook
- [ ] T017 [P] [US2] Tests: draft edit leaves `runtime:live` stable in `router/services/tests/test_runtime_config_isolation.py`
- [ ] T018 [P] [US2] Tests: preview message uses `runtime:preview:{user}` only in `router/tasks/tests/test_runtime_config_preview.py`

**Checkpoint**: Draft isolation fixed; production latency immune to editor activity

---

## Phase 5: User Story 3 — Publish and rollback warm live config off hot path (Priority: P2)

**Goal**: Publish/rollback eagerly warm `runtime:live`; customer messages not blocked

**Independent Test**: Publish release, verify live blob `release_uuid` updates before next production message (quickstart §3)

### Implementation for User Story 3

- [ ] T019 [US3] Implement `RuntimeConfigService.warm_live` and `invalidate_live` in `router/services/runtime_config_service.py`
- [ ] T020 [US3] Call `warm_live` from publish handler (post-commit) in sibling publish use case module (e.g. `nexus/usecases/projects/publish_release.py` — create hook when sibling lands)
- [ ] T021 [US3] Call `warm_live` from rollback handler in sibling rollback use case module
- [ ] T022 [P] [US3] Tests: publish warms live blob with new `release_uuid` in `router/services/tests/test_runtime_config_warm.py`
- [ ] T023 [P] [US3] Tests: in-flight invoke not blocked during publish warm in `router/tasks/tests/test_runtime_config_publish_concurrency.py`

**Checkpoint**: Live cache always warm after admin release operations

---

## Phase 6: User Story 4 — Safe rollout with regression gates (Priority: P2)

**Goal**: Metrics, flag fallback, phased rollout validation

**Independent Test**: Disable flag → legacy path; enable canary → 7-day p50/p99 gate (quickstart §5, §7)

### Implementation for User Story 4

- [ ] T024 [US4] Emit structured metrics/logs (`runtime_config.cache_hit`, `build_ms`, `blob_bytes`, `layer`) from `RuntimeConfigService` in `router/services/runtime_config_service.py`
- [ ] T025 [US4] Ensure metrics remain inside existing `PHASE_PRE_GENERATION` timing in `router/tasks/latency_context.py` (no new phase name)
- [ ] T026 [P] [US4] Tests: feature flag off uses `PreGenerationService` fallback in `router/tasks/tests/test_runtime_config_feature_flag.py`
- [ ] T027 [P] [US4] Tests: cache miss rebuild duration assertion (< 500 ms mocked/staging) in `router/services/tests/test_runtime_config_miss_budget.py`
- [ ] T028 [US4] Document phase-0 baseline capture procedure and regression gate checklist in `specs/002-agent-versioning-latency/quickstart.md` (§7)

**Checkpoint**: Rollout-safe with observability and instant rollback

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Doc alignment, legacy deprecation, full quickstart validation

- [ ] T029 [P] Remove `session_epoch` from rollback row in invalidation matrix in `nexus/staticfiles/docs/versioning/agent_versioning_runtime_config.md`
- [ ] T030 [P] Sync implementation checklist in `nexus/staticfiles/docs/versioning/agent_versioning_latency_plan.md` with completed tasks
- [ ] T031 Stop legacy granular cache invalidation on draft-only edits (phase 4 rollout) in `router/services/cache_invalidation_observers.py`
- [ ] T032 Remove production reads of legacy granular keys when flag fully enabled (phase 5) in `router/services/pre_generation_service.py` — keep as explicit fallback path only
- [ ] T033 Run all scenarios in `specs/002-agent-versioning-latency/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

```text
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) — BLOCKS US1–US4
    ↓
Phase 3 (US1) ── MVP
    ↓
Phase 4 (US2) — depends on T009–T011 (live path exists)
    ↓
Phase 5 (US3) — depends on T019; sibling publish API
    ↓
Phase 6 (US4) — depends on T009–T011; can parallelize metrics with US2/US3
    ↓
Phase 7 (Polish)
```

### User Story Dependencies

| Story | Depends on | Can parallelize with |
|-------|------------|----------------------|
| US1 | Phase 2 | — (MVP first) |
| US2 | US1 live path | US4 metrics (partial) |
| US3 | US1 `warm_live` contract | US2 after T019 |
| US4 | US1 invoke wiring | US2/US3 late tasks |

### Within Each User Story

- Foundational resolver/adapter before service methods
- Service methods before invoke wiring
- Core implementation before integration tests marked [P]

---

## Parallel Examples

### Foundational (after T004 starts)

```bash
# Parallel: adapter + service skeleton + tests
T005  router/tasks/invocation_context.py
T006  router/services/runtime_config_service.py
T007  nexus/projects/services/tests/test_release_resolver.py
T008  router/tasks/tests/test_invocation_context_runtime_config.py
```

### User Story 1 tests

```bash
T012  router/services/tests/test_runtime_config_service.py
T013  router/tasks/tests/test_runtime_config_live.py
```

### User Story 2 + US4 metrics (late)

```bash
T017  router/services/tests/test_runtime_config_isolation.py
T018  router/tasks/tests/test_runtime_config_preview.py
T024  router/services/runtime_config_service.py  # metrics
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1–2 (Setup + Foundational)
2. Complete Phase 3 (US1): `get_live` + feature flag in `invoke.py`
3. **STOP and VALIDATE**: quickstart §1 — cache hit, zero DB, single GET
4. Enable flag for staging canary only

### Incremental Delivery

1. US1 → production read path under flag (MVP)
2. US2 → draft isolation (fixes prod churn leak)
3. US3 → publish/rollback warm (miss rate < 1%)
4. US4 → metrics + regression gates → expand flag rollout
5. Phase 7 → legacy key deprecation

### Parallel Team Strategy

| Developer | Focus |
|-----------|--------|
| A | Phase 2 + US1 (`release_resolver`, `get_live`, invoke) |
| B | US2 (observers, preview path, isolation tests) |
| C | US3 + US4 (warm hooks, metrics, flag tests) |

---

## Notes

- Guardrails PATCH may still invalidate live cache until snapshotted on release (documented exception in research R10)
- Official catalog async fan-out (UC-01) can be a follow-up task after US3 if not in sibling scope
- Sibling `ProjectRelease` not merged: use factory fixtures in T007–T010 tests until models land
- Total tasks: **33** (Setup 3, Foundational 5, US1 5, US2 5, US3 5, US4 5, Polish 5)
