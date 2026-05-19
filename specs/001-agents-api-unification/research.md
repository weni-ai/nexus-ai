# Research: Unified Agents API

## R1 — Pagination style for official v1 and project catalog

**Decision**: Use **offset-based** pagination (`page`, `page_size`) with **`page_size` capped at 20**
per FR-009. Default `page=1`.

**Rationale**: Matches existing DRF patterns in the codebase; simplest for cache keys and OpenAPI
documentation. Cursor-based can be a follow-up if deep pagination performance requires it.

**Alternatives considered**: Cursor (`next_token`) — better for huge catalogs; rejected for v1 due
to implementation cost and current scale assumptions.

---

## R2 — Cache backend and invalidation

**Decision**: Use Django’s **`default` cache** (`django.core.cache.cache`) for **`GET /api/v1/official/agents`**
response fragments or full JSON blobs per cache key. Invalidate on existing **`notify_async`**
events already fired from assign/unassign and agent push (`cache_invalidation:team`,
`cache_invalidation:project`) plus any **admin-side** saves that change official templates (add
signal handler if gap found in implementation).

**Rationale**: Reuses infrastructure; aligns with current async invalidation pattern.

**Alternatives considered**: Redis-only custom client — unnecessary if default cache is Redis in
target environments (verify deployment settings).

---

## R3 — `available_systems` URL

**Decision**: **`GET /api/v1/official/available-systems`** with same **`AUTHENTICATION_CLASSES`** and
**`CombinedExternalProjectPermission`** as `OfficialAgentsV1` unless planning discovers a stricter
loosening requirement.

**Rationale**: Keeps official read APIs under one versioned prefix; easy to document and cache
independently.

**Alternatives considered**: `/api/agents/available-systems` — rejected to avoid mixing unversioned
and v1 official surfaces.

---

## R4 — Option A payload size

**Decision**: Proceed with **full detail fields per row** on official v1 list; monitor response
size in staging with worst-case official groups.

**Rationale**: Explicit product acceptance that 20 × (group + MCP + credentials) remains
comfortable.

**Alternatives considered**: Optional `?verbose=0` — rejected (strict unification).

---

## R5 — FR-013 enforcement surface

**Decision**: Centralize in **`agent_creation_policy.user_may_create_agents(email)`**; call from
**`PushAgents`** and audit any other entry point that creates `Agent` rows for projects.

**Rationale**: Matches constitution single-responsibility and avoids duplicated allow-list checks.

**Alternatives considered**: Middleware — too broad.

---

## R6 — C11 exact email match

**Decision**: Normalize with **`.strip().casefold()`** (or email policy canonical form) on both
sides; membership via **`in` on a set** of normalized allow-list entries, **not** substring on user
email.

**Rationale**: Eliminates false positives (e.g. `admin@corp.com` matching `notadmin@corp.com`).

**Alternatives considered**: Regex boundaries — unnecessary if full-string equality after normalize.
