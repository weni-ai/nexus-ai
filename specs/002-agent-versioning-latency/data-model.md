# Data Model: Agent Versioning — Production Latency & Cache Isolation

This feature adds **cache-layer entities and metrics**; persistent release models are owned by the sibling agent versioning spec. References below describe fields consumed by `resolve_release()`.

## Cache entities (Redis)

### LiveRuntimeSnapshot

| Attribute | Type | Notes |
|-----------|------|-------|
| redis_key | string | `project:{project_uuid}:runtime:live` |
| payload | JSON object | Conforms to `runtime_config.v1.schema.json` |
| ttl_seconds | int | 86400 (24h), aligned with `CacheService` |
| built_at | ISO datetime | Envelope field; rebuild trigger audit |
| release_uuid | UUID | Source `ProjectRelease` for deployed config |
| schema_version | int | Envelope format (default 1) |

**Rules**
- Written on: publish warm, rollback warm, cache miss, async catalog fan-out.
- Never invalidated by draft-only editor saves.
- Production read: single GET; no Postgres on hit.

---

### PreviewRuntimeSnapshot

| Attribute | Type | Notes |
|-----------|------|-------|
| redis_key | string | `project:{project_uuid}:runtime:preview:{user_email}` |
| payload | JSON object | Same schema; may include draft release |
| ttl_seconds | int | 86400 default; may shorten in implementation |
| preview_user | string | Normalized email |
| release_uuid | UUID | Draft or selected superseded release |

**Rules**
- Invalidated on draft instruction/KB/agent/formatter edits for that project.
- Must not replace or delete live snapshot.
- Used only when `preview=True` in `start_inline_agents`.

---

### PreviewReleaseSelection (optional Redis key)

| Attribute | Type | Notes |
|-----------|------|-------|
| redis_key | string | `project:{project_uuid}:preview:selection:{user_email}` |
| release_uuid | UUID | Explicit preview target (draft default) |

---

## Service entities (application layer)

### RuntimeConfigService

| Operation | Input | Output | Hot path? |
|-----------|-------|--------|-----------|
| `get_live(project_uuid)` | project UUID | `CachedProjectData` | **Yes** (production) |
| `get_preview(project_uuid, user_email)` | UUID + email | `CachedProjectData` | Preview only |
| `warm_live(project_uuid)` | UUID | void | No (publish/rollback) |
| `invalidate_preview(project_uuid, user_email=None)` | UUID, optional user | void | No (draft edit) |
| `invalidate_live(project_uuid)` | UUID | void | No (publish/catalog) |

---

### ReleaseResolver (`resolve_release`)

| Input | Output |
|-------|--------|
| `ProjectRelease` instance + `runtime_mode` (`live` \| `preview`) | Dict matching RuntimeConfig v1 |

**Prefetch**: `team_members`, linked `Version` rows, project FK.

**Validation**
- Live mode requires `release.status == deployed` and matches `Project.active_release`.
- Preview mode allows `status == draft`.
- Official agents: live global lookup at build (UC-01); custom agents from release `Version` snapshot.

---

## Postgres entities (dependency — sibling spec)

Not created by this feature's migrations; consumed on cache miss:

| Entity | Role in latency path |
|--------|----------------------|
| `Project.active_release` | Pointer for live miss rebuild |
| `ProjectRelease` | Denormalized snapshot JSON + team members |
| `ReleaseTeamMember` | Team roster in blob |
| `Version` | Custom agent snapshot fields |

See `nexus/staticfiles/docs/versioning/agent_versioning_models.md`.

---

## Feature flag entity

| Field | Value |
|-------|-------|
| key | `runtime_config_live_read` (proposed) |
| scope | per `project_uuid` via GrowthBook attributes |
| when active | `start_inline_agents` uses `RuntimeConfigService.get_live` |
| when inactive | `PreGenerationService.fetch_pre_generation_data` (legacy) |

---

## Observability records

### RuntimeConfigBuildMetric (log/metric event, not DB)

| Field | Type | Purpose |
|-------|------|---------|
| project_uuid | string | Dimension |
| cache_layer | enum | `live` \| `preview` |
| cache_hit | bool | Hit ratio (SC-005) |
| build_duration_ms | float | Miss path (SC-006) |
| blob_bytes | int | Size regression |
| release_uuid | UUID | Traceability |

Emitted inside `PHASE_PRE_GENERATION` scope; persisted via existing turn latency pipeline where applicable.

---

## State transitions

```text
[no live cache] --publish/warm/miss--> LiveRuntimeSnapshot populated
LiveRuntimeSnapshot --draft edit--> unchanged (isolation)
LiveRuntimeSnapshot --publish/rollback--> replaced (new warm)
LiveRuntimeSnapshot --TTL expiry--> miss --> rebuild from active_release

PreviewRuntimeSnapshot --draft edit--> invalidated --> rebuilt on next preview message
```

---

## Invalidation matrix (latency-critical)

| Event | Live key | Preview key |
|-------|----------|-------------|
| Draft instruction/KB/agent edit | **No op** | Invalidate + rebuild |
| Publish | Replace (warm) | Optional invalidate |
| Rollback | Replace (warm) | Optional invalidate |
| Official catalog update | Async invalidate + warm | Async optional |
| Guardrails PATCH (interim) | Invalidate + warm | Invalidate + warm |

**Never**: rebuild live from live `ContentBaseInstruction` on draft edit.
