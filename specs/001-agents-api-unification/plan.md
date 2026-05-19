# Implementation Plan: Unified Agents API

**Branch**: `001-agents-api-unification` | **Date**: 2026-04-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-agents-api-unification/spec.md`

## Summary

Unify agent HTTP read and roster contracts: **Option A (strict)** — each paginated catalog row
carries the **full** per-group payload (including MCP and credential metadata previously fetched
via detail), bounded by **≤20 groups per page** and acceptable payload size per product review.
Add **`GET /api/v1/official/available-systems`** for global system metadata; remove **`legacy` /
`new` envelope**, legacy **`/api/agents/official/<project_uuid>/`**, and **`GET /api/v1/official/agents/{identifier}`**.
Align **`/api/agents/teams/...`**, **`/api/agents/my-agents/...`** (and VTEX mirrors) to the same
**novo retorno** field set. Introduce a **service-layer** catalog builder with **cache + pagination**
for official v1 list. Fix **C11**: **`OFFICIAL_SMART_AGENT_EDITORS`** checks MUST use **exact
case-normalized email equality**, never substring `in`.

## Technical Context

**Language/Version**: Python 3.10 (Dockerfile / Poetry)
**Primary Dependencies**: Django, Django REST Framework, drf-spectacular, PostgreSQL
**Storage**: PostgreSQL (`Agent`, `AgentGroup`, `IntegratedAgent`, `AgentSystem`, `MCP`, etc.)
**Testing**: `pytest` / Django `TestCase` — primary suite `nexus/agents/api/test_agents_api.py` and
inline agents tests
**Target Platform**: Linux / containerized API (`nexus/urls.py` mounts `nexus/agents/api/routers.py` under `/api/`)
**Project Type**: Django REST backend (multi-route agents surface)
**Performance Goals**: Official v1 list p95 within existing SLO where possible; **cache** hot
read path; pagination caps payload per FR-009
**Constraints**: Max **20** agent **groups** per listing page; **no** top-level `type` / `system` on
unified row envelope (FR-005); retain **`model`** (FR-001a); traces use **`name`** (FR-012)
**Scale/Scope**: All consumers of `OfficialAgentsV1`, `OfficialAgentDetailV1`, `InlineOfficialAgentsView`,
`TeamView` / `AgentsView`, VTEX app mirrors, OpenAPI schema, and trace producers / readers

## Constitution Check

*GATE: Passed with explicit layering plan. Re-check after Phase 1.*

Verify against `.specify/memory/constitution.md` (Nexus AI Constitution):

- [x] **Traceability**: Plan maps FR/US to files and phased delivery; `tasks.md` will follow
- [x] **Security**: C11 exact-match allow-list; no secrets in repo; FR-013 creation gate centralized
- [x] **Verification**: Contract tests + updated `test_agents_api` scenarios for new shapes and 404s
- [x] **Observability**: Cache miss/hit metrics optional; trace `name` doc in `quickstart.md`; logging on invalidation
- [x] **Simplicity**: Reuse existing query helpers where possible; one novo retorno builder
- [x] **Layering**: New **service module** for catalog assembly; views thin (parse, authorize, call service, serialize)
- [x] **Side effects**: Reuse existing `notify_async` cache invalidation events (`cache_invalidation:team`, `project`)
- [x] **Typing and errors**: New service functions fully typed; domain errors → HTTP via existing DRF patterns

## Project Structure

### Documentation (this feature)

```text
specs/001-agents-api-unification/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
└── tasks.md              # produced by /speckit-tasks (not this command)
```

### Source Code (repository root)

```text
nexus/
├── urls.py                          # API root (includes agent_routes only; typically unchanged)
├── agents/api/
│   └── routers.py                   # MODIFY: routes add/remove/rename
├── inline_agents/api/
│   ├── views.py                     # MODIFY (large): refactor views; DELETE classes per plan
│   ├── serializers.py             # MODIFY: novo retorno, team/my-agents; deprecate old official serializers
│   └── services/                    # CREATE package
│       ├── __init__.py
│       ├── official_catalog.py    # CREATE: grouping, pagination, cache keys, row build
│       ├── available_systems.py   # CREATE: query + DTO for systems list
│       └── agent_creation_policy.py  # CREATE: OFFICIAL_SMART_AGENT_EDITORS exact-match helper (FR-013 + C11)
├── usecases/inline_agents/
│   ├── assign.py                    # MODIFY only if return payloads need usecase-level DTOs
│   └── create.py                    # REVIEW: ensure creation paths respect FR-013 when invoked outside PushAgents
└── agents/api/
    └── test_agents_api.py           # MODIFY: extensive contract updates
```

**Structure Decision**: All new orchestration lives under `nexus/inline_agents/api/services/` to
satisfy constitution service-layer rules without moving Django models.

## Complexity Tracking

No constitution violations requiring justification.

---

## Strategic decision: Option A (strict unification)

**Decision**: One **novo retorno** row shape for list (and any remaining single-resource reads that
must match) including MCP/credential detail formerly behind `OfficialAgentDetailV1`.

**Rationale**: Product confirmed MCP/credential volume is small; **20 rows/page** keeps responses
bounded. Eliminates second round-trip and removes `legacy`/`new` divergence.

**Alternatives rejected**: Lazy optional `include=full` query (adds branching); separate BFF layer
(out of scope).

---

## Phased execution (mandatory order)

### Phase 1 — Isolate `available_systems`

**Goal**: FR-006 — clients fetch systems only from a dedicated GET.

| Action | File |
|--------|------|
| **CREATE** service | `nexus/inline_agents/api/services/available_systems.py` — load `AgentSystem` queryset, reuse serialization logic equivalent to today’s `AgentSystemSerializer(all_systems)` |
| **CREATE** view | `OfficialAvailableSystemsV1` (module: either new `nexus/inline_agents/api/views_official.py` **or** bottom section of `views.py` if team prefers single file — **prefer new file** `views_official_extras.py` to shrink `views.py`) |
| **MODIFY** routes | `nexus/agents/api/routers.py` — add `path("v1/official/available-systems", ...)` **before** refactoring consumers |
| **MODIFY** consumer | `OfficialAgentsV1.get` — **remove** embedding `available_systems` from response |
| **DELETE** inline systems blob | Response dict in `OfficialAgentsV1.get` that sets `"available_systems": systems_data` inside `new` |

**Contract**: See `contracts/available-systems-get.md`.

---

### Phase 2 — Unified serializer (“novo retorno”)

**Goal**: Single structured representation for an agent **group row** (official grouped, official
legacy-as-row, custom project agents normalized to same keys).

| Action | File |
|--------|------|
| **CREATE** serializer module | `nexus/inline_agents/api/serializers/catalog.py` (or `novo_retorno.py`) — e.g. `NovoRetornoAgentGroupSerializer` / `build_novo_retorno_row(agent|group_context, project_uuid, ...)` |
| **MODIFY / RETIRE** | Merge capabilities of `OfficialAgentListSerializer`, `_build_group_payload`, and **`OfficialAgentDetailSerializer`** field rules into one builder + thin serializer |
| **ENSURE** | Presence of `is_official`, `model` (FR-001a), **no** top-level `type` / `system` on envelope (FR-005); inner `agents[]` members follow unified nested rules agreed in contract |
| **OPENAPI** | Update `@extend_schema` on `OfficialAgentsV1` to reference novo retorno schema |

**Contract**: See `contracts/official-agents-list-get.md` (includes pagination envelope).

---

### Phase 3 — Listing + assignment on unified structure

**Goal**: Official v1 GET + POST assign return novo retorno; cache + pagination; remove legacy envelope.

| Action | File |
|--------|------|
| **CREATE** | `nexus/inline_agents/api/services/official_catalog.py` — `list_official_agent_groups_page(...)`, cache get/set, invalidation hooks (subscribe to same events as today’s `notify_async` for team/project) |
| **MODIFY** | `OfficialAgentsV1` — `get`: call service; apply **cursor or offset pagination** (research: offset/limit with `page` + `page_size`≤20); **delete** `legacy`/`new` keys; use novo retorno list only |
| **MODIFY** | `OfficialAgentsV1` — `post`: response `agent` field uses novo retorno builder |
| **MODIFY** | `consolidate_grouped_agents`, `_process_legacy_agents`, `_build_group_payload` — **inline into service** or shrink to private helpers used only by service; **remove** `{"legacy","new"}` return |
| **MODIFY** | `GetInlineAgentsUsecase` (if needed) — only if team listing logic must share queries with service |

**Cache**: Django cache (`django.core.cache.cache`) with keys derived from query params + page;
invalidate on agent/group/MCP template changes and on assign/unassign (reuse existing async events).

---

### Phase 4 — Team + My Agents strict contract

**Goal**: FR-007, FR-008 — same keys as novo retorno row; `slug` not `id`; system = `{name}` only;
strip `description` / `skills` from team roster contract.

| Action | File |
|--------|------|
| **MODIFY** | `IntegratedAgentSerializer` in `nexus/inline_agents/api/serializers.py` — rename serialized **`id` → `slug`**, remove `description`, `skills`, `about` if not in novo retorno (align field-for-field) |
| **MODIFY** | `get_mcp` return shape — **system** object only `{"name": ...}` for team response path (or drop mcp nesting if spec parity requires — **confirm against final novo retorno** in implementation) |
| **MODIFY** | `AgentSerializer` (my-agents) — output keys MUST match novo retorno for `AgentsView` |
| **MODIFY** | `InlineTeamView`, `VtexAppInlineTeamView` — ensure they use updated serializer / same builder |
| **MODIFY** | `InlineAgentsView`, `VtexAppInlineAgentsView` — idem |

**Contract**: See `contracts/team-roster-get.md`.

---

### Phase 5 — Deprecation and deletion

**Goal**: Remove legacy routes, views, and envelope logic.

| Item | Action |
|------|--------|
| `path("v1/official/agents/<str:identifier>", OfficialAgentDetailV1...)` | **DELETE** route |
| `OfficialAgentDetailV1` class | **DELETE** from `views.py` (or extracted file) |
| `path("agents/official/<project_uuid>", InlineOfficialAgentsView...)` | **DELETE** route (FR-002) |
| `InlineOfficialAgentsView` | **DELETE** class |
| `path("agents/app-official/<project_uuid>", ...)` | **DELETE** or **rewire** to same unified entry point as product dictates for VTEX |
| `OfficialAgentDetailSerializer` | **DELETE** if fully merged; else reduce to private helpers only |
| `legacy` / `new` keys, `_process_legacy_agents` as separate API concern | **DELETE** — legacy agents folded into same list with `is_official` |
| Assign duplicate | **MODIFY** `routers.py` — keep **one** canonical PATCH assign path per environment; deprecate `app-assign` **or** document single supported client (spec FR-004) |

**URL registration note**: HTTP routes live in **`nexus/agents/api/routers.py`**. **`nexus/urls.py`**
only includes `agent_routes` under `api/` — no change expected unless a new include is added.

---

## Security: C11 and FR-013 (`OFFICIAL_SMART_AGENT_EDITORS`)

| File | Change |
|------|--------|
| `nexus/inline_agents/api/views.py` | Replace `if can_edit_email in user_email` with **exact match** after **case-fold** (or canonical email from `request.user.email`) against `settings.OFFICIAL_SMART_AGENT_EDITORS` |
| `nexus/inline_agents/api/services/agent_creation_policy.py` | **CREATE** `user_may_create_agents(email: str) -> bool` centralizing allow-list logic |
| `PushAgents.post` | Call policy helper before any create/update of official or custom agents per FR-013 |

**Audit**: Grep for `CreateAgentUseCase`, other views creating `Agent`, and ensure FR-013 is enforced
or explicitly out of scope with ticket reference.

---

## Trace correlation (FR-012)

| Area | Action |
|------|--------|
| Trace **writers** (where JSONL lines are produced) | Ensure agent identifier written as **`name`**; document in `quickstart.md` |
| `AgentTracesView` / `get_inline_traces` | Optional **read-time** normalization only if backward compatibility required for old files |

---

## File inventory summary

### CREATE

- `nexus/inline_agents/api/services/__init__.py`
- `nexus/inline_agents/api/services/official_catalog.py`
- `nexus/inline_agents/api/services/available_systems.py`
- `nexus/inline_agents/api/services/agent_creation_policy.py`
- `nexus/inline_agents/api/serializers/catalog.py` (novo retorno)
- Optional: `nexus/inline_agents/api/views_official_extras.py` for small new view classes
- `specs/001-agents-api-unification/contracts/*.md` (this command)

### MODIFY

- `nexus/agents/api/routers.py`
- `nexus/inline_agents/api/views.py` (major)
- `nexus/inline_agents/api/serializers.py` (major)
- `nexus/agents/api/test_agents_api.py` (major)
- `nexus/settings.py` — **no** change expected (list already from env); document exact-match behavior in README/contrib env docs if needed

### DELETE (or fully inline then remove)

- `OfficialAgentDetailV1` + route
- `InlineOfficialAgentsView` + route (`agents/official/...`, `agents/app-official/...` per product)
- `OfficialAgentDetailSerializer` (post-merge)
- Legacy envelope branches and dead helpers after service extraction

---

## Risks

| Risk | Mitigation |
|------|------------|
| External frontends not in repo break silently | Publish OpenAPI diff + `quickstart.md` migration table |
| Cache stale after admin edits | Tie invalidation to existing `notify_async` + admin save signals if missing |
| Name collisions in traces (FR-012) | Document; optional secondary `uuid` in trace metadata in later iteration |

---

## Post-design Constitution Check

All gates remain **satisfied** after adding service modules and contracts.

**Next command**: `/speckit-tasks` to generate `tasks.md` from this plan.
