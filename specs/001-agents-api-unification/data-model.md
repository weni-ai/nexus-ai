# Data Model: Unified Agents API

Logical entities touched by this feature (Django models under `nexus.inline_agents.models` unless noted).

## Agent

- **Identity**: `uuid`, `slug`, `name`
- **Classification**: `is_official`, `source_type` (e.g. platform vs VTEX app)
- **Presentation**: `collaboration_instructions` (exposed historically as `description`)
- **Relations**: `project`, `group` (`AgentGroup`), `category`, `agent_type`, `systems` (M2M),
  `mcps` (M2M), `current_version` / `Version` for skills display
- **Model field**: `foundation_model` (API key **`model`** in novo retorno per FR-001a)

## AgentGroup

- **Identity**: `slug`, `name`
- **Modal**: `AgentGroupModal` — `agent_name`, presentation payloads for official UX

## IntegratedAgent

- **Purpose**: Assignment of an `Agent` to a `Project` with `is_active`, `metadata` (mcp, system, mcp_config)
- **API impact**: Serialized for team roster; must align with novo retorno field names

## AgentSystem

- **Fields**: `slug`, `name`, `logo`, …
- **API impact**: Full objects only on **`/api/v1/official/available-systems`** after FR-006

## MCP

- **Relation**: Linked to `Agent` and `AgentSystem`; drives credential templates and detail payloads

## AgentCredential

- **Scope**: Per agent/project credential rows; included in unified row when policy allows

## Category

- **Field**: `slug` MUST mirror admin configuration (FR-010)

## Validation rules (API-level)

- Listing page: **≤ 20** agent **groups** (FR-009)
- Unified row: **`is_official`** required; **`model`** present; **no** top-level **`type`** or
  **`system`** on envelope (FR-005)
- Team roster: top-level identifier key **`slug`** (not `id`); nested **`system`** only **`name`**

## State transitions

- **Assign / unassign**: `IntegratedAgent` created/activated/deleted; triggers cache invalidation
  events as today
