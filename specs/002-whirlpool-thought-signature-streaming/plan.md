# Implementation Plan: Whirlpool Thought-Signature Streaming

**Branch**: `fix/whirlpool-thought-signature-streaming` | **Date**: 2026-09-18 | **Spec**: `specs/002-whirlpool-thought-signature-streaming/spec.md`

**Input**: Feature specification from `/specs/002-whirlpool-thought-signature-streaming/spec.md`

## Summary

Preserve Whirlpool/Gemini thought signatures through the production `Runner.run_streamed` path. Carry provider metadata on synthesized tool-call deltas, invoke the SDK converter with a Gemini hint only from `WhirlpoolModel`, replay a documented sentinel for unsigned historical/injected calls, and group parallel function results. Keep shared manager instructions, model resolution, public APIs, and other vendors unchanged.

## Technical Context

**Language/Version**: Python 3.10-3.11

**Primary Dependencies**: Django 4.2, OpenAI Agents SDK, OpenAI Python types

**Storage**: Existing Redis agent session history; no schema or persistence changes

**Testing**: Django `SimpleTestCase` through pytest

**Target Platform**: Linux Celery inline-agents workers

**Project Type**: Django backend service

**Performance Goals**: No extra network request; constant metadata-copy overhead per function call

**Constraints**: Whirlpool-only activation, no secrets/payload logging, no manager instruction fork, compatibility with old unsigned Redis sessions

**Scale/Scope**: Four existing custom-provider files plus focused translation tests; one production Whirlpool project

## Constitution Check

The repository constitution is still an unfilled template and defines no enforceable project gates. Workspace rules apply:

- Required weekly-plan and Start here context was read before implementation.
- Work is isolated to `nexus-ai`.
- Branch was created from latest `origin/main`.
- Production is inspected through Sentry and, if needed, a copy-paste Django shell snippet rather than direct access.
- No secrets, credentials, token URLs, or production payload content are added.

Post-design check: PASS. The plan adds no new service, contract, database entity, dependency, or cross-repository change.

## Project Structure

### Documentation

```text
specs/002-whirlpool-thought-signature-streaming/
├── spec.md
├── research.md
├── plan.md
├── quickstart.md
└── tasks.md
```

### Source Code

```text
inline_agents/backends/openai/custom_providers/
├── base.py
├── whirlpool/
│   ├── model.py
│   └── translate.py
└── tests/
    ├── test_translate.py
    └── test_registry.py
```

**Structure Decision**: Extend the existing custom-provider adapter and its unit tests. `base.py` remains a helper used only by Whirlpool today; the metadata-preserving option defaults off and is activated only by `WhirlpoolModel`.

## Implementation Phases

### Phase 0 - Confirm isolation

1. Diff release tags and identify changed runtime paths.
2. Correlate Sentry issue/project distributions around the deployment boundary.
3. Confirm custom-provider call sites and non-Whirlpool model resolution.

### Phase 1 - Preserve streamed metadata

1. Add a synthesized tool-call delta subtype capable of carrying `extra_content`.
2. Add an optional converter model argument to the stream synthesizer.
3. Pass the Gemini converter hint only from `WhirlpoolModel.stream_response`.
4. Use the same hint when converting replay history.

### Phase 2 - Build valid replay payloads

1. Echo real signatures as siblings of `functionCall`.
2. Use the validation-skip sentinel only when the signature is absent.
3. Group adjacent parallel tool responses in one user turn.
4. Retain the Whirlpool gateway continuation prompt.
5. Log counts without logging signature values or payloads.

### Phase 3 - Verify

1. Run focused translation, Whirlpool model, and registry tests.
2. Run formatting/lint checks for changed Python files.
3. Inspect the final branch diff against `origin/main`.
4. After deployment, monitor NEXUS-2WF and confirm no new missing-signature events.

## Complexity Tracking

No constitution violations or additional complexity exceptions.
