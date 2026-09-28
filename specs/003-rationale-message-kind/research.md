# Phase 0 Research: Rationale vs Final Response Message Kind

**Feature**: `003-rationale-message-kind` | **Date**: 2026-09-28

## R1 — How rationale reaches the user today

**Finding**: Reasoning summaries from the model become traces in `RunnerHooks.on_llm_end`
(`inline_agents/backends/openai/hooks.py:557-576`), shaped as
`orchestrationTrace.rationale.{text, reasoningId}`. `RationaleObserver.perform`
(`router/traces_observers/rationale/observer.py:96`) consumes the trace, rewrites the text through
Bedrock (`RationaleTextImprover`), and sends it as an **ordinary chat message** via
`RationaleObserver.task_send_rationale_message` (`observer.py:263`).

Production path inside that Celery task:

```python
broadcast = SendMessageHTTPClient(FLOWS_REST_ENDPOINT, FLOWS_SEND_MESSAGE_INTERNAL_TOKEN)  # use_grpc defaults to False
broadcast.send_direct_message(text=text, urns=urns, project_uuid=..., user=..., full_chunks=...)
```

`SendMessageHTTPClient.send_direct_message` with `use_grpc=False` posts to `POST {flows}/mr/msg/send`
with a **flat, closed payload** (`router/clients/flows/http/send_message.py:65-72`):

```python
payload = {"user": user, "project_uuid": project_uuid, "urns": urns, "text": text}
```

Preview path: `_handle_preview_message` (`observer.py:73`) and the tail of the task (`observer.py:292`)
push `{"type": "preview", "content": <text>}` onto the preview websocket.

**Decision**: Tag at `task_send_rationale_message`. It is the single funnel for every rationale message,
both preview and production, and it already knows the stage unambiguously.

**Rationale**: Any tagging done further upstream (hooks, observer handlers) would have to be threaded
through `send_message_callback`, which is user-injectable; the task is the narrow waist.

**Alternatives considered**: Tag inside `RationaleMessageSender.send_rationale_message`
(`handlers.py:36`) — rejected, it delegates to a callback whose implementation varies, so the tag
would be set in one place and consumed in another.

---

## R2 — How the final response reaches the user today

**Finding**: `_run_post_generation` (`router/tasks/workflow_orchestrator.py:377`) ends the turn through
one of three branches:

| Branch | Condition | Sink |
|---|---|---|
| `skip_dispatch` | agent already sent messages itself | preview socket only, `{"type": "broadcast", "message": ..., "fonts": []}` |
| `dispatch_preview` | `preview or preview_websocket` | `router/tasks/invoke.py:285` → preview socket |
| `dispatch` | production | `router/dispatcher.py:12` → `direct_message.send_direct_message(...)` |

`dispatch` receives whichever client `get_action_clients` built (`router/tasks/actions_client.py:17`):

| Client | Endpoint | Payload shape |
|---|---|---|
| `SendMessageHTTPClient` (`use_grpc=False`) | `POST /mr/msg/send` | flat `{user, project_uuid, urns, text}` |
| `SendMessageHTTPClient` (`use_grpc=True`) | `POST /api/v2/internals/messages/stream` | `{urns, project_uuid, channel_uuid, **{"msg": {"text": ...}}}` |
| `WhatsAppBroadcastHTTPClient` | `POST /api/v2/internals/whatsapp_broadcasts` | `{urns, project, **msg}` where `msg` is agent-authored JSON |
| `InstagramCommentBroadcastHTTPClient` | same as above, single text | idem |

A fourth terminal sink exists: `_handle_guardrails_block`
(`workflow_orchestrator.py:183`) sends the refusal through `get_guardrail_block_broadcast_client`
and the same `dispatch` / `dispatch_preview` pair.

**Decision**: Tag at `dispatch` and `dispatch_preview`, plus the `skip_dispatch` preview branch.
Guardrail blocks inherit the tag for free because they reuse `dispatch`/`dispatch_preview`.

**Rationale**: These three call sites cover every terminal message of a turn and nothing else. Tagging
inside the individual HTTP clients would mean touching four classes and would not distinguish a
rationale send from a final send, since `SendMessageHTTPClient` serves both.

**Alternatives considered**: Tagging inside `send_direct_message` implementations — rejected, the
clients are shared between the rationale path and the final path, so they cannot tell the stages apart
without being told.

---

## R3 — Can the field survive the transport?

**Finding**: Three different transports, three different answers.

1. **Preview websocket** (`nexus/projects/websockets/consumers.py:158`) — `message_data` is a free-form
   dict serialized straight to JSON by `preview_message`. **Adding a key is free and entirely inside
   Nexus.**
2. **`POST /mr/msg/send`** — the payload dict is built literally in `send_message.py:67` and the
   receiver is mailroom. An extra key here is a **cross-team change**: Nexus can send it, but nothing
   guarantees mailroom forwards it to the webchat socket. Unknown keys are typically ignored, so
   sending one is safe but not sufficient.
3. **gRPC stream** (`inline_agents/backends/openai/grpc/`) — `StreamMessage` already carries
   `map<string, string> metadata` (field 6 in `message_stream_service.proto`) on **every** message, and
   `type` already separates `setup` / `delta` / `completed`. `StreamingSession._create_message`
   (`streaming_client.py:91`) currently stamps one session-level `self.metadata` on all messages.
   Note this path is **opt-in per project** via `GRPC_ENABLED_PROJECTS` and only when
   `use_components=False and stream_support=True` (`streaming_client.py:25`).

**Critical asymmetry**: with gRPC streaming on, the **final response goes through the gRPC stream**
(`backend.py:599`, `send_completed`) while **rationale still goes through `/mr/msg/send`**. The two
stages already travel on different transports in production. A single uniform field is therefore not
automatically visible to one consumer.

**Decision**: Ship the preview websocket first (self-contained, testable this sprint, satisfies SC-004),
send the field on `/mr/msg/send` and the broadcast/stream `msg` dict as a best-effort additive key,
cover the gRPC stream via its existing `metadata` map, and open a dependency with the Flows/mailroom
owners for the production webchat passthrough.

**Rationale**: It unblocks the front-end contract validation immediately without waiting on another
team, and it matches the spec's FR-008 (silent degradation).

**Correction after `/speckit-analyze` (2026-09-28)**: the first draft of this decision left gRPC
streaming out of scope. That was wrong and contradicted FR-001. `is_grpc_enabled` returns false when
`use_components` is true, so **streaming is the non-components path**, and rationale eligibility is
independent of both (`backend.py:349` — rationale switch, GPT manager model, webchat/preview channel).
A streaming-enabled webchat project therefore runs rationale **and** gRPC at once, which is the
shopping assistant's own likely profile. Excluding it would have left the final response untagged for
exactly the consumer this feature is for. gRPC is now in scope (spec FR-007).

**Alternatives considered**:
- gRPC `metadata` only — rejected as the *sole* transport: narrower reach (allowlisted projects only)
  and it does not carry rationale at all today. It is now additive to the other transports, not a
  replacement.
- A brand-new socket event type for rationale — rejected, it breaks FR-004 (additive only) and would
  force the front to merge two ordered streams.

---

## R4 — Field shape

**Finding**: The Slack thread (Mardone, 2026-09-22) proposed "uma flag de finalresponse e uma de
racional". The codebase has no precedent for either shape on outgoing messages; the closest analogue is
`is_final_output` in `router/tasks/sqs_message_events.py:64`, an **internal** agent-tool flag, not a
wire contract.

**Decision**: A single closed enum, `message_kind: "rationale" | "final_response"`. **Confirmed in
`/speckit-clarify`** and now binding as spec FR-010.

**Rationale**: Two independent booleans admit two meaningless states (`both true`, `both false`) that
the front would have to defend against. An enum is exhaustive, extensible (a future `tool_progress`
kind costs nothing), and switch-friendly.

**Alternatives considered**: `is_rationale` / `is_final_response` booleans — matches the thread verbatim
and may slot into an existing front-end field. Deferred to the front-end team's call.

---

## R5 — Persistence across reload

**Finding**: Rationale is persisted like any other agent turn output.
`RationaleMessageSender.send_rationale_message` calls `save_inline_message_to_database`
(`router/traces_observers/save_traces.py:151`) with `source_type="agent"`. `InlineAgentMessage`
(`nexus/inline_agents/models.py:227`) has no column that distinguishes the stage:

```python
created_at, uuid, text, project, session_id, contact_urn, source_type, source
```

So a live-only flag is **provably lost on reload** — history cannot reconstruct which messages were
rationale.

**Decision**: Persist. A nullable column on `InlineAgentMessage` plus a backfill-free migration
(existing rows stay `NULL` → front falls back to today's rendering, per spec acceptance scenario
US3-2). **Confirmed in `/speckit-clarify`** and now binding as spec FR-012.

**Rationale**: The migration is cheap and additive (nullable `CharField`, no default rewrite, no lock on
a large table), and a live-only flag would be provably lost on every page refresh.

**Alternatives considered**: Derive the kind at read time from trace data — rejected, traces are stored
as JSONL in object storage keyed by message UUID (`InlineAgentMessage.trace_path`) and reading them to
render history would be far more expensive than a column.

---

## R6 — Testing approach

**Finding**: The repo runs Django's test runner under coverage with a 75% floor
(`.pre-commit-config.yaml` `check-coverage`; canonical command
`poetry run coverage run --source='.' manage.py test`). Existing tests for these exact paths already
exist and are the natural extension points:

- `router/tasks/tests/test_guardrail_block_broadcast.py` — asserts which client each branch of
  `_run_post_generation` picks, including a `preview_websocket` case.
- `inline_agents/backends/openai/tests/` — adapter/backend/hook coverage.
- `router/traces_observers/` has no dedicated rationale-send test yet; one will be added.

**Decision**: Unit-test the tagging at each of the four call sites, plus one integration-style test that
walks a turn and asserts the emitted sequence is `rationale*` then `final_response`.

**Rationale**: The failure mode this feature must prevent is a mis-tagged or untagged message, which is
exactly what a per-call-site assertion catches.

---

## R7 — Where history is read back

**Finding**: **Unresolved.** FR-012 requires the persisted kind to be visible when conversation history
is read back, but no read path has been identified. `InlineAgentMessage` is written by
`save_inline_message_to_database`; the serializer or endpoint that serves this history to the shopping
assistant has not been located, and it may live outside this repository.

**Decision**: Treat this as a research task during implementation, not a design decision. The write
side (column + migration + write path) is fully specified and can land independently of the read side.

**Rationale**: The persistence decision is settled; only its consumer is unknown. Blocking the column on
an unlocated serializer would stall work that is otherwise ready.

---

## Questions resolved in `/speckit-clarify` (session 2026-09-28)

| Spec ref | Question | Resolution |
|---|---|---|
| FR-010 | Enum vs two booleans | Enum `message_kind` (R4) |
| FR-011 | Preview only, or preview + production | Both; production best-effort pending mailroom (R3) |
| FR-012 | Persist the kind in history | Persist, nullable column (R5) |
| FR-013 | Explicit end-of-turn signal? | No signal; consumer closes on `final_response` or timeout |
| FR-007 | gRPC streaming in scope? | Yes — reversed after `/speckit-analyze`, see the correction in R3 |
| SC-003 | "Identical payloads" — literally? | Identical except the one additive field |

## Still open

| Ref | Question | Owner |
|---|---|---|
| R7 | Which serializer/endpoint serves conversation history to the shopping assistant? | Implementation-time research |
| — | Is the shopping assistant project actually in `GRPC_ENABLED_PROJECTS`? Env-configured, not visible in the repo | Deploy/infra |
