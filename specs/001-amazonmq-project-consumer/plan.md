# Implementation Plan: Amazon MQ Project Consumer

## Architecture

Dual-broker setup during gradual migration:

- **Legacy RabbitMQ** (`manage.py edaconsume`): all existing queues including `OldProjectConsumer` on `nexus-ai.projects`
- **Amazon MQ** (`manage.py edaconsume_amq`): only `WeniEDAProjectConsumer` on `nexus-ai.projects`

Both consumers delegate to `ProjectsUseCase.create_project`.

## Dependencies

- `weni-eda = "0.2.0a6"` — provides `AMQConnectionParamsFactory`, `EDAConsumer`, and `edaconsume` CLI with `--params-class` / `--handle` flags

## Key Files

| File | Change |
|------|--------|
| `nexus/projects/consumers/project_consumer.py` | Extract `_build_project_dto`, add `OldProjectConsumer` + `WeniEDAProjectConsumer` |
| `nexus/projects/handle.py` | Use `OldProjectConsumer` |
| `nexus/event_driven/handle_amq.py` | New AMQ-only handler |
| `nexus/event_driven/management/commands/edaconsume_amq.py` | New management command |
| `nexus/settings.py` | Add `AMQ_*` settings |
| `entrypoint.sh` | Add `edaconsume-amq` alias |
| `contrib/gen_env.py` | Add AMQ env var placeholders |

## Reference

- chats-engine PR #1056: https://github.com/weni-ai/chats-engine/pull/1056
