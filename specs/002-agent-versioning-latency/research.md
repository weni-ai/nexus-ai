# Research: Agent Versioning — Production Latency & Cache Isolation

## R1 — Single blob vs granular Redis keys

**Decision**: One `project:{uuid}:runtime:live` JSON blob per project replaces up to 7 granular keys for production reads.

**Rationale**: Today `PreGenerationService.fetch_pre_generation_data` may issue sequential GETs for `data`, `content_base`, `instructions`, `team:{backend}`, `guardrails_v2`, `inline_agent_config`, `agent`. Consolidation reduces network round-trips and guarantees atomic config view per release. Schema defined in `runtime_config.v1.schema.json`.

**Alternatives considered**:
- **Keep granular keys with release version suffix** — more invalidation complexity; still multiple GETs on hot path.
- **Redis MGET of legacy keys** — does not fix draft-isolation leak; still ties production to live table rebuilds.

---

## R2 — Cache miss source: release graph vs live editor tables

**Decision**: On live cache miss, rebuild exclusively from `Project.active_release` via `resolve_release()`, never from live `ContentBaseInstruction` / `IntegratedAgent`.

**Rationale**: Spec FR-006 and FR-003 require draft isolation and correct published behavior. Current miss path uses `get_project_and_content_base_data` + `ORMTeamRepository.get_team()` against live rows — acceptable pre-versioning but wrong post-versioning.

**Alternatives considered**:
- **Hybrid: live tables on miss** — simpler migration but exposes unpublished edits if draft invalidation regresses.
- **S3 published SoT (architect model)** — rejected for release SoT; adds cold-path latency.

---

## R3 — Draft edit invalidation scope

**Decision**: Draft saves invalidate and rebuild `runtime:preview:{user}` (or `runtime:preview:*` pattern) only; **never** touch `runtime:live`.

**Rationale**: Root cause of today's production latency churn: inline KB/instruction edits trigger `CacheService` invalidation for `:instructions` and related keys used by production. Explicit matrix in runtime config doc.

**Touchpoints to audit**:
- `InlineContentBaseTextViewset._reindex_inline_content_base_text`
- Any `cache_service.invalidate_*` on instruction/agent save paths
- Guardrails PATCH (may still invalidate live until snapshotted on release — document as exception)

---

## R4 — Publish / rollback warm-up timing

**Decision**: Eager `runtime:live` SET synchronously in publish/rollback transaction **or** immediately after commit via same request handler; never defer to first customer message if avoidable.

**Rationale**: SC-005 targets < 1% miss rate; first message after publish should hit warm cache. Admin path latency is not customer SLO.

**Alternatives considered**:
- **Lazy warm on first message** — acceptable for rollback only if miss rate gate still met; prefer eager for publish.
- **Background Celery warm only** — race window where customers see stale live blob.

---

## R5 — Feature flag and fallback path

**Decision**: GrowthBook flag (e.g. `runtime_config_live_read`) per project; when off, `start_inline_agents` uses existing `PreGenerationService`.

**Rationale**: Project already uses `weni-feature-flags` / GrowthBook. Enables phase 2–3 rollout and instant rollback without schema revert (spec assumption).

**Alternatives considered**:
- **Django settings boolean** — no per-project gradual rollout.
- **Dual-write only without read switch** — does not validate latency until read cutover.

---

## R6 — Preview cache key and identity

**Decision**: `project:{uuid}:runtime:preview:{user_email}` scoped to authenticated editor email (normalized lowercase); selection of draft vs superseded release via separate `preview:selection:{user}` key or embedded in preview blob metadata.

**Rationale**: Spec FR-004; preview is not production SLO path; higher miss rate acceptable.

---

## R7 — Official agent catalog updates (UC-01)

**Decision**: Async batch job invalidates + warms `runtime:live` for affected projects; no synchronous fan-out in `start_inline_agents`.

**Rationale**: Spec FR-009; global catalog change may touch many projects; must not add per-message latency.

---

## R8 — Observability and regression gates

**Decision**: Reuse `PHASE_PRE_GENERATION` in `TurnLatencyRecorder`; add structured log/metric tags: `runtime_config.cache_hit`, `runtime_config.build_ms`, `runtime_config.blob_bytes`. Compare flagged vs control projects for 7 days after phase 3.

**Rationale**: Spec FR-008, FR-010; existing analytics pipeline in `nexus/analytics/latency_phases.py`.

**Alternatives considered**:
- **New phase name** — breaks baseline comparison.
- **session_epoch per message** — rejected for v1 (config freshness via publish warm).

---

## R9 — session_epoch on rollback

**Decision**: **Do not** bump `session_epoch` on rollback for v1 latency spec. Rollback = rebuild `runtime:live` only.

**Rationale**: Conversation history is not rewritten; each message already reads fresh live blob. `session_epoch` was demoted in architecture discussion — optional future context trim only.

**Note**: Update invalidation matrix in `agent_versioning_runtime_config.md` to remove `session_epoch` on rollback (doc drift).

---

## R10 — Guardrails on live blob

**Decision (interim)**: Resolve guardrails at `resolve_release()` build time via `ProjectGuardrailsConfigUseCase.get_runtime_config_as_dict` until guardrails are snapshotted on `ProjectRelease`.

**Rationale**: Matches today's behavior; guardrails PATCH may invalidate live cache (documented exception). Future: snapshot on publish to tighten isolation.

---

## Open items (non-blocking for plan)

| Item | Owner | Notes |
|------|-------|-------|
| Exact GrowthBook flag key name | Implementation | Coordinate with platform flags naming |
| Guardrails snapshot on release | Sibling versioning spec | Reduces live invalidation exception |
| UC-06 agent hard delete | Team discussion | Affects rebuild error handling on miss |
