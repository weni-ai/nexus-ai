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

## Response envelope

```json
{
  "count": 0,
  "page": 1,
  "page_size": 20,
  "results": []
}
```

Global agent systems metadata (`{"available_systems": [...]}` per `contracts/available-systems-get.md`) is **not** embedded in this response (FR-006). That read surface is implemented on branch **`feat/add-available-systems-endpoint`**, not duplicated here.

Each element of **`results`** (catalog rows — one per **`AgentGroup`**):

- Shares **identical** keys and nesting rules for list-only and “detail-equivalent” consumption.
- Includes **`is_official`**, inner **`agents`** members with **`assigned`** / **`active`**, **`about`**, **`conversation_example`**, and **`mcps`** (config + credential template shape).
- No top-level **`type`** on the row envelope; **`systems`** is the list of system slugs for the group (FR-005).
- Does **not** embed global **`available_systems`** (FR-006).

## Removed behaviors

- No **`legacy`** or **`new`** top-level keys.
- No per-row split between “summary” and “detail” shapes.

## Errors

- **400** if `page_size` > 20.
