# Data Model: Project Guardrails Category Configuration

## Entities

### GuardrailCategoryCatalogEntry (code constant, not DB)

Fixed catalog in `settings.GUARDRAIL_CATEGORY_CATALOG` — defined directly in code, not persisted.

| Field | Type | Notes |
|-------|------|-------|
| slug | string | Stable key, e.g. `politics`, `physical_health` |
| name | string | English label in settings (Bedrock/docs; **not** returned by API) |
| description | string | English scope in settings (Bedrock/docs; **not** returned by API) |
| bedrock_definition | string | Denied topic definition for Bedrock create (may equal description) |
| bedrock_examples | string[] | Optional sample phrases for Bedrock (max 5) |

**Initial slugs (11)**: `politics`, `physical_health`, `sexual_content`, `bias`, `hate`, `religion`, `suicide`, `self_harm`, `beliefs`, `gender_identity`, `sexual_relations`

> Not to be confused with `nexus.intelligences.models.Topics` (conversation classification).

---

### BedrockGuardrailPool (new model — registry)

One row per unique combination of blocked catalog slugs.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| combination_key | CharField / TextField | unique | Deterministic key from sorted blocked slugs (e.g. bitmask or canonical join) |
| category_slugs | JSONField | list[str] | Slugs with `blocked=true` represented by this pool |
| bedrock_guardrail_identifier | CharField | required after create | AWS Guardrail id |
| bedrock_guardrail_version | CharField | required after create | AWS version string |
| created_on / modified_on | DateTime | auto | |

**Rules**

- Key **excludes** project language and blocking message.
- Lazy create: first project that needs a missing combination calls `CreateGuardrail`.
- Reuse: subsequent projects with the same key only point at this row.

---

### ProjectGuardrailsConfig (model in `nexus/projects/models.py`)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| project | OneToOne → Project | CASCADE | |
| category_states | JSONField | `{slug: bool}` | `true` = blocked |
| blocking_message | TextField | null, max 240 | null = use `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` |
| bedrock_guardrail_identifier | CharField | null/blank until assigned | Copy/pointer of assigned pool id |
| bedrock_guardrail_version | CharField | null/blank until assigned | Copy/pointer of assigned pool version |
| created_on / modified_on | DateTime | auto | |
| initialized_as_new_project | Boolean | default False | Audit for lazy init |

Optional FK to `BedrockGuardrailPool` may be used instead of (or in addition to) denormalized id/version — implementation MUST keep a single source of truth for ApplyGuardrail.

**Validation**

- `category_states` keys = catalog slugs only; unknown keys stripped on write.
- Missing slugs filled on read with project-type default.
- If any category blocked, effective message must be non-empty (custom or settings default).

**Pool resolve rules**

- Category PATCH → compute combination key from `blocked=true` → get_or_create pool (lazy Bedrock create) → persist id/version on project.
- Message-only PATCH → local field only; **no** Bedrock create/update; pool assignment unchanged.
- All unblocked → skip ApplyGuardrail; clear or ignore pool pointer as implemented.

---

## State Transitions

```
blocked --PATCH--> unblocked --> resolve pool for new combination (reuse or lazy create)
unblocked --PATCH--> blocked --> resolve pool for new combination (reuse or lazy create)

(no pool row) --first need--> CreateGuardrail --> registry row
(project A, project B, same subset) --> same pool identifier/version

(no ProjectGuardrailsConfig row) --first GET--> lazy init --> row

ApplyGuardrail INTERVENED --> return project effective message (ignore Bedrock canned text)
```

## Migration notes

- Migrations for `ProjectGuardrailsConfig` fields and `BedrockGuardrailPool` (or equivalent).
- No backfill of historical conversations; new catalog slugs merged at read time.
- Bedrock resources created lazily on first resolve need — not pre-created by Cloud/console.
