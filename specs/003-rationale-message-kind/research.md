# Research: Rationale on the Live Answer Stream

**Date**: 2026-10-06
**Spec**: [spec.md](spec.md)

## 1. Where the progress sentence goes today

**Decision**: Treat the short feedback as assistant text on the OpenAI stream, and stop forwarding that text as answer deltas.

**Rationale**: With rationale enabled, the manager writes a short shopper-facing sentence and then calls a tool or agent. `OpenAIBackend._process_delta_event` forwards every `ResponseTextDeltaEvent` through `StreamingSession.send_delta` with no kind. The same `msg_id` later receives `send_completed` with only `result.final_output`. The socket therefore shows the progress sentence and then replaces it with the answer. That sentence is not `reasoning.summary`, and the OpenAI path does not post it to `/mr/msg/send`. `RationaleObserver` listens to `inline_trace_observers` (Bedrock). OpenAI notifies `inline_trace_observers_async`, so the REST rationale sender never runs for this stream.

**Alternatives considered**:

- Keep tagging `/mr/msg/send` and leave the stream as it is. Rejected: the sentence the shopper sees is already on the stream, and a second connection can duplicate or reorder it (spec FR-006).
- Read `reasoning.summary`. Rejected: that is not the historical sentence, and the stream does not deliver it.

## 2. How to tell progress text from the answer

**Decision**: Hold assistant text for the current model response. If a `tool_call_item` arrives before that text is released, emit the hold once as a complete `rationale` message and do not emit those tokens as deltas. If the response ends with no tool call, release the hold as `delta` messages, then send `completed` with the full final text.

**Rationale**: The model already produces the sentence before the tool call. The stream loop in `_invoke_agents_async` already observes `tool_call_item`. Holding until that event, or until the response ends, is enough to satisfy SC-001 without a new tool and without changing the progressive-feedback instruction. The final answer is still `result.final_output`, which is the last assistant output, so `completed` does not need the held progress text removed from it.

**Alternatives considered**:

- An internal `send_progress_update` tool plus a prompt that forbids interim assistant text. Rejected for this release: it adds a tool the model must remember to call, and it depends on a prompt change. The delivery contract does not require it. Revisit only if holding text makes the final answer arrive too late to be useful as deltas.
- Guess from wording or from a pause. Rejected: spec FR-008.

## 3. Wire shape

**Decision**: Do not change `message_stream_service.proto`. `type` is a free string and `metadata` is `map<string, string>`.

| Message | `type` | Closes the stream | Extra metadata |
|---|---|---|---|
| Open | `setup` | no | session metadata only (`session_id`, `language`) |
| Progress | `rationale` | no | `message_kind=rationale`, `rationale_index` as `"1"`, `"2"`, … |
| Answer piece | `delta` | no | `message_kind=final_response` |
| Close | `completed` | yes | `message_kind=final_response` |

Session metadata is merged into every message, including the new ones. `rationale_index` restarts at 1 for each stream, because each stream is one turn.

**Rationale**: Paulo Bernardo accepted this payload on 2026-10-06 as the socket contract. An unknown `type` can be ignored; the answer pieces and the closing message stay on the types the socket already handles (spec FR-009).

**Alternatives considered**: A new proto field. Rejected: the map already carries string metadata, and a proto change forces a coordinated regenerate.

## 4. What stays off this stream

**Decision**: Turns that do not open the live stream are unchanged. That includes preview (`grpc_session` is created only when `not preview`) and components (`is_grpc_enabled` is false when `use_components` is true). Components and rationale stay mutually exclusive (spec FR-013). Bedrock rationale delivery is unchanged.

**Rationale**: The shopping assistant socket is the consumer that asked for this contract. Opening a rationale channel on preview or on the REST path would be the second connection the spec forbids.

## 5. Persistence

**Decision**: Add nullable `message_kind` and `rationale_index` on `InlineAgentMessage`. Write one row when a rationale message is emitted, and stamp `final_response` on the row that already stores the answer. `InlineConversationSerializer` exposes the fields and omits them when null.

**Rationale**: Spec FR-011 and user story 3. `save_inline_message_to_database` is the existing write path. A nullable column leaves rows written before this feature without a kind. No backfill.

**Alternatives considered**: Store the kind only on the socket. Rejected: a reload of Nexus history would collapse the distinction. Store it on `MessageLog.llm_response`. Rejected: that column is one answer per turn, not one row per progress update.
