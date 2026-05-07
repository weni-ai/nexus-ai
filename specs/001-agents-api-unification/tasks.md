# Tasks: Unified Agents API

**Input**: Design documents from `/specs/001-agents-api-unification/`
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Story points (SP)**: Fibonacci scale **1, 2, 3, 5, 8** — velocity = sum of SP for completed tasks only; no calendar deadlines. SP and **Definition of Done (DoD)** for each task id are listed in [Task metadata](#task-metadata-sp--definition-of-done).

**Organization**: Phases follow **plan execution order** (available_systems → novo retorno → official list/cache → project parity → assign → team/my-agents → removal → polish). User story labels **[US1]–[US5]** map to `spec.md` sections.

## Format

`- [ ] [TaskID] [P?] [Story?] Description with file path`

---

## Phase 1: Setup (shared)

**Purpose**: Confirm feature context and conventions (no code yet).

- [ ] T001 [P] Confirm active branch `001-agents-api-unification` and that `specs/001-agents-api-unification/plan.md` matches merged clarifications in `specs/001-agents-api-unification/spec.md`

**Checkpoint**: Ready for foundational implementation.

---

## Phase 2: Foundational (blocking)

**Purpose**: Service package layout and **C11 / FR-013** creation policy before API refactors.

**⚠️ CRITICAL**: Complete this phase before user story implementation.

- [ ] T002 Create package `nexus/inline_agents/api/services/__init__.py` exporting public service callables per `specs/001-agents-api-unification/plan.md`
- [ ] T003 Implement **`user_may_create_agents(email: str) -> bool`** (official **or** custom) using **exact** normalized email equality against `settings.OFFICIAL_SMART_AGENT_EDITORS` in `nexus/inline_agents/api/services/agent_creation_policy.py`; export it from `nexus/inline_agents/api/services/__init__.py` per plan/research
- [ ] T004 Replace substring `in` check in `PushAgents._check_can_edit_official_agent` with policy helper and extend checks to cover **custom** creation per FR-013 in `nexus/inline_agents/api/views.py`
- [ ] T005 [P] Add type hints and unit tests for `agent_creation_policy` in `nexus/inline_agents/api/tests/test_agent_creation_policy.py` (create file if missing)

**Checkpoint**: Security gate C11 closed; services importable.

---

## Phase 3: User Story 5 — Official v1 single read surface (Priority: P1)

**Goal**: `GET /api/v1/official/agents` is the only official catalog read; paginated, cached, full
row payload (Option A); detail route removed; `available_systems` isolated.

**Independent Test**: Curl/OpenAPI — list returns `results` without `legacy`/`new`, without embedded
systems blob; `GET /api/v1/official/agents/{id}` returns 404/410 per migration; systems only from new
endpoint.

### Implementation

- [ ] T006 [US5] Implement `fetch_available_systems_payload()` delegating to existing `AgentSystemSerializer` patterns in `nexus/inline_agents/api/services/available_systems.py`
- [ ] T007 [US5] Add `OfficialAvailableSystemsV1` APIView + `@extend_schema` in `nexus/inline_agents/api/views_official_extras.py` (create module) with `AUTHENTICATION_CLASSES` / `CombinedExternalProjectPermission` matching `OfficialAgentsV1`
- [ ] T008 [US5] Register `path("v1/official/available-systems", OfficialAvailableSystemsV1.as_view(), name="v1-official-available-systems")` in `nexus/agents/api/routers.py`
- [ ] T009 [US5] Remove embedded `available_systems` from `OfficialAgentsV1.get` response assembly in `nexus/inline_agents/api/views.py`
- [ ] T010 [US5] Implement typed pagination input (`page`, `page_size` max 20) + cache key builder + `list_official_catalog_page` in `nexus/inline_agents/api/services/official_catalog.py`
- [ ] T011 [US5] Wire cache get/set and hook invalidation to existing `notify_async` events used for team/project invalidation in `nexus/inline_agents/api/services/official_catalog.py`
- [ ] T012 [US5] Create `build_novo_retorno_group_row(...)` merging `_build_group_payload` + `OfficialAgentDetailSerializer` field rules (FR-005, FR-001a) in `nexus/inline_agents/api/serializers/catalog.py`
- [ ] T013 [US5] Refactor `OfficialAgentsV1.get` to call `official_catalog.list_official_catalog_page` and return unified envelope per `contracts/official-agents-list-get.md` in `nexus/inline_agents/api/views.py`
- [ ] T014 [US5] Remove `consolidate_grouped_agents` **legacy/new** split; fold legacy rows into same `results` list with `is_official` in `nexus/inline_agents/api/views.py` (or move logic fully into `official_catalog.py`)
- [ ] T015 [US5] Delete `OfficialAgentDetailV1` class and remove `path("v1/official/agents/<str:identifier>", ...)` from `nexus/agents/api/routers.py` and `nexus/inline_agents/api/views.py`
- [ ] T016 [US5] Update `@extend_schema` on `OfficialAgentsV1` to novo retorno list schema in `nexus/inline_agents/api/views.py`
- [ ] T017 [US5] Ensure `OfficialAgentsV1.post` attaches novo retorno-shaped `agent` when present in `nexus/inline_agents/api/views.py`

**Checkpoint**: US5 acceptance scenarios in `spec.md` satisfied for official v1 read path.

---

## Phase 4: User Story 1 — Unified project catalog shape (Priority: P1)

**Goal**: Project-scoped catalog consumption uses the same per-row rules as novo retorno; official vs
custom is only `is_official` (FR-001).

**Independent Test**: For a project with mixed agents, listing endpoints expose identical key sets
per row as documented in `contracts/` and `spec.md` FR-001.

### Implementation

- [ ] T018 [US1] Audit project-scoped agent list endpoints in `nexus/agents/api/routers.py` and `nexus/inline_agents/api/views.py` and document which views must call `build_novo_retorno_group_row` or equivalent in `specs/001-agents-api-unification/research.md` (append section) if gaps found
- [ ] T019 [US1] Refactor identified project catalog GET handler(s) to reuse `nexus/inline_agents/api/serializers/catalog.py` builder so row shape matches official list rules where applicable in `nexus/inline_agents/api/views.py`

**Checkpoint**: US1 structural parity verifiable without second detail shape where spec requires single surface.

---

## Phase 5: User Story 2 — Single assign / unassign (Priority: P2)

**Goal**: FR-004 — one canonical assign and one unassign per product context (remove parallel
legacy/new route semantics).

**Independent Test**: Matrix in `nexus/agents/api/test_agents_api.py` shows single supported pair per
environment; deprecated paths return documented status.

### Implementation

- [ ] T020 [US2] Document and implement single canonical PATCH assign path; deprecate or remove `project/<uuid>/app-assign/<agent_uuid>` in `nexus/agents/api/routers.py` with migration note in `specs/001-agents-api-unification/quickstart.md`
- [ ] T021 [US2] Align `VtexAppActiveInlineAgentsView` behavior or remove route per product decision captured in `specs/001-agents-api-unification/plan.md` Phase 5 in `nexus/inline_agents/api/views.py`

**Checkpoint**: US2 acceptance scenarios hold.

---

## Phase 6: User Story 3 — Pagination & category slugs (Priority: P3)

**Goal**: FR-009, FR-010 — max 20 groups per page; category slugs align with admin.

**Independent Test**: Request page 2 with 40+ groups; assert ≤20 per page; category slugs match admin
source.

### Implementation

- [ ] T022 [US3] Enforce `page_size` upper bound 20 and return 400 on violation in `nexus/inline_agents/api/services/official_catalog.py` and/or `nexus/inline_agents/api/views.py`
- [ ] T023 [US3] Verify queryset uses `category__slug` (and `others` null behavior) unchanged or fixed in `nexus/inline_agents/api/views.py` filters for official list
- [ ] T024 [US3] Add regression tests for pagination cap and category filter in `nexus/agents/api/test_agents_api.py`

**Checkpoint**: US3 scenarios pass.

---

## Phase 7: User Story 4 — Team roster & my agents parity (Priority: P3)

**Goal**: FR-007, FR-008 — `slug` not `id`; strip `skills`/`description`; `system` exposes `name`
only; same keys as novo retorno for my-agents.

**Independent Test**: Diff JSON keys between team/my-agents item and catalog row — identical sets;
VTEX mirrors match.

### Implementation

- [ ] T025 [US4] Refactor `IntegratedAgentSerializer` in `nexus/inline_agents/api/serializers.py` per `contracts/team-roster-get.md` (rename serialized id field to `slug`, remove forbidden fields, narrow `system`)
- [ ] T026 [US4] Refactor `AgentSerializer` in `nexus/inline_agents/api/serializers.py` to match `contracts/my-agents-get.md` and novo retorno parity
- [ ] T027 [US4] Ensure `InlineTeamView`, `VtexAppInlineTeamView`, `AgentsView`, `VtexAppInlineAgentsView` return updated shapes in `nexus/inline_agents/api/views.py`

**Checkpoint**: US4 acceptance scenarios pass.

---

## Phase 8: Deprecation & cleanup (cross-cutting)

**Goal**: Phase 5 of `plan.md` — remove legacy routes, serializers, envelope code.

**Independent Test**: Grep shows no `legacy`/`new` response keys; removed routes 404/410; OpenAPI has
no deleted paths.

### Implementation

- [ ] T028 [P] [US5] Delete `InlineOfficialAgentsView` and routes `agents/official/<project_uuid>` and VTEX mirror per `plan.md` in `nexus/inline_agents/api/views.py` and `nexus/agents/api/routers.py`
- [ ] T029 [P] [US5] Remove dead helpers (`_process_legacy_agents` if fully inlined) and unused imports after service migration in `nexus/inline_agents/api/views.py`
- [ ] T030 Remove `OfficialAgentDetailSerializer` if fully superseded by `nexus/inline_agents/api/serializers/catalog.py` and clean imports in `nexus/inline_agents/api/serializers.py`
- [ ] T031 Update `nexus/agents/api/test_agents_api.py` for all removed routes and new response contracts
- [ ] T032 [P] Regenerate or hand-update OpenAPI snapshots if project uses schema tests under `nexus/` (search `SpectacularAPIView` / schema tests)

**Checkpoint**: Legacy surface area gone; CI green.

---

## Phase 9: Polish & traceability (FR-012, docs)

**Purpose**: Cross-cutting documentation and optional trace writer alignment.

- [ ] T033 [P] Document trace **`name`** correlation in `specs/001-agents-api-unification/quickstart.md` and link FR-012
- [ ] T034 [P] Audit trace JSONL writers to emit `name` where slug was used; list files touched in commit message — search under `nexus/` for inline trace write paths
- [ ] T035 [P] Re-run constitution checklist in `specs/001-agents-api-unification/plan.md` Constitution Check section and tick post-implementation boxes in a follow-up PR note (markdown only)

---

## Dependencies (story order)

```text
Phase 2 → Phase 3 [US5] → Phase 4 [US1] (depends on novo retorno builder T012)
Phase 3 [US5] → Phase 8 (deprecation uses stable novo retorno)
Phase 4 [US1] can overlap Phase 5 [US2] after T012 complete
Phase 7 [US4] depends on T012 + T026 catalog field stability
```

**Suggested MVP (velocity slice)**: Complete through **T017** (end of Phase 3) = official v1 read
path fully migrated — **SP sum T001–T017**.

---

## Parallel execution examples

- After **T002**: **T003** and **T005** can proceed in parallel (different test vs policy file).
- After **T012**: **T025** and **T026** can proceed in parallel (same serializers file — **avoid**;
  sequence T025 then T026 unless branched).
- **T031** and **T032** parallelizable after T028–T030 if different files.

---

## Implementation strategy

1. Land **security + services skeleton** (Phase 2) early.
2. Deliver **official v1 vertical** (Phase 3) as first measurable increment (MVP).
3. Layer **project parity**, **assign consolidation**, **team/my-agents**, then **delete legacy**.

---

## Task metadata (SP + Definition of Done)

| ID   | SP | DoD |
|------|----|-----|
| T001 | 1  | Branch verified; plan and spec conflict list empty or noted in PR description. |
| T002 | 2  | `import nexus.inline_agents.api.services` works; package docstring lists modules. |
| T003 | 3  | `user_may_create_agents` implemented and exported; unit tests cover exact match, substring false positive rejection, non-listed denial. |
| T004 | 3  | `PushAgents` uses helper only; grep shows no `can_edit_email in user_email` in repo for this check. |
| T005 | 3  | New test file runs green under project pytest. |
| T006 | 2  | **`available_systems`** array inside envelope matches prior `AgentSystemSerializer(all, many=True).data` for same DB snapshot (test fixture). |
| T007 | 3  | `GET /api/v1/official/available-systems` returns 200 + schema in Swagger. |
| T008 | 1  | Route registered; name stable for reverse(). |
| T009 | 2  | Official list JSON never contains top-level `available_systems`. |
| T010 | 5  | Pagination metadata present; page>1 works; cache hit on repeated request in test with cache backend mocked. |
| T011 | 3  | Invalidation clears cache entry on simulated `notify_async` event in test. |
| T012 | 8  | Row includes fields required by retired detail contract checklist in plan; no top-level `type`/`system` on envelope. |
| T013 | 5  | `OfficialAgentsV1.get` body matches `contracts/official-agents-list-get.md`. |
| T014 | 5  | No `legacy`/`new` keys in response; all agents in flat `results`. |
| T015 | 3  | Detail URL 404/410; class deleted; imports clean. |
| T016 | 2  | OpenAPI operation shows unified schema only. |
| T017 | 2  | POST response `agent` matches novo retorno keys when returned. |
| T018 | 2  | Audit appendix committed in `research.md`. |
| T019 | 5  | At least one project list view uses catalog builder; manual or automated JSON key diff passes. |
| T020 | 3  | Only one assign route documented in `quickstart.md`; duplicate returns 410 or is removed. |
| T021 | 3  | VTEX assign path decision implemented as documented. |
| T022 | 2  | Request with `page_size=21` returns 400. |
| T023 | 2  | Category filter tests still pass for `others` + slug. |
| T024 | 3  | New tests green. |
| T025 | 5  | Team JSON uses `slug`; no `skills`/`description`; system `{name}` only. |
| T026 | 5  | My-agents JSON key set equals novo retorno row key set (test assertion). |
| T027 | 2  | All four views return new shapes. |
| T028 | 3  | Legacy routes removed; manual curl 404. |
| T029 | 2  | `ruff`/`flake` or project linter clean for `views.py`. |
| T030 | 2  | No remaining import of `OfficialAgentDetailSerializer` except removed. |
| T031 | 8  | Full `test_agents_api` module passes. |
| T032 | 3  | Schema job green if applicable; else task marked N/A in PR. |
| T033 | 1  | `quickstart.md` merged with trace guidance. |
| T034 | 5  | Grep-driven list of writers updated + tests if writers touched. |
| T035 | 1  | Constitution section updated in plan copy or checklist file. |

**Total tasks**: 35
**Total SP**: 110 (sum of metadata table)

---

## Suggested MVP scope

**Tasks T001–T017** (Phases 1–3) — **SP total 53** — delivers official v1 read unification,
`available_systems` isolation, C11 wiring on `PushAgents`, and removal of official detail route.
