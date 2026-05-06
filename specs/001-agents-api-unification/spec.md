# Feature Specification: Unified Agents API

**Feature Branch**: `001-agents-api-unification`
**Created**: 2026-04-30
**Status**: Draft
**Input**: User description: "Refactor the Agents API to unify Official and Custom agents; merge listing and detail into one payload shape; remove legacy official catalog and legacy/new assign split; isolate available systems; tighten team assigned and my-agents responses; pagination and admin category slug alignment."

## Clarifications

### Session 2026-04-30

- Q: How should official agents v1 read endpoints (`GET /api/v1/official/agents` vs `GET /api/v1/official/agents/{identifier}`) evolve? → A: Unify to **one** `GET /api/v1/official/agents` surface that returns **all** data needed for agents in a group; implement **caching** and **pagination** on that surface; the **per-identifier detail route is removed**.
- Q: What identifier should traces use for agents? → A: Traces MUST use the agent **`name`** (not `slug`); document this for operators and integrators (API roster identifiers may still use `slug` where this spec already requires it).
- Q: Who may create custom or official agents? → A: Only principals whose **email** appears in the **`OFFICIAL_SMART_AGENT_EDITORS`** environment-defined list may create agents (**custom or official**); all others are denied.
- Q: Should `model` (and related keys) be dropped from the unified “novo retorno” payload? → A: **Retain `model`** in the unified payload for this release; do **not** remove it yet.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Browse and inspect agents with one catalog shape (Priority: P1)

Administrators and integrators browse the project agent catalog and open a specific agent without
learning two different response shapes. Official agents and custom agents differ only by an
explicit official flag on each record, not by divergent fields or nested structures.

**Why this priority**: This is the core product contract; every downstream screen and integration
depends on a single mental model.

**Independent Test**: Call the unified project catalog listing and confirm each row matches the
agreed per-group “novo retorno” item rules; where a separate detail route still exists in
product, compare one row to that detail item—otherwise confirm a single read surface returns
complete group payload without a second fetch shape.

**Acceptance Scenarios**:

1. **Given** a project with both official and custom agents, **When** a client requests the
   unified listing, **Then** every group includes an official-or-custom indicator as the sole
   discriminator and there is no separate legacy official-only catalog route for that project.
2. **Given** any agent visible in the unified project listing, **When** a client inspects that
   agent through the **same** structural rules as the listing row (single shape or merged list
   contract per release notes), **Then** fields and nesting match the listing item and the
   official flag is consistent.
3. **Given** a client that previously relied on the removed official-only catalog, **When** they
   follow migration guidance to the unified listing, **Then** they can still enumerate all
   official agents by filtering on the official flag.

---

### User Story 2 - Assign and unassign through one flow (Priority: P2)

Users assign or unassign agents to the project through a single pair of operations with no
separate “legacy” versus “new” paths.

**Why this priority**: Duplicate routes create inconsistent behavior and support load.

**Independent Test**: Exercise assign and unassign once each and confirm there is no alternate
route label or behavior split documented for the same action.

**Acceptance Scenarios**:

1. **Given** an agent eligible for assignment, **When** a user assigns it through the unified
   assign operation, **Then** the assignment succeeds without requiring a different URL or
   payload shape than other agents of the other category.
2. **Given** an assigned agent, **When** a user unassigns through the unified unassign
   operation, **Then** the agent is removed from the project roster through the same contract as
   assignment used historically for “new” flows only.

---

### User Story 3 - Listing quality: pagination and category alignment (Priority: P3)

Operators scanning long catalogs see manageable pages, and categories shown to end users align
with the slugs used in the admin experience so filters and deep links stay consistent.

**Why this priority**: Prevents UX drift and broken filters at scale.

**Independent Test**: Request successive listing pages and compare category identifiers to admin
panel slug references for the same project configuration.

**Acceptance Scenarios**:

1. **Given** more than twenty agent groups for a project, **When** a client requests the first
   page of the unified listing, **Then** at most twenty groups are returned and navigation
   metadata indicates how to fetch additional pages.
2. **Given** admin-managed categories for a project, **When** a client reads category slugs from
   the listing, **Then** those slugs match the admin panel’s category slug set for that project.

---

### User Story 4 - Team roster and personal agents match the catalog contract (Priority: P3)

Team leads review who is assigned under the project; individuals review “my agents.” Both
surfaces expose the same field set as the unified catalog listing so clients reuse one parser.

**Why this priority**: Reduces client defects from schema drift between “catalog” and “my” views.

**Independent Test**: Compare field keys (and presence rules) between unified listing items and
items returned for team assigned and my-agents flows for the same underlying agents.

**Acceptance Scenarios**:

1. **Given** agents assigned to a team for a project, **When** a client requests the team
   assigned roster for that project, **Then** each entry uses a stable slug identifier (not a
   numeric-only surrogate labeled as id) and any embedded system summary exposes only the system
   name without description or skills fields.
2. **Given** a user with personal agent access, **When** they request the my-agents surface,
   **Then** each returned item includes the same fields as the unified listing contract (no
   extra or missing catalog fields relative to the agreed unified shape).
3. **Given** a client needs platform compatibility metadata, **When** they request the unified
   listing or detail, **Then** bulk system compatibility lists are not embedded there; they are
   obtained only from the dedicated available-systems surface.

---

### User Story 5 - Official agents v1 single read surface (Priority: P1)

Integrators and internal tools consume official smart-agent catalog data through one paginated,
cache-backed listing that already contains the full agents-in-group payload, without a second
identifier-scoped detail request.

**Why this priority**: Removes duplicate contracts and aligns capacity work (cache, pagination)
with the only read path.

**Independent Test**: Request `GET /api/v1/official/agents` with pagination parameters, confirm
each page includes complete group payloads and that `GET /api/v1/official/agents/{identifier}`
returns no successful catalog response (removed or non-catalog behavior per migration).

**Acceptance Scenarios**:

1. **Given** multiple official agent groups, **When** a client calls the unified official listing,
   **Then** each entry includes all data required to render agents in that group without calling a
   per-group detail URL.
2. **Given** a catalog larger than one page, **When** the client walks pagination, **Then** cache
   behavior conforms to product rules (staleness bounds documented in planning) and no page
   exceeds the agreed page-size policy for this surface.
3. **Given** a bookmark to the old detail path, **When** the client requests it, **Then** they
   receive a documented migration outcome (gone or redirect) and use only the listing surface for
   reads.

---

### Edge Cases

- Listing with zero agents returns an empty page with valid pagination metadata.
- Last page may contain fewer than twenty groups; clients must not assume a full page.
- An agent that is official in one context must not show conflicting flags between listing and
  detail for the same project.
- Concurrent assignment and unassign operations must leave the roster consistent (no duplicate
  assignments for the same logical slot).
- Removal of legacy routes: unknown or deprecated URLs return a clear not-found or gone
  response consistent with product policy (exact HTTP semantics left to planning).
- Trace and analytics pipelines that relied on **slug** MUST be updated to **`name`** per
  clarification; duplicate **names** across agents can make traces ambiguous—document mitigation
  (for example secondary correlation fields in planning if needed).
- Official v1 **cache** invalidation: define behavior when group membership or metadata changes
  mid-session so clients do not rely on stale pages indefinitely.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The product MUST expose one canonical **project** catalog response shape (unified
  “novo retorno” per agent group row). Where the product still exposes a separate detail read for
  project agents, that detail MUST use the **same** per-group structural rules as each listing
  row; where listing alone carries the full payload, clients MUST not depend on a second shape.
  The only categorical distinction in the row is an `is_official` boolean per agent group.
- **FR-001a**: The unified “novo retorno” payload for this release MUST **retain** a `model` key
  (not removed); other key removals follow earlier requirements unless amended in a future
  clarification.
- **FR-002**: The product MUST remove the dedicated official-only catalog entry point for
  projects (see stakeholder route references below) so that no client can rely on it after
  release.
- **FR-003**: The product MUST remove all behavior branches, flags, or documentation strings that
  split “legacy” versus “new” agent implementations for catalog, assignment, or listing flows.
- **FR-004**: Assign and unassign operations MUST each be reachable through a single unified route
  per action, replacing any parallel legacy and new assign/unassign routes.
- **FR-005**: The unified listing and detail payloads MUST NOT include top-level `type` or `system`
  keys in the main envelope agreed for this release.
- **FR-006**: Compatibility or capability lists previously carried as `available_systems` inside the
  main listing or detail payload MUST be removed from those payloads and MUST be exposed only via
  a dedicated available-systems surface (separate request contract).
- **FR-007**: For the team assigned roster for a project (see stakeholder route references), each
  entry MUST identify the agent group with a `slug` key (replacing any prior `id` key used for the
  same purpose) and any nested system object MUST contain only a `name` property (no `description`,
  no `skills`).
- **FR-008**: The my-agents surface for end users (see stakeholder route references) MUST return
  items whose field set matches the unified listing contract field-for-field (same keys and
  presence rules).
- **FR-009**: The unified listing MUST support pagination with a hard maximum of twenty agent
  groups per page.
- **FR-010**: Category identifiers exposed to clients in listing contexts MUST use slugs that
  mirror the category slugs configured in the admin panel for the same project data.
- **FR-011**: The product MUST expose **only** `GET /api/v1/official/agents` as the supported read
  path for the official smart-agent catalog (v1): it MUST return the **complete** agents-in-group
  payload on each row, MUST support **pagination**, and MUST use a **cache** strategy consistent
  with performance goals defined in planning. The route `GET /api/v1/official/agents/{identifier}`
  MUST be **removed** as a catalog detail endpoint (migration guidance required).
- **FR-012**: Observability and **trace** correlation for agents MUST record the agent **`name`**
  (not `slug`) as the human-facing identifier in trace payloads; this MUST be documented for
  operators. API contracts elsewhere in this spec that require **`slug`** for stable roster keys
  remain unchanged.
- **FR-013**: Creation of **official or custom** agents MUST be allowed **only** for authenticated
  principals whose **email** is listed in the **`OFFICIAL_SMART_AGENT_EDITORS`** configuration;
  all other creation attempts MUST be denied with a predictable authorization outcome.

### Key Entities

- **Agent group (catalog row)**: A deployable or configurable agent offering for a project;
  carries display metadata, category placement, and the official flag.
- **Project agent assignment**: Links a project (and optionally team context) to an agent group
  with assign/unassign lifecycle.
- **System (compatibility context)**: A platform or integration family relevant to availability;
  for roster views only the name is exposed inline; richer metadata lives on dedicated surfaces.
- **Category**: Admin-defined grouping for agents within a project; identified by a slug aligned
  across admin and API listing consumers.
- **Smart agent editor allow-list**: Email addresses authorized to create agents (custom or
  official), supplied via `OFFICIAL_SMART_AGENT_EDITORS`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a sample project with at least forty agent groups, two successive listing pages
  never contain more than twenty groups each and together cover all groups without gaps or
  duplicates.
- **SC-002**: In acceptance testing, one hundred percent of structural comparisons between a
  catalog listing row and the agreed single-shape rules for that agent (including any remaining
  project detail route, if present) pass equality checks on keys and nesting (values may differ).
  For official v1, one hundred percent of groups on a sample page satisfy “no missing detail
  fields” versus the retired per-identifier contract checklist.
- **SC-003**: Zero supported client flows require the removed official-only catalog route after
  migration notes are published (verified by test matrix covering former entry points).
- **SC-004**: For five representative agents, team-assigned and my-agents responses each expose
  the same field names as the unified listing items, with no `description` or `skills` fields under
  embedded system objects on the team roster.

## Assumptions

- Authentication and most authorization rules stay as today except **agent creation**, which is
  explicitly narrowed to emails in **`OFFICIAL_SMART_AGENT_EDITORS`** (see FR-013).
- Admin panel category slug data is the source of truth for slug alignment; any historical
  mismatches are corrected on the API side to match admin.
- Clients will receive migration guidance for removed URLs and for any parser changes (removed
  keys, relocated `available_systems`).
- “Unified novo retorno shape” is already defined in product or design documentation; this spec
  treats structural parity between list and detail as the acceptance bar without embedding the
  full JSON schema here.

## Stakeholder route references *(product contract traceability)*

These identifiers anchor scope discussions; naming in planning may refine edge cases (trailing
slashes, minor path variants) without changing intent.

- Legacy official-only catalog to remove: `/api/agents/official/{project_uuid}/`
- Team assigned roster to reshape: `/api/agents/teams/{project_uuid}`
- Personal agents surface to align with listing: `/api/agents/my-agents/` (and any subpaths in
  current product use)
- Dedicated surface for `available_systems`: exact path to be finalized in planning while
  satisfying FR-006 isolation from listing and detail payloads
- Official smart agents v1 read consolidation: unified listing `GET /api/v1/official/agents`
  (paginated, cached); removed catalog detail `GET /api/v1/official/agents/{identifier}`
