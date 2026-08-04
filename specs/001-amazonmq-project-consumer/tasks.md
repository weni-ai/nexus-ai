# Tasks: Amazon MQ Project Consumer

## Phase 1 — Setup

- [x] Create feature spec (`spec.md`, `plan.md`, `tasks.md`)
- [x] Remove `.specify` / `specs/` from `.gitignore`

## Phase 2 — Dependency

- [x] Add `weni-eda = "0.2.0a6"` to `pyproject.toml`
- [x] Run `poetry lock && poetry install`

## Phase 3 — Consumer

- [x] Extract `_build_project_dto(body)` helper
- [x] Rename `ProjectConsumer` → `OldProjectConsumer`
- [x] Add `WeniEDAProjectConsumer` extending `weni.eda.django.consumers.EDAConsumer`

## Phase 4 — Handlers & Settings

- [x] Create `nexus/event_driven/handle_amq.py`
- [x] Update `nexus/projects/handle.py` to use `OldProjectConsumer`
- [x] Add `AMQ_*` settings to `nexus/settings.py`
- [x] Add AMQ env vars to `contrib/gen_env.py`

## Phase 5 — Commands & Entrypoint

- [x] Create `edaconsume_amq` management command
- [x] Add `edaconsume-amq` alias to `entrypoint.sh`

## Phase 6 — Tests & Verification

- [x] Add `test_project_consumer.py` with tests for both consumers
- [x] Run lint and pytest
