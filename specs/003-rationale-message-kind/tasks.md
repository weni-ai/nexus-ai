---
description: "Task list for rationale messages on the live answer stream"
---

# Tasks: Rationale on the Live Answer Stream

**Input**: Design documents from `/specs/003-rationale-message-kind/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. The failure mode is a progress sentence leaking into answer deltas, or a second send of the same sentence. The independent tests in the spec are the acceptance bar.

**Organization**: Grouped by user story so each can be implemented and checked on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Paths are relative to the `nexus-ai` repository root

## Path Conventions

Django backend. Stream code lives in `inline_agents/backends/openai/`. History lives in `nexus/inline_agents/` and `nexus/logs/api/`.

---

## Phase 1: Setup

**Purpose**: Record a green baseline so later failures belong to this work.

- [ ] T001 Run the baseline suite and record coverage: `cd nexus-ai && poetry run coverage run --source='.' manage.py test --verbosity=2 --noinput && poetry run coverage report --fail-under=75`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The stream can carry a complete rationale message and can stamp a kind on answer messages. No classification yet.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 Add `send_rationale` to `StreamingSession` in `inline_agents/backends/openai/grpc/streaming_client.py`. It queues `type: rationale` with the full text, merges session metadata with `message_kind=rationale` and `rationale_index`, and does not close the stream or enqueue the stop signal
- [ ] T003 Teach `send_delta` and `send_completed` in `inline_agents/backends/openai/grpc/streaming_client.py` to merge extra metadata onto the session metadata. Answer sends pass `message_kind=final_response`. `send_completed` still closes the stream. `setup` stays without a kind
- [ ] T004 [P] Add `inline_agents/backends/openai/tests/test_rationale_stream.py` covering `send_rationale` (stream stays open, metadata merged, index is a string) and delta/completed kind stamping (session `session_id` and `language` still present)

**Checkpoint**: A caller can emit the three message shapes from [contracts/outgoing-message-kind.md](contracts/outgoing-message-kind.md).

---

## Phase 3: User Story 1 — Progress updates stay separate from the answer (Priority: P1) 🎯 MVP

**Goal**: A progress sentence is one `rationale` message. Answer deltas and `completed` contain only the final answer.

**Independent Test**: Feed text deltas, then a tool call, then more text, then the end of the stream. Assert one rationale message, then only final deltas, then `completed` whose text is the answer.

### Tests for User Story 1

- [ ] T005 [P] [US1] Extend `inline_agents/backends/openai/tests/test_rationale_stream.py` for the hold: text then `tool_call_item` emits one rationale and zero deltas of that text; text with no tool call is released as deltas; an empty hold emits no rationale; rationale disabled forwards deltas immediately and emits no rationale

### Implementation for User Story 1

- [ ] T006 [US1] Create `inline_agents/backends/openai/grpc/rationale_stream.py` that holds `ResponseTextDeltaEvent` text, flushes the hold as one rationale when a tool call arrives, and releases the hold as final-response deltas when the response ends without a tool call
- [ ] T007 [US1] Use that classifier from the stream loop in `inline_agents/backends/openai/backend.py` (`_process_delta_event` and the end of the `stream_events` loop). Pass `rationale_switch`. `send_completed` sends `result.final_output` with `message_kind=final_response` and must not include held progress text
- [ ] T008 [US1] Stamp `message_kind=final_response` on the error session in `OpenAIBackend._send_grpc_error_message` (`inline_agents/backends/openai/backend.py`) and send no rationale there

**Checkpoint**: User story 1 is testable on the stream without persistence.

---

## Phase 4: User Story 2 — Several progress updates stay ordered (Priority: P2)

**Goal**: Each rationale message in a turn has the next index, and the next turn starts at 1.

**Independent Test**: Two tool calls in one classifier produce `"1"` then `"2"`. A new classifier starts at `"1"`.

### Tests for User Story 2

- [ ] T009 [P] [US2] Extend `inline_agents/backends/openai/tests/test_rationale_stream.py` with two tool calls (indexes `"1"` and `"2"`, both before any final delta) and a second classifier instance that starts at `"1"`

### Implementation for User Story 2

- [ ] T010 [US2] Keep the 1-based counter on the classifier in `inline_agents/backends/openai/grpc/rationale_stream.py` and pass it as the string `rationale_index` to `send_rationale`. One `StreamingSession` is one turn, so the next session starts at 1 without extra reset logic

**Checkpoint**: User stories 1 and 2 are both visible on a single stream.

---

## Phase 5: User Story 3 — Reloading keeps the distinction (Priority: P3)

**Goal**: Stored rows keep the kind. Older rows stay without one.

**Independent Test**: A rationale row and a final-response row reload with their kinds. A row with both columns null is serialized without those keys.

### Tests for User Story 3

- [ ] T011 [P] [US3] Add a serializer test in `nexus/logs/api/test_logs_api.py` (or the existing inline-conversation test module beside it) asserting `message_kind` and `rationale_index` are present when set and omitted when null

### Implementation for User Story 3

- [ ] T012 [US3] Add nullable `message_kind` (`CharField`, max length 32) and `rationale_index` (`PositiveIntegerField`) to `InlineAgentMessage` in `nexus/inline_agents/models.py`, with a new migration under `nexus/inline_agents/migrations/`. No default that rewrites existing rows and no data migration
- [ ] T013 [US3] Add optional `message_kind` and `rationale_index` to `save_inline_message_to_database` in `router/traces_observers/save_traces.py` and thread them through the `save_inline_trace_events` task kwargs
- [ ] T014 [US3] On each rationale emit from `inline_agents/backends/openai/backend.py`, persist one `InlineAgentMessage` with that text, kind `rationale`, and the integer index. In `TraceHandler.save_trace_data` (`inline_agents/backends/openai/hooks.py`), stamp the existing answer row `final_response` and leave `rationale_index` unset
- [ ] T015 [US3] Expose `message_kind` and `rationale_index` on `InlineConversationSerializer` in `nexus/logs/api/serializers.py`, omitting each key when the value is null

**Checkpoint**: User story 3 is a history read. It does not change the socket sequence.

---

## Phase 6: Polish

- [ ] T016 Confirm the OpenAI stream path still notifies `inline_trace_observers_async` with `send_message_callback=None` in `inline_agents/backends/openai/hooks.py`, and that the new emit path does not call `RationaleObserver` or `/mr/msg/send`
- [ ] T017 Run the unit checks in `specs/003-rationale-message-kind/quickstart.md` and fix failures until the coverage floor still passes

---

## Dependencies

- Phase 2 blocks all stories.
- US1 (Phase 3) blocks US2 (Phase 4).
- US3 (Phase 5) depends on Phase 2 and on the rationale emit from US1 (T007). It does not depend on US2's tests, but it stores the index US2 produces, so implement US2 before T014.
- Polish waits on the stories you intend to ship.

```text
T001 → T002 → T003 → T004
              T003 → T006 → T007 → T008
                     T005 (parallel with T006 after T003)
T007 → T010
T009 (parallel with T010 after T006)
T007 → T012 → T013 → T014 → T015
T011 (parallel with T012)
T014 → T016 → T017
```

## Parallel example: User Story 1

```text
T005  test the hold in inline_agents/backends/openai/tests/test_rationale_stream.py
T006  implement the hold in inline_agents/backends/openai/grpc/rationale_stream.py
```

## Implementation strategy

MVP is Phase 3 (User Story 1): one progress sentence and an answer that does not repeat it, on the existing stream. User Story 2 adds the index the socket needs when a turn calls more than one agent. User Story 3 is the reload and can follow the socket work.

## Notes

- Do not change `inline_agents/backends/openai/grpc/message_stream_service.proto`.
- Do not send this sentence through `router/traces_observers/rationale/observer.py`.
- Preview and components turns do not open the stream; leave them alone.
