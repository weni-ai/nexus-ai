# Data Model: Rationale on the Live Answer Stream

**Date**: 2026-10-06
**Spec**: [spec.md](spec.md)

## 1. Stream messages

One `StreamMessage` sequence per turn. Same `msg_id` for the whole sequence. Proto fields are unchanged.

| Field | Setup | Rationale | Delta | Completed |
|---|---|---|---|---|
| `type` | `setup` | `rationale` | `delta` | `completed` |
| `content` | empty | full progress sentence | one answer token chunk | full final answer |
| `metadata.session_id` | yes | yes | yes | yes |
| `metadata.language` | yes | yes | yes | yes |
| `metadata.message_kind` | absent | `rationale` | `final_response` | `final_response` |
| `metadata.rationale_index` | absent | `"1"`, `"2"`, … | absent | absent |
| Closes the stream | no | no | no | yes |

Rules:

- `message_kind` is only `rationale` or `final_response`.
- `rationale_index` is a decimal string, 1-based, contiguous within the turn, restarted on the next turn.
- An empty progress sentence produces no rationale message.
- Progress text never appears in a `delta` or in `completed.content`.
- A failure message that is actually delivered uses `delta` + `completed` with `final_response` and no rationale message.

## 2. Stored agent message

`nexus.inline_agents.models.InlineAgentMessage` gains two nullable columns:

| Column | Type | Null | Meaning when null |
|---|---|---|---|
| `message_kind` | `CharField(max_length=32)` | yes | Row predates this feature, or the writer did not know the stage |
| `rationale_index` | `PositiveIntegerField` | yes | Not a rationale row |

Validation:

- `message_kind`, when set, is `rationale` or `final_response`.
- `rationale_index` is set only when `message_kind` is `rationale`, and then it is `>= 1`.
- A final-response row leaves `rationale_index` null.

One rationale row is inserted per emitted rationale message, with the same text. The existing answer row is written as today and stamped `final_response`.

Migration is additive: new columns, no default that rewrites old rows, no data migration.

## 3. History read

`InlineConversationSerializer` (`nexus/logs/api/serializers.py`) adds `message_kind` and `rationale_index`. Both are omitted from the payload when null, so older rows stay as they were stored.

## 4. State of one turn

```text
setup
  → zero or more rationale messages (index 1..N)
  → zero or more final-response deltas
  → one final-response completed   (closes)
```

If the turn dies after a rationale message, the stream ends without `completed`. Nothing else is sent.

## 5. Out of scope for this model

- Preview websocket frames.
- `/mr/msg/send` bodies.
- Bedrock rationale rows, except that new writes of the final answer on the OpenAI stream carry `message_kind`.
