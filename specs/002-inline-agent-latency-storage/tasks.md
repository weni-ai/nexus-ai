# Tasks: Inline Agent Latency Storage (Plan B)

## Phase 0 — Instrumentation (prerequisite) ✅

- [x] `TurnLatencyRecorder` + phase timers
- [x] Celery lifecycle signals (`nexus/celery_latency_signals.py`)
- [x] Router/enqueue timestamps
- [x] Required `project_uuid` guardrail
- [x] Optional Prometheus metrics module
- [x] Celery startup import fix
- [ ] Merge Phase 0 to main/staging (if not already)
- [ ] Celery Prometheus scrape — **paused** (ops optional)

## Phase 1 — Spec & plan

- [x] Update `nexus/tem_latency_plan.md` (Plan B architecture)
- [x] Create `specs/002-inline-agent-latency-storage/spec.md`
- [x] Create `specs/002-inline-agent-latency-storage/plan.md`
- [x] Create `specs/002-inline-agent-latency-storage/tasks.md`

## Phase 2 — Data model

- [x] Add `InlineAgentLatencyHourly` model
- [x] Add `InlineAgentTurnOutlier` model
- [x] Migration: indexes + unique constraint `(project_uuid, hour_ts, execution_path, phase)`
- [x] Migration: outlier indexes `(project_uuid, turn_finished_at DESC)`
- [ ] SQL views for Grafana (`inline_agent_latency_hourly_v`)

## Phase 3 — Write path

- [x] Create `nexus/analytics/latency_phases.py` (registry + buckets)
- [x] Create `nexus/analytics/latency_writer.py`
- [x] Wire writer into `TurnLatencyRecorder.finish()`
- [x] Add settings: SLO targets (15s/20s/30s), outlier thresholds, sample rates (env-configurable), kill switch
- [x] Unit tests: rollup UPSERT, outlier rules, missing project_uuid skip

## Phase 4 — Read path (API)

- [x] `latency_conversation_lookup.py` helper
- [x] Query helpers: summary, timeseries, outliers (`latency_queries.py`)
- [x] API views + routes under `nexus/analytics/api/`
- [x] Auth: `InternalCommunicationPermission`
- [x] Query guardrails: max 90 days, limit cap, required `project_uuid`
- [x] Query unit tests

## Phase 5 — Retention

- [x] Management command `export_inline_agent_latency` (stub — no S3 delete yet)
- [ ] Celery beat schedule (daily)
- [ ] Document S3 path / cold storage contract with infra

## Phase 6 — Grafana & docs

- [ ] Postgres dashboard JSON or query doc in `contrib/grafana/`
- [ ] Note in plan: Prometheus dashboard is ops-optional reference

## Phase 7 — Validation

- [ ] Staging: send traffic, verify rollups increment
- [ ] Staging: verify outliers for slow/failed turns
- [ ] Compare in-task P95 before/after writer merge
- [ ] Staff API smoke test with superuser token

## Future — MCP + Keycloak (Phase 6 in master plan)

- [ ] MCP tools wrapping analytics API
- [ ] Keycloak JWT validation on MCP server
- [ ] Project scope claims

## Future — Performance optimizations

- [ ] Redis buffer + batch flush if PG write pressure
- [ ] Adaptive P95 outlier capture
- [ ] Daily rollup materialized view for faster summary API

## Future — Infra (parallel track)

- [ ] Dedicated Celery broker Redis (Phase 1 in master plan)
- [ ] Optional: enable Celery Prometheus exporter scrape
