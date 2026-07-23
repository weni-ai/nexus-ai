# Implementation Plan: Inline Agent Latency Storage (Plan B)

## Architecture

```
start_inline_agents (Celery)
    └── TurnLatencyRecorder.finish()
            └── InlineAgentLatencyWriter
                    ├── upsert_hourly_rollups()   → inline_agent_latency_hourly
                    └── maybe_insert_outlier()    → inline_agent_turn_outlier

Staff / Grafana
    └── nexus/analytics/api/ (read-only use cases)
            └── SQL views (Grafana Postgres datasource)
```

**Write:** Celery worker process (same as Phase 0 recorder).  
**Read:** Nexus API pods (read replica recommended for analytics queries).

## Dependencies

- Phase 0 merged: `TurnLatencyRecorder`, `latency_context.py`, Celery signals
- Django PostgreSQL (existing Nexus DB)
- No new external services for Phase 1b

## Data Model

### App location

`nexus/analytics/models.py` (or `nexus/inline_agents/models/latency.py` if preferred — default to `analytics` alongside resolution-rate).

### Migrations

1. Create `InlineAgentLatencyHourly` model
2. Create `InlineAgentTurnOutlier` model
3. Create indexes and unique constraint on hourly table
4. Create SQL views: `inline_agent_latency_hourly_v`, `inline_agent_latency_daily_v` (optional aggregate)

### JSONB bucket schema (v1)

```json
{
  "500": 0,
  "1000": 0,
  "2500": 5,
  "5000": 12,
  "10000": 3,
  "30000": 0,
  "inf": 0
}
```

## Write Path

### New module: `nexus/analytics/latency_writer.py`

```python
class InlineAgentLatencyWriter:
    def record_turn(self, *, project_uuid, execution_path, finished_at, status,
                    total_ms, boundaries_ms, phase_ms, correlation, context) -> None:
        self._upsert_rollups(...)
        self._maybe_insert_outlier(...)
```

Called from `TurnLatencyRecorder.finish()` when `metrics_enabled`.

### Phase registry: `nexus/analytics/latency_phases.py`

- `EXECUTION_PATH_INLINE_AGENTS = "inline_agents"`
- `PHASES_INLINE_AGENTS` list
- `BOUNDARY_METRICS` list
- `bucket_ms(duration_ms) -> str` helper

### Settings (optional)

| Setting | Default | Description |
|---------|---------|-------------|
| `INLINE_AGENT_LATENCY_OUTLIER_MS` | `5000` | Total ms threshold |
| `INLINE_AGENT_LATENCY_BROKER_OUTLIER_MS` | `2000` | Broker wait threshold |
| `INLINE_AGENT_LATENCY_SAMPLE_RATE` | `0.001` | Random sample rate |
| `INLINE_AGENT_LATENCY_ENABLED` | `true` | Kill switch |

## Read Path

### Use cases

| Module | Responsibility |
|--------|----------------|
| `nexus/analytics/usecases/latency_summary.py` | Daily/hourly aggregates |
| `nexus/analytics/usecases/latency_timeseries.py` | Hourly series |
| `nexus/analytics/usecases/latency_outliers.py` | Spike drill-down + `conversation_lookup` |

### API routes

Add to `nexus/analytics/api/routers.py`:

```
inline-agent-latency/summary/
inline-agent-latency/timeseries/
inline-agent-latency/outliers/
```

### Serializers

`nexus/analytics/api/serializers/latency.py` — mirror resolution-rate patterns.

### Auth

Reuse `InternalCommunicationPermission` from `nexus/analytics/api/views.py`.

### conversation_lookup builder

`nexus/analytics/latency_conversation_lookup.py`:

- Input: outlier row
- Output: dict with `project_uuid`, `contact_urn`, `start_date`, `end_date`, optional `correlation_id`
- Window: `turn_finished_at ± 5 minutes` (configurable)

## Retention

### Management command: `export_inline_agent_latency`

- Export rollups + outliers older than 90 days to S3 Parquet (path TBD with infra)
- Delete exported rows
- Idempotent per partition date

Schedule via Celery beat (daily).

## Grafana

- Document Postgres queries in `contrib/grafana/inline_agent_turn_latency_postgres.json` (new) or README
- Panels query `inline_agent_latency_hourly_v` only
- Template variable: `project_uuid`

Prometheus dashboard `contrib/grafana/inline_agent_turn_latency.json` — keep as reference for optional ops path.

## Optional / Paused

| Item | Status |
|------|--------|
| `nexus/celery_prometheus_exporter.py` | Implemented; scrape config paused |
| `router/tasks/inline_agent_metrics.py` | Keep observe calls optional or remove in Phase 7 |

## Key Files

| File | Change |
|------|--------|
| `router/tasks/latency_context.py` | Call `InlineAgentLatencyWriter` in `finish()` |
| `nexus/analytics/models.py` | New models |
| `nexus/analytics/latency_writer.py` | New |
| `nexus/analytics/latency_phases.py` | New |
| `nexus/analytics/api/views.py` | New views |
| `nexus/analytics/api/routers.py` | New routes |
| `nexus/analytics/management/commands/export_inline_agent_latency.py` | New |
| `nexus/settings.py` | Optional latency settings |
| `nexus/tem_latency_plan.md` | Updated master plan |

## Testing

| Test | Location |
|------|----------|
| Writer upsert + outlier rules | `nexus/analytics/tests/test_latency_writer.py` |
| API auth + query guards | `nexus/analytics/tests/test_latency_api.py` |
| conversation_lookup builder | `nexus/analytics/tests/test_latency_conversation_lookup.py` |
| Recorder integration | extend `router/tasks/tests/test_latency_context.py` |

## Future (not this PR)

- MCP server + Keycloak (`tem_latency_plan.md` Phase 6)
- Adaptive P95 outlier capture
- Redis write buffer for high QPS

## Reference

- Master plan: `nexus/tem_latency_plan.md`
- Mock inserts / examples: discussed in PR/design review (rollup UPSERT + outlier INSERT)
- nexus-conversations public API: `nexus/intelligences/api/supervisor_public.py`
