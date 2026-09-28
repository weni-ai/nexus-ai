# Implementation Plan: Rationale vs Final Response Message Kind

**Branch**: `003-rationale-message-kind` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-rationale-message-kind/spec.md`

## Summary

Tag every outgoing agent message with the stage that produced it, so the shopping assistant front can
render rationale in its dedicated presentation instead of as a normal chat bubble.

Nexus already knows the stage at emission time — rationale and the final response leave through
different code paths. The work is stamping an additive field at four call sites and letting it survive
the transports, not detecting anything:

| Stage | Call site | File |
|---|---|---|
| `rationale` | `RationaleObserver.task_send_rationale_message` | `router/traces_observers/rationale/observer.py` |
| `final_response` | `dispatch` | `router/dispatcher.py` |
| `final_response` | `dispatch_preview` | `router/tasks/invoke.py` |
| `final_response` | `_run_post_generation` skip-dispatch branch | `router/tasks/workflow_orchestrator.py` |
| `final_response` | `grpc_session.send_completed` | `inline_agents/backends/openai/backend.py` |

Guardrail refusals need no extra work: `_handle_guardrails_block` reuses `dispatch` / `dispatch_preview`.

The preview websocket is fully inside Nexus and ships first. The production webchat path needs Flows or
mailroom to forward the field, which is a cross-team dependency — Nexus sends it best-effort and
degrades silently.

A fifth emission point exists on the gRPC streaming path. `is_grpc_enabled` returns false when
components are on, so streaming is the **non-components** path, and rationale eligibility is
independent of it (rationale switch + GPT manager + webchat/preview channel). A streaming-enabled
webchat project therefore emits rationale over the message endpoint **and** the final response over the
gRPC stream — the shopping assistant's own likely profile. `StreamMessage.metadata` already exists in
the proto, so covering it costs one method change and no regeneration.

## Technical Context

**Language/Version**: Python 3.11, Django

**Primary Dependencies**: Django Channels (preview websocket), Celery (rationale send task), `requests`
(Flows HTTP), `grpcio` (opt-in streaming path), OpenAI Agents SDK (hooks that surface reasoning summaries)

**Storage**: PostgreSQL. One additive nullable column on
`nexus.inline_agents.models.InlineAgentMessage` (FR-012).

**Testing**: Django test runner under coverage — `poetry run coverage run --source='.' manage.py test`,
`coverage report --fail-under=75` (floor enforced by the `check-coverage` pre-commit hook)

**Target Platform**: Linux server (Nexus AI backend)

**Project Type**: Web service — backend only. No frontend work in this repo.

**Performance Goals**: No measurable change. The field is a constant string added to payloads that are
already being built; no extra round trip, no extra query (spec SC-005).

**Constraints**:
- Strictly additive. Existing payload keys, ordering, and delivery behaviour must not change (FR-004).
- Silent degradation where a transport drops the field (FR-008).
- Channels that never emit rationale still receive the field, so the contract is uniform; nothing else
  about their payloads may change (SC-003).

**Scale/Scope**: 5 call sites, 4 transports, 1 migration. Every outgoing agent message.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is **still the unfilled template** — every principle is a
`[PRINCIPLE_N_NAME]` placeholder. There are no ratified project principles to gate against, so this
check is **vacuous, not passing**.

| Gate | Result |
|---|---|
| Constitution principles | Not evaluable — constitution not ratified |
| Complexity justification | Not applicable — no violations to justify |

**Recommended follow-up (out of scope here)**: run `/speckit-constitution`, or the
`setup-engineering` skill that generates the constitution from the shared VTEX CX base, so future
features in this repo have a real gate. Not a blocker for this feature.

Applied in place of a constitution, from repo conventions observed in `research.md`:

- Backward compatibility on wire contracts is treated as mandatory (FR-004, FR-005, FR-008).
- Test coverage floor of 75% is enforced by pre-commit and must not regress.
- Migrations must be additive and lock-free (see `data-model.md` §3).

## Project Structure

### Documentation (this feature)

```text
specs/003-rationale-message-kind/
├── plan.md                              # This file
├── spec.md                              # Feature specification
├── research.md                          # Phase 0 — 6 findings, 3 questions carried to /speckit-clarify
├── data-model.md                        # Phase 1 — MessageKind, payload shapes per transport, optional column
├── quickstart.md                        # Phase 1 — how to validate
├── contracts/
│   └── outgoing-message-kind.md         # Phase 1 — the wire contract to hand to the front-end team
├── checklists/
│   └── requirements.md                  # Spec quality checklist
└── tasks.md                             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
router/
├── dispatcher.py                        # MODIFIED — tag final_response on the production dispatch
├── entities/
│   └── message_kind.py                  # NEW — MessageKind constants + payload helper
├── tasks/
│   ├── invoke.py                        # MODIFIED — dispatch_preview tags final_response
│   ├── workflow_orchestrator.py         # MODIFIED — skip_dispatch preview branch tags final_response
│   └── tests/
│       ├── test_guardrail_block_broadcast.py   # EXTENDED — guardrail refusal is final_response
│       └── test_message_kind_dispatch.py       # NEW — dispatch/preview/skip_dispatch tagging
├── clients/flows/http/
│   └── send_message.py                  # MODIFIED — carry the field onto /mr/msg/send and broadcast bodies
└── traces_observers/
    ├── rationale/
    │   └── observer.py                  # MODIFIED — task_send_rationale_message tags rationale
    ├── save_traces.py                   # MODIFIED — optional message_kind kwarg
    └── tests/
        └── test_rationale_message_kind.py      # NEW — rationale tagging, preview + production

nexus/
├── projects/websockets/
│   └── consumers.py                     # UNCHANGED — message_data is already free-form; callers add the key
└── inline_agents/
    ├── models.py                        # MODIFIED — nullable message_kind column
    └── migrations/00XX_inlineagentmessage_message_kind.py   # NEW

inline_agents/backends/openai/
├── backend.py                           # MODIFIED — pass the kind to send_completed
└── grpc/
    └── streaming_client.py              # MODIFIED — per-message metadata override
                                         # message_stream_service.proto UNCHANGED: metadata already exists
```

**Structure Decision**: Existing Django app layout, unchanged. The one new module,
`router/entities/message_kind.py`, sits beside `router/entities/mailroom.py`, which already holds the
shared outgoing-message helpers (`extract_ig_comment_broadcast_fields`, `stream_support_for_message`).
Keeping the constants and the payload helper in one place is what stops the four call sites from
drifting apart — the single failure mode this feature must avoid.

## Phasing

All open questions were resolved in `/speckit-clarify` (spec `## Clarifications`, session 2026-09-28).
Phases are ordered so the front-end is unblocked as early as possible, not to hedge against undecided
questions.

| Phase | Content | Depends on |
|---|---|---|
| A | `MessageKind` module + tagging at the preview call sites + tests | — |
| B | Carry the field onto `/mr/msg/send` and broadcast bodies | A |
| C | gRPC `metadata` per-message override for streaming projects | A |
| D | Persist on `InlineAgentMessage` + expose in history | A |

Phase A alone satisfies spec SC-004 — the front-end team can validate the full contract on preview
without any other team.

## Complexity Tracking

No constitution violations to justify (the constitution is not ratified). One design choice worth
recording:

| Choice | Why | Simpler alternative rejected because |
|---|---|---|
| Field at the envelope level, not inside `content` / `msg` | `content` is polymorphic (string, broadcast object, component list) and `msg` is agent-authored and may be a list | Nesting it would collide with component payloads and force the front to look in three places |
| Tag at the 4 emitting call sites, not inside the HTTP clients | The clients are shared between the rationale path and the final path and cannot tell the stages apart | Tagging in the clients would need a stage argument threaded in anyway — same change, worse location |
