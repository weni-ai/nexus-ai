# Contract: GET /api/v1/official/agents (unified)

## Purpose

Single read surface for official smart-agent catalog (FR-011, Option A). Each item is a **novo
retorno** row including data historically provided by **`GET /api/v1/official/agents/{identifier}`**.

## Query parameters

| Parameter | Notes |
|-----------|--------|
| `project_uuid` | Optional; drives `assigned` flags |
| `page` | Integer ≥ 1 |
| `page_size` | Integer ≥ 1, **≤ 20** (hard cap) |
| `name`, `group`, `category`, `system`, … | Existing filters preserved where still applicable |

## Response envelope (illustrative — finalize in OpenAPI)

```json
{
  "count": 0,
  "page": 1,
  "page_size": 20,
  "results": []
}
```

Each element of **`results`**:

- Shares **identical** keys and nesting rules for list-only and “detail-equivalent” consumption.
- Includes **`is_official`**, **`model`**, and **no** top-level **`type`** or **`system`** on the row
  envelope (FR-005).
- Does **not** embed global **`available_systems`** (FR-006).

## Removed behaviors

- No **`legacy`** or **`new`** top-level keys.
- No per-row split between “summary” and “detail” shapes.

## Errors

- **400** if `page_size` > 20.
