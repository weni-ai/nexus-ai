# Quickstart: validating `message_kind`

**Feature**: `003-rationale-message-kind` | **Branch**: `003-rationale-message-kind`

How to prove the feature works. Contract details live in
[`contracts/outgoing-message-kind.md`](contracts/outgoing-message-kind.md); payload shapes in
[`data-model.md`](data-model.md).

## Prerequisites

- `nexus-ai` dependencies installed (`poetry install`)
- A project with `rationale_switch = True` (`nexus/projects/models.py:63`, defaults to `True`)
- For the manual preview check: Agent Builder pointed at a local or staging Nexus, authenticated with a
  user that has project `GET` permission (enforced in `PreviewConsumer.connect`)

## 1. Automated suite

Canonical command for this repo (Django runner under coverage, 75% floor enforced by the
`check-coverage` pre-commit hook):

```bash
cd /home/ruan/codes/weni/nexus-ai
poetry run coverage run --source='.' manage.py test --verbosity=2 --noinput
poetry run coverage report --fail-under=75
```

Narrow runs while iterating:

```bash
poetry run python manage.py test router.traces_observers          # rationale tagging
poetry run python manage.py test router.tasks.tests               # dispatch + guardrail tagging
poetry run python manage.py test nexus.projects                   # preview websocket envelope
```

## 2. What the suite must prove

| # | Scenario | Expected | Spec ref |
|---|---|---|---|
| 1 | Rationale message emitted | payload declares `rationale` | FR-002 |
| 2 | Final answer emitted | payload declares `final_response` | FR-003 |
| 3 | Three rationale messages then an answer | first three `rationale`, last `final_response` | US1-3 |
| 4 | Answer split into several messages | **every** part declares `final_response` | edge case |
| 5 | Guardrail block | the refusal declares `final_response` | edge case |
| 6 | `skip_dispatch` branch | preview payload still declares `final_response` | FR-006 |
| 7 | Rationale disabled on the project | no message declares `rationale` | US1-4 |
| 8 | WhatsApp / Instagram / components turn | every pre-existing key identical in name, value and position; the new field is the only difference | FR-005, SC-003 |
| 9 | Downstream strips or rejects the field | message still delivered, no exception raised | FR-008 |
| 10 | Streaming-enabled project (gRPC) | the `completed` stream message carries the kind in its `metadata` map | FR-007 |
| 11 | Turn interrupted after rationale | no `final_response` and no end-of-turn signal are emitted | FR-013 |

Scenario 8 is the regression guard for SC-003 and is the one worth asserting strictly: compare the full
payload dict against the expected one, rather than only checking that the new key is present.

## 3. Manual preview check

1. Start Nexus with channels/websockets enabled and open Agent Builder's preview for the project.
2. Send a message that makes the agent call at least one tool, so rationale is produced.
3. Watch the websocket frames in the browser devtools Network → WS panel.

Expected frame sequence:

```jsonc
{"type": "preview", "message": {"type": "preview", "content": "Estou verificando...", "message_kind": "rationale"}}
{"type": "preview", "message": {"type": "preview", "content": {"type": "broadcast", "message": "...", "fonts": []}, "message_kind": "final_response"}}
```

Interleaved `trace_update` frames are expected and unrelated — they are the debugging surface, not the
chat stream (see `data-model.md` §4).

If no `rationale` frame appears, check in order: `project.rationale_switch`,
`turn_off_rationale` (set when the input carries attachments, `router/tasks/invoke.py:201`), and
whether the model actually returned a reasoning summary.

## 4. Production path check

Nexus-side verification does not require mailroom to be ready:

```bash
# tail the outgoing request log and confirm the field is on the wire
poetry run python manage.py shell
# then trigger a turn and inspect the logged Flows payload
```

`SendMessageHTTPClient` logs at `debug`, `FlowsRESTClient.whatsapp_broadcast` logs the full body at
`info` (`nexus/internals/flows.py:109`). Confirm the key is present in the body Nexus sends.

Whether the shopping assistant actually receives it depends on the mailroom passthrough, tracked as a
dependency in the spec. Nexus is done when the field is on the wire.

For a streaming-enabled project (one listed in `GRPC_ENABLED_PROJECTS`, with components off and
`stream_support` on), the final response leaves through the gRPC stream instead, so check the
`completed` message's `metadata` map rather than an HTTP body. Rationale still goes out over
`/mr/msg/send` on those projects — the two stages use different transports, which is why both need
tagging.

## 5. Front-end handoff

Share [`contracts/outgoing-message-kind.md`](contracts/outgoing-message-kind.md) with the shopping
assistant team. The contract is decided (§4 of that document); what remains is their confirmation
before implementation starts.
