# Implementation Plan: Rationale on the Live Answer Stream

**Branch**: `003-rationale-message-kind` | **Date**: 2026-10-06 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-rationale-message-kind/spec.md`

## Summary

Deliver each progress sentence as one complete message on the OpenAI live stream that already carries the answer. Do not post it to a second endpoint. Answer deltas and the closing message contain only the final answer, and both declare that.

The sentence is assistant text the manager writes before a tool call. Today every text delta is forwarded immediately, so the socket shows that sentence and then replaces it when `completed` arrives with `final_output`. The work is to hold that text until the response is classified, emit it as `type: rationale` when a tool call follows, and release it as final-response deltas only when the response ends without a tool call.

`message_stream_service.proto` does not change. `type` is already a free string and `metadata` is already `map<string, string>`.

## Technical Context

**Language/Version**: Python 3.11, Django

**Primary Dependencies**: `grpcio`, OpenAI Agents SDK streaming (`ResponseTextDeltaEvent`, `tool_call_item`)

**Storage**: PostgreSQL. Two additive nullable columns on `nexus.inline_agents.models.InlineAgentMessage`.

**Testing**: Django test runner under coverage — `poetry run coverage run --source='.' manage.py test`, `coverage report --fail-under=75`

**Target Platform**: Linux server (Nexus AI backend)

**Project Type**: Web service — backend only. The shopping assistant socket consumes the contract; it is not implemented in this repo.

**Performance Goals**: No second connection and no extra model round trip (spec SC-003). Final-answer deltas are released when the last response is classified, which is when that response finishes, not token-by-token while it is still possible for a tool call to follow.

**Constraints**:

- One stream per turn (spec FR-006).
- Progress text never appears in a delta or in `completed` (spec FR-003, SC-001).
- Preview and components turns do not open this stream and are unchanged (spec FR-013).
- Unknown `type` must not be required for the answer to complete (spec FR-009).

**Scale/Scope**: The OpenAI gRPC session, the stream loop that already sees text deltas and tool calls, and the inline-message row used for history.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` is still the unfilled template. There are no ratified principles to gate against. This check is vacuous.

| Gate | Result |
|---|---|
| Constitution principles | Not evaluable — constitution not ratified |
| Complexity justification | Not applicable |

Applied from repo conventions and the spec:

- The wire change is additive on the existing stream.
- The migration is additive and does not rewrite old rows.
- Coverage floor of 75% stays in force.

**Post-design re-check**: Research resolved classification, the wire shape, and persistence. No constitution violation to justify. The hold-until-classified choice is recorded under Complexity Tracking because it delays first final token until the last response finishes.

## Project Structure

### Documentation (this feature)

```text
specs/003-rationale-message-kind/
├── plan.md
├── spec.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── outgoing-message-kind.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
inline_agents/backends/openai/
├── backend.py                         # MODIFIED — classify held text; do not forward progress as deltas
├── grpc/
│   ├── streaming_client.py            # MODIFIED — send_rationale; per-message metadata merge
│   ├── rationale_stream.py            # NEW — hold, classify, index
│   └── message_stream_service.proto   # UNCHANGED
└── tests/
    └── test_rationale_stream.py       # NEW

router/traces_observers/
└── save_traces.py                     # MODIFIED — optional message_kind and rationale_index

nexus/
├── inline_agents/
│   ├── models.py                      # MODIFIED — nullable columns
│   └── migrations/00XX_inlineagentmessage_message_kind.py
└── logs/api/
    └── serializers.py                 # MODIFIED — expose kind and index, omit when null
```

**Structure Decision**: The classifier lives next to the gRPC client because that is the only transport this reformulation changes. `RationaleObserver` and `/mr/msg/send` stay as they are for Bedrock. The OpenAI stream must not start calling them.

## Phasing

| Phase | Content | Depends on |
|---|---|---|
| A | `send_rationale`, metadata merge, kind on delta and completed | — |
| B | Hold and classify in the stream loop; no rationale when disabled or empty | A |
| C | Index increments inside the turn and restarts on the next stream | B |
| D | Persist kind and index; history omits nulls | B |

Phase B is the shopper-visible fix. Phase D is the reload story and does not change the socket payload.

## Complexity Tracking

No constitution violations. One design choice:

| Choice | Why | Simpler alternative rejected because |
|---|---|---|
| Hold assistant text until a tool call or the end of that response | The same response can start with the progress sentence and only later reveal the tool call. Releasing tokens early puts the sentence into answer deltas | Streaming every delta immediately is the current bug. A dedicated progress tool would stream the answer live, but it needs a new tool and a prompt change the spec does not require |
