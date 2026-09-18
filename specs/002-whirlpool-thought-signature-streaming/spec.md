# Feature Specification: Whirlpool Thought-Signature Streaming

**Feature Branch**: `fix/whirlpool-thought-signature-streaming`

**Created**: 2026-09-18

**Status**: Implementing

**Input**: Preserve Gemini thought signatures across the production streamed inline-agent path, only when `model_vendor=whirlpool`, without changing other model vendors.

**Scope**: Nexus backend custom Whirlpool provider and focused unit tests. No shared manager prompt fork, model-provider registry contract, public API, database, or other-vendor behavior change.

## User Scenarios & Testing

### User Story 1 - Replay streamed Whirlpool tool calls (Priority: P1)

As a Whirlpool project user, I need a streamed tool call returned by Whirlpool to retain its `thoughtSignature` when the tool result is sent on the next model turn, so Gemini accepts the request.

**Why this priority**: Production uses `Runner.run_streamed`; the existing non-streaming fix does not protect this path and repeated requests fail with HTTP 400.

**Independent Test**: Translate a signed Whirlpool function-call response, synthesize the SDK stream, replay its completed output with a tool result, and assert that the next Gemini payload contains the original signature as a sibling of the matching `functionCall`.

**Acceptance Scenarios**:

1. **Given** a Whirlpool response whose function-call part has a `thoughtSignature`, **When** the response passes through the streamed SDK path and is replayed with a tool result, **Then** the next `generateContent` payload contains the same signature beside `functionCall`.
2. **Given** the same streamed execution for a non-Whirlpool model vendor, **When** its normal OpenAI, Mantle, or LiteLLM model resolves, **Then** it does not instantiate or invoke the Whirlpool adapter.

---

### User Story 2 - Replay unsigned historical or injected calls (Priority: P1)

As a Whirlpool project user with old session history or injected context, I need unsigned function calls that Gemini did not emit to use the documented validation-skip sentinel so the current turn remains valid.

**Why this priority**: Existing Redis sessions and context injection can contain calls for which no real Gemini signature exists.

**Independent Test**: Convert an unsigned assistant function call and decode the resulting `thoughtSignature`, verifying it equals `skip_thought_signature_validator`.

**Acceptance Scenarios**:

1. **Given** an unsigned Whirlpool function call from old history or context injection, **When** the next payload is built, **Then** the function-call part contains the base64 validation-skip sentinel.
2. **Given** a real signature, **When** the next payload is built, **Then** the real signature is preserved and is not replaced by the sentinel.

---

### User Story 3 - Preserve parallel tool-turn ordering (Priority: P2)

As a Whirlpool project user, I need parallel function results represented in one Gemini user turn after all function calls so Gemini accepts the conversation ordering.

**Why this priority**: Gemini rejects interleaved function-call/function-response turns.

**Independent Test**: Convert one assistant turn with two calls followed by two tool outputs and assert one model turn contains both calls and one following user turn contains both responses.

**Acceptance Scenarios**:

1. **Given** two function calls in one Whirlpool model turn, **When** both tool outputs are translated, **Then** all calls precede one user turn containing both responses.
2. **Given** the final user turn ends in function responses, **When** the Whirlpool gateway payload is built, **Then** its required continuation text remains the final part.

### Edge Cases

- The signature may be attached directly to a function-call part or to a preceding thought part; the first function call must receive it.
- In a parallel call turn, only the first call may carry the real turn signature; unsigned calls still need valid replay behavior.
- A function-call response may contain text plus tool calls; visible text must remain intact.
- Existing Redis history may predate signature persistence.
- The custom model id does not contain `gemini`, although the Agents SDK gates metadata preservation on that substring.

## Requirements

### Functional Requirements

- **FR-001**: The streamed Whirlpool model path MUST retain `extra_content.google.thought_signature` from translated tool-call messages through the Agents SDK stream handler.
- **FR-002**: Whirlpool history conversion MUST activate the Agents SDK Gemini metadata behavior without changing the HTTP model id.
- **FR-003**: The next Whirlpool `generateContent` payload MUST emit the real signature as a sibling of `functionCall`.
- **FR-004**: If no real signature exists, the Whirlpool payload MUST emit the base64-encoded `skip_thought_signature_validator` sentinel.
- **FR-005**: Parallel tool outputs from one call round MUST be grouped into one user turn after the model function-call turn.
- **FR-006**: The Whirlpool gateway continuation text MUST remain after a final function response.
- **FR-007**: The signature stream hint and Gemini payload translation MUST be invoked only by the custom model selected for `model_vendor=whirlpool`.
- **FR-008**: OpenAI, `aws_mantle`, LiteLLM, and unknown-vendor model resolution and request paths MUST remain unchanged.
- **FR-009**: Logs MAY report signature counts or sentinel use but MUST NOT log signature values, credentials, token URLs, or payload content.
- **FR-010**: The shared manager/project instruction source MUST remain unchanged.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Focused tests prove both non-streamed and streamed signed tool-call roundtrips preserve the exact signature.
- **SC-002**: Focused tests prove unsigned calls receive the documented sentinel and parallel responses are grouped.
- **SC-003**: Registry tests continue to prove non-Whirlpool vendors resolve to their existing model types.
- **SC-004**: After deployment, Sentry issue NEXUS-2WF records no new missing-`thought_signature` failures for the Whirlpool project during the agreed observation window.
- **SC-005**: The implementation changes no public API, database schema, or non-Whirlpool adapter.

## Assumptions

- Whirlpool's gateway returns `thoughtSignature` and forwards it without stripping unknown Gemini part fields.
- Production executes Whirlpool through `Runner.run_streamed`.
- The installed Agents SDK preserves Gemini metadata when its converter model contains `gemini`.
- Calls injected by Nexus or stored before signature support are eligible for Google's documented validation-skip sentinel.

## Out of Scope

- Changing project instructions or creating a Whirlpool-specific prompt source.
- Fixing unrelated data-lake serialization issue NEXUS-2VT.
- Changing the `rationale_switch` default introduced in 3.7.13.
- Adding Whirlpool to LiteLLM.
- Public model-provider API changes.
