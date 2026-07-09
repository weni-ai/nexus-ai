# Data Model: Project Guardrails Category Configuration

## Entities

### GuardrailCategoryCatalogEntry (code constant, not DB)

Fixed catalog in `settings.GUARDRAIL_CATEGORY_CATALOG` — defined directly in code, not persisted.

| Field | Type | Notes |
|-------|------|-------|
| slug | string | Stable key, e.g. `politics`, `physical_health` |
| name | string | English display label (API response) |
| description | string | English scope description (API response) |

**Initial slugs (11)**: `politics`, `physical_health`, `sexual_content`, `bias`, `hate`, `religion`, `suicide`, `self_harm`, `beliefs`, `gender_identity`, `sexual_relations`

> Not to be confused with `nexus.intelligences.models.Topics` (conversation classification).

---

### ProjectGuardrailsConfig (new model in `nexus/projects/models.py`)

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| project | OneToOne → Project | CASCADE | |
| category_states | JSONField | `{slug: bool}` | `true` = blocked |
| blocking_message | TextField | null, max 240 | null = use `GUARDRAILS_DEFAULT_BLOCKING_MESSAGE` |
| created_on / modified_on | DateTime | auto | |
| initialized_as_new_project | Boolean | default False | Audit for lazy init |

**Validation**

- `category_states` keys = catalog slugs only; unknown keys stripped on write.
- Missing slugs filled on read with project-type default.
- If any category blocked, effective message must be non-empty (custom or settings default).

---

## State Transitions

```
blocked --PATCH + confirm_disable--> unblocked
unblocked --PATCH--> blocked

(no row) --first GET--> lazy init --> row
```

## Migration notes

- Single migration; no backfill; new catalog slugs merged at read time.
