# Feature Specification: Rationale on the Live Answer Stream

**Feature Branch**: `003-rationale-message-kind`

**Created**: 2026-09-28

**Status**: Draft

**Input**: User description: "Reformulate the rationale contract. Do not post each progress update to a second message endpoint. Deliver each progress update as one complete message on the same live stream that already carries the final answer. Streamed pieces and the closing message contain only the final answer. Each progress update carries its order so the shopping assistant can show it as its own loading state."

**Scope**: Nexus backend only, on turns where progressive feedback (rationale) is enabled and the live answer stream is open. The shopping assistant owns how the progress text is drawn. A second connection per turn for the progress text is out of scope.

**Terminology**: **Rationale** (also *progressive feedback*, *racional*) is the short feedback the manager produces while the turn is still working. It is a normal short message, not the model's private reasoning. **Final response** is the answer produced at the end of the turn. **Message kind** says which of the two a delivered message is.

## Clarifications

### Session 2026-09-28

- Q: Field shape — single enum or two booleans? → A: **Single closed enum** `message_kind: "rationale" | "final_response"`.
- Q: Must the kind survive a page reload? → A: **Yes, persist it.** Messages stored before this feature stay without a kind and the consumer falls back to today's rendering.
- Q: Turn interrupted before the final response — extra end-of-turn signal? → A: **No.** The consumer closes the rationale presentation on the first final response or on its own timeout. A failure message that reaches the user is itself a final response.
- Q: "Zero regressions" on channels without rationale — byte-identical payloads? → A: **Identical except for the additive kind on the final answer.** Channels that never show rationale still receive a final response marked as such. Existing keys, values, and delivery behavior stay the same.

### Session 2026-10-06

- Q: Deliver rationale on a second message endpoint while the answer streams? → A: **No.** One live stream per turn. A second connection risks duplicate text and reordered delivery.
- Q: How does a progress update arrive? → A: **One complete message per update**, on that same stream, before the answer pieces. It does not close the stream. It carries `message_kind: rationale` and a 1-based order, `rationale_index`, as text (`"1"`, `"2"`, …).
- Q: What do the answer pieces and the closing message contain? → A: **Only the final answer.** The progress text must not appear inside them. Both declare `message_kind: final_response`. The closing message ends the stream and carries the full final answer.
- Q: Can components and rationale be on together? → A: **No.** Those modes are mutually exclusive. A turn that is not on the live answer stream does not need a parallel rationale channel.
- Q: May the consumer treat the first streamed text as rationale by guessing? → A: **No.** The progress update and the answer are different messages. The consumer switches on kind and order, not on wording or arrival timing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Progress updates stay separate from the answer (Priority: P1)

As a shopper on the shopping assistant, while my request is still being handled I see each short progress update on its own, with a loading treatment, and then I see the real answer stream in. The progress sentence does not reappear as the start of the answer.

**Why this priority**: This is the broken experience. Today the progress sentence and the answer share the same streamed text, so the assistant cannot tell them apart and the audit keeps only the answer.

**Independent Test**: Send a request that makes the manager report progress and then call another agent. Capture the live stream. Assert one complete progress message, then only answer pieces, then one closing message whose text is the answer and not the progress sentence.

**Acceptance Scenarios**:

1. **Given** rationale is enabled and the live answer stream is open, **When** the manager produces a short progress update and then keeps working, **Then** the shopper receives that update once, in full, marked as rationale, and the stream stays open.
2. **Given** that same turn, **When** the answer is produced, **Then** the streamed pieces and the closing message contain only the answer and are marked as the final response.
3. **Given** the progress update was "Vou consultar o status do pedido informado." and the answer was "Não foi possível localizar o pedido.", **When** the turn finishes, **Then** the progress sentence is not a prefix of the streamed answer or of the closing message.
4. **Given** rationale is disabled, **When** the agent answers, **Then** the stream has no rationale message and the answer is marked as the final response.

---

### User Story 2 - Several progress updates stay ordered (Priority: P2)

As the shopping assistant, when a turn reports progress more than once, I can tell the first update from the second and from the last, so each one can be shown in order next to its loading state.

**Why this priority**: A turn can call more than one agent. Without an order, the front cannot tell which update is which.

**Independent Test**: Run a turn that produces two progress updates before the answer. Assert two complete rationale messages, with orders 1 and 2, both before any answer piece, on the same turn.

**Acceptance Scenarios**:

1. **Given** a turn that produces two progress updates, **When** the stream is read, **Then** the first message has order 1 and the second has order 2.
2. **Given** those two updates, **When** the answer starts streaming, **Then** no further rationale message arrives, and neither update's text is inside the answer.
3. **Given** a later turn from the same shopper, **When** it produces a progress update, **Then** that update starts again at order 1.

---

### User Story 3 - Reloading keeps the distinction (Priority: P3)

As a shopper who refreshes the page, I still see past progress updates as progress updates and the answer as the answer.

**Why this priority**: The live presentation delivers most of the value. History should not collapse progress updates into ordinary bubbles after a reload.

**Independent Test**: Finish a turn that had a progress update and an answer, reload the conversation, and assert each stored message still reports the kind it was sent with.

**Acceptance Scenarios**:

1. **Given** a finished turn with a progress update and an answer, **When** the history is read back, **Then** the update is still rationale and the answer is still the final response.
2. **Given** history written before this feature, **When** it is read back, **Then** messages without a kind are returned as they were stored.

---

### Edge Cases

- **Turn interrupted after a progress update**: the update was already delivered and the stream never closes with a final response. No extra end signal is sent. The front closes the loading state on its own timeout. A failure message that is actually delivered is a final response.
- **Several progress updates**: each is its own complete message, in order, and none of them is repeated inside the answer.
- **Rationale enabled but the manager produces no progress text**: the turn delivers only the final response. No empty rationale message is sent.
- **Guardrail block or canned refusal**: the message that reaches the shopper is a final response.
- **Older consumer**: an unrecognized message type or an extra field must not break delivery of the answer. Until the consumer understands rationale messages, those messages may be ignored; the answer stream still completes.
- **Channel that never shows rationale**: no rationale message is produced. The final response still declares its kind.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: On a turn whose answer is delivered on the live stream, every shopper-visible agent message MUST declare its stage as `rationale` or `final_response`.
- **FR-002**: Each progress update MUST be delivered once, in full, as its own message on that same stream. The message type is `rationale`. It MUST carry `message_kind: rationale` and `rationale_index` as a 1-based decimal string. It MUST NOT close the stream.
- **FR-003**: Progress text MUST NOT be delivered as answer pieces. Answer pieces use the existing piece type, carry only final-answer text, and declare `message_kind: final_response`.
- **FR-004**: The turn MUST end with one closing message on that stream. It carries the full final answer, declares `message_kind: final_response`, and closes the stream.
- **FR-005**: The opening of the stream stays as it is today: an empty setup message, with the same session metadata on every following message.
- **FR-006**: A turn MUST NOT open a second connection to deliver progress updates.
- **FR-007**: Order numbers MUST increase by one within a turn and MUST restart at 1 on the next turn.
- **FR-008**: The system MUST NOT ask the consumer to infer rationale from message wording, from "the first text before a pause", or from any other heuristic.
- **FR-009**: Consumers that do not understand `rationale` MUST still receive the answer pieces and the closing message unchanged in text and delivery.
- **FR-010**: Where rationale is disabled, or the manager emits no progress text, the stream MUST contain no rationale message.
- **FR-011**: The kind MUST be stored with the agent message so a reload keeps the distinction. Storage is additive: older messages keep no kind and are returned as stored.
- **FR-012**: Nexus MUST NOT emit an extra end-of-turn signal beyond the closing final-response message.
- **FR-013**: Turns that are not on the live answer stream are unchanged by this reformulation. Components and rationale are mutually exclusive, so those turns do not gain a rationale channel.

### Key Entities

- **Live turn stream**: the single sequence already used to deliver an answer. It opens, may carry zero or more complete progress updates, then answer pieces, then one closing message.
- **Progress update**: one short feedback sentence, delivered whole, with kind `rationale` and an order.
- **Final response**: the answer. Its pieces and its closing message share the kind `final_response`. The closing message holds the full answer text.
- **Stored agent message**: the persisted copy. Gains an optional kind. Absent means the message predates this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of streamed turns with rationale enabled, every progress sentence appears exactly once as a complete rationale message, and 0% of those sentences appear inside the answer pieces or the closing message.
- **SC-002**: The shopping assistant can render each progress update with its loading treatment using only the message type, the kind, and the order, without reading the sentence or guessing from timing.
- **SC-003**: A turn still uses one connection. Progress updates do not add a second send, and answer delivery time is not increased by an extra round trip.
- **SC-004**: Channels that do not show rationale keep today's delivery, aside from the final answer declaring its kind.
- **SC-005**: After a reload, 100% of progress updates and answers stored by this feature are still distinguishable by kind.

## Assumptions

- The shopping assistant already consumes the live answer stream. This feature adds a message type and fields on that stream. It does not add a channel.
- Components and rationale cannot be enabled together. Turns outside the live stream are out of this reformulation.
- The progress text is the short feedback the manager writes for the shopper. It is not private model reasoning, and it is not generated by a separate summarizer in this release.
- How the manager is instructed to produce that sentence can change without changing this delivery contract.
- The shopping assistant team (Paulo Bernardo) implements the new message type on the socket from this contract. If a detail of the payload changes, Nexus tells that team before they rely on it.
- Presentation (loading indicator, styling, replacing the loading state when the answer arrives) is owned by the shopping assistant and is out of scope here.
- A turn has one closing final response. Several progress updates may precede it.

## Dependencies

- **Shopping assistant socket**: must accept the `rationale` message type before, or in the same release as, Nexus starts sending it. If Nexus ships first, those updates are dropped and the answer still completes.
- **Contract already agreed** in the 2026-10-06 exchange: one stream; complete rationale messages with kind and order; answer pieces and the closing message are final response only.
