# Inline Agent Latency Dashboards

## Recommended: Postgres datasource (Plan B)

Staff and project metrics should query **rollup views** in PostgreSQL, not Prometheus.

**Table / view:** `inline_agent_latency_hourly_v` (see `specs/002-inline-agent-latency-storage/plan.md`)

**Example query (avg + volume by hour):**

```sql
SELECT
  hour_ts,
  turn_count,
  sum_ms / NULLIF(turn_count, 0) AS avg_ms,
  max_ms
FROM inline_agent_latency_hourly_v
WHERE project_uuid = '$project_uuid'
  AND execution_path = 'inline_agents'
  AND phase = 'total'
  AND hour_ts >= NOW() - INTERVAL '7 days'
ORDER BY hour_ts;
```

**Datasource:** Grafana Postgres (read replica recommended).  
**Never** point dashboard panels at `inline_agent_turn_outlier` for aggregate charts — use the outliers API for drill-down.

---

## Optional: Prometheus datasource (ops / paused)

File: `inline_agent_turn_latency.json`

Requires Celery worker scrape into Mimir/Prometheus (`nexus/celery_prometheus_exporter.py`).  
This path is **paused** — metrics are recorded in workers but not exported to Mimir unless cloud team adds scrape config.

Use only if platform ops enables Celery pod scraping.
