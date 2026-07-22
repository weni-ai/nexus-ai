# Specification Quality Checklist: Project Guardrails Topic Configuration

**Purpose**: Validate specification completeness before planning
**Created**: 2026-07-06
**Feature**: [spec.md](./spec.md)

## Content Quality

- [x] Focused on backend API and runtime behavior (no frontend scope)
- [x] User value expressed via API consumer / platform outcomes
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable via API and runtime assertions
- [x] Success criteria are measurable
- [x] Edge cases identified
- [x] Scope bounded (backend only)

## Feature Readiness

- [x] FRs map to acceptance scenarios
- [x] Out of scope explicitly excludes frontend work

## Notes

- 2026-07-06: Rewritten for strict backend scope; confirmation was initially API contract (`409` / `confirm_disable`).
- 2026-07-06 clarify: 5 questions resolved (admin role, new/existing default, default message, PATCH confirmation, catalog merge).
- 2026-07-20: Confirmation moved to frontend-only (FDD modal); backend persists unblock immediately — no `confirm_disable` / `409`.
- 2026-07-06 clarify (naming): *topic* → **guardrail category**; *topic_states* → **category_states**; backend i18n out of scope (T002 dropped).
- 2026-07-16: Runtime redesigned — `ApplyGuardrail` in Nexus preprocess (INPUT only), one Bedrock guardrail per project, omit unblocked categories on sync, blocking message Option A (Nexus message, ignore Bedrock canned text). Replaced payload/`categories` map for Models + Lambda path.
- 2026-07-22: **Superseded 1:1 Guardrail/project** → hybrid **pool** by blocked-category combination (lazy CreateGuardrail, shared across projects, message Option A, no language in pool key). Prompt soft layer + OUTPUT deferred. IAM/quota via Cloud; no console pre-create.
