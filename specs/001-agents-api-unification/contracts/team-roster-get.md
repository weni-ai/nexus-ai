# Contract: GET /api/agents/teams/{project_uuid}

## Purpose

Project team roster aligned with **novo retorno** (FR-007, FR-008 parity with catalog parser).

## Response shape rules

- Top-level wrapper may remain `{ "manager": {...}, "agents": [...] }` unless spec requires a
  flatter envelope — **each item in `agents`** MUST match novo retorno field names.
- Identifier: field name **`slug`** (string), **not** `id`.
- Remove **`description`** and **`skills`** from items.
- When a **`system`** object appears inside MCP or similar nested structure, it MUST be
  **`{"name": "<display or technical name>"}`** only — **no** `slug`, `logo`, or localized
  description blobs on this endpoint.

## Compatibility

- **Breaking** change for existing consumers expecting `id`, `skills`, or rich `system` objects —
  coordinate release with frontend.
