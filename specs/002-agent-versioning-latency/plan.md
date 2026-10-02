# Implementation Plan: Agent Versioning — Production Latency & Cache Isolation

**Branch**: `002-agent-versioning-latency` | **Date**: 2026-08-24 | **Spec**: [spec.md](./spec.md)

**Scope**: Router inline-agent configuration load path — consolidate Redis cache, isolate draft/preview invalidation, eager live warm on publish/rollback, feature-flag rollout, observability gates. Depends on sibling versioning work (`ProjectRelease`, publish API) but can land read-path + cache layer in phases.

## Summary

Replace fragmented pre-generation cache reads (up to 7 Redis keys + scattered DB fallbacks) with a **single live runtime snapshot** (`project:{uuid}:runtime:live`) built from `Project.active_release`. Production messages (`preview=False`) must hit cache with **zero Postgres** on steady state. Draft edits refresh **preview snapshots only** (`runtime:preview:{user}`), fixing today's leak where `ContentBaseInstruction` invalidation rebuilds production cache from live DB. Publish/rollback warm live cache off the message path. Phased rollout via GrowthBook feature flag with fallback to `PreGenerationService`. Instrument hit/miss/rebuild metrics inside existing `pre_generation` latency phase.

## Technical Context

**Language/Version**: Python 3.11, Django 4.2

**Primary Dependencies**: Redis (`CacheService` / Django cache backend), `PreGenerationService`, `CachedProjectData`, `TurnLatencyRecorder` (`PHASE_PRE_GENERATION`), GrowthBook via `weni-feature-flags`, Celery (async catalog fan-out optional)

**Storage**: Redis — `runtime:live`, `runtime:preview:{user}`; Postgres — `Project.active_release` + `ProjectRelease` graph on cache miss only (sibling feature)

**Testing**: pytest in `router/` and `nexus/`; mock Redis; integration tests comparing `from_runtime_config` invoke kwargs vs legacy path; staging load test for miss p99

**Target Platform**: Linux (Router Celery workers — `start_inline_agents`)

**Project Type**: Backend worker hot-path optimization + cache layer

**Performance Goals**: SC-002/SC-003 — p50 ≤ baseline, p99 ≤ baseline + 10% for `pre_generation`; SC-005 — < 1% live cache miss rate steady state; SC-006 — rebuild p99 < 500 ms staging

**Constraints**: No Postgres on production cache hit; no live cache rebuild on draft edit; no per-message session epoch; 24h TTL aligned with `CacheService`; KB RAG outside scope

**Scale/Scope**: All inline-agent projects; one blob per project (live) + one per editor (preview)

## Constitution Check

| Gate | Status |
|------|--------|
| Placeholder constitution | PASS (N/A) |
| Tests for new service + invoke integration + invalidation matrix | PASS (required) |
| Feature flag rollback without migration undo | PASS |
| No regression on `pre_generation` phase reporting | PASS (FR-010) |
| Scope: no LLM/KB-search latency changes | PASS |

## Project Structure

### Documentation

```text
specs/002-agent-versioning-latency/
├── spec.md, plan.md, research.md, data-model.md
├── quickstart.md
├── contracts/runtime-config-service.md
└── checklists/requirements.md
```

### Source Code

```text
router/
├── services/
│   ├── cache_service.py              # extend: runtime key helpers, deprecate granular invalidation on draft
│   ├── pre_generation_service.py     # legacy fallback (phases 0–5)
│   └── runtime_config_service.py     # NEW: get_live, get_preview, warm, invalidate
├── tasks/
│   ├── invoke.py                     # start_inline_agents: flag → RuntimeConfigService
│   ├── invocation_context.py         # CachedProjectData.from_runtime_config
│   └── latency_context.py            # optional tags on pre_generation (hit/miss)
nexus/
├── projects/
│   └── services/release_resolver.py  # NEW (or under usecases): resolve_release()
├── inline_agents/team/repository.py    # team dict builders reused at build time
└── feature_flags/                      # GrowthBook key for read-path rollout

nexus/staticfiles/docs/versioning/
├── agent_versioning_latency_plan.md    # design reference (aligned)
├── agent_versioning_runtime_config.md
└── schemas/runtime_config.v1.schema.json
```

**Structure Decision**: New `RuntimeConfigService` in `router/services/` (same layer as `PreGenerationService`); release resolution in `nexus/` close to `ProjectRelease` models (sibling PR may own models first).

## Phase 0 — Research

Complete → [research.md](./research.md)

## Phase 1 — Design & Contracts

Complete → [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Phase 2 — Tasks

Complete → [tasks.md](./tasks.md)

## Implementation Phases (rollout)

Aligned with [latency plan](../../nexus/staticfiles/docs/versioning/agent_versioning_latency_plan.md) §8:

| Phase | Deliverable | Latency impact |
|-------|-------------|----------------|
| 0 | Baseline `pre_generation` dashboards | None |
| 1 | `resolve_release` + warm on publish (write-only) | None on read path |
| 2 | Feature flag: `get_live()` with `PreGenerationService` fallback | ≤ baseline |
| 3 | Production reads `runtime:live` only | Target ≤ baseline p50 |
| 4 | Stop draft-edit invalidation of legacy keys | Fixes prod churn |
| 5 | Remove legacy granular keys | Same as phase 3 |

## Complexity Tracking

No constitution violations requiring justification.
