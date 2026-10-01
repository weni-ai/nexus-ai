# Implementation Plan: [FEATURE]

**Branch**: `[###-feature-name]` | **Date**: [DATE] | **Spec**: [link]

**Input**: Feature specification from `/specs/[###-feature-name]/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

[Extract from feature spec: primary requirement + technical approach from research]

## Technical Context

<!--
  ACTION REQUIRED: Replace the content in this section with the technical details
  for the project. The structure here is presented in advisory capacity to guide
  the iteration process.
-->

**Language/Version**: [e.g., Python 3.11, Swift 5.9, Rust 1.75 or NEEDS CLARIFICATION]

**Primary Dependencies**: [e.g., FastAPI, UIKit, LLVM or NEEDS CLARIFICATION]

**Storage**: [if applicable, e.g., PostgreSQL, CoreData, files or N/A]

**Testing**: [e.g., Django TestCase via `manage.py test` (pytest only with justification) or NEEDS CLARIFICATION]

**Target Platform**: [e.g., Linux server, iOS 15+, WASM or NEEDS CLARIFICATION]

**Project Type**: [e.g., library/cli/web-service/mobile-app/compiler/desktop-app or NEEDS CLARIFICATION]

**Performance Goals**: [domain-specific, e.g., 1000 req/s, 10k lines/sec, 60 fps or NEEDS CLARIFICATION]

**Constraints**: [domain-specific, e.g., <200ms p95, <100MB memory, offline-capable or NEEDS CLARIFICATION]

**Scale/Scope**: [domain-specific, e.g., 10k users, 1M LOC, 50 screens or NEEDS CLARIFICATION]

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

<!--
  Gates map 1:1 to the principles in .specify/memory/constitution.md.
  Mark each gate PASS, FAIL, or N/A with a one-line justification. Every FAIL
  MUST be justified in Complexity Tracking or the plan MUST NOT proceed.
-->

| # | Principle | Gate | Status |
|---|-----------|------|--------|
| I | Version Control and Review | Work happens on a branch from latest `main` and lands through a reviewed PR with green CI | [PASS/FAIL/N/A] |
| II | Contained Changes | Scope is limited to this feature; no unrelated refactors; cross-repo impact (e.g. `nexus-conversations`) is named | [PASS/FAIL/N/A] |
| III | Commit Messages | Commits will be atomic `<type>: <description>` (≤50 chars) | [PASS/FAIL/N/A] |
| IV | Specification Traceability | spec.md opens with the inheritance section and a pinned product-spec version | [PASS/FAIL/N/A] |
| V | No Silent Divergence | Any contradiction with the product spec is an approved amendment listed under Divergences | [PASS/FAIL/N/A] |
| VI | Versioned Contracts | Changed HTTP APIs, events, or gRPC contracts are backward compatible or carry a version/deprecation plan | [PASS/FAIL/N/A] |
| VII | Changelog Maintenance | User-facing changes get a `CHANGELOG.md` entry with Keep a Changelog categories | [PASS/FAIL/N/A] |
| VIII | Security and Secrets | No secrets in code, fixtures, or specs; new config comes from env; least-privilege access | [PASS/FAIL/N/A] |
| IX | Never Trust the Client | Every external input (API, webhook, router message, LLM/tool output) is validated server-side; authorization enforced per request | [PASS/FAIL/N/A] |
| X | Fail Gracefully and Predictably | Every external call has an explicit timeout and a defined error response | [PASS/FAIL/N/A] |
| XI | Bounded Retry Over REST | Inter-service propagation retries only transient failures, with max attempts, backoff, idempotency, and a recoverable exhausted path | [PASS/FAIL/N/A] |
| XII | Scalability and Peak Load | No cross-request state in process memory or local disk; peak load declared in spec.md | [PASS/FAIL/N/A] |
| XIII | Observability and Diagnosable Errors | Structured logs; Sentry events carry opaque project/account/user/correlation IDs; no PII (no raw contact URNs or message text) | [PASS/FAIL/N/A] |
| XIV | Tests Exercise Flows | Each flow has an end-to-end Django test covering success and failure paths | [PASS/FAIL/N/A] |
| XV | Explicit Over Clever | Meaningful literals are named constants/settings; no hidden side effects; comments explain why | [PASS/FAIL/N/A] |

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)
<!--
  ACTION REQUIRED: Replace the placeholder tree below with the concrete layout
  for this feature. Delete unused options and expand the chosen structure with
  real paths (e.g., apps/admin, packages/something). The delivered plan must
  not include Option labels.
-->

```text
# [REMOVE IF UNUSED] Option 1: Single project (DEFAULT)
src/
├── models/
├── services/
├── cli/
└── lib/

tests/
├── contract/
├── integration/
└── unit/

# [REMOVE IF UNUSED] Option 2: Web application (when "frontend" + "backend" detected)
backend/
├── src/
│   ├── models/
│   ├── services/
│   └── api/
└── tests/

frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/
└── tests/

# [REMOVE IF UNUSED] Option 3: Mobile + API (when "iOS/Android" detected)
api/
└── [same as backend above]

ios/ or android/
└── [platform-specific structure: feature modules, UI flows, platform tests]
```

**Structure Decision**: [Document the selected structure and reference the real
directories captured above]

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
