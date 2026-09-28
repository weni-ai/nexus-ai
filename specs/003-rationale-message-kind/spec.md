# Feature Specification: Rationale vs Final Response Message Kind

**Feature Branch**: `003-rationale-message-kind`

**Created**: 2026-09-28

**Status**: Draft

**Input**: [NEXUS-6076](https://vtex-dev.atlassian.net/browse/NEXUS-6076) — Slack thread [#weni-corner-experience-nexus](https://vtex.slack.com/archives/C0ADFJF6WP8/p1789999017171009) (Cristian, 2026-09-21): the shopping assistant front cannot tell a rationale message apart from the final answer; they are building a dedicated rationale presentation and need Nexus to signal, per outgoing message, which stage it belongs to. Mardone confirmed Nexus already knows the stage and proposed "a flag for final response and one for rationale".

**Scope**: Nexus backend only — tagging outgoing agent messages with the stage that produced them, on the channels where progressive feedback (rationale) is enabled. Front-end rendering of the rationale is owned by the shopping assistant team. Any passthrough required in Flows/mailroom is a dependency tracked here, not implemented here.

**Terminology**: **Rationale** (also *progressive feedback*, *racional*) is the intermediate "thinking out loud" text Nexus emits while the agent is still working. **Final response** is the answer produced at the end of the turn. **Message kind** is the new signal that says which of the two an outgoing message is.

## Clarifications

### Session 2026-09-28

- Q: Field shape — single enum or the two booleans proposed in the Slack thread? → A: **Single closed enum** `message_kind: "rationale" | "final_response"`. Two independent booleans admit two meaningless states (both true, both false) that the consumer would have to defend against; the enum is exhaustive and extensible.
- Q: Which delivery surfaces are in scope for this release? → A: **Preview socket plus the production path, best-effort.** Nexus puts the field on the wire everywhere it controls; reaching the production shopping assistant still depends on Flows/mailroom forwarding it, and delivery degrades silently until then.
- Q: Are gRPC streaming projects in scope? → A: **Yes.** Initially excluded, then included after `/speckit-analyze` found the exclusion contradicted FR-001. gRPC streaming is the path taken when components are **off** (`is_grpc_enabled` returns false when `use_components` is true), and rationale eligibility is independent of it — it depends only on the rationale switch, a GPT manager model, and a webchat/preview channel. So a streaming-enabled webchat project has **both**: rationale over the message endpoint and the final response over the gRPC stream. Excluding it would leave the final response untagged for exactly the shopping assistant's own profile. Cost is low: `StreamMessage.metadata` already exists in the proto.
- Q: Must the kind survive a page reload? → A: **Yes, persist it.** Additive nullable column on the stored agent message; rows written before this feature stay null and the consumer falls back to today's rendering.
- Q: Turn interrupted before the final response — does Nexus emit an explicit end-of-turn signal? → A: **No extra signal.** The consumer closes the rationale block on the first `final_response` or on its own timeout. Nexus already sends a default error message on failure, which is itself a `final_response`.
- Q: "Zero regressions" on channels without rationale — does it mean byte-identical payloads? → A: **Identical except for the additive field.** The field is emitted uniformly, including on channels that never produce rationale, so the contract stays uniform. Everything else about those payloads — keys, values, ordering, delivery behavior — is unchanged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Front distinguishes rationale from final answer (Priority: P1)

As the shopping assistant front-end, when I receive agent messages over the socket during a turn, I need each message to declare whether it is rationale or the final response, so I can render the rationale in its dedicated presentation and the final answer as a normal chat message.

**Why this priority**: This is the whole request. Without it the front has no way to separate the two, which is what blocks the new rationale UI.

**Independent Test**: Run a turn on a channel that emits rationale, capture the outgoing messages, and assert that every message carries a kind and that the kinds match the actual sequence (rationale messages first, final response last). Delivers the full value on its own.

**Acceptance Scenarios**:

1. **Given** a project with rationale enabled on a rationale-capable channel, **When** the agent emits an intermediate rationale message, **Then** the outgoing message declares the kind `rationale`.
2. **Given** the same turn, **When** the agent emits the answer at the end of the turn, **Then** the outgoing message declares the kind `final_response`.
3. **Given** a turn that emits three rationale messages before the answer, **When** the front receives them, **Then** the first three declare `rationale` and only the last declares `final_response`.
4. **Given** a project with rationale disabled, **When** the agent answers, **Then** the single outgoing message declares `final_response` and no message declares `rationale`.
5. **Given** a consumer that ignores the new signal, **When** it receives either kind, **Then** the message text and existing payload fields are unchanged and the consumer keeps working.

---

### User Story 2 - Kind survives across the whole rationale-capable surface (Priority: P2)

As the shopping assistant team, I need the kind to be present on every outgoing agent message on the surfaces where rationale exists, not only on a subset, so the front does not have to guess when the signal is missing.

**Why this priority**: A partially tagged stream is worse than none: the front would need a fallback heuristic anyway. But it only matters once P1 works on at least one surface.

**Independent Test**: Exercise each rationale-capable surface (Agent Builder preview and production webchat) and assert no outgoing agent message arrives without a kind.

**Acceptance Scenarios**:

1. **Given** the Agent Builder preview, **When** a turn produces rationale and a final answer, **Then** both kinds reach the preview socket.
2. **Given** production webchat, **When** a turn produces rationale and a final answer, **Then** both kinds reach the front, provided the downstream message transport forwards the field.
3. **Given** a channel where rationale is not emitted (for example WhatsApp), **When** the agent answers, **Then** behavior is unchanged apart from the final answer declaring `final_response`.
4. **Given** the downstream transport does not yet forward the field, **When** a turn runs in production, **Then** messages are still delivered normally with their existing content and no error is raised.

---

### User Story 3 - Reloading the conversation keeps the distinction (Priority: P3)

As a shopping assistant user who refreshes the page mid-conversation, I want the rationale blocks to keep their dedicated presentation instead of turning into ordinary chat bubbles.

**Why this priority**: Rationale messages are persisted as ordinary agent messages today, so a live-only signal is lost on reload. This is a real inconsistency, but the new presentation delivers most of its value live, so it can follow P1.

**Independent Test**: Run a turn with rationale, reload the conversation history, and assert the previously-rationale messages are still identifiable as rationale.

**Acceptance Scenarios**:

1. **Given** a finished turn with rationale and a final answer, **When** the conversation history is read back, **Then** each stored agent message still reports the kind it was sent with.
2. **Given** history recorded before this feature, **When** it is read back, **Then** messages without a kind are returned as-is and the front falls back to today's rendering.

---

### Edge Cases

- **Turn interrupted before the answer**: rationale messages were already sent, the final response never is. No end-of-turn signal is emitted (FR-013); the front closes the rationale block on its own timeout. Note that an agent failure already produces a default error message, which is itself a `final_response`.
- **Answer split into several messages**: when the final answer is delivered as more than one message (components, multiple chat bubbles), every one of them declares `final_response`, not just the last.
- **Guardrail block / canned refusal**: the turn ends with a blocking message instead of an agent answer. It is a terminal message to the user and declares `final_response`.
- **Rationale enabled but the model emits no reasoning summary**: the turn produces only a final response; no empty rationale message is emitted.
- **Consumer on an older version**: an unknown extra field must never break parsing or delivery for existing consumers (WhatsApp, Instagram, flows).
- **Kind on a channel that never shows rationale**: the field is still populated for the final response so the contract is uniform, but no rationale message is ever produced there.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every outgoing agent message produced by a turn MUST declare which stage produced it: rationale or final response.
- **FR-002**: Messages emitted by the progressive-feedback/rationale path MUST declare the `rationale` kind.
- **FR-003**: Messages emitted by the end-of-turn dispatch path MUST declare the `final_response` kind, including when the answer is split into multiple messages and including terminal blocking messages.
- **FR-004**: The signal MUST be an additive field on the existing outgoing payload. Existing fields, message text, and ordering MUST NOT change.
- **FR-005**: Consumers that do not read the new field MUST keep working unchanged, on every channel.
- **FR-006**: The signal MUST be emitted on the Agent Builder preview socket.
- **FR-007**: The signal MUST be emitted on every production send path Nexus controls, including the streaming path used by projects with gRPC streaming enabled, so it can reach the shopping assistant once the downstream transport forwards it.
- **FR-008**: Where the downstream transport does not forward the field, message delivery MUST degrade silently: same delivery, same content, no error.
- **FR-009**: The system MUST NOT infer the kind from message content or text heuristics; the kind comes from the stage that emitted the message.
- **FR-010**: The signal MUST be a single field named `message_kind`, carrying a closed set of string values: `rationale` and `final_response`. Consumers MUST tolerate the field being absent (legacy messages) and MUST fall back to normal rendering on an unrecognized value.
- **FR-011**: Reaching the production shopping assistant additionally requires Flows/mailroom to forward the field. Nexus MUST NOT block on that: it emits the field regardless, and production degrades per FR-008 until the passthrough exists.
- **FR-012**: The kind MUST be persisted alongside the stored agent message so conversation history keeps the distinction after a reload. Persistence MUST be additive and nullable: messages stored before this feature keep no kind and are returned as-is.
- **FR-013**: Nexus MUST NOT emit an explicit end-of-turn signal. A turn that is interrupted after rationale simply produces no `final_response`, and consumers close the rationale block on the first `final_response` or on their own timeout.

### Key Entities

- **Outgoing agent message**: the unit delivered to the end user during a turn. Gains one additive attribute, `message_kind`, describing the stage that produced it. Everything else about it is unchanged.
- **Message kind**: the stage classification, carried as `message_kind`. Two values in this release: `rationale` and `final_response`. Closed and explicit so the front can switch on it.
- **Stored agent message**: the persisted record of an outgoing message. Gains a nullable copy of the kind so history reads keep the distinction; null means "written before this feature".
- **Turn**: one user input and the agent work it triggers. Produces zero or more rationale messages followed by one final response (possibly split into several messages).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of turns on rationale-capable surfaces, every outgoing agent message carries a kind, and the kind matches the stage that produced it.
- **SC-002**: The shopping assistant front can render the dedicated rationale presentation without reading message text or applying any ordering heuristic.
- **SC-003**: Zero regressions on channels that do not use rationale: WhatsApp, Instagram and flow-driven deliveries keep identical payloads **except for the one additive field**, and identical delivery behavior. Every pre-existing key keeps its name, value, and position.
- **SC-004**: The front-end team can validate the contract end to end on the preview surface within the sprint, without waiting on any other team.
- **SC-005**: No measurable change in message delivery latency for a turn, since no additional round trip is introduced.

## Assumptions

- Rationale is only emitted today on webchat and preview surfaces; other channels are unaffected because they never receive rationale.
- Nexus already knows, at emission time, whether a message is rationale or the final response. No new detection logic or model call is needed.
- The shopping assistant front reads the same socket stream that already delivers agent messages; this feature adds a field to those messages rather than creating a new channel or event type.
- The front-end presentation of the rationale (collapsing, styling, animation) is owned by the shopping assistant team and out of scope here.
- Rationale text itself is unchanged: this feature does not alter how rationale is generated, rewritten, or throttled.
- A turn emits at most one final response, possibly split across several messages.

## Dependencies

- **Contract sign-off with the shopping assistant front-end team** (Cristian / Paulo Bernardo): the field name and value set are decided (FR-010) and must be confirmed with them before implementation, so both sides ship against the same contract.
- **Flows/mailroom passthrough**: the production send path drops unknown fields today. Reaching the production shopping assistant requires the downstream transport to forward `message_kind`.
  - **Nexus owner**: whoever opens the request (tasks T002).
  - **Consumer owner**: shopping assistant front, Cristian / Paulo Bernardo, in [#weni-corner-experience-nexus](https://vtex.slack.com/archives/C0ADFJF6WP8/p1789999017171009).
  - **Transport owner**: not named in that thread. T002 records the person who owns `/mr/msg/send` and the webchat socket when the request is opened.
  - **Timeline**: none committed. Preview validation (SC-004) does not wait.
  - **Fallback**: FR-008. If the field is dropped, production delivery is unchanged and the front keeps today's rendering. No second code path, no feature flag.
  - Blocks FR-007 end to end. Does not block the preview surface, and does not block Nexus from putting the field on the wire.
