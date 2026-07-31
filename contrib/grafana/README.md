# Inline Agent Latency Dashboards

Staff and project metrics use **Postgres rollups** via the analytics API or Grafana Postgres datasource.

**Table:** `inline_agent_latency_hourly`

**Example query (avg + volume by hour):**

```sql
SELECT
  hour_ts,
  turn_count,
  sum_ms / NULLIF(turn_count, 0) AS avg_ms,
  max_ms
FROM inline_agent_latency_hourly
WHERE project_uuid = '$project_uuid'
  AND execution_path = 'inline_agents'
  AND phase = 'total'
  AND hour_ts >= NOW() - INTERVAL '7 days'
ORDER BY hour_ts;
```

**API (internal auth):**

- `GET /api/analytics/inline-agent-latency/summary/`
- `GET /api/analytics/inline-agent-latency/timeseries/`
- `GET /api/analytics/inline-agent-latency/outliers/`

See `specs/002-inline-agent-latency-storage/plan.md` for full details.
