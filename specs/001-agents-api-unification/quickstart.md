# Quickstart: Unified Agents API (development)

## Prerequisites

- Docker Compose or local Django per repository `README.md`
- Environment: `OFFICIAL_SMART_AGENT_EDITORS` as a **comma-separated list** of editor emails
  (exact match after normalize — see plan **C11**)

## Verify new read surfaces

```bash
# Replace host and token as appropriate
# Non-superuser Bearer tokens MUST include project_uuid (same permission stack as official agents list).
curl -sS -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/official/available-systems?project_uuid=<project_uuid>"

curl -sS -H "Authorization: Bearer <token>" \
  "http://localhost:8000/api/v1/official/agents?page=1&page_size=20&project_uuid=<uuid>"
```

## Migration expectations

| Removed / changed | Client action |
|-------------------|---------------|
| `GET /api/v1/official/agents/{identifier}` | Use list row payload only |
| `legacy` / `new` keys on v1 official list | Parse flat `results` (or agreed key) only |
| `GET /api/agents/official/<project_uuid>/` | Use unified project catalog / v1 official per product mapping |
| Embedded `available_systems` on v1 list | Call `/api/v1/official/available-systems` |
| Team roster `id` | Read `slug` |
| Traces agent key | Prefer **`name`** for new spans (FR-012); update dashboards |

## Tests

From the **repository root** (clone location on your machine):

```bash
poetry run pytest nexus/agents/api/test_agents_api.py -q --no-header -x
```

Adjust command if the project uses a different test runner entrypoint.
