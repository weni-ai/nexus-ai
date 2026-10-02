# Quickstart: Agent Versioning — Production Latency & Cache Isolation

Validation guide for cache isolation and latency gates. Assumes sibling versioning has `ProjectRelease`, `active_release`, and publish API available (phase 1+).

**References**: [data-model.md](./data-model.md), [contracts/runtime-config-service.md](./contracts/runtime-config-service.md), [design doc](../../nexus/staticfiles/docs/versioning/agent_versioning_latency_plan.md)

---

## Prerequisites

```bash
export PROJECT_UUID="<project-with-published-release>"
export REDIS_URL="<redis>"
# GrowthBook / feature flag service configured for local or staging
```

Capture **phase-0 baseline** before enabling read path:

```bash
# Query pre_generation p50/p99 for control projects (analytics dashboard or DB)
# Document baseline window start date
```

---

## 1. Live cache hit — zero DB on production path

**Goal**: SC-001, FR-001, FR-002

```bash
# Warm live cache (publish or manual warm)
python manage.py shell -c "
from router.services.runtime_config_service import RuntimeConfigService
RuntimeConfigService().warm_live('$PROJECT_UUID')
"

# Verify key exists
redis-cli GET "project:${PROJECT_UUID}:runtime:live" | head -c 200

# Send production message (preview=false) via staging invoke or integration test
pytest router/tasks/tests/test_runtime_config_live.py -q -k cache_hit_no_db
```

**Expected**
- Single Redis GET in traces/logs
- No Postgres queries for project config during `pre_generation`
- `runtime_config.cache_hit=true`

---

## 2. Draft edit does not invalidate live cache

**Goal**: SC-004, FR-003, User Story 2

```bash
# Record live key TTL / payload hash before edit
redis-cli GET "project:${PROJECT_UUID}:runtime:live" | shasum

# Save draft instruction via editor API (staging)
# ... PATCH draft content ...

# Confirm live key unchanged
redis-cli GET "project:${PROJECT_UUID}:runtime:live" | shasum

# Concurrent production messages: pre_generation p50 unchanged vs control
pytest router/tasks/tests/test_runtime_config_isolation.py -q
```

**Expected**
- Live key hash identical after draft save
- Preview key invalidated or rebuilt on next preview message only

---

## 3. Publish warms live cache off hot path

**Goal**: SC-007, FR-005, User Story 3

```bash
# Publish release via admin API
# ... POST publish ...

# Immediately check live key references new release_uuid
python manage.py shell -c "
import json
from django.core.cache import cache
blob = cache.get('project:${PROJECT_UUID}:runtime:live')
data = json.loads(blob) if isinstance(blob, str) else blob
print(data.get('release_uuid'))
"

# Next production message: cache_hit=true with new release_uuid
```

**Expected**
- Publish response completes without blocking message workers
- Live blob updated before or immediately after publish TX

---

## 4. Cache miss rebuild bounded

**Goal**: SC-006

```bash
# Delete live key to simulate miss
redis-cli DEL "project:${PROJECT_UUID}:runtime:live"

# Trigger production message; capture build_ms in logs
pytest router/services/tests/test_runtime_config_service.py -q -k miss_rebuild_under_budget
```

**Expected (staging)**
- `runtime_config.build_ms` p99 < 500 ms at typical team size
- Single release-graph Postgres query plan (not 6+ scattered fetches)

---

## 5. Feature flag fallback

**Goal**: FR-007, User Story 4

```bash
# Disable runtime_config_live_read for project
# Send production message

# Expected: PreGenerationService path, no error

# Re-enable flag; verify runtime path restored
pytest router/tasks/tests/test_runtime_config_feature_flag.py -q
```

**Expected**
- Instant rollback to legacy path without migration undo

---

## 6. Schema validation

```bash
# Requires check-jsonschema (optional CI step)
check-jsonschema \
  --schemafile nexus/staticfiles/docs/versioning/schemas/runtime_config.v1.schema.json \
  nexus/staticfiles/docs/versioning/schemas/runtime_config.v1.example.live.json
```

---

## 7. Regression gate (phase 3 rollout)

After enabling `runtime_config_live_read` for canary projects:

1. Run 7-day comparison: canary vs control `pre_generation` p50/p99
2. Verify SC-002: p50 ≤ baseline
3. Verify SC-003: p99 ≤ baseline × 1.10
4. Verify SC-005: live cache miss rate < 1%

**Fail action**: disable feature flag for canary; investigate `blob_bytes` and `build_ms` outliers.

---

## Test suite (target)

```bash
pytest router/services/tests/test_runtime_config_service.py \
       router/tasks/tests/test_runtime_config_*.py \
       -q
```

Tests MUST include:
- `from_runtime_config` invoke kwargs parity vs `from_pre_generation_data`
- Draft edit isolation (live key stable)
- Preview path uses preview key only
- Metrics tags emitted on hit/miss
