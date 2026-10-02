# Feature Specification: Agent Versioning — Production Latency & Cache Isolation

**Feature Branch**: `002-agent-versioning-latency`

**Created**: 2026-08-24

**Status**: Draft

**Input**: Latency plan for agent versioning (draft → preview → publish → live with rollback). Production customer messages must stay cache-first with no added latency; draft edits must not affect live traffic.

**Scope**: Performance and isolation requirements for the agent versioning feature when inline agents handle customer messages. Covers production message path, preview path, publish/rollback warm-up, cache invalidation rules, rollout phases, and observability gates. Depends on the broader versioning architecture (releases, runtime config blob) documented in `nexus/staticfiles/docs/versioning/`.

**Out of scope**: Versioning data model design, UI for publish/rollback, KB search latency, LLM inference time, implementation of `ProjectRelease` entities (covered by sibling versioning specs).

## Clarifications

### Session 2026-08-24

- Q: Must production add database reads per message after versioning? → A: **No** on the steady-state (cache hit) path.
- Q: Do draft instruction/KB edits affect live customer traffic latency? → A: **No** — they must only refresh preview configuration.
- Q: Is preview held to the same latency SLO as production? → A: **No** — preview may rebuild more often; production SLO is strict.
- Q: Per-message session versioning checks on hot path? → A: **Out of scope for v1** — config freshness is ensured at publish/rollback and cache warm-up, not per turn.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Customer messages stay fast in production (Priority: P1)

As an end customer chatting with a published agent configuration, I need my messages to be processed without noticeable delay from configuration loading, so conversations feel as responsive as today.

**Why this priority**: Production latency directly affects customer experience and platform trust. Versioning is only acceptable if it does not slow the live message path.

**Independent Test**: Send production messages (`preview=false`) against a project with a published release and warm cache; compare configuration-load portion of turn time to pre-versioning baseline. Steady-state path must not add persistent database reads.

**Acceptance Scenarios**:

1. **Given** a project with a published live configuration and warm cache, **When** a customer sends a message, **Then** the system loads all inline agent configuration from a single cached snapshot without querying the database for project config.
2. **Given** steady-state production traffic, **When** measuring configuration load time over 7 days, **Then** median (p50) configuration load time is less than or equal to the pre-versioning baseline.
3. **Given** steady-state production traffic, **When** measuring configuration load time over 7 days, **Then** p99 configuration load time is at most 10% above the pre-versioning baseline.
4. **Given** a warm live cache, **When** a customer message is processed, **Then** configuration is retrieved in one cache read operation (not multiple fragmented reads).

---

### User Story 2 - Editors can draft without slowing live traffic (Priority: P1)

As a project editor working on draft instructions, knowledge base content, or agents, I need my changes to affect preview only, so live customers never pay latency cost for my unpublished work.

**Why this priority**: Today, draft-like edits can invalidate production caches and rebuild from live database state — both a correctness and latency problem once versioning exists.

**Independent Test**: Edit draft content while production messages run concurrently; production configuration-load metrics must remain unchanged; preview messages must reflect draft after preview cache rebuild.

**Acceptance Scenarios**:

1. **Given** an editor saves draft instruction or KB changes, **When** a live customer message is processed at the same time, **Then** live configuration cache is not invalidated or rebuilt.
2. **Given** draft edits, **When** only preview cache is refreshed, **Then** production message configuration-load time shows zero measurable regression versus control.
3. **Given** an editor opens preview, **When** they send a test message, **Then** the system uses preview-specific cached configuration tied to the editor context.
4. **Given** repeated draft saves, **When** production traffic continues, **Then** live cache miss rate and configuration-load p99 do not increase due to editor activity.

---

### User Story 3 - Publish and rollback update live config off the message path (Priority: P2)

As a project admin publishing or rolling back a release, I need live configuration to update reliably without blocking or slowing in-flight customer messages.

**Why this priority**: Publish/rollback are infrequent but must not create latency spikes on the customer hot path; the next message after warm-up should see the new live snapshot cheaply.

**Independent Test**: Publish or rollback while messages are in flight; admin action completes without synchronously blocking message workers; subsequent production messages read updated live cache in one read.

**Acceptance Scenarios**:

1. **Given** an admin publishes a release, **When** the operation completes, **Then** live configuration cache is rebuilt or warmed before or immediately after the publish transaction, not during each customer message.
2. **Given** an admin rolls back to a prior release, **When** the operation completes, **Then** live configuration cache reflects the rolled-back release on the next production message.
3. **Given** publish or rollback in progress, **When** customer messages are processed, **Then** message handling is not blocked waiting for admin operations.
4. **Given** a publish completes, **When** the next customer message arrives, **Then** it uses the newly published configuration via a single cache read (after warm-up).

---

### User Story 4 - Safe rollout with measurable regression gates (Priority: P2)

As the platform team rolling out versioning, I need phased enablement and automatic comparison to baseline metrics so we can halt rollout if production latency regresses.

**Why this priority**: Consolidating cache keys changes behavior; feature flags and regression gates de-risk production impact.

**Independent Test**: Enable versioning read path for a subset of projects; compare configuration-load histograms to control group; roll back feature flag if gates fail.

**Acceptance Scenarios**:

1. **Given** phase-0 baseline captured, **When** phase-3 (live snapshot reads) is enabled for flagged projects, **Then** a 7-day comparison report shows p50/p99 configuration load within defined gates versus baseline.
2. **Given** regression beyond gates, **When** operators disable the feature flag, **Then** production reverts to the legacy configuration load path without data migration rollback.
3. **Given** cache miss on cold start or TTL expiry, **When** live snapshot is rebuilt, **Then** rebuild completes within 500 ms p99 at typical project team size in staging load tests.
4. **Given** steady state after publish warm-up, **When** measuring cache effectiveness, **Then** fewer than 1% of production turns incur a live configuration cache miss.

---

### Edge Cases

- What happens when live cache expires during traffic? System rebuilds from the active published release once, caches the result, and continues; occasional miss is acceptable if rare and bounded.
- What happens when publish fails mid-transaction? Live cache remains on the last successful published release; customers are not exposed to partial draft state.
- What happens when global official agent catalog updates? Affected projects refresh live cache asynchronously; no synchronous fan-out during a single customer message.
- What happens when preview cache is cold after many draft edits? Preview messages may load slower; production path is unaffected.
- What happens on platform cold start with empty cache? First production message pays one-time rebuild cost; subsequent messages hit cache.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST load all inline agent configuration for production messages from a single consolidated live cached snapshot when cache is warm.
- **FR-002**: System MUST NOT perform database reads for project inline configuration on the production steady-state (cache hit) message path.
- **FR-003**: System MUST NOT invalidate or rebuild live configuration cache when draft-only content (instructions, KB, agents, formatter, personality) is edited.
- **FR-004**: System MUST maintain a separate preview configuration cache per editor context for preview messages.
- **FR-005**: System MUST rebuild or warm live configuration cache on publish and rollback, outside the per-message customer hot path.
- **FR-006**: System MUST resolve production configuration from the active published release on cache miss, not from live editable tables used by the draft editor.
- **FR-007**: System MUST support phased rollout via feature flag with fallback to the legacy configuration load path.
- **FR-008**: System MUST record configuration cache hit/miss, rebuild duration, and snapshot size for observability and regression detection.
- **FR-009**: System MUST apply global catalog updates (official agents, manager catalog) via asynchronous cache invalidation and warm-up, not synchronous per-message fan-out.
- **FR-010**: System MUST preserve existing turn-level latency phase reporting for configuration load so before/after comparisons remain valid.

### Key Entities

- **Live runtime snapshot**: Immutable cached bundle of all inline agent configuration served to production messages for a project; keyed by project and TTL (~24h); rebuilt on publish, rollback, miss, or async catalog update.
- **Preview runtime snapshot**: Cached bundle for draft/preview messages, scoped to project and editor identity; rebuilt on draft edits; must not replace live snapshot.
- **Active published release**: The release pointer determining what live snapshot contains after publish or rollback; source of truth on cache miss only.
- **Configuration load phase**: Measured portion of a message turn spent fetching inline agent configuration before agent execution begins.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Under steady-state production traffic with warm cache, 100% of configuration loads complete without database access for project inline config.
- **SC-002**: Median (p50) configuration load time for production messages after full rollout is less than or equal to the pre-versioning baseline measured over the same traffic profile.
- **SC-003**: p99 configuration load time for production messages after full rollout is at most 10% above the pre-versioning baseline.
- **SC-004**: Draft or preview edits cause zero measurable increase in production configuration load p50/p99 when compared to a control window of concurrent live traffic.
- **SC-005**: Fewer than 1% of production message turns incur a live configuration cache miss under steady state (post warm-up, 24h TTL, publish-triggered warm).
- **SC-006**: Live configuration cache rebuild on miss completes within 500 ms p99 for typical team size in staging load tests.
- **SC-007**: Publish and rollback operations do not block customer message processing; updated live configuration is visible on the next message after warm-up completes.
- **SC-008**: Preview messages reflect draft changes after preview cache rebuild without requiring stricter latency targets than production.

## Assumptions

- Agent versioning architecture (draft/preview/publish/rollback, release records) is implemented or specified separately; this spec defines latency and cache isolation constraints on top of it.
- Pre-versioning baseline metrics for configuration load (`pre_generation` phase) are captured before phased rollout begins.
- Typical project team size and configuration blob size remain within ranges observed in current production; oversized blobs are monitored via snapshot size metrics.
- Knowledge base retrieval (RAG search) remains outside configuration load phase, as today.
- LLM inference latency is unchanged by this feature and is out of scope for acceptance gates.
- 24-hour cache TTL for live snapshots matches current configuration cache TTL behavior unless explicitly changed in a separate decision.
- Feature flag controls read path only; rollback of rollout does not require undoing release schema migrations.

## Dependencies

- Broader agent versioning feature: release lifecycle, `active_release` / `draft_release` pointers, runtime config schema v1.
- Existing inline agent message pipeline and turn latency instrumentation.
- Design reference: `nexus/staticfiles/docs/versioning/agent_versioning_latency_plan.md` (technical latency plan aligned with this spec).
