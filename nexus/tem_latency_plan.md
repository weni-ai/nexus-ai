# Latency & Observability Plan: `start_inline_agents`

**Last updated:** July 2026  
**Scope:** OpenAI backend only (`OpenAIBackend`). Bedrock paths are deprecated and out of scope.  
**Entry point:** `router/tasks/invoke.py` → `start_inline_agents` (single production path)  
**Supersedes:** `nexus/tem_latency_old_plan.md`  
**Speckit:** `specs/002-inline-agent-latency-storage/`

---

## Executive Summary

Previous work on caching, `PreGenerationService`, workflow state, and observers **materially improved the codebase** and surfaced patterns worth keeping. That effort paused before end-to-end latency measurement shipped; the workflow entry point was never adopted in production.

**Phase 0 (instrumentation) is implemented:** `TurnLatencyRecorder`, Celery lifecycle signals, phase timers, and Postgres persistence in `finish()`.

**Direction change (July 2026):** Primary storage and staff-facing metrics move to **PostgreSQL (Plan B: rollups + outliers)** owned by Nexus, not Prometheus/Mimir scrape dependency. This unblocks staff and Grafana (Postgres datasource) without waiting on cloud team Celery scrape config.

**Three priorities going forward:**

1. **Map the full timeline** — HTTP → Celery broker → in-task phases (already instrumented in Phase 0)
2. **Persist aggregates at scale** — hourly rollups for millions of turns/month; selective outlier rows for spike drill-down
3. **Treat shared Redis as a first-class suspect** — broker wait measured separately from in-task work

All improvements ship in **`start_inline_agents` only**, via continuous delivery. Workflow-era modules remain as libraries — never as a second entry point.

**Hard rule:** Nothing in this plan may **increase** user-visible latency. Instrumentation must use in-process timers and a bounded write in `finish()` (rollup UPSERT + conditional outlier INSERT). No per-turn sync HTTP, no extra Redis round-trips for metrics, no expanded Elastic APM in Celery workers.

---

## Architecture Overview

```
POST /messages → enqueue → Celery start_inline_agents
                                │
                    TurnLatencyRecorder.finish()
                                │
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
   inline_agent_latency_hourly          inline_agent_turn_outlier
   (UPSERT every turn)                   (INSERT if slow/failed/sample)
              │                                   │
              ├─► Grafana (Postgres datasource)   ├─► Staff REST API
              ├─► Internal analytics API          ├─► Future MCP (Keycloak)
              └─► 90-day retention in PG          └─► nexus-conversation lookup
                                                        │
   > 90 days ──────────────────────────────────────────┴─► S3 Parquet / ES (cold)
```

### Why not Prometheus-first?

| Issue | Resolution |
|-------|------------|
| Metrics recorded in Celery worker memory | Postgres write at `finish()` |
| Grafana depends on Mimir scrape + cloud team | Grafana reads Postgres rollups |
| Millions of raw rows in PG | Rollups + outliers only (~1–5% detail rows) |
| Conversations in nexus-conversation | Outlier rows store URN + correlation IDs |

**Optional later:** Celery Prometheus scrape was removed — Postgres + analytics API is the sole staff metrics path (no cloud scrape required).

---

## Plan B — Storage Design

### Design principles

1. **Dashboards never scan raw executions** — only rollup views.
2. **`project_uuid` required** on every write; guardrail if missing (Phase 0).
3. **Drill-down uses outliers** — slow, failed, or sampled turns with correlation fields.
4. **Low-cardinality rollups only** — no `contact_urn`, tool name, or model in hourly aggregates.
5. **Extensibility** — `execution_path`, JSONB `buckets` / `phase_ms` / `context` for new paths and phases.

### Tables

#### `inline_agent_latency_hourly`

One row per `(project_uuid, hour_ts, execution_path, phase)`.

| Column | Type | Notes |
|--------|------|-------|
| `project_uuid` | UUID | Required |
| `hour_ts` | timestamptz | Truncated to hour UTC |
| `execution_path` | varchar | e.g. `inline_agents` (extensible) |
| `phase` | varchar | `total`, `orchestration`, `pre_generation`, `generation_setup`, `agent_execution`, `post_generation`, `broker_queue_wait`, … |
| `turn_count` | int | |
| `sum_ms` | bigint | |
| `max_ms` | int | |
| `buckets` | jsonb | Histogram counts — must include **`15000`, `20000`, `30000`** for SLO bands |
| `error_count` | int | |
| `blocked_count` | int | |
| `schema_version` | smallint | Default `1` |

**Unique key:** `(project_uuid, hour_ts, execution_path, phase)`

#### `inline_agent_turn_outlier`

One row per slow, failed, or sampled turn.

| Column | Type | Notes |
|--------|------|-------|
| `project_uuid` | UUID | |
| `execution_path` | varchar | |
| `turn_finished_at` | timestamptz | Index for spike hour queries |
| `contact_urn` | varchar | nexus-conversation lookup |
| `turn_id` | varchar | `msg_external_id` / correlation id |
| `message_conversation_log_uuid` | UUID | Dynamo incoming row id |
| `channel_type` | varchar | e.g. `TG`, `WC` |
| `celery_task_id` | varchar | Ops debug |
| `status` | varchar | `success`, `failed`, `blocked` |
| `total_ms` | int | |
| `boundaries_ms` | jsonb | `broker_queue_wait`, `router_to_enqueue`, … |
| `phase_ms` | jsonb | Extensible phase durations |
| `context` | jsonb | `backend`, `pipeline_version`, enums only |
| `router_received_at` | timestamptz | Optional end-to-end later |
| `sample_reason` | varchar | `threshold`, `failed`, `blocked`, `broker_threshold`, `elevated_sample`, `random_sample` |
| `schema_version` | smallint | |

**Indexes:** `(project_uuid, turn_finished_at DESC)`, optional `(project_uuid, total_ms DESC)` on recent partitions.

### SLO targets (product)

| Concept | Default | Meaning |
|---------|---------|---------|
| **Target band** | 15 – 20 s | Where we want to operate — tracked in rollups |
| **Max tolerable** | 30 s | Hard ceiling — not acceptable; always outlier |

### Outlier capture rules

| Rule | Action |
|------|--------|
| `status != success` | Always insert |
| `total_ms >= 30_000` (max tolerable) | Always insert (`threshold`) |
| `broker_queue_wait_ms > threshold` | Always insert |
| `15_000 <= total_ms < 30_000` | Insert if elevated sample hits (`elevated_sample`, default 1%, configurable) |
| Random sample | Insert (`random_sample`, default 0.1%, env-configurable) |
| Otherwise | Rollup only |

**15–20s understanding:** primarily from rollup buckets and API SLO fields (`p95_ms`, `% under 20s`). Elevated sampling gives optional drill-down in that band without storing every turn.

### Retention

| Tier | Data | Retention | Query |
|------|------|-----------|-------|
| **Hot** | Hourly (+ optional daily) rollups | 90 days PG | Grafana, analytics API |
| **Warm** | Outliers | 90 days PG | Drill-down API, future MCP |
| **Cold** | Parquet or ES export | 12+ months | Athena / support tooling |

Daily job: export partitions older than 90 days → S3; drop PG partitions.

### Scale estimate (5M turns/month)

| Store | Rows / 90 days | Size (order of) |
|-------|----------------|-----------------|
| Hourly rollups | ~few M small rows | hundreds MB – low GB |
| Outliers (~2–5%) | ~2–7M | ~1–5 GB |
| Raw every turn | ~15M | **Avoid in PG** |

---

## Correlation with nexus-conversation

Conversations are **not** stored in Nexus. Outlier rows must carry:

| Field | Use |
|-------|-----|
| `project_uuid` | Scope |
| `contact_urn` | Primary lookup |
| `turn_id` | SQS / `correlation_id` on `message.received` |
| `message_conversation_log_uuid` | Incoming row id |
| `turn_finished_at` ± window | Time-bounded conversation search |

**API response helper (`conversation_lookup`):**

```json
{
  "service": "nexus-conversations",
  "project_uuid": "...",
  "contact_urn": "telegram:1487030707",
  "start_date": "2026-07-16T19:12:00Z",
  "end_date": "2026-07-16T19:22:00Z",
  "correlation_id": "<turn_id>"
}
```

---

## End-to-End Latency Model

```
T-1  HTTP POST /messages accepted          router/main.py
T0a  Celery task published                 before_task_publish signal
T0b  Worker received task from broker      task_received signal
T0c  Task execution starts                 task_prerun signal
     ─── start_inline_agents body ───
T1   Orchestration
T2   Pre-generation
T3   Generation setup
T4   Agent execution                       Langfuse detail
T5   Post-generation
T6   Task finished                          TurnLatencyRecorder.finish()
```

| Metric | Formula | Rollup phase |
|--------|---------|--------------|
| `broker_queue_wait` | T0c − T0a | `broker_queue_wait` |
| `router_to_enqueue` | T0a − T-1 | boundary on outlier |
| `orchestration` | phase timer | `orchestration` |
| `pre_generation` | phase timer | `pre_generation` |
| `generation_setup` | phase timer | `generation_setup` |
| `agent_execution` | phase timer | `agent_execution` |
| `post_generation` | phase timer | `post_generation` |
| `user_turn_total` | T6 − T0c (in-task) | `total` |

---

## Read Surfaces

### 1. Internal REST API (Phase 1b — primary)

Under `nexus/analytics/api/`, same auth as resolution-rate (`InternalCommunicationPermission`):

| Endpoint | Source | Purpose |
|----------|--------|---------|
| `GET …/inline-agent-latency/summary/` | daily rollup | Project overview |
| `GET …/inline-agent-latency/timeseries/` | hourly rollup | Charts |
| `GET …/inline-agent-latency/outliers/` | outlier table | Spike investigation |

**Guardrails:** require `project_uuid`; max 90-day range; `limit` cap (e.g. 100); read replica + `statement_timeout`.

### 2. Grafana (Postgres datasource)

Query **views only** (never outlier table for global dashboards):

```sql
SELECT hour_ts, turn_count, sum_ms / turn_count AS avg_ms, max_ms
FROM inline_agent_latency_hourly_v
WHERE project_uuid = '$project_uuid' AND phase = 'total'
  AND hour_ts >= now() - interval '7 days';
```

P95 from JSONB `buckets` (same math as Prometheus histogram_quantile).

Grafana Postgres dashboards can query `inline_agent_latency_hourly` directly — see `contrib/grafana/README.md`.

### 3. Future MCP for staff (Phase 3)

MCP tools call the **same analytics API** — not Postgres directly.

| Phase | Auth |
|-------|------|
| 1b | `InternalCommunicationPermission`, superuser token, OIDC |
| 3 | Keycloak JWT on MCP server + project scope claims |

Example tools: `latency_summary`, `latency_timeseries`, `latency_outliers`, `latency_spike_investigate`.

### 4. Secondary observability (unchanged)

| Tool | Use |
|------|-----|
| **Langfuse / Logfire** | LLM/tool spans inside T4 |
| **Sentry** | Errors, tags from recorder |
| **S3 inline traces** | Per-turn jsonl drill-down |

---

## Write Path

### Phase 0 (done)

- `TurnLatencyRecorder` in `router/tasks/latency_context.py`
- Celery signals in `nexus/celery_latency_signals.py`
- `router/tasks/inline_agent_enqueue.py` — router timestamps
- Postgres persistence via `TurnLatencyRecorder.finish()` → `record_turn_latency()`

### Phase 1b (next)

1. Django models + migrations for hourly rollup + outlier tables
2. `InlineAgentLatencyWriter` called from `TurnLatencyRecorder.finish()`
3. Phase registry in code (extensible paths/phases)
4. Analytics API + serializers
5. SQL views for Grafana
6. Retention management command (export + partition drop)
7. Tests: writer unit tests, outlier rules, API auth

Add to `nexus/settings.py` (all overridable via env):

| Setting | Default |
|---------|---------|
| `INLINE_AGENT_LATENCY_TARGET_MS_LOW` | `15000` |
| `INLINE_AGENT_LATENCY_TARGET_MS_HIGH` | `20000` |
| `INLINE_AGENT_LATENCY_OUTLIER_MS` | `30000` |
| `INLINE_AGENT_LATENCY_BROKER_OUTLIER_MS` | `2000` |
| `INLINE_AGENT_LATENCY_SAMPLE_RATE` | `0.001` |
| `INLINE_AGENT_LATENCY_ELEVATED_MS` | `15000` |
| `INLINE_AGENT_LATENCY_ELEVATED_SAMPLE_RATE` | `0.01` |
| `INLINE_AGENT_LATENCY_ENABLED` | `true` |

**Write cost:** sync rollup UPSERT (~6–8 rows/turn) + conditional outlier INSERT. Target +2–10 ms; if pressure appears → Redis buffer + batch flush.

---

## Extensibility

| Change | Schema impact |
|--------|---------------|
| New phase name | New `phase` value + key in `phase_ms` |
| New execution path | New `execution_path` value |
| New backend metadata | `context` JSONB |
| High-cardinality (tool/model) | **Outlier `context` or cold store only** — not rollups |

```python
PHASE_REGISTRY = {
    "inline_agents": [
        "orchestration", "pre_generation", "generation_setup",
        "agent_execution", "post_generation",
    ],
}
BOUNDARY_METRICS = ["broker_queue_wait", "router_to_enqueue"]
```

---

## Zero-Latency-Cost Constraint

| Allowed | Not allowed |
|---------|-------------|
| `perf_counter` in task body | Sync HTTP per turn |
| Bounded PG write in `finish()` | Full raw row for every turn in PG forever |
| Celery signal timestamps in headers | Extra Redis keys for metrics |
| Conditional outlier INSERT | Mandatory Sentry transaction per turn |
| Sampled DEBUG logs | High-cardinality rollup labels |

**Validation:** P95 in-task turn duration before vs after persistence PR; roll back if +5% regression.

---

## Known Production Signal: Shared Redis

(Unchanged — see Phase 1 infra below.)

Redis is shared for Celery broker, Django cache, app cache, Channels. Contention shows as high `broker_queue_wait` — measure via rollup phase `broker_queue_wait`.

---

## Implementation Phases

### Phase 0 — Instrumentation + single path ✅ (shipped)

**Status:** Implemented on `feat/inline-agent-phase0-latency-instrumentation`.

- [x] Remove workflow branch from `invoke.py`
- [x] Celery lifecycle signals + headers
- [x] `TurnLatencyRecorder` with required `project_uuid`
- [x] Postgres persistence in `finish()` via `record_turn_latency()`
- [x] Router timestamp propagation
- [x] Grafana query doc (`contrib/grafana/README.md`)
- [x] Celery startup fix (`nexus/celery_latency_signals.py`)

---

### Phase 1b — Postgres storage + staff API (CRITICAL — current focus)

**Goal:** Staff/super users see per-project latency without Mimir; Grafana optional via Postgres.

**Deliverables:** See `specs/002-inline-agent-latency-storage/`.

**Success metrics:**

- Rollups updating for 100% of turns with valid `project_uuid`
- Outlier rate stable (~1–5% of traffic)
- API P95 response < 200 ms for 90-day summary
- Spike drill-down returns `conversation_lookup` for nexus-conversation
- 90-day PG size within budget

---

### Phase 1 — Redis & Celery infrastructure (parallel)

**Goal:** Reduce `broker_queue_wait` without app latency cost.

- Dedicated Redis for Celery broker
- Redis monitoring (infra Grafana — independent of Nexus PG metrics)
- Dedicated `inline-agents` workers
- Per-turn Redis call audit

---

### Phase 2 — Internal structure (HIGH)

Refactor `invoke.py` into phases module — no new broker hops.

---

### Phase 3 — Pre-generation & setup (HIGH)

Cache-first pre-gen, supervisor cache — driven by rollup phase P95.

---

### Phase 4 — Agent execution & tools (MEDIUM)

Tool timeouts, retries; detail in Langfuse + outlier `context` enums.

---

### Phase 5 — Post-generation & capacity (MEDIUM)

Dispatch-first validation; worker autoscale from rollup `broker_queue_wait`.

---

### Phase 6 — Staff MCP (OPTIONAL)

Keycloak-authenticated MCP server wrapping analytics API.

---

### Phase 7 — Cleanup (LOW)

Remove workflow dead code.

---

## Observability Ownership Matrix

| Concern | Tool | Phase |
|---------|------|-------|
| Phase P95, cache hits, errors by `project_uuid` | **Postgres rollups + API** | 1b |
| Spike → conversation | **Outlier table + nexus-conversation** | 1b |
| Staff Grafana charts | **Grafana → Postgres** | 1b |
| LLM/tool spans | **Langfuse / Logfire** | existing |
| Errors, tags on failure | **Sentry** | 0 |
| AI-assisted staff queries | **MCP + Keycloak** | 6 |
| Queue depth, Redis health | **Infra Grafana** | 1 |

---

## Key Files

| Role | Path |
|------|------|
| Production entry | `router/tasks/invoke.py` |
| Latency recorder | `router/tasks/latency_context.py` |
| Postgres writer | `nexus/analytics/latency_writer.py` |
| Celery signals | `nexus/celery_latency_signals.py` |
| Enqueue timestamps | `router/tasks/inline_agent_enqueue.py` |
| Analytics API | `nexus/analytics/api/latency_views.py` |
| Speckit spec | `specs/002-inline-agent-latency-storage/` |
| Grafana queries | `contrib/grafana/README.md` |

---

## Open Questions

1. ~~Outlier threshold~~ — **resolved:** 30s max tolerable; 15–20s target band via rollups + elevated sample
2. ~~Random sample rate~~ — **resolved:** default 0.1%, env-configurable; elevated band 1%, env-configurable
3. Cold export: S3 Parquet vs Elasticsearch?
4. Grafana: team-managed Postgres datasource vs Nexus UI only?
5. After Phase 1 infra: % of total time in `broker_queue_wait` vs `agent_execution`?

---

## Summary

1. **Phase 0 instrumentation ships** — full timeline captured in `TurnLatencyRecorder`  
2. **Plan B Postgres** — rollups for scale, outliers for drill-down, 90-day hot retention  
3. **Nexus-owned read path** — analytics API + optional Grafana Postgres; no Mimir blocker  
4. **nexus-conversation correlation** — URN, turn_id, timestamps on every outlier  
5. **Future MCP + Keycloak** — same API, later auth phase  
6. **Hard rule: no latency regression** — validate every persistence PR against P95  
