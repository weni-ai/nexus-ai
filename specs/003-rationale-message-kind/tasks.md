---
description: "Task list for Rationale vs Final Response Message Kind"
---

# Tasks: Rationale vs Final Response Message Kind

**Input**: Design documents from `/specs/003-rationale-message-kind/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: Included. This feature is a wire contract whose only failure mode is a mis-tagged or untagged
message, and it must not regress channels it does not target (spec SC-003). Assertions are the deliverable.

**Organization**: Grouped by user story so each can be implemented, tested, and shipped on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths are given, relative to the `nexus-ai` repository root

## Path Conventions

Django project, backend only. Real directories: `router/`, `nexus/`, `inline_agents/`. Tests live
beside the code they cover (`router/tasks/tests/`, `router/traces_observers/tests/`), following the
existing repo layout.

---

## Phase 0: Coordination (no code, does not block Phase 2)

All contract questions were decided in `/speckit-clarify` (spec `## Clarifications`). What remains is
confirming and unblocking, which runs in parallel with implementation.

- [ ] T001 Confirm the decided contract with the shopping assistant front-end team (Cristian / Paulo Bernardo) by sharing `specs/003-rationale-message-kind/contracts/outgoing-message-kind.md`; if they request a change, update the contract and the spec `## Clarifications` before Phase 3 lands
- [ ] T002 Open the Flows/mailroom passthrough request for `message_kind`. Nexus owner is whoever implements this task; the consumer side is the shopping assistant front (Cristian / Paulo Bernardo, thread [#weni-corner-experience-nexus](https://vtex.slack.com/archives/C0ADFJF6WP8/p1789999017171009)); the transport owner is whoever owns `/mr/msg/send` and the webchat socket, and T002 must name that person in `spec.md` under Dependencies when the request is opened. There is no committed date. Fallback, already specified as FR-008: if the field is dropped, production delivery is unchanged and the front keeps today's rendering. Preview does not wait on this request (spec SC-004). The request gates only end-to-end production delivery, never Nexus-side work
- [ ] T003 Confirm with infra whether the shopping assistant project is listed in `GRPC_ENABLED_PROJECTS`; the answer changes which transport carries its final response and therefore how Phase 7 is prioritized, but not whether Phase 7 happens (spec FR-007)

---

## Phase 1: Setup

**Purpose**: Nothing to scaffold — this feature adds to an existing Django service. Only verify the
baseline is green so later failures are attributable.

- [ ] T004 Run the baseline suite and record the starting coverage number: `cd nexus-ai && poetry run coverage run --source='.' manage.py test --verbosity=2 --noinput && poetry run coverage report --fail-under=75`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared vocabulary every call site imports. Without this, the four tagging sites drift
apart — the single failure mode called out in plan.md's Structure Decision.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T005 Create `router/entities/message_kind.py` defining the closed value set (`RATIONALE = "rationale"`, `FINAL_RESPONSE = "final_response"`, per spec FR-010) and a `MESSAGE_KIND_CHOICES` tuple; place it beside `router/entities/mailroom.py`, which already holds shared outgoing-message helpers
- [ ] T006 Add a payload helper to `router/entities/message_kind.py` that stamps the kind onto an outgoing payload dict at the envelope level and returns it, so the four call sites never hand-write the key (see `data-model.md` §2 placement rules)
- [ ] T007 [P] Create `router/entities/tests/test_message_kind.py` covering the helper: stamps the key, leaves every pre-existing key untouched, rejects an unknown kind

**Checkpoint**: Foundation ready — user stories can begin.

---

## Phase 3: User Story 1 — Front distinguishes rationale from final answer (Priority: P1) 🎯 MVP

**Goal**: Every outgoing agent message on the preview surface declares whether it is rationale or the
final response, so the front can render the dedicated rationale presentation.

**Independent Test**: Run a turn in Agent Builder preview that triggers a tool call; assert the
websocket frames are `rationale`* followed by `final_response`, per `quickstart.md` §3.

**Scope note**: Preview only. That is enough to satisfy spec SC-004 — the front-end team validates the
full contract without waiting on Flows or mailroom.

### Tests for User Story 1

> Write these first and confirm they fail before implementing.

- [ ] T008 [P] [US1] Create `router/traces_observers/tests/test_rationale_message_kind.py` asserting `RationaleObserver.task_send_rationale_message` tags the preview websocket payload with the rationale kind (spec FR-002)
- [ ] T009 [P] [US1] Create `router/tasks/tests/test_message_kind_dispatch.py` asserting `dispatch_preview` tags the final-response kind, including the case where the answer is split into several messages so **every** part is tagged (spec FR-003, edge case "answer split")
- [ ] T010 [P] [US1] In `router/tasks/tests/test_message_kind_dispatch.py`, assert the `skip_dispatch` branch of `_run_post_generation` also tags its preview payload (spec FR-006)
- [ ] T011 [P] [US1] Extend `router/tasks/tests/test_guardrail_block_broadcast.py` asserting a guardrail refusal is tagged as the final response, on both the preview and production branches (spec edge case "guardrail block")
- [ ] T012 [P] [US1] In `router/traces_observers/tests/test_rationale_message_kind.py`, assert a project with `rationale_switch=False` produces no message tagged rationale (spec US1 scenario 4)
- [ ] T013 [US1] Add an ordering test walking a turn that emits three rationale messages then an answer, asserting the emitted sequence is exactly `rationale, rationale, rationale, final_response` (spec US1 scenario 3)

### Implementation for User Story 1

- [ ] T014 [US1] Tag the rationale kind in `RationaleObserver.task_send_rationale_message` (`router/traces_observers/rationale/observer.py`) on both preview websocket sends — the `preview` branch via `_handle_preview_message` and the `preview_websocket` branch at the tail of the task
- [ ] T015 [US1] Tag the rationale kind in `RationaleObserver._handle_preview_message` (`router/traces_observers/rationale/observer.py`) where it builds `{"type": "preview", "content": ...}`
- [ ] T016 [P] [US1] Tag the final-response kind in `dispatch_preview` (`router/tasks/invoke.py`) at the envelope level, sibling of `content`, not inside it
- [ ] T017 [P] [US1] Tag the final-response kind in the `skip_dispatch` preview branch of `_run_post_generation` (`router/tasks/workflow_orchestrator.py`)
- [ ] T018 [US1] Verify `nexus/projects/websockets/consumers.py` needs no change — `message_data` is serialized verbatim by `preview_message`, so the key added by callers already reaches the socket; if serialization drops it, fix it here and note why in the PR

**Checkpoint**: US1 complete. The front-end team can validate the contract end to end on preview.

---

## Phase 4: Regression guard (cross-cutting, required before merge)

**Purpose**: Prove the change is additive. Spec SC-003 and FR-005 are the acceptance bar and the most
likely thing to break silently.

- [ ] T019 [P] Add a test asserting a WhatsApp / components turn produces a payload whose every pre-existing key is identical in name, value and position, with the new field as the only difference — assert against a full expected dict, not just the presence of the new key (spec SC-003)
- [ ] T020 [P] Add a test asserting an Instagram comment reply is unaffected, covering `InstagramCommentBroadcastHTTPClient` (spec FR-005)
- [ ] T021 Add a test asserting that when a downstream transport rejects or strips the field, the message is still delivered and no exception surfaces to the user (spec FR-008)
- [ ] T021a [P] Add a test asserting that a turn interrupted after rationale emits no `final_response` and no end-of-turn signal of any kind, so the absence of a terminal message stays the contract (spec FR-013)

**Checkpoint**: Additivity proven. US1 is mergeable on its own.

---

## Phase 5: User Story 2 — Kind reaches the production surface (Priority: P2)

**Goal**: The field is on the wire for production webchat, so it reaches the shopping assistant once
the downstream transport forwards it.

**Independent Test**: Trigger a production-path turn and confirm from the Flows request logs
(`FlowsRESTClient.whatsapp_broadcast` logs the body; `SendMessageHTTPClient` logs at debug) that the field is in the body Nexus
sends. Nexus is done when the field is on the wire, independent of mailroom readiness.

**Not gated by T002.** The mailroom passthrough gates end-to-end delivery to the front, never the
Nexus-side work (spec FR-008).

### Tests for User Story 2

- [ ] T022 [P] [US2] Assert `SendMessageHTTPClient.send_direct_message` with `use_grpc=False` includes the field in the flat `/mr/msg/send` payload, for both kinds (`data-model.md` §2.2)
- [ ] T023 [P] [US2] Assert `WhatsAppBroadcastHTTPClient.send_direct_message` puts the field at the **top level** of the broadcast body and never inside `msg`, which is agent-authored and may be a list (`data-model.md` §2.3)
- [ ] T024 [P] [US2] Assert `SendMessageHTTPClient` with `use_grpc=True` includes the field in the stream-endpoint body

### Implementation for User Story 2

- [ ] T025 [US2] Thread the kind through `dispatch` (`router/dispatcher.py`) into `direct_message.send_direct_message(...)`, alongside the existing `ig_comment_fields` pattern
- [ ] T026 [US2] Accept and forward the kind in `SendMessageHTTPClient.send_direct_message` (`router/clients/flows/http/send_message.py`), on both the `/mr/msg/send` payload and the `use_grpc=True` stream body
- [ ] T027 [US2] Accept and forward the kind in `WhatsAppBroadcastHTTPClient.send_direct_message` (`router/clients/flows/http/send_message.py`), placing it at the body top level; confirm `InstagramCommentBroadcastHTTPClient` inherits the behaviour without change
- [ ] T028 [US2] Pass the rationale kind through the production branch of `RationaleObserver.task_send_rationale_message`, where it builds `SendMessageHTTPClient` directly (`router/traces_observers/rationale/observer.py`)
- [ ] T029 [US2] Confirm `FlowsRESTClient.whatsapp_broadcast` (`nexus/internals/flows.py`) forwards the top-level key unchanged through its `body.update(msg)` merge, and that the key cannot be shadowed by an agent-authored `msg` payload

**Checkpoint**: The field is on the wire for every production transport Nexus controls.

---

## Phase 6: User Story 3 — Kind survives a reload (Priority: P3)

**Goal**: Reloading the conversation keeps rationale rendered as rationale instead of as ordinary chat
bubbles.

**Independent Test**: Run a turn with rationale, read the conversation history back, and assert
previously-rationale messages are still identifiable.

**Note**: the write side (T032–T035) and the Nexus read side (T036) are both in this repository.
A customer reload that reads mailroom history instead of `GET /api/<project_uuid>/conversations/` is
the same external dependency as T002, not a missing serializer.

### Tests for User Story 3

- [ ] T030 [P] [US3] Assert `save_inline_message_to_database` persists the kind when given one, and that existing callers that omit it still work unchanged
- [ ] T031 [P] [US3] Assert rows written before this feature read back with a null kind and are returned as-is, so the front falls back to today's rendering (spec US3 scenario 2)

### Implementation for User Story 3

- [ ] T032 [US3] Add a nullable `message_kind` field to `InlineAgentMessage` (`nexus/inline_agents/models.py`) using `MESSAGE_KIND_CHOICES` from T005, `null=True`, **no default** (`data-model.md` §3)
- [ ] T033 [US3] Generate the migration and verify it is metadata-only: additive nullable column, no default, no backfill, no table rewrite — `poetry run python manage.py makemigrations inline_agents && poetry run python manage.py sqlmigrate inline_agents <NNNN>`
- [ ] T034 [US3] Add an optional `message_kind` kwarg to `save_inline_message_to_database` (`router/traces_observers/save_traces.py`), defaulted so every existing caller is unaffected
- [ ] T035 [US3] Pass the rationale kind from `RationaleMessageSender.send_rationale_message` (`router/traces_observers/rationale/handlers.py`) into `save_inline_message_to_database`, and pass `final_response` from `save_inline_trace_events` in the same file, which is the write path for the end-of-turn answer
- [ ] T036 [US3] Expose `message_kind` on `InlineConversationSerializer` (`nexus/logs/api/serializers.py`), served by `InlineConversationsViewset` at `GET /api/<project_uuid>/conversations/` (`nexus/logs/api/routers.py`). Fields today are `id`, `uuid`, `text`, `source_type`, `created_at`. Null stays null so pre-feature rows fall back to today's rendering. If the shopping assistant reloads from mailroom history instead of this endpoint, that gap is T002, not a second serializer to find

**Checkpoint**: The distinction survives a page refresh.

---

## Phase 7: gRPC streaming projects (in scope — spec FR-007)

**Purpose**: Carry the kind on the gRPC stream. Not optional: `is_grpc_enabled`
(`inline_agents/backends/openai/grpc/streaming_client.py`) returns false when components are on, so
streaming is the **non-components** path, and rationale eligibility is independent of it
(`OpenAIBackend.invoke_agents` in `inline_agents/backends/openai/backend.py`). A streaming-enabled
webchat project therefore emits rationale over `/mr/msg/send` and its final response over the gRPC
stream — skipping this phase would leave the final response untagged for exactly the shopping
assistant's profile (`research.md` R3 correction).

- [ ] T037 Let `StreamingSession._create_message` (`inline_agents/backends/openai/grpc/streaming_client.py`) merge a per-message metadata override on top of the session-level `self.metadata`, so a single session can stamp different kinds
- [ ] T038 Pass the final-response kind from `StreamingSession.send_completed` where `OpenAIBackend` closes the turn (`inline_agents/backends/openai/backend.py`)
- [ ] T039 [P] Test the per-message override without changing `message_stream_service.proto` — `map<string, string> metadata` (field 6) already exists on every `StreamMessage`, so no regeneration is needed
- [ ] T039a Check the gRPC error path: `OpenAIBackend._send_grpc_error_message` sends a default error message on failure, which is a terminal message and must be tagged `final_response` like any other

---

## Phase 8: Polish & Handoff

- [ ] T040 [P] Mark `specs/003-rationale-message-kind/contracts/outgoing-message-kind.md` as confirmed once T001 comes back from the front-end team
- [ ] T041 Run the full validation in `quickstart.md` §1 and §3, including the manual preview check
- [ ] T042 Run the final quality gates: `poetry run pre-commit run --all-files` and confirm coverage has not regressed below 75%
- [ ] T043 Share the finalized contract in the [#weni-corner-experience-nexus](https://vtex.slack.com/archives/C0ADFJF6WP8/p1789999017171009) thread and update [NEXUS-6076](https://vtex-dev.atlassian.net/browse/NEXUS-6076)
- [ ] T044 Run `/speckit-constitution` (or the `setup-engineering` skill) for this repository — `.specify/memory/constitution.md` is still the unfilled template, so the plan's Constitution Check was vacuous rather than passing. Not a blocker for this feature; it is a gap for every future one

---

## Dependencies & Execution Order

### Phase dependencies

- **Coordination (Phase 0)**: runs in parallel with everything; blocks no code. T001 can still change the field name, so land it before Phase 3 merges
- **Setup (Phase 1)**: independent, run it first to get an attributable baseline
- **Foundational (Phase 2)**: blocks all user stories
- **US1 (Phase 3)**: needs Phase 2
- **Regression guard (Phase 4)**: needs Phase 3; required before merging anything
- **US2 (Phase 5)**: needs Phase 2; independent of US1, but shipping it without US1 delivers no user-visible value
- **US3 (Phase 6)**: needs Phase 2; write side and the Nexus read side (T036) are both in this repo
- **gRPC (Phase 7)**: needs Phase 2; in scope per FR-007
- **Polish (Phase 8)**: needs every other phase complete

### Within each user story

- Tests are written and failing before implementation
- The shared helper (T005, T006) before any call site
- Model change (T032) before the migration (T033) before the write path (T034, T035)

### Parallel opportunities

- T008–T012 are five different test files or independent test methods — all parallel
- T016 and T017 touch different files (`invoke.py`, `workflow_orchestrator.py`) — parallel
- T019 and T020 are independent regression tests — parallel
- T022–T024 are independent client tests — parallel
- US2 and US3 can be staffed in parallel once Phase 2 lands and their gates are closed

---

## Parallel Example: User Story 1

```bash
# Launch the US1 tests together (all fail before implementation):
Task: "Rationale tagging test in router/traces_observers/tests/test_rationale_message_kind.py"
Task: "dispatch_preview tagging test in router/tasks/tests/test_message_kind_dispatch.py"
Task: "skip_dispatch branch test in router/tasks/tests/test_message_kind_dispatch.py"
Task: "Guardrail refusal test in router/tasks/tests/test_guardrail_block_broadcast.py"
Task: "rationale_switch=False test in router/traces_observers/tests/test_rationale_message_kind.py"

# Then the two independent final-response call sites together:
Task: "Tag final_response in router/tasks/invoke.py"
Task: "Tag final_response in router/tasks/workflow_orchestrator.py"
```

---

## Implementation Strategy

### MVP (User Story 1 only)

1. Send T001 to the front-end team, then keep going — it confirms a decided contract rather than opening one
2. Phase 1 baseline, then Phase 2 foundation
3. Phase 3 (US1) + Phase 4 (regression guard)
4. **STOP and VALIDATE**: `quickstart.md` §3 manual preview check with the front-end team
5. Ship. The front-end can build against a real contract.

### Incremental delivery

1. Foundation → US1 + regression guard → **MVP, preview surface working**
2. US2 → the field is on the wire in production; the front sees it once mailroom forwards it
3. Phase 7 (gRPC) → streaming projects stop being a hole in FR-001
4. US3 → reload keeps the distinction

Each increment is independently shippable and does not break the previous one. If T003 confirms the
shopping assistant is a streaming project, Phase 7 moves ahead of US2 — its final response goes over
the stream, not over HTTP.

### PR split (Graphite stack, 1 task group = 1 PR)

1. Phase 2 + Phase 3 + Phase 4 — the MVP, self-contained and independently reviewable
2. Phase 5 — production HTTP transports
3. Phase 7 — gRPC streaming
4. Phase 6 — model, migration, persistence

Keeping the migration in its own PR matters: it is the only task group with a schema change, and it
should be reviewable and revertible on its own.

---

## Notes

- `[P]` means different files with no dependency on incomplete work
- Tasks name the symbol and the file, not a line number. Line numbers go stale; search for the symbol
- Guardrail refusals need no dedicated implementation task — `_handle_guardrails_block` reuses
  `dispatch` / `dispatch_preview`, so T016 and T025 cover them. T011 exists to prove that.
- Do not infer the kind from message text under any circumstance (spec FR-009). This is a design
  constraint with no direct test; it is enforced at review time.
- SC-005 (no measurable latency change) has no dedicated task by design: the field is a constant string
  added to payloads already being built, with no extra round trip or query. If that stops being true,
  add a task.
