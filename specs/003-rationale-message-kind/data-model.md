# Phase 1 Data Model: Rationale vs Final Response Message Kind

**Feature**: `003-rationale-message-kind` | **Date**: 2026-09-28

> Field name and value set are settled by spec FR-010 (`/speckit-clarify`, session 2026-09-28):
> `message_kind`, values `rationale` and `final_response`.

## 1. `MessageKind` — value object

A closed set of stage classifications for an outgoing agent message. Not persisted as a table; a
module-level constant set (`router/entities/` or alongside the dispatcher).

| Value | Meaning | Emitted by |
|---|---|---|
| `rationale` | Intermediate progressive-feedback text; the turn is still running | `RationaleObserver.task_send_rationale_message` |
| `final_response` | Terminal message of the turn, including guardrail refusals and every part of a split answer | `dispatch`, `dispatch_preview`, `_run_post_generation` skip-dispatch branch, `grpc_session.send_completed` |

**Validation rules**

- Closed set. An unrecognized value is a programming error, not user input.
- Never inferred from message text (spec FR-009).
- Absent means "legacy / unknown" for consumers; producers in scope must always set it.

**State transitions within a turn**

```
turn start
  └─> rationale*        (zero or more, only on rationale-capable surfaces)
        └─> final_response+   (one or more messages, all tagged final_response)
```

A turn may end without `final_response` if it is interrupted, and **no end-of-turn signal is emitted**
in that case (spec FR-013). A turn may emit zero `rationale` messages (rationale disabled, non-GPT
manager model, unsupported channel, or no reasoning summary produced).

---

## 2. Outgoing message payloads — per transport

The field is **additive**; every existing key keeps its name, type, and meaning (spec FR-004).

### 2.1 Preview websocket (in scope, fully owned by Nexus)

Producer: `send_preview_message_to_websocket(project_uuid, message_data, user_email)`
(`nexus/projects/websockets/consumers.py:158`). The consumer emits `{"type": ..., "message": ...}`
verbatim, so `message_data` is the contract surface.

Rationale — today vs after:

```jsonc
// before
{"type": "preview", "content": "Estou verificando seu pedido..."}
// after
{"type": "preview", "content": "Estou verificando seu pedido...", "message_kind": "rationale"}
```

Final response — today vs after:

```jsonc
// before
{"type": "preview", "content": {"type": "broadcast", "message": "...", "fonts": []}}
// after
{"type": "preview", "content": {"type": "broadcast", "message": "...", "fonts": []}, "message_kind": "final_response"}
```

**Placement rule**: sibling of `content`, not inside it. `content` is polymorphic — a bare string for
rationale, a broadcast object for the final response, an agent-authored component list when
`use_components` is on. Only the envelope is stable enough to hold the field.

### 2.2 `POST /mr/msg/send` (best-effort, needs mailroom passthrough)

Producer: `SendMessageHTTPClient.send_direct_message` with `use_grpc=False`
(`router/clients/flows/http/send_message.py:65`). Flat payload:

```jsonc
{"user": "...", "project_uuid": "...", "urns": ["ext:..."], "text": "...", "message_kind": "rationale"}
```

Carries **both** kinds: rationale always, and the final response whenever gRPC streaming is off.

### 2.3 Broadcast / stream `msg` dict (best-effort)

Producers: `WhatsAppBroadcastHTTPClient`, `InstagramCommentBroadcastHTTPClient`, and
`SendMessageHTTPClient` with `use_grpc=True`. `FlowsRESTClient.whatsapp_broadcast`
(`nexus/internals/flows.py:83`) merges the `msg` dict into the request body, so the field rides
alongside `msg`:

```jsonc
{"urns": [...], "project_uuid": "...", "channel_uuid": "...", "msg": {"text": "..."}, "message_kind": "final_response"}
```

**Placement rule**: top level of the body, not inside `msg`. `msg` is agent-authored content parsed by
`format_message_for_openai` / `get_json_strings` and may be a list; injecting into it risks colliding
with component payloads.

### 2.4 gRPC `StreamMessage` (in scope — spec FR-007)

`message_stream_service.proto` already declares `map<string, string> metadata = 6` on every
`StreamMessage`. `StreamingSession._create_message` (`streaming_client.py:91`) stamps a single
session-level `self.metadata`; carrying a per-message kind means letting that method merge a
per-call override. **No `.proto` change and no regeneration required.**

This path matters more than its allowlist suggests: `is_grpc_enabled` (`streaming_client.py:25`)
returns false when `use_components` is true, so streaming is the **non-components** path, and rationale
eligibility is independent of it. A streaming-enabled webchat project emits rationale over
`/mr/msg/send` **and** the final response over the gRPC stream — leaving this transport out would leave
the final response untagged for exactly the shopping assistant's profile.

---

## 3. `InlineAgentMessage` — persistence (in scope — spec FR-012)

Current model (`nexus/inline_agents/models.py:227`) has no stage column.

**Proposed additive field**

| Field | Type | Null | Default | Notes |
|---|---|---|---|---|
| `message_kind` | `CharField(max_length=32, choices=MESSAGE_KIND_CHOICES)` | yes | `None` | `NULL` = written before this feature |

**Migration characteristics**

- Additive nullable column, no default → PostgreSQL metadata-only change, no table rewrite, no long
  lock. Safe on a large table.
- No backfill. Pre-existing rows stay `NULL`, which the front reads as "legacy" and renders the old way
  (spec US3 acceptance scenario 2).
- Write sites: `save_inline_message_to_database` (`router/traces_observers/save_traces.py:151`) gains an
  optional `message_kind` kwarg, defaulted so existing callers are unaffected.

**Read site**: whichever endpoint serves conversation history to the shopping assistant must expose the
column. That serializer has **not been located yet** (`research.md` R7) and may live outside this
repository. Identifying it is a task in `tasks.md`; the write side can land independently.

---

## 4. Non-entities (explicitly unchanged)

- Rationale text generation, rewriting, and throttling (`RationaleTextImprover`, `RationaleValidator`,
  `redis_task_manager` session state) — untouched.
- Trace payloads (`orchestrationTrace.rationale`, `trace_update` websocket events from
  `router/traces_observers/summary.py`) — untouched. Traces are a debugging surface, not the chat
  stream the front renders.
- Channel eligibility (`supports_progressive_feedback`) — untouched. This feature labels messages, it
  does not change who receives rationale.
