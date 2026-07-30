# Implementation Plan: Project Guardrails Category Configuration

**Branch**: `001-project-guardrails-config` / `feat/guardrails-bedrock-pool-registry` | **Date**: 2026-07-22 | **Spec**: [spec.md](./spec.md)

**Scope**: Nexus backend only — models, API, use cases, Bedrock Guardrail **pool registry** (lazy create), `ApplyGuardrail` preprocess gate, cache invalidation, tests.

## Summary

Add project-level guardrails configuration to Nexus: fixed 11-**category** catalog (`GUARDRAIL_CATEGORY_CATALOG`), per-category `blocked` boolean in `category_states`, single blocking message (≤240 chars), admin-only PATCH, lazy defaults, immediate unblock (confirmation UX is frontend-only), **hybrid Bedrock Guardrail pools** keyed by blocked-category combination (lazy `CreateGuardrail`, shared across projects), **`ApplyGuardrail` on INPUT** in existing preprocess (Option A message resolution), cache invalidation. No backend i18n. No Lambda for this flow. No system-prompt soft layer / OUTPUT in this release.

## Technical Context

**Language/Version**: Python 3.11, Django 4.2

**Primary Dependencies**: DRF, drf-spectacular, boto3 (`bedrock` + `bedrock-runtime`), `GuardrailsUsecase`, `CacheService`, `router/tasks/invoke.py` preprocess

**Storage**: PostgreSQL — `ProjectGuardrailsConfig` + `BedrockGuardrailPool` (or equivalent registry)

**Testing**: pytest / Django TestCase / APIClient in `nexus/` and `router/`; Bedrock clients mocked (E2E against real AWS waits on Cloud IAM)

**Target Platform**: Linux (Nexus API + Router workers)

**Project Type**: Backend web service (REST API + pre-input Bedrock gate)

**Performance Goals**: GET/PATCH p95 < 200ms (excluding first-time pool create); `ApplyGuardrail` on critical path — measure and budget; reuse `GUARDRAILS_TTL` cache for id/version + effective message

**Constraints**: 240-char message; admin-only writes; last-write-wins; no retroactive rewrite; INPUT-only; message-only PATCH skips Bedrock; pool key has no language

**Scale/Scope**: All projects; 11 categories v1; ≤ 2^11 pool combinations in theory (lazy; far fewer in practice)

## Constitution Check

| Gate | Status |
|------|--------|
| Placeholder constitution | PASS (N/A) |
| Tests for new API + use case + ApplyGuardrail path | PASS |
| Cache invalidation on mutation | PASS |
| 240-char validation | PASS |
| Scope: no per-agent / custom categories / Lambda / prompt soft layer | PASS |

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
│   ├── models.py                    # ProjectGuardrailsConfig + BedrockGuardrailPool
│   ├── migrations/
│   └── api/
│       ├── routers.py
│       ├── views.py                 # ProjectGuardrailsConfigView
│       ├── serializers.py
│       └── permissions.py           # GuardrailsConfigAdminPermission
├── usecases/guardrails/
│   ├── guardrails_usecase.py        # resolve config + ApplyGuardrail gate helpers
│   ├── project_guardrails_config.py # get/merge/init/update
│   └── bedrock_guardrail_pool.py    # combination key, get_or_create pool, CreateGuardrail
└── settings.py                      # GUARDRAIL_CATEGORY_CATALOG + default message + baseline

router/
├── services/cache_service.py
└── tasks/invoke.py                  # _preprocess_message_input → ApplyGuardrail (INPUT)
```

## Phase 0 — Research

Complete → [research.md](./research.md)

## Phase 1 — Design & Contracts

Complete → [data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

## Phase 2 — Tasks

→ [tasks.md](./tasks.md)
