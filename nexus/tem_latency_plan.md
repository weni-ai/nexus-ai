# Latency & Observability Plan: `start_inline_agents`

**Last updated:** July 2026  
**Scope:** OpenAI backend only (`OpenAIBackend`). Bedrock paths are deprecated and out of scope.  
**Entry point:** `router/tasks/invoke.py` → `start_inline_agents` (single production path)  
**Supersedes:** `nexus/tem_latency_old_plan.md`

---

## Executive Summary

Previous work on caching, `PreGenerationService`, workflow state, and observers ** materially improved the codebase** and surfaced patterns worth keeping. That effort paused before end-to-end latency measurement shipped; the workflow entry point was never adopted in production.

**This plan continues from that foundation** with three priorities:

1. **Map the full timeline** — from HTTP `/messages` through Celery broker pickup to each processing phase (not just in-task work)
2. **Treat shared Redis as a first-class suspect** — production evidence points to Redis/Celery dequeue latency as a top contributor
3. **Instrument via Prometheus + Grafana from day one** — structured latency views without adding hot-path overhead

All improvements ship in **`start_inline_agents` only**, via continuous delivery. Workflow-era modules remain as libraries to reuse or retire later — never as a second entry point.

**Hard rule:** Nothing in this plan may **increase** user-visible latency. Instrumentation must be in-process counters/histograms or deferred to task `finally`; no synchronous network calls, no extra Redis round-trips per turn, no expanded Elastic APM in the Celery worker.

---

## What Previous Work Delivered (Keep Building On)

| Deliverable | Value |
|-------------|-------|
| `CacheService` + invalidation observers | Reduced DB load; reusable across the app |
| `PreGenerationService` + `CachedProjectData` | Dict-based, cache-first data layer |
| `RedisTaskManager` | Pending-task and message-cache patterns |
| Observer infrastructure | Decoupled side effects (SQS, traces, typing) |
| Workflow orchestrator (unused) | Reference for concat/revoke semantics |

**Direction change:** Stop routing through `inline_agent_workflow`; import useful pieces into the live path.

---

## Known Production Signal: Shared Redis

Redis is **shared across multiple applications** and used for several roles in Nexus:

| Role | Config today |
|------|----------------|
| **Celery broker** | `CELERY_BROKER_URL` → `REDIS_URL` |
| **Celery result backend** | Same URL (`CELERY_TASK_IGNORE_RESULT = True` but connection still exists) |
| **Django cache** | `CACHES["default"]` → same `REDIS_URL` |
| **App cache** (pending tasks, project cache, sessions) | `router/utils/redis_clients.py` → same cluster |
| **Channels** (websockets) | `channels_redis` — separate config but often same cluster in practice |

When Redis is contended, **Celery workers block on BRPOP/LPUSH**, which shows up as long gaps before `start_inline_agents` even begins — often misattributed to "slow agent code."

**Implication:** Phase 0 must measure **broker wait** separately from **in-task Redis** (cache, pending tasks). Infrastructure remediation (dedicated broker Redis) may deliver more gain than code micro-optimizations.

---

## End-to-End Latency Model

Every user message should be traceable across these checkpoints:

```
T-1  HTTP POST /messages accepted          router/main.py
T0a  Celery task published                 before_task_publish signal
T0b  Worker received task from broker      task_received signal  ← Redis dequeue
T0c  Task execution starts                 task_prerun signal
     ─── start_inline_agents body begins ───
T1   Orchestration                         pending tasks, typing (Redis + revoke)
T2   Pre-generation                        PreGenerationService, CacheService (Redis + PG)
T3   Generation setup                      supervisor, adapter, conversation (PG + Redis session)
T4   Agent execution                       LLM + Lambda tools
T5   Post-generation                      dispatch, SQS observers
T6  Task finished                           task_postrun signal
```

### Derived metrics (all exportable to Prometheus, label **`project_uuid`** required)

| Metric | Formula | What it tells us |
|--------|---------|------------------|
| `broker_queue_wait` | T0c − T0a | Celery + **shared Redis broker** contention |
| `worker_scheduling_delay` | T0c − T0b | Worker pool / prefetch / CPU |
| `orchestration` | T2 − T0c | In-task setup + Redis pending-task I/O |
| `pre_generation` | T3 − T2 | Cache + DB bootstrap |
| `generation_setup` | T4_start − T3 | Backend prep before LLM |
| `agent_execution` | T4_end − T4_start | LLM + tools (Langfuse detail) |
| `post_generation` | T6 − T4_end | Dispatch + side effects |
| `user_turn_total` | T6 − T-1 | Full platform latency (needs router timestamp propagation) |

Filter or group any panel in Grafana by **`project_uuid`** to isolate slow tenants vs platform-wide issues.

**Today:** Only pre-generation logs duration internally. Celery lifecycle is **not** mapped. This gap is Phase 0's main deliverable.

---

## Is Celery the Right Tool?

Evaluate per step — default is **keep Celery** unless metrics prove otherwise.

| Step | Current | Fits? | Notes |
|------|---------|-------|-------|
| **Agent turn** (`start_inline_agents`) | Celery task, `inline-agents` queue | **Yes** | Long-running (minutes), retries, rate limit, isolation from web workers |
| **Message routing** (`start_route`) | Celery | Yes | Separate concern |
| **Save inline message** | `save_inline_message_async.delay` | **Maybe** | Already async; if broker is slow, inline thread-pool or batch may be cheaper — measure publish latency first |
| **Typing indicator** | Sync HTTP in task | **Maybe** | Blocks T1; observer already exists — prefer async fire-and-forget **only if** it reduces T1 without extra Redis |
| **Trace upload / SQS** | Observers + Celery tasks | Yes | Already off critical path if dispatch-first |
| **Splitting pre-gen / gen / post into separate Celery tasks** | Not deployed | **No (for now)** | Adds broker round-trips on shared Redis — likely **increases** latency |

**Broker alternative:** If Phase 0 shows `broker_queue_wait` dominates, evaluate **dedicated Redis instance for Celery broker only** (infra change, zero code latency cost) before migrating to RabbitMQ/SQS.

---

## Observability Stack (Structured View From Day One)

### Primary: Prometheus + Grafana ✅

Already in the project (`django-prometheus`, `prometheus_client`, `/api/prometheus/` endpoint, existing `Gauge` patterns in `nexus/logs/observers.py`).

**Use for:**

- Histograms: `inline_agent_*_duration_seconds` (phase breakdown)
- Counters: errors by phase, cache hit/miss
- Gauges: Celery queue depth (via exporter or custom probe)

**Why primary:** In-process `Histogram.observe()` is microseconds — **no added latency** when done once per task in `finally`.

**Grafana dashboards (deliver with Phase 0):**

1. **Turn overview** — P50/P95/P99 `user_turn_total`, error rate; **`project_uuid` filter required**
2. **Per-project drill-down** — same panels scoped to one project (compare against global baseline)
3. **Celery & Redis** — `broker_queue_wait`, queue depth, correlation with Redis CPU/latency (infra panels)
4. **In-task phases** — stacked P95: T1–T5 by `project_uuid`
5. **Cache** — hit ratio by type and project
6. **Tools** — P95 per tool name (top N, cardinality capped)

### Secondary: Sentry ✅

**Use for:** Exceptions, tags (`last_completed_phase`, `project_uuid`, `task_id`), optional **low sample rate** performance transactions.

**Do not use for:** Primary latency dashboards or per-turn phase timing (overhead + sampling gaps).

### Generation traces: Langfuse / Logfire ✅

**Use for:** LLM/tool span detail inside T4 (already integrated in `OpenAIBackend`).

**Keep separate from** platform turn dashboard — link via `turn_id` / `message_conversation_log_uuid`.

### Elastic APM — not recommended for new instrumentation ⚠️

Elastic APM is enabled for Django (`TracingMiddleware`) and used minimally in `invoke.py` (`set_custom_context`). It is valuable for web requests but **problematic for Celery** in this setup (overhead, configuration friction, overlap with Prometheus/Langfuse).

**Policy:**

- Do **not** add new Elastic APM spans or middleware in `start_inline_agents` or Celery signals
- Keep existing Django APM as-is unless team decides to remove it separately
- If distributed trace correlation is needed later, prefer **OpenTelemetry → existing backend** with explicit sampling — not default Elastic in the worker hot path

---

## Zero-Latency-Cost Constraint

Every deliverable must pass this checklist:

| Allowed | Not allowed |
|---------|-------------|
| `time.perf_counter()` in task body | Sync HTTP in new observers on critical path |
| Single `Histogram.observe()` batch in `finally` | Per-phase `event_manager.notify()` with sync observers |
| Celery signals writing timestamps to `request.headers` / task meta only | Extra Redis GET/SET per turn for metrics |
| Reuse existing Redis connections (pools) | New Redis keys written synchronously for tracing |
| Prometheus counters in `CacheService` on existing code path | Elastic APM transaction per phase |
| Propagate `enqueued_at` in task kwargs (one field) | JSON log line per phase at INFO on every message |
| Sampled DEBUG logs | Mandatory Sentry transaction per turn |

**Validation:** Compare P95 `user_turn_total` and P95 `broker_queue_wait` for 24h before vs after each instrumentation PR. Roll back if +5% regression.

---

## Single-Path Strategy

```
POST /messages → start_inline_agents.delay(...) → invoke.py (only path)
```

**Reuse from workflow effort (libraries only):** `PreGenerationService`, `CacheService`, `CachedProjectData`, optionally `handle_workflow_message_concatenation`, `TypingIndicatorObserver`.

**Retire routing:** `WORKFLOW_ARCHITECTURE_PROJECTS`, `inline_agent_workflow.run()` branch — remove in Phase 0.

---

## Implementation Phases

---

### Phase 0 — Full Timeline Instrumentation + Single Path (CRITICAL)

**Goal:** Grafana dashboards show broker wait vs in-task phases for 100% of production traffic, with zero measurable latency regression.

**Deliverables**

1. **Remove workflow branch** from `invoke.py` (confirmed unused)

2. **Celery lifecycle timestamps** via lightweight signals in `nexus/celery.py`:
   - `before_task_publish` → stamp `enqueued_at` in headers
   - `task_received` → stamp `received_at`
   - `task_prerun` → stamp `started_at` (only for `start_inline_agents`)
   - Pass through to task via headers (no Redis)

3. **Required `project_uuid`** — every turn must be attributable to a project:
   - **`TurnLatencyRecorder(project_uuid: str, ...)`** — `project_uuid` is a **required** constructor argument (no default, no empty string)
   - Read from `message["project_uuid"]` at task start; validate format (UUID) before recording
   - If missing or invalid: **do not observe latency histograms**; increment `inline_agent_turn_missing_project_uuid_total` and report to Sentry at warning level — same pattern as existing required-field guards
   - Propagate `project_uuid` in Celery task headers at publish time (`before_task_publish`) so broker-wait metrics can be labeled even before the message dict is parsed in the worker

4. **`TurnLatencyRecorder`** in `router/tasks/latency_context.py`:
   - Required fields: `project_uuid`, `turn_id`, `task_id`
   - Records T1–T5 with `perf_counter` only
   - Single method `finish(status)` → observes all Prometheus histograms once, always with `project_uuid` label

5. **Prometheus metrics** (module-level, follow `nexus/logs/observers.py` pattern):
   ```
   inline_agent_broker_queue_wait_seconds     Histogram  label: project_uuid
   inline_agent_phase_duration_seconds        Histogram  labels: phase, project_uuid
   inline_agent_turn_duration_seconds         Histogram  labels: status, project_uuid
   inline_agent_cache_access_total            Counter    labels: cache_type, hit, project_uuid
   inline_agent_errors_total                  Counter    labels: phase, project_uuid
   inline_agent_turn_missing_project_uuid_total  Counter   (no project label — global guardrail)
   ```
   - **Per-project slicing:** Grafana uses a `project_uuid` template variable to filter P50/P95/P99 by project
   - **Cardinality:** `project_uuid` is acceptable (bounded tenant set); do **not** add `contact_urn` as a metric label

6. **Router timestamp:** add optional `received_at` to message payload or task kwargs at `router/main.py` for T-1 → T0a gap

7. **Grafana dashboard JSON** checked into repo (`contrib/grafana/` or docs path team prefers):
   - Required variable: **`project_uuid`** (dropdown / text, “All” uses `sum without (project_uuid)` or top-N recording rule)
   - Panels: phase breakdown and broker wait **filterable by project**

8. **Sentry enrichment only:** set tags in existing error handler from recorder (`project_uuid` required) — no new transactions

**Not in Phase 0:** Elastic APM changes, new observers that run network I/O, per-phase event bus.

**Success metrics**

- Dashboards live; 7-day baseline captured
- `broker_queue_wait` P95 visible separately from `agent_execution` P95
- **Per-project:** any project selectable in Grafana; P95 by phase available for incident investigation
- `inline_agent_turn_missing_project_uuid_total` = 0 in production (required field enforced)
- Instrumentation PR shows ≤ 2% change in P95 turn duration vs prior week

**Tasks**

- [ ] Remove workflow flag/branch
- [ ] Celery signal timestamps + header propagation (include `project_uuid` in headers)
- [ ] `TurnLatencyRecorder` with **required** `project_uuid` + wire into `invoke.py`
- [ ] Prometheus metrics module (`project_uuid` label) + scrape verified
- [ ] Grafana dashboard with **`project_uuid` variable**
- [ ] Propagate router `received_at`
- [ ] Validation test: task without `project_uuid` increments guardrail counter, skips histograms
- [ ] 24h before/after latency comparison runbook

---

### Phase 1 — Redis & Celery Infrastructure (CRITICAL — parallel with Phase 0 analysis)

**Goal:** Reduce T0b–T0c (`broker_queue_wait`) and in-task Redis contention without code that adds round-trips.

**Context:** Shared Redis likely hurts Celery dequeue more than Python processing time.

**Deliverables (infra — highest ROI, zero app latency cost)**

1. **Dedicated Redis for Celery broker** — separate instance/DB index from Django cache + app cache + Channels
2. **Document topology** — which apps share which Redis; target state diagram
3. **Redis monitoring** — Grafana panels: connected clients, CPU, memory, ops/sec, latency (`redis_exporter` or cloud metrics)
4. **Celery worker tuning review:**
   - `CELERY_WORKER_PREFETCH_MULTIPLIER = 1` (already set) — keep for fair `inline-agents` queue
   - `worker_disable_prefetch = True` in `celery.py` — verify interaction
   - Dedicated workers consuming **only** `inline-agents` queue
   - `INVOKE_AGENTS_RATE_LIMIT` vs worker count — ensure not artificial backlog

**Deliverables (app — must reduce or neutral Redis use)**

5. **Audit Redis calls in T1–T2** per turn (`RedisTaskManager`, `CacheService`) — count round-trips; pipeline where safe
6. **Ensure read replica** (`REDIS_READ_URL`) used for all read-only cache paths (already partially done)
7. **Evaluate** moving Django `CACHES` off Celery broker Redis (config change)

**Celery fit review (output doc, not immediate migration)**

8. Decision record: stay on Redis broker vs RabbitMQ — based on Phase 0 `broker_queue_wait` after dedicated broker trial

**Success metrics**

- `broker_queue_wait` P95 drops measurably after dedicated broker Redis (target set from baseline)
- In-task Redis round-trips per turn documented and not increased by later phases

**Tasks**

- [ ] Redis topology doc + dedicated Celery broker instance
- [ ] Grafana Redis + Celery queue panels
- [ ] Dedicated `inline-agents` workers verification
- [ ] Per-turn Redis call audit
- [ ] Broker decision record

---

### Phase 2 — Internal Structure (HIGH, zero-behavior-change)

**Goal:** Readable, testable `invoke.py` — same Celery task, no new broker hops.

**Deliverables**

- Extract `router/tasks/inline_agent/phases.py` (private functions)
- Optional: adopt workflow concat/revoke logic if metrics show T1 improvement
- Phase unit tests

**Constraint:** Refactor-only PRs must show ≤ 2% P95 regression.

---

### Phase 3 — Pre-Generation & Setup (HIGH)

**Goal:** Reduce T2–T3 when Phase 0 shows they matter **after** broker wait is understood.

**Deliverables**

1. Cache-first `PreGenerationService` (skip DB on composite hit)
2. Optimized `get_project_and_content_base_data` on miss
3. Supervisor cache + invalidation
4. Tool index from cached `team` (remove per-tool DB in adapter)
5. Module-level boto3 Lambda client

**Excluded unless proven neutral:** parallel thread pools in T2 (GIL + complexity — measure first)

**Success metrics**

- T2 P95 < 500 ms on cache hit
- T3 supervisor cache hit > 90%
- No increase in Redis round-trips per turn

---

### Phase 4 — Agent Execution & Tools (MEDIUM)

**Goal:** T4 tail latency and reliability.

**Deliverables**

- Lambda retry (transient only) + timeouts
- `inline_agent_tool_duration_seconds` histogram (observe in tool wrapper — one call per tool, acceptable)
- Formatter path counter (which merge path taken)
- Data lake serialization fix

Langfuse continues to cover LLM span detail; Prometheus covers aggregate T4.

---

### Phase 5 — Post-Generation & Capacity (MEDIUM)

**Goal:** T5 and worker capacity without new Celery tasks on shared broker.

**Deliverables**

- Confirm dispatch happens before heavy observers
- Autoscale workers on queue depth / `broker_queue_wait` P95
- Post-generation Celery bundle **only if** T5 > 10% of total **and** broker is isolated

---

### Phase 6 — Cleanup (LOW)

- Delete unused workflow entry files
- Remove Bedrock dead code in `invoke.py`
- Remove `WORKFLOW_ARCHITECTURE_PROJECTS` from settings

---

## Observability Ownership Matrix

| Concern | Tool | Phase |
|---------|------|-------|
| Broker wait, phase P95, cache hits, errors (by **`project_uuid`**) | **Prometheus + Grafana** | 0 |
| Queue depth, Redis health | **Grafana** (+ infra exporters) | 1 |
| Exceptions, phase tags on error | **Sentry** | 0 |
| LLM/tool spans | **Langfuse / Logfire** | existing |
| Web request tracing | Elastic APM (Django only) | no change |
| Celery worker APM | **Not planned** | — |

---

## Rollout: Continuous Delivery

```
Phase 0 + Phase 1 analysis in parallel
  → baseline Grafana
  → dedicated broker Redis (infra PR)
  → then Phase 3+ optimizations one per PR
Each PR: 24h P95 comparison, roll back if regression
```

---

## Open Questions (Answer from Phase 0/1 dashboards)

1. What % of `user_turn_total` P95 is `broker_queue_wait` vs `agent_execution`?
2. Does dedicated broker Redis clear the backlog?
3. How many Redis round-trips per turn in T1–T2 today?
4. Is `save_inline_message_async.delay` publishing to contended broker worth keeping async?
5. Cache hit rate per type at production QPS?

---

## Key Files

| Role | Path |
|------|------|
| Production entry | `router/tasks/invoke.py` |
| HTTP entry | `router/main.py` |
| Celery config | `nexus/celery.py`, `nexus/settings.py` |
| Redis clients | `router/utils/redis_clients.py` |
| Pre-generation | `router/services/pre_generation_service.py` |
| Cache | `router/services/cache_service.py` |
| Pending tasks | `router/tasks/redis_task_manager.py` |
| Prometheus patterns | `nexus/logs/observers.py`, `django_prometheus` |
| Backend | `inline_agents/backends/openai/backend.py` |

---

## Summary

This plan **builds on** prior caching and service extraction work, focuses on **`start_inline_agents` only**, and treats **shared Redis / Celery dequeue** as the leading hypothesis for platform latency — not just in-task Python time.

1. **Map the full Celery lifecycle** (publish → receive → prerun → phases → postrun)  
2. **Prometheus + Grafana first** — structured latency from day one, zero hot-path network cost  
3. **Isolate Celery broker Redis** — infra win without code overhead  
4. **Sentry for errors; Langfuse for LLM; skip new Elastic APM in workers**  
5. **Hard rule: no change that increases latency** — validate every PR against P95  
6. **Question Celery splits** — more tasks on shared Redis likely hurt; dedicated broker first  

Each phase has clear deliverables and success metrics for task creation and prioritization by measured ROI.
