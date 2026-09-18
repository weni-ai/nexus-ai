# Tasks: Whirlpool Thought-Signature Streaming

**Input**: Design documents from `/specs/002-whirlpool-thought-signature-streaming/`

**Prerequisites**: `spec.md`, `research.md`, `plan.md`

## Phase 1: Investigation and isolation

- [x] T001 Diff `3.7.11..3.7.12` and `3.7.12..3.7.13` to identify runtime blast radius.
- [x] T002 Correlate Sentry production errors and project UUIDs around the 3.7.13 boundary.
- [x] T003 Confirm `resolve_custom_model` and stream helper call sites isolate the active path to `model_vendor=whirlpool`.

## Phase 2: User Story 1 - Streamed signature roundtrip (P1)

**Goal**: Preserve the real Whirlpool/Gemini signature through `Runner.run_streamed`.

**Independent Test**: A signed translated response passes through synthesized streaming and appears unchanged in the next Gemini payload.

- [x] T004 [US1] Carry tool-call `extra_content` in synthesized deltas in `inline_agents/backends/openai/custom_providers/base.py`.
- [x] T005 [US1] Add an optional converter-model hint to the stream handler in `inline_agents/backends/openai/custom_providers/base.py`.
- [x] T006 [US1] Activate `gemini-whirlpool` conversion only from `inline_agents/backends/openai/custom_providers/whirlpool/model.py`.
- [x] T007 [US1] Add non-streamed and streamed roundtrip tests in `inline_agents/backends/openai/custom_providers/tests/test_translate.py`.

## Phase 3: User Story 2 - Unsigned compatibility (P1)

**Goal**: Keep old/injected Whirlpool history valid without replacing real signatures.

**Independent Test**: An unsigned call receives base64 `skip_thought_signature_validator`; a signed call keeps its original value.

- [x] T008 [US2] Add sentinel fallback and value-safe logging in `inline_agents/backends/openai/custom_providers/whirlpool/translate.py`.
- [x] T009 [US2] Add unsigned-call sentinel coverage in `inline_agents/backends/openai/custom_providers/tests/test_translate.py`.

## Phase 4: User Story 3 - Parallel tool ordering (P2)

**Goal**: Emit all function responses from one round in one Gemini user turn.

**Independent Test**: Two calls are followed by one user turn containing both corresponding responses and the gateway continuation text.

- [x] T010 [US3] Group adjacent tool outputs in `inline_agents/backends/openai/custom_providers/whirlpool/translate.py`.
- [x] T011 [US3] Add parallel grouping coverage in `inline_agents/backends/openai/custom_providers/tests/test_translate.py`.

## Phase 5: Verification

- [x] T012 Run focused custom-provider translation, Whirlpool model, and registry tests (35 passed).
- [x] T013 Run changed-file formatting/lint checks and `git diff --check` (critical Ruff/import checks and diff check pass; full Ruff/Blue report pre-existing style debt in these files).
- [x] T014 Review the final diff against `origin/main` for non-Whirlpool runtime changes.
- [ ] T015 After deployment, verify NEXUS-2WF records no new missing-signature events.

## Dependencies and execution order

- T001-T003 establish that the change is correctly scoped.
- T004-T006 enable T007.
- T008 enables T009.
- T010 enables T011.
- T012-T014 gate merge readiness.
- T015 is post-deployment validation and does not block opening the pull request.
