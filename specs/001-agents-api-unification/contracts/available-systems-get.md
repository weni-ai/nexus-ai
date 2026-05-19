# Contract: GET /api/v1/official/available-systems

## Purpose

Expose full **`AgentSystem`** metadata for clients after FR-006 removes inline embedding from
official agents list.

## Method and path

- **GET** `/api/v1/official/available-systems`

## Authentication / authorization

- Same stack as **`OfficialAgentsV1`** unless implementation discovers a requirement to relax
  project scoping (document deviation in `research.md` if so).

## Response body

Single envelope (clients MUST parse this shape only):

- **200**: JSON object:
  - **`available_systems`** *(array)* — each element matches **`AgentSystemSerializer`** with
    `many=True` (`slug`, `name`, `logo`, …), identical to the list formerly nested under
    `GET /api/v1/official/agents` → `new.available_systems`.

Example:

```json
{
  "available_systems": [
    { "slug": "...", "name": "...", "logo": "..." }
  ]
}
```

- **401** / **403**: Standard DRF error envelope.

## Caching

- May be cached independently of catalog pages; shorter TTL acceptable if systems rarely change.
