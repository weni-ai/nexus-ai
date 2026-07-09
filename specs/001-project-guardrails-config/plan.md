# Implementation Plan: Project Guardrails Topic Configuration

**Branch**: `001-project-guardrails-config` | **Date**: 2026-07-06 | **Spec**: [spec.md](./spec.md)

**Scope**: Nexus backend only — models, API, use cases, runtime payload, cache invalidation, tests.

## Summary

Add project-level guardrails configuration to Nexus: fixed 11-**category** catalog (`GUARDRAIL_CATEGORY_CATALOG`), per-category `blocked` boolean in `category_states`, single blocking message (≤240 chars), admin-only PATCH, lazy defaults, confirmation contract (`disable_category` / `disable_all`), extended runtime payload with `categories` map, cache invalidation. No backend i18n.

## Technical Context

**Language/Version**: Python 3.11, Django 4.2

**Primary Dependencies**: DRF, drf-spectacular, `GuardrailsUsecase`, `CacheService`, router guardrails handler

**Storage**: PostgreSQL — `ProjectGuardrailsConfig` (JSONField + TextField)

**Testing**: pytest / Django TestCase / APIClient in `nexus/` and `router/`

**Target Platform**: Linux (Nexus API + Router workers)

**Project Type**: Backend web service (REST API + runtime injection)

**Performance Goals**: GET/PATCH p95 < 200ms; reuse existing `GUARDRAILS_TTL` cache

**Constraints**: 240-char message; admin-only writes; last-write-wins; no retroactive rewrite

**Scale/Scope**: All projects; 11 topics v1; uniform per project

## Constitution Check

| Gate | Status |
|------|--------|
| Placeholder constitution | PASS (N/A) |
| Tests for new API + use case | PASS |
| Cache invalidation on mutation | PASS |
| 240-char validation | PASS |
| Scope: no per-agent / custom topics | PASS |

## Project Structure

### Documentation

```text
specs/001-project-guardrails-config/
├── spec.md, plan.md, research.md, data-model.md
├── quickstart.md, tasks.md
├── contracts/guardrails-config-api.yaml
└── checklists/requirements.md
```

### Source Code

```text
nexus/
├── projects/
│   ├── models.py                    # ProjectGuardrailsConfig (OneToOne Project)
│   ├── migrations/
│   └── api/
│       ├── routers.py               # route registration
│       ├── views.py                 # ProjectGuardrailsConfigView
│       ├── serializers.py
│       └── permissions.py           # GuardrailsConfigAdminPermission
├── usecases/guardrails/
│   ├── guardrails_usecase.py        # extended runtime payload
│   └── project_guardrails_config.py # get/merge/init/update
└── settings.py                      # GUARDRAIL_CATEGORY_CATALOG + default message

router/
├── services/cache_service.py
└── tasks/workflow_orchestrator.py
```

## Phase 0 — Research

Complete → [research.md](./research.md)

## Phase 1 — Design & Contracts

Complete → [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Phase 2 — Tasks

→ [tasks.md](./tasks.md)
