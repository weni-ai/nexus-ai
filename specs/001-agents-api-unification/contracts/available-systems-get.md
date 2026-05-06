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

- **200**: JSON array or wrapped list of system objects compatible with existing
  **`AgentSystemSerializer`** output (`slug`, `name`, `logo`, …).
- **401** / **403**: Standard DRF error envelope.

## Caching

- May be cached independently of catalog pages; shorter TTL acceptable if systems rarely change.
