# Contract: RuntimeConfigService (internal)

**Version**: 1.0  
**Consumers**: `router/tasks/invoke.py` (`start_inline_agents`)  
**Producers**: `router/services/runtime_config_service.py`, publish/rollback handlers

## Purpose

Define the internal interface for loading inline agent configuration with latency guarantees from [spec.md](../spec.md).

---

## Redis keys

| Key pattern | TTL | Used when |
|-------------|-----|-----------|
| `project:{project_uuid}:runtime:live` | 86400s | `preview=False` |
| `project:{project_uuid}:runtime:preview:{user_email}` | 86400s | `preview=True` |
| `project:{project_uuid}:preview:selection:{user_email}` | 86400s | Optional explicit release selection |

`user_email` MUST be normalized (lowercase, trimmed).

---

## Payload schema

- **Schema file**: `nexus/staticfiles/docs/versioning/schemas/runtime_config.v1.schema.json`
- **Examples**: `runtime_config.v1.example.live.json`, `runtime_config.v1.example.preview.json`

Minimum envelope fields:

```json
{
  "schema_version": 1,
  "project_uuid": "uuid",
  "agents_backend": "openai|bedrock|...",
  "release_uuid": "uuid",
  "release_status": "deployed|draft",
  "built_at": "ISO-8601",
  "project": {},
  "content_base": {},
  "instructions": [],
  "team": [],
  "guardrails": {},
  "inline_agent_config": null,
  "agent_data": null,
  "knowledge_base": { "version": "1", "include_draft": false }
}
```

---

## Service methods

### `get_live(project_uuid: str) -> CachedProjectData`

**Preconditions**
- `preview=False` invocation path only.

**Behavior**
1. `GET` `project:{project_uuid}:runtime:live`
2. On hit: deserialize → `CachedProjectData.from_runtime_config(payload)`; emit `cache_hit=true`
3. On miss: load `Project.active_release`; `resolve_release(release, runtime_mode="live")`; `SET` live key; emit `cache_hit=false`, `build_duration_ms`

**Postconditions**
- Steady-state: zero Postgres queries on hit (FR-002).
- Returned `CachedProjectData.get_invoke_kwargs(team)` MUST match legacy path for same release content.

**Errors**
- No `active_release`: fail with explicit error (project not publishable).
- Invalid blob schema: treat as miss, rebuild once; log corruption.

---

### `get_preview(project_uuid: str, user_email: str) -> CachedProjectData`

**Behavior**
1. Resolve selected release (draft default or `preview:selection` key).
2. `GET` preview key; on miss `resolve_release(..., runtime_mode="preview")` and `SET`.

**Postconditions**
- MUST NOT read or write live key.

---

### `warm_live(project_uuid: str) -> None`

**Behavior**
- Build from `Project.active_release` and `SET` live key.

**Called from**
- Publish transaction (post-commit) or rollback handler — not from message worker hot path unless miss.

---

### `invalidate_preview(project_uuid: str, user_email: str | None = None) -> None`

**Behavior**
- Delete matching preview key(s); never delete live key.

**Called from**
- Draft content save signals / viewsets.

---

## Feature flag

| Key | When true |
|-----|-----------|
| `runtime_config_live_read` | `get_live` used in `start_inline_agents` |
| false / absent | `PreGenerationService.fetch_pre_generation_data` |

---

## Adapter contract: `CachedProjectData.from_runtime_config`

**Input**: RuntimeConfig v1 dict  
**Output**: `CachedProjectData` with same fields as `from_pre_generation_data`

**Invariant**: For equivalent source data, `get_invoke_kwargs(team=payload["team"])` equals legacy adapter output (contract test required).

---

## Metrics contract

Each `get_live` / `get_preview` call SHOULD emit:

| Metric / log field | Type | SLO linkage |
|--------------------|------|-------------|
| `runtime_config.cache_hit` | bool | SC-005 |
| `runtime_config.build_ms` | float | SC-006 |
| `runtime_config.blob_bytes` | int | monitoring |
| `runtime_config.layer` | `live` \| `preview` | — |

Recorded within existing `pre_generation` phase timing (FR-010).

---

## Non-goals (v1)

- Public REST API for runtime blobs
- Per-message `session_epoch` check
- S3 read on this path
- Synchronous multi-project fan-out on catalog update
