# Contract: `message_kind` on outgoing agent messages

**Feature**: `003-rationale-message-kind` | **Status**: Decided (spec FR-010, `/speckit-clarify` 2026-09-28) — pending confirmation with the front-end team
**Consumers**: shopping assistant front-end (Cristian / Paulo Bernardo), Agent Builder preview
**Producer**: Nexus AI

---

## 1. The field

```
name:     message_kind
type:     string (closed enum)
values:   "rationale" | "final_response"
required: producer MUST set it on every outgoing agent message in scope
          consumer MUST tolerate its absence (legacy messages, out-of-scope transports)
```

### Semantics

| Value | The consumer should render it as |
|---|---|
| `rationale` | Intermediate "thinking" content, in the dedicated rationale presentation. More messages are coming. |
| `final_response` | The answer. Normal chat bubble. The turn is over, unless more `final_response` parts follow immediately. |
| *absent* | Unknown stage. Fall back to current behaviour (render as a normal chat message). |

### Rules

1. **Additive only.** No existing field changes name, type, position, or meaning.
2. **Never inferred.** The value comes from the code path that emitted the message, never from the text.
3. **A split answer is still final.** When the answer arrives as several messages, every one is tagged
   `final_response`. The consumer MUST NOT assume exactly one.
4. **Guardrail refusals are `final_response`.** They are terminal messages to the user.
5. **No `final_response` is not an error.** An interrupted turn can end after rationale messages, and
   Nexus emits **no end-of-turn signal** in that case (spec FR-013). The consumer MUST close the
   rationale block on the first `final_response` or on its own timeout. Note that an agent failure
   already produces a default error message, which is itself a `final_response`.
6. **Unknown values.** If a future release adds a kind, consumers MUST fall back to normal rendering
   rather than dropping the message.

### Ordering guarantee

Within a turn, all `rationale` messages precede all `final_response` messages. Nexus does not
interleave them.

---

## 2. Wire examples

### 2.1 Preview websocket — in scope, testable end to end inside Nexus

Field sits at the envelope level, sibling of `content`. `content` is polymorphic and is not a safe
place to attach it.

```jsonc
// rationale
{
  "type": "preview",
  "content": "Estou verificando o status do seu pedido...",
  "message_kind": "rationale"
}

// final response
{
  "type": "preview",
  "content": {"type": "broadcast", "message": "Seu pedido 123 saiu para entrega.", "fonts": []},
  "message_kind": "final_response"
}
```

Note the socket frame itself is `{"type": "preview", "message": <the object above>}` — the consumer
reads `message.message_kind`.

### 2.2 `POST /mr/msg/send` — best-effort, needs mailroom passthrough

```jsonc
{
  "user": "...",
  "project_uuid": "...",
  "urns": ["ext:webchat-contact-id"],
  "text": "Estou verificando o status do seu pedido...",
  "message_kind": "rationale"
}
```

### 2.3 Broadcast / stream body — best-effort

Top level of the body, never inside `msg` (which is agent-authored and may be a list).

```jsonc
{
  "urns": ["ext:..."],
  "project_uuid": "...",
  "channel_uuid": "...",
  "msg": {"text": "Seu pedido 123 saiu para entrega."},
  "message_kind": "final_response"
}
```

### 2.4 gRPC `StreamMessage` — in scope, for streaming-enabled projects

Uses the existing `map<string, string> metadata` field. No `.proto` change, no stub regeneration.
Relevant because streaming is the **non-components** path and rationale runs independently of it, so a
streaming-enabled webchat project delivers its final response here while its rationale goes over the
message endpoint.

```
StreamMessage {
  type: "completed"
  content: "Seu pedido 123 saiu para entrega."
  metadata: { "message_kind": "final_response" }
}
```

---

## 3. Compatibility

| Consumer | Behaviour after this change |
|---|---|
| Shopping assistant front (updated) | Switches on `message_kind`, renders the dedicated rationale UI |
| Shopping assistant front (not yet updated) | Ignores the unknown key, renders exactly as today |
| WhatsApp / Instagram / flows | Unaffected — they never receive rationale, and the extra key is ignored downstream |
| Agent Builder preview (not yet updated) | Ignores the unknown key, renders exactly as today |

**Degradation requirement (spec FR-008)**: if a downstream transport rejects or strips the field,
message delivery MUST be unchanged — same content, same ordering, no error surfaced to the user.

---

## 4. Decisions taken

| # | Question | Decision | Spec ref |
|---|---|---|---|
| 1 | Enum, or the two booleans from the Slack thread? | **Enum `message_kind`.** Two independent booleans admit `both true` and `both false`, two states with no meaning that the consumer would have to defend against | FR-010 |
| 2 | Production webchat in scope, or preview only? | **Both.** Nexus emits the field on every path it controls; production reaches the front once mailroom forwards it, and degrades silently until then | FR-007, FR-011 |
| 3 | Must the kind survive a page reload? | **Yes.** Persisted as a nullable column; pre-existing rows stay null | FR-012 |
| 4 | Explicit end-of-turn signal on an interrupted turn? | **No.** Consumer closes on `final_response` or its own timeout | FR-013 |
| 5 | Are gRPC streaming projects in scope? | **Yes.** Streaming is the non-components path and coexists with rationale; excluding it would leave the final response untagged for the shopping assistant's own profile | FR-007 |

## 5. Remaining action

Confirm this contract with the shopping assistant front-end team (Cristian / Paulo Bernardo) before
implementation starts, so both sides ship against the same document.
