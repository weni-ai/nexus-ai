# Conversation Microservice - Documentation

## Overview

Microservice responsible for processing conversation messages from SQS FIFO queue, managing conversations, and handling message persistence.

## Architecture 1.0

### Requirements

| #   | Requirement                        | Status    | Notes                            |
| --- | ---------------------------------- | --------- | -------------------------------- |
| 1.0 | Service interno, sem autenticação  | ✅ Done   | Consumer SQS only, no REST API   |
| 1.1 | Sem DNS externo                    | ✅ Done   | No external endpoints            |
| 2.0 | Mesma fila para incoming/outgoing  | ✅ Done   | Consumer processes both types    |
| 3.0 | Fechamento baseado em timezone     | ⏸️ Paused | Will be implemented later        |
| 4.0 | Schedule para fechamento           | ⏸️ Paused | Will be implemented later        |
| 5.0 | Enviar CSAT/NPS para datalake      | ✅ Done   | CSATNPSService implemented       |
| 6.0 | Tabela ConversationMessages        | ✅ Done   | Model created, migration pending |
| 6.1 | Mensagens em progresso no DynamoDB | ✅ Done   | Integrated in MessageRepository  |
| 6.2 | Salvar no Postgres após fechamento | ✅ Done   | MessageMigrationService ready    |
| 7.0 | Dados de conversa do Postgres      | ✅ Done   | ConversationService integrated   |

## What's Done ✅

### Core Infrastructure

- ✅ SQS Consumer (FIFO) implementation
- ✅ Message processing pipeline (received/sent)
- ✅ ConversationService integration
- ✅ Event DTOs (MessageReceivedEvent, MessageSentEvent)
- ✅ Error handling with Sentry
- ✅ Structured logging
- ✅ Django initialization

### Services

- ✅ `MessageService`: Processes message.received and message.sent events
- ✅ `ConversationService`: Ensures conversation exists before processing
- ✅ `CSATNPSService`: Handles CSAT/NPS events and sends to datalake
- ✅ `MessageMigrationService`: Migrates messages from DynamoDB to Postgres
- ✅ Consumer handlers integrated with MessageService

### Repositories

- ✅ `ConversationRepository`: Base structure (not actively used yet)
- ✅ `MessageRepository`: Integrated with DynamoDB for in-progress conversations

### Models

- ✅ `ConversationMessages`: Django model for storing messages in Postgres (JSONField)

## What's Pending ⏳

### 1. Migration File

- [ ] Create Django migration for ConversationMessages model
- Command: `python manage.py makemigrations intelligences`

### 2. Integration Points

- [ ] Call MessageMigrationService when conversation closes (currently manual trigger needed)
- [ ] Add hook/trigger point for automatic migration on conversation closure

## What's Paused ⏸️

### 1. Timezone-based Closing

- Will be implemented after core functionality is complete
- Requires timezone configuration per project

### 2. Celery Beat Schedule

- Will be implemented after timezone logic
- Will run periodic tasks to close conversations

## Project Structure

```
conversation_ms/
├── main.py                          # Entry point
├── consumers/
│   └── sqs_consumer.py              # SQS FIFO consumer
├── services/
│   ├── message_service.py           # Main message processing
│   ├── conversation_service.py      # Conversation management
│   ├── csat_nps_service.py          # CSAT/NPS event handling
│   └── message_migration_service.py  # DynamoDB → Postgres migration
├── repositories/
│   ├── message_repository.py        # Message persistence (DynamoDB + Postgres)
│   └── conversation_repository.py   # Conversation queries
├── models/
│   └── events.py                    # Event DTOs
├── exceptions.py                     # Custom exceptions
└── README.md                         # This file
```

## Flow Diagram

```
SQS FIFO Queue
    ↓
ConversationSQSConsumer
    ↓
MessageService.process_message_received/sent()
    ├── Parse event (MessageReceivedEvent/MessageSentEvent)
    ├── ConversationService.ensure_conversation_exists()
    │   └── Uses router.services.conversation_service
    └── MessageRepository.save_received_message/save_sent_message()
        ├── If conversation in progress → DynamoDB (with TTL)
        └── If conversation closed → Skip DynamoDB (migration handled separately)
    ├── CSATNPSService._handle_special_events()
    │   └── If weni_csat or weni_nps → Send to datalake
    └── MessageMigrationService (when conversation closes)
        └── Migrate DynamoDB messages → ConversationMessages (Postgres)
```

## Environment Variables

- `SQS_CONVERSATION_QUEUE_URL`: SQS FIFO queue URL
- `SQS_CONVERSATION_DLQ_URL`: Dead Letter Queue URL
- `SQS_CONVERSATION_REGION`: AWS region
- `DYNAMODB_MESSAGE_TABLE`: DynamoDB table name for messages
- `DYNAMODB_REGION`: DynamoDB region

## Next Steps

1. ✅ Create ConversationMessages model - **DONE**
2. ✅ Integrate DynamoDB repository - **DONE**
3. ✅ Implement CSAT/NPS handler - **DONE**
4. ✅ Implement message migration logic - **DONE**
5. Create migration file for ConversationMessages model
6. Add tests
7. Deploy and monitor
8. Implement timezone-based closing (when ready)
9. Implement Celery Beat schedule (when ready)

## Implementation Details

### Message Storage Strategy

- **In Progress**: Messages stored in DynamoDB with 48-hour TTL
- **After Closure**: Messages migrated to PostgreSQL `ConversationMessages` table (JSONField)
- **Rationale**: Avoids constant PostgreSQL updates during active conversations

### CSAT/NPS Processing

- Events detected by `key` field (`weni_csat` or `weni_nps`) in message events
- Conversation fields (CSAT/NPS) updated in Conversation model via `update_conversation_data`
- Sent to datalake via Celery task (`send_data_lake_event.delay()`)
- Metadata includes conversation UUID, start_date, end_date, agent_uuid

### Message Migration

- Triggered when conversation is closed (resolution != IN_PROGRESS)
- Fetches all messages from DynamoDB for the conversation
- Stores as JSON array in `ConversationMessages.messages` field
- Uses `update_or_create` to handle existing records

## Recent Changes

### 2025-01-XX - Initial Implementation

- ✅ Created ConversationMessages model in `nexus/intelligences/models.py`
- ✅ Integrated DynamoDB repository in MessageRepository
- ✅ Implemented CSATNPSService for datalake events
- ✅ Implemented MessageMigrationService for DynamoDB → Postgres migration
- ✅ Updated MessageService to handle special events (CSAT/NPS)
- ✅ All services include Sentry monitoring

## Notes

- Messages in progress are stored in DynamoDB to avoid constant PostgreSQL updates
- Messages are migrated to PostgreSQL only after conversation closure
- CSAT/NPS events are sent to datalake for analytics
- All errors are tracked via Sentry with proper context
- Timezone-based closing and Celery Beat schedule are paused for now
- CSAT/NPS events also update Conversation model fields (csat/nps)
