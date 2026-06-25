# Feature Spec: Amazon MQ Project Consumer Migration

## Overview

Migrate the `nexus-ai.projects` queue consumer from legacy RabbitMQ to Amazon MQ using the `weni-eda` library, following the dual-broker pattern established in chats-engine PR #1056.

## User Stories

### US-1: Parallel Amazon MQ consumer

As a platform operator, I want nexus-ai to consume project creation events from Amazon MQ so that we can gradually decommission the legacy RabbitMQ broker.

**Acceptance criteria:**
- A dedicated `edaconsume_amq` process connects to Amazon MQ over SSL (port 5671)
- Only the `nexus-ai.projects` queue is bound on the AMQ process
- All other queues remain on the legacy `edaconsume` process unchanged

### US-2: Backward-compatible message handling

As a developer, I want the new consumer to process the same message payload as the legacy consumer so that upstream publishers require no changes.

**Acceptance criteria:**
- `WeniEDAProjectConsumer` maps the same JSON fields to `ProjectCreationDTO`
- `ProjectsUseCase.create_project` is invoked with identical arguments
- Successful processing acks the message; failures reject without requeue

### US-3: Observability on failure

As an operator, I want processing errors reported to Sentry so that I can diagnose failed project creations.

**Acceptance criteria:**
- Exceptions during consumption are captured in Sentry before the message is rejected

## Message Contract

Queue: `nexus-ai.projects`

| Field | Type | Required | Maps to |
|-------|------|----------|---------|
| `uuid` | string | yes | `ProjectCreationDTO.uuid` |
| `name` | string | yes | `ProjectCreationDTO.name` |
| `is_template` | boolean | yes | `ProjectCreationDTO.is_template` |
| `template_type_uuid` | string | conditional | `ProjectCreationDTO.template_type_uuid` |
| `organization_uuid` | string | yes | `ProjectCreationDTO.org_uuid` |
| `brain_on` | boolean | no | `ProjectCreationDTO.brain_on` (default: false) |
| `authorizations` | list | no | `ProjectCreationDTO.authorizations` |
| `indexer_database` | string | no | defaults to `Project.BEDROCK` |
| `inline_agent_switch` | boolean | no | defaults to `true` |
| `user_email` | string | yes | passed to `create_project` |

## Rollout Strategy

1. Deploy with both `edaconsume` (legacy) and `edaconsume-amq` (Amazon MQ) running
2. Route new traffic to Amazon MQ
3. Once traffic is fully migrated, remove `OldProjectConsumer` from the legacy handler

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AMQ_BROKER_HOST` | `localhost` | Amazon MQ hostname |
| `AMQ_BROKER_USER` | `guest` | Broker username |
| `AMQ_BROKER_PASSWORD` | `guest` | Broker password |
| `AMQ_VIRTUAL_HOST` | `/` | Virtual host |
| `AMQ_BROKER_PORT` | `5671` | SSL port |
| `AMQ_BROKER_SSL_SERVER_HOSTNAME` | none | SNI hostname for certificate verification |
| `AMQ_BROKER_HEARTBEAT` | `300` | Heartbeat interval (seconds) |

## Out of Scope

- Other project queues (`nexus-ai.projects.auth`, integrated-feature queues)
- Orgs and inline_agents consumers
- Publisher migration to Amazon MQ
- Removing legacy consumer (post cutover)
