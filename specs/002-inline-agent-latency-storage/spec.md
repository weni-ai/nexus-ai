# Feature Spec: Inline Agent Latency Storage (Plan B)

## Overview

Persist inline agent turn latency from `start_inline_agents` into PostgreSQL using **hourly rollups** (all turns) and an **outlier table** (slow, failed, or sampled turns). Expose metrics to staff and super users via internal REST API and optional Grafana Postgres datasource — without depending on Prometheus/Mimir Celery scrape.

Builds on **Phase 0 instrumentation** (`TurnLatencyRecorder`, Celery lifecycle signals) already implemented on `feat/inline-agent-phase0-latency-instrumentation`.

## User Stories

### US-1: Per-project latency overview

As a staff user, I want to see aggregated latency (avg, max, volume) for a project over a date range so that I can tell if the project is healthy without reading Celery logs.

**Acceptance criteria:**
- `GET /api/analytics/inline-agent-latency/summary/` accepts `project_uuid`, `start_date`, `end_date`
- Response includes turn counts, phase-level aggregates, and SLO fields: `p95_ms`, `pct_under_target_high_ms` (% turns ≤ 20s), `pct_over_max_tolerable_ms` (% turns ≥ 30s)
- Requires `InternalCommunicationPermission` (superuser token or `can_communicate_internally`)
- Max query range: 90 days
- Response time target: < 200 ms p95 under normal load

### US-2: Time series for charts

As a staff user, I want hourly latency trends so that I can spot spikes over time (Grafana or API).

**Acceptance criteria:**
- `GET /api/analytics/inline-agent-latency/timeseries/` returns hourly buckets from `inline_agent_latency_hourly`
- Supports `phase` filter (`total`, `agent_execution`, etc.)
- Supports `execution_path` filter (default `inline_agents`)
- P95 estimable from JSONB `buckets` field

### US-3: Spike investigation → conversation

As a staff user investigating a slow hour, I want the slowest turns with enough metadata to find the conversation in **nexus-conversation** so that I can understand what caused the spike.

**Acceptance criteria:**
- `GET /api/analytics/inline-agent-latency/outliers/` returns ranked outlier rows for `project_uuid` + time window
- Each row includes: `contact_urn`, `turn_id`, `message_conversation_log_uuid`, `phase_ms`, `total_ms`, `status`
- Each row includes `conversation_lookup` object with nexus-conversations query parameters
- Default `limit` 50, max 100
- Failures always stored as outliers

### US-4: Scale-safe writes

As a platform engineer, I want every turn to update rollups without storing every turn as a full row so that Postgres remains bounded at millions of messages per month.

**Acceptance criteria:**
- Every successful/failed turn with valid `project_uuid` UPSERTs hourly rollup rows
- Outlier INSERT only when capture rules match (threshold, failure, sample)
- No write when `project_uuid` missing (guardrail counter + Sentry, Phase 0 behavior)
- In-task P95 regression ≤ 5% vs week before persistence merge

### US-5: Retention and cold archive

As a platform engineer, I want 90 days of hot data in Postgres and older data exportable so that storage cost stays predictable.

**Acceptance criteria:**
- Management command or scheduled task exports partitions older than 90 days to cold storage (S3 Parquet — format TBD)
- PG partitions or rows dropped after successful export
- Rollups and outliers follow same retention policy

### US-6: Extensibility for new phases and paths

As a developer adding a new execution path or phase, I can register it without a migration per phase.

**Acceptance criteria:**
- Rollups keyed by `(project_uuid, hour_ts, execution_path, phase)`
- `phase_ms`, `boundaries_ms`, `context` on outliers are JSONB
- Phase list driven by code registry, not DB columns per phase

## SLO & Latency Targets

| Concept | Default (ms) | Purpose |
|---------|--------------|---------|
| **Target band** | 15 000 – 20 000 | Operational goal — track via rollups (% under 20s, P95 trend) |
| **Max tolerable** | 30 000 | Hard ceiling — turns at or above this are unacceptable |
| **Broker wait** | 2 000 | Separate threshold for queue/Redis issues |

Rollup histogram buckets MUST include **`15000`, `20000`, `30000`** so the 15–20s band and 30s breach are visible in Grafana/API **without** storing every turn.

## Outlier Capture Rules

| Condition | Store outlier | `sample_reason` |
|-----------|---------------|-----------------|
| `status` is `failed` or `blocked` | Always | `failed` / `blocked` |
| `total_ms` ≥ max tolerable (default 30 000 ms) | Always | `threshold` |
| `broker_queue_wait_ms` > broker threshold | Always | `broker_threshold` |
| Target band (≥ 15 000 ms and < 30 000 ms) | Configurable sample | `elevated_sample` |
| Random sample (default 0.1%, **env-configurable**) | Yes | `random_sample` |
| Otherwise | Rollup only | — |

**Understanding the 15–20s band:** aggregate metrics come from rollups (primary). The **elevated band sample** is optional drill-down for turns between target and max tolerable — rate is tunable if volume is too high.

## Configurable Settings (environment / Django)

| Setting | Default | Description |
|---------|---------|-------------|
| `INLINE_AGENT_LATENCY_TARGET_MS_LOW` | `15000` | SLO band lower bound (reporting) |
| `INLINE_AGENT_LATENCY_TARGET_MS_HIGH` | `20000` | SLO band upper bound (reporting) |
| `INLINE_AGENT_LATENCY_OUTLIER_MS` | `30000` | Max tolerable — always capture outlier |
| `INLINE_AGENT_LATENCY_BROKER_OUTLIER_MS` | `2000` | Broker wait outlier threshold |
| `INLINE_AGENT_LATENCY_SAMPLE_RATE` | `0.001` | Random sample (0.1%) — **change without deploy** if env-driven |
| `INLINE_AGENT_LATENCY_ELEVATED_MS` | `15000` | Lower bound for elevated-band sampling |
| `INLINE_AGENT_LATENCY_ELEVATED_SAMPLE_RATE` | `0.01` | Sample rate for 15s–30s band (1%); set `0` to disable |
| `INLINE_AGENT_LATENCY_ENABLED` | `true` | Kill switch |

## Correlation Contract (nexus-conversation)

Outlier rows and API responses MUST include:

| Field | Source |
|-------|--------|
| `project_uuid` | message |
| `contact_urn` | message |
| `turn_id` | `msg_event.msg_external_id` or generated |
| `message_conversation_log_uuid` | generated in `invoke.py` |
| `turn_finished_at` | wall clock at `finish()` |
| `channel_type` | derived from message / channel URN |

## Non-Functional Requirements

- **Cardinality:** no `contact_urn` or tool names in rollup tables
- **Auth:** Phase 1 uses existing internal analytics permissions; Keycloak MCP is out of scope here
- **PII:** `contact_urn` in outliers — staff-only endpoints, audit access later
- **Hot path:** sync PG write in `finish()` unless profiling shows need for batch buffer

## Out of Scope (this spec)

- Keycloak MCP server (future Phase 6 in `tem_latency_plan.md`)
- Prometheus Celery scrape / Mimir integration
- Storing full conversation text in Nexus
- Per-tool/per-model rollup dashboards (outlier `context` or Langfuse only)
- Raw row for every turn in Postgres (Plan C — only if compliance requires later)

## Related Documents

- `nexus/tem_latency_plan.md` — master plan
- `specs/002-inline-agent-latency-storage/plan.md` — implementation architecture
- `specs/002-inline-agent-latency-storage/tasks.md` — task checklist
