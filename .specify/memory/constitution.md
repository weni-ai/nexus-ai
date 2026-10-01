<!--
Sync Impact Report:
- Version change: none (unfilled template) → 1.0.0
- Modified principles: none (first generation; all template placeholders replaced)
- Added principles:
  I. Version Control and Review
  II. Contained Changes
  III. Commit Messages
  IV. Specification Traceability
  V. No Silent Divergence
  VI. Versioned Contracts
  VII. Changelog Maintenance
  VIII. Security and Secrets
  IX. Never Trust the Client
  X. Fail Gracefully and Predictably
  XI. Bounded Retry Over REST
  XII. Scalability and Peak Load
  XIII. Observability and Diagnosable Errors (root Observability + backend Diagnosable Errors)
  XIV. Tests Exercise Flows
  XV. Explicit Over Clever
- Added sections: Technology Stack and Project Constraints; Development Workflow and Quality Gates; Governance
- Removed sections: none
- Templates requiring updates (not modified by this generation):
  ⚠ .specify/templates/spec-template.md — has no "Inheritance from Product Spec" block (Principle IV) nor a "Peak load" field (Principle XII)
  ⚠ .specify/templates/plan-template.md — "Constitution Check" gates should list Principles I–XV
- Follow-up TODOs:
  TODO(PRODUCT_SPEC_REPO): name the product-spec repository that engineering specs inherit from.
  TODO(CI_LINT): decided — replace CI's `flake8 nexus/` with `ruff check .` so CI matches pre-commit; to be done in a separate PR.
  TODO(FORMATTER): pre-commit formats with `ruff format` (line 120, double quotes) while `task format` / `task lint` use blue (line 79, single quotes); decision deferred.
  TODO(DEPENDENCY_SCANNING): no vulnerability scanning of dependencies is configured (deferred).
  TODO(SENTRY_PII): existing code tags Sentry events with `contact_urn` and attaches end-user message text; no user identifier is set. New code follows Principle XIII; existing calls to be fixed separately.
- Resolved at ratification:
  Branch protection on `main` confirmed in place.
  Specs that predate 1.0.0 are exempt from the inheritance section (Principle IV).
  Commit and changelog formats apply from 1.0.0 onward; history is not rewritten (Principles III, VII).
  Django `TestCase` via `manage.py test` is the standard test stack; pytest is the exception.

Provenance:
- Source: weni-ai/vtex-cx-engineering-constitutions (main)
- Files: base-constitution.md, backend/base-constitution.md
- Domains: backend
- Generated: 2026-10-01 via setup-engineering
-->

# Nexus AI Constitution

Engineering constitution for `nexus-ai` — the Weni/VTEX CX AI agents platform
(Django packages `nexus`, `router`, `inline_agents`). Principles are declarative
and testable, stated with `MUST` / `SHOULD`, each with its rationale.

## Core Principles

### I. Version Control and Review

All code MUST enter `main` through a pull request on
`github.com/weni-ai/nexus-ai`. A merge MUST require at least one approved review
and a green run of `.github/workflows/ci.yml`. Direct pushes to `main` MUST be
blocked through GitHub branch protection. Work MUST start on a branch created
from the latest `main`.

**Rationale:** the policy is only real when the platform enforces it, not when it
depends on trust. Peer review and a protected `main` keep history auditable and
stop unreviewed changes from reaching production.

### II. Contained Changes

A change MUST be limited to the context it was asked to address. Refactoring,
renaming, reformatting, or behaviour adjustments outside that context MUST NOT
ride along; each belongs to its own change. This principle governs the scope of
a change as a whole; Principle III governs how that change is divided into
commits, and a change that stays within scope MAY span several commits.
Generated Django migrations MUST cover only the models the change touches. When
a change must span repositories (for example an event contract shared with
`nexus-conversations`), the PR MUST state which repositories are touched and why.

**Rationale:** a change that reaches beyond its stated scope is a change nobody
reviewed on purpose. It hides the intended fix inside unrelated edits, makes the
diff expensive to read, and turns a revert into a choice between losing the fix
and keeping an unrelated regression.

### III. Commit Messages

Commits MUST follow Conventional Commits in the form `<type>: <description>`.
Allowed types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. The
description MUST be imperative, specific, and no longer than 50 characters.
Commits MUST be atomic: one logical change per commit. This applies to commits
made from version 1.0.0 of this constitution onward; existing history is not
rewritten.

**Rationale:** conventional commits enable automated changelog generation and
semantic versioning. Atomic commits simplify bisecting, reverting, and reviewing.

### IV. Specification Traceability

Every engineering spec under `specs/<NNN-feature>/spec.md` MUST derive from
exactly one approved product spec and MUST reference it through an immutable,
pinned version (commit or tag); a mutable URL or ID alone MUST NOT be used. The
product spec MUST exist and be tagged before its engineering spec is created. An
engineering spec MUST NOT redefine the "what" it inherits: problem, scope,
success criteria, and binding decisions belong to the product spec. A technical
architecture document SHOULD be produced for non-trivial features; when it
exists it MUST be linked from the engineering spec, also pinned by commit or tag,
but its absence MUST NOT block the engineering spec.

Every engineering spec MUST open with an inheritance section in exactly this
format:

```
## Inheritance from Product Spec
- Product Spec: <title> — <URL>
- Pinned version: <commit/tag>
- Architecture doc: <none | URL + commit/tag>
- Inherited binding decisions: <short list>
- Scope of this spec: <slice implemented by this repo>
- Divergences: <none | link to amendment>
```

**Rationale:** traceability from product intent to technical execution keeps
decisions auditable and lets any change be traced back to the need that
justified it. Pinning the version guarantees that every team implements the same
version of the feature instead of divergent readings of a spec that changed
mid-flight. A mandatory product spec prevents engineering work without an agreed
problem; an optional architecture doc avoids blocking delivery on ceremony when
the design is trivial. A single inheritance format keeps the link
machine-checkable and uniform across repositories.

**Exception:** specs created before version 1.0.0 of this constitution (for
example `specs/001-project-guardrails-config`) are exempt from the inheritance
section, because the product-spec pipeline did not yet exist when they were
written. Every spec created from 1.0.0 onward MUST comply.

### V. No Silent Divergence

When a technical need contradicts something inherited from the product spec —
scope, success criteria, or a binding decision — the divergence MUST NOT be
implemented silently in code. It MUST be raised as an amendment in the product
repository and recorded in the `Divergences` field of the engineering spec's
inheritance section, linking to that amendment. Once the amendment is approved
and produces a new tag, the engineering spec's `Pinned version` MUST be updated
to it. Answers recorded under a spec's `## Clarifications` that contradict the
product spec are divergences and follow this process. A technical difference
that contradicts nothing inherited is an implementation decision and MUST live
in the engineering spec.

**Rationale:** when the product spec is the single source of truth, a silent code
deviation makes intent and implementation drift apart with no audit trail.
Routing divergences through amendments keeps the spec authoritative and every
decision traceable to an agreed change.

### VI. Versioned Contracts

Every public interface of this service MUST be versioned following SemVer. In
`nexus-ai` that includes: the DRF HTTP APIs (documented through drf-spectacular),
event payloads published to other services — notably those consumed by
`nexus-conversations` — and the gRPC contract in
`inline_agents/backends/openai/grpc/message_stream_service.proto`. Changes MUST
be backward compatible or ship with an announced deprecation path. Silent
breaking changes MUST NOT be introduced. A change to an event contract MUST be
coordinated with its consumers in the same delivery.

**Rationale:** consumers depend on stable contracts; explicit versioning and
deprecation give them a predictable path to adapt without outages. Event
consumers are invisible from this codebase, so a payload change that looks local
can break a downstream service silently.

### VII. Changelog Maintenance

Any public library published from this repository MUST maintain a changelog in
Keep a Changelog format. `nexus-ai` itself is a deployable service and keeps
`CHANGELOG.md` as its release record: every user-facing change MUST appear there
under a SemVer version. Entries added from version 1.0.0 of this constitution
onward MUST use the Keep a Changelog categories (Added, Changed, Deprecated,
Removed, Fixed, Security); earlier entries are left as written. Version bumps
MUST follow SemVer.

**Rationale:** a well-maintained changelog communicates impact to consumers and
serves as release documentation. SemVer alignment sets predictable upgrade
expectations.

### VIII. Security and Secrets

Secrets MUST never be committed to the repository — including settings, fixtures,
tests, specs, and helper scripts. Secrets MUST be provided by an external secrets
manager and injected at runtime as environment variables read through
`django-environ` in `nexus/settings.py`; local `.env` files MUST stay gitignored.
Access MUST follow least privilege by default, including the IAM permissions used
for AWS (Bedrock, S3, SQS). Dependencies MUST come only from trusted sources
through Poetry and MUST be checked for known vulnerabilities.

**Rationale:** leaked credentials and untrusted dependencies are among the most
common and most damaging breaches; prevention is far cheaper than remediation.

### IX. Never Trust the Client

Everything that reaches the server from outside — the Weni web app, a channel
message entering `router/`, a third-party webhook, another Weni service, or a
response from an LLM provider or agent tool — MUST be treated as potentially
malicious, incomplete, or incorrect until it is rigorously validated. Every
external input MUST be validated for type, format, range, and business rules at
the server boundary (DRF serializers, router entities, or explicit validators)
before use. Authorization MUST be enforced on the server for every request
through DRF permission classes or equivalent checks, regardless of any check
already performed by the client. Webhooks MUST verify their shared secret or
signature.

**Rationale:** clients run outside the server's control and can be inspected,
modified, or bypassed, and model output is untrusted by construction. Treating
external input as untrusted until validated prevents injection, data corruption,
and privilege escalation that client-side checks can never stop.

### X. Fail Gracefully and Predictably

Every external dependency will eventually fail — PostgreSQL, Redis, LLM providers
(Bedrock, OpenAI, LiteLLM), Weni platform services, and the data lake included.
Calls to external dependencies MUST have explicit timeouts and MUST NOT block
indefinitely; HTTP calls through `requests` MUST pass `timeout=`, because the
library's default is to wait forever. Failures MUST be handled explicitly and
surfaced as consistent, well-defined error responses — never as unhandled crashes
or leaked internal details such as stack traces or provider error bodies.

**Rationale:** failure is a certainty, not an edge case. Handling it explicitly
keeps partial outages contained and observable instead of letting one failing
dependency take the system down or expose internals to callers.

### XI. Bounded Retry Over REST

When data is propagated between services over a REST call, a failure in that call
MUST be retried rather than dropped. A retry MUST be attempted only when the
failure could plausibly succeed on another attempt — a connection error, a
request timeout, an HTTP 5xx, or an HTTP 429 — and MUST NOT be attempted on a 4xx
that reflects a defect in the request itself. A retry MUST only be applied to an
operation that is idempotent or protected by a deduplication key; when the
operation is neither, it MUST be made idempotent rather than left without retry.
Every retry policy MUST define a maximum number of attempts and a backoff
strategy; unbounded retry MUST NOT be used. For Celery tasks this means explicit
`max_retries` and backoff, not `autoretry_for` alone. When the attempts are
exhausted, the failure MUST be logged and MUST remain recoverable — it MUST NOT
be silently discarded.

**Rationale:** propagation between services fails for transient reasons far more
often than for permanent ones, so retrying keeps services converging instead of
drifting apart. Retry only helps when it can change the outcome: resending a
request rejected on its merits multiplies load, and retrying a non-idempotent
operation duplicates its effect. Bounds keep the mechanism from becoming the
outage, and a recoverable exhausted case prevents data from disappearing between
two services that each believe they succeeded.

### XII. Scalability and Peak Load

Every process — web (gunicorn/daphne), router API, and Celery workers — MUST be
stateless so that it can scale horizontally: state that outlives a single request
or task MUST NOT be kept in process memory or on local disk, and MUST live in an
external store shared by all instances (PostgreSQL, Redis, or object storage).
The peak load a feature is expected to sustain MUST be declared in its
engineering spec, stated as peak and not as average.

**Rationale:** capacity is a design input, not something discovered during an
incident. Sizing for average traffic guarantees failure when demand matters most,
such as a seasonal sales peak. Statelessness is what makes adding instances a
valid answer to load at all; declaring the peak turns scalability from an
assumption into a reviewable, testable number.

### XIII. Observability and Diagnosable Errors

Logs MUST be structured and MUST never contain secrets or sensitive personal
data. Errors MUST be traceable across components — HTTP requests, Celery tasks,
and events — through correlation or trace identifiers. Every error reported to
Sentry MUST carry enough context to be located and filtered without reproducing
it: at minimum the project identifier, the account (organization) identifier, the
user identifier, and the correlation identifier of the request. Those
identifiers MUST be opaque. Sensitive personal data — names, e-mail addresses,
phone numbers, government identifiers — MUST NOT be attached to a log line or an
error report under any circumstance; this includes contact URNs that embed a
phone number and raw end-user message content.

**Rationale:** structured, privacy-safe telemetry makes incidents diagnosable
without creating new data-exposure risks. An error without identifying context
can be counted but not investigated; opaque identifiers give exactly the
filtering an investigation needs while keeping reports free of personal data.

### XIV. Tests Exercise Flows

Every flow MUST have at least one test covering the complete use case, from input
to resulting effect — typically through the DRF API or the `usecases/` entry
point, with only true external dependencies mocked. Tests MUST be written with
Django's test framework (`django.test.TestCase` and friends, run by
`manage.py test`); pytest-only tests are an exception that MUST be justified in
the plan. Tests that assert a single
method in isolation are allowed and SHOULD be used to explore edge cases and
input variations that are expensive to reach through the whole flow, but they
MUST NOT be the only coverage a flow has. Every flow MUST cover its success path
and its failure paths; an error path that no test exercises MUST NOT be
considered covered.

**Rationale:** a suite made only of isolated method tests can be green while the
composition is broken, because the bug lives in how the pieces interact. Failure
paths are the least exercised in development and the most expensive in
production.

### XV. Explicit Over Clever

What a piece of code does MUST be evident where it happens. Hidden side effects
and implicit control flow MUST NOT be introduced to save lines; side effects
dispatched through Django signals or `event_domain` observers MUST be traceable
from the emitting code by an explicit event name. Any literal that carries
meaning — a threshold, a limit, a timeout, a retry count — MUST be a named
constant or a setting rather than an inline value; a literal with no meaning
beyond its own value, such as an index of 0 or an increment of 1, is exempt.
Comments MUST explain why a decision was made: the constraint, the trade-off, or
the non-obvious reason. A comment that restates what the code already says is a
signal that the code SHOULD be rewritten to say it.

**Rationale:** code is read far more often than it is written, usually by someone
without the context that made the clever version feel obvious. An unexplained
literal is a decision nobody can review; comments on the why preserve what the
code cannot carry without a second description that silently goes stale.

## Technology Stack and Project Constraints

- Runtime: Python `>=3.10,<3.12`, Django 4.2, Django REST Framework, Celery with
  Redis, PostgreSQL, Django Channels; dependencies managed with Poetry.
- Packages: `nexus/` (main Django project), `router/` (inbound message routing),
  `inline_agents/` (inline agent execution and backends).
- Layering: domain logic MUST live in `usecases/`; routing concerns MUST stay in
  `router/`; views and serializers MUST NOT hold business rules beyond boundary
  validation.
- Lint and style: ruff (line length 120, mccabe max complexity 12) and isort; the
  configuration in `pyproject.toml` is authoritative.
- Configuration: every tunable value (timeouts, limits, feature dates) MUST be a
  setting read through `env(...)` with a documented default.
- Downstream consumers: changes touching conversation records or emitted events
  MUST consider `nexus-conversations` (Principle VI).

## Development Workflow and Quality Gates

- Features follow Speckit: `spec.md` → `plan.md` → `tasks.md` under
  `specs/<NNN-feature>/`. The plan's **Constitution Check** MUST evaluate
  Principles I–XV; any justified violation MUST be recorded in the plan's
  **Complexity Tracking** table.
- Before review: `pre-commit` hooks (ruff format, ruff check, file hygiene,
  Poetry check) MUST pass; the push-stage coverage hook MUST stay at or above 75%.
- CI (`.github/workflows/ci.yml`, running `manage.py test` with coverage) MUST
  be green before merge (Principle I).
- New or changed flows MUST ship with flow tests covering success and failure
  paths (Principle XIV).
- PRs that change a public contract MUST call it out and include the version or
  deprecation plan (Principle VI) and the `CHANGELOG.md` entry (Principle VII).

## Governance

This constitution supersedes conflicting practices, READMEs, and local
conventions in this repository. Precedence for content is: VTEX CX engineering
root constitution > backend domain constitution > this project layer. Domain and
project rules specialize the root and MUST NOT contradict it without an explicit,
justified exception written into the affected principle.

Amendments are made by pull request to `.specify/memory/constitution.md`, with an
updated Sync Impact Report. Changes to the upstream bases in
`weni-ai/vtex-cx-engineering-constitutions` are pulled in by re-running
`setup-engineering`. Versioning follows SemVer: MAJOR for removing or redefining
a principle, MINOR for adding a principle or section or materially expanding
guidance, PATCH for clarifications and wording.

Compliance: every plan MUST pass the Constitution Check; reviewers MUST verify
compliance on every PR; `/speckit.analyze` MUST treat any conflict with a `MUST`
in this document as CRITICAL.

**Version**: 1.0.0 | **Ratified**: 2026-10-01 | **Last Amended**: 2026-10-01
