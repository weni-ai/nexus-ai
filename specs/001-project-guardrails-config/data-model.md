# Data Model: Project Guardrails Category Configuration

## Entities

### GuardrailCategoryCatalogEntry (code constant, not DB)

Fixed catalog in `settings.GUARDRAIL_CATEGORY_CATALOG` — defined directly in code, not persisted.

| Field | Type | Notes |
|-------|------|-------|
| slug | string | Stable key, e.g. `politics`, `physical_health` |
| name | string | English label in settings (Bedrock/docs; **not** returned by API) |
| description | string | English scope in settings (Bedrock/docs; **not** returned by API) |
| bedrock_definition | string | Denied topic definition for Bedrock sync (may equal description) |
| bedrock_examples | string[] | Optional sample phrases for Bedrock (max 5) |

**Initial slugs (11)**: `politics`, `physical_health`, `sexual_content`, `bias`, `hate`, `religion`, `suicide`, `self_harm`, `beliefs`, `gender_identity`, `sexual_relations`

> Not to be confused with `nexus.intelligences.models.Topics` (conversation classification).

---

### ProjectGuardrailsConfig (new model in `nexus/projects/models.py`)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| project | OneToOne → Project | CASCADE | |
| category_states | JSONField | `{slug: bool}` | `true` = blocked |
| blocking_message | TextField | null, max 240 | null = use `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` |
| bedrock_guardrail_identifier | CharField | null/blank until first sync | Bedrock Guardrail id |
| bedrock_guardrail_version | CharField | null/blank until first sync | Bedrock version string |
| created_on / modified_on | DateTime | auto | |
| initialized_as_new_project | Boolean | default False | Audit for lazy init |

**Validation**

- `category_states` keys = catalog slugs only; unknown keys stripped on write.
- Missing slugs filled on read with project-type default.
- If any category blocked, effective message must be non-empty (custom or settings default).

**Bedrock sync rules**

- Category PATCH → upsert Denied Topics for slugs where `blocked=true` only; persist new identifier/version.
- Message-only PATCH → local field only; **no** Bedrock update.
- Existing `Guardrail` model (identifier/version, global/current_version) may be reused or superseded by these fields — implementation MUST keep a single source of truth per project.

---

## State Transitions

```
blocked --PATCH--> unblocked --> Bedrock sync (omit category)
unblocked --PATCH--> blocked --> Bedrock sync (include category)

(no row) --first GET--> lazy init --> row [--> create/sync Bedrock when any blocked]

ApplyGuardrail INTERVENED --> return project effective message (ignore Bedrock canned text)
```

## Migration notes

- Single migration; no backfill of historical conversations; new catalog slugs merged at read time.
- Bedrock resources created lazily on first sync need (lazy init and/or first category PATCH).
