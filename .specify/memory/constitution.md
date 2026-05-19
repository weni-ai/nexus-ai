<!--
Sync Impact Report
- Version change: prior 1.0.0 or absent → 1.1.0
- Modified principles: Titles unchanged (I–V); Principle V cross-references backend layering
- Added sections: Backend architecture and implementation standards (SOLID, layering, DTOs,
  patterns, typing, errors)
- Removed sections: None
- Templates: .specify/templates/plan-template.md ✅ updated |
  .specify/templates/spec-template.md ✅ reviewed (no edit) |
  .specify/templates/tasks-template.md ✅ updated
- Follow-up TODOs: None
-->

# Nexus AI Constitution

## Core Principles

### I. Specification traceability

Every feature delivered through Spec Kit MUST have `spec.md`, `plan.md`, and `tasks.md` under
`specs/[###-feature-name]/` before implementation work begins. Code changes MUST map to tasks and
user stories. Scope or requirement drift MUST be recorded by updating the spec and plan before
expanding the implementation.

**Rationale**: Traceability keeps reviews honest, preserves intent for operators, and lets agents
and humans work from the same source of truth.

### II. Security and privacy

Secrets and credentials MUST NOT be committed; use environment variables and approved secret
management. Authentication and authorization MUST follow the project identity model (Keycloak
where the product integrates with it). Handling of personal or sensitive data MUST comply with
product policy and applicable regulation; least privilege applies to services and credentials.

**Rationale**: The stack is network-facing and multi-tenant by nature; a single leaked secret
or weak auth boundary has disproportionate impact.

### III. Automated verification

Changes MUST pass repository CI before merge. Behavior that affects correctness, API contracts,
or security boundaries MUST include automated tests at an appropriate level (unit, integration,
or contract). Omitting tests requires explicit justification and reviewer agreement in the PR.

**Rationale**: CI is the shared safety net for a distributed team and for automated agents that
edit code.

### IV. Observability and operability

The application MUST remain runnable through documented paths (for example Docker Compose) with
environment variables documented for required configuration. Errors and failures in request
paths and asynchronous workers (for example Celery) MUST be diagnosable through structured or
actionable logs and documented troubleshooting steps where behavior is non-obvious.

**Rationale**: Nexus AI runs as a service with databases, brokers, and workers; silent failures
are unacceptable in production.

### V. Simplicity and dependency discipline

Implement the smallest change that satisfies the approved spec. New dependencies MUST be
justified (license compatible with the project, maintained, necessary). Public interfaces and
shared schemas MUST preserve backward compatibility or ship an explicit deprecation and migration
path. Application structure MUST follow the layering and cohesion rules in **Backend
architecture and implementation standards** so that presentation code does not accumulate
business rules.

**Rationale**: Uncontrolled complexity and dependency growth slow delivery and increase incident
risk; thin boundaries keep the codebase maintainable.

## Technology and operational constraints

- **Language and packaging**: Python 3.10, Django, Poetry for dependency management.
- **Data and messaging**: PostgreSQL as primary persistence; Redis and Celery for asynchronous work
  where the architecture requires them.
- **Delivery**: Container images and Compose definitions in the repository are authoritative for
  local and deployment-shaped runs unless documentation states otherwise.
- **Configuration**: Twelve-factor style configuration via environment variables; no secrets in
  source control.
- **User-visible text**: Locale files and copy MUST follow project translation and Content Guide
  rules where they apply.

## Backend architecture and implementation standards

These rules apply to all new and substantially modified Python code in this repository.

### Core design

- **SOLID**: Modules MUST respect single responsibility, open-closed extension (prefer extension
  over invasive edits), Liskov-safe subtyping, focused interfaces, and dependency inversion
  (depend on abstractions and injected collaborators, not concrete globals in business logic).
- **DRY and KISS**: Duplicated logic MUST be consolidated into helpers or shared components when
  it represents the same policy or invariant; abstractions MUST NOT be introduced speculatively
  before a second real use case exists.
- **Boy Scout rule**: When changing a module, contributors MUST remove dead code, unused imports,
  and obsolete “band-aid” workarounds touched by that change unless a tracked follow-up documents
  why they must remain.

### Layering and boundaries

- **Separation of concerns**: Views, controllers, and HTTP adapters MUST remain thin: routing,
  parsing, authentication context, and response serialization only.
- **Service layer**: Business rules, orchestration, validation of domain invariants, and
  persistence mutations MUST live in dedicated service modules or callables invoked from the
  adapter layer.
- **DTOs**: Data crossing the boundary between HTTP (or other presentation) and services MUST use
  DTOs implemented with Pydantic models, dataclasses, or serializers as appropriate. Raw request
  objects, Django `HttpRequest` bodies, or framework-specific objects MUST NOT be passed into
  service functions.

### Design patterns

- **Observer and side effects**: Secondary effects (email, webhooks, fan-out integrations) MUST
  not block or entangle the primary business transaction unless the spec explicitly requires
  synchronous behavior. Use domain events, Django signals, dispatchers, or Celery tasks with
  clear contracts so the core flow stays decoupled.
- **Factory and builder**: Instantiating polymorphic or variant-heavy graphs (for example distinct
  agent or provider implementations) MUST use factories or builders instead of large conditional
  chains in views or serializers.

### Code quality

- **Typing**: All functions, methods, and public class attributes in new or modified code MUST
  have PEP 484 type annotations. Use of `typing.Any` or unchecked `dict` payloads in public
  service APIs requires explicit review justification.
- **Naming**: Identifiers MUST be descriptive and intention-revealing; cryptic abbreviations are
  not acceptable for public APIs.
- **Errors**: Bare `except:` or `except Exception:` without re-raise MUST NOT be used to swallow
  errors. Catch specific exception types; raise domain-specific exceptions from services; map
  them in the API layer to predictable HTTP status codes and uniform JSON error bodies.

## Spec Kit development workflow

- Feature work uses Spec Kit artifacts (`spec.md`, `plan.md`, `tasks.md`, and generated research,
  data model, and contracts as required by `/speckit-plan`).
- Each `plan.md` MUST complete the **Constitution Check** gates against this file before Phase 0
  research and MUST re-check after Phase 1 design when architecture changes.
- When Git extension hooks are enabled, follow `.specify/extensions.yml` for branch and commit
  conventions tied to Spec Kit commands.

## Governance

- This constitution supersedes informal team habits when they conflict with its rules.
- **Amendments**: Edit `.specify/memory/constitution.md`, describe material changes in the Sync
  Impact Report comment at the top, and propagate updates to plan/spec/tasks templates when
  gates or mandatory sections change.
- **Versioning** (this document only): **MAJOR** — removal or incompatible redefinition of a
  principle; **MINOR** — new principle or materially expanded guidance; **PATCH** — wording,
  clarifications, non-semantic fixes. **LAST_AMENDED_DATE** MUST be updated on every merge that
  changes governance text; **RATIFICATION_DATE** records first adoption and does not move on
  routine amendments.
- **Compliance**: Reviewers SHOULD confirm Constitution Check items for changes touching security,
  authentication, persistence migrations, external integrations, Spec Kit deliverables, or public
  HTTP APIs and service boundaries.

**Version**: 1.1.0 | **Ratified**: 2026-04-30 | **Last Amended**: 2026-04-30
