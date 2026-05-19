# Contract: GET /api/agents/my-agents/{project_uuid}

## Purpose

List project-owned and custom agents for the authenticated user context (FR-008).

## Rules

- Each list item MUST expose the **same field names and presence rules** as a **novo retorno**
  catalog row for that agent (strict parity with unified listing).
- VTEX variant **`GET /api/agents/app-my-agents/{project_uuid}`** MUST return the **identical**
  contract under its authentication rules.
