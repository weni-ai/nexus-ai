# gRPC Message Streaming Client

Stream messages to external services using gRPC.

## Quick Start

```python
from inline_agents.backends.openai.grpc import MessageStreamingClient

# Initialize and use
with MessageStreamingClient(host='service.com', port=50051) as client:
    for response in client.stream_messages_with_setup(
        msg_id="unique-id",
        channel_uuid="channel-uuid",
        contact_urn="whatsapp:+5511999999999"
    ):
        print(response['message'])
        if response['is_final']:
            break
```

## Setup

### 1. Install Dependencies

```bash
poetry add grpcio grpcio-tools
```

### 2. Generate Python Code

```bash
cd inline_agents/backends/openai/grpc
./generate_grpc_code.sh
```

### 3. Configure

```python
# settings.py
GRPC_HOST = env.str('GRPC_HOST', default='localhost')
GRPC_PORT = env.int('GRPC_PORT', default=50051')
```

## Usage

### Basic Streaming

```python
from inline_agents.backends.openai.grpc import MessageStreamingClient

with MessageStreamingClient(
    host=settings.GRPC_HOST,
    port=settings.GRPC_PORT,
    use_secure_channel=True  # Use TLS in production
) as client:
    
    for response in client.stream_messages_with_setup(
        msg_id="msg-123",
        channel_uuid="uuid-456",
        contact_urn="whatsapp:+5511999999999",
        messages=["Hello!"]  # Optional: send additional messages
    ):
        if response['status'] == 'success':
            print(response['message'])
        elif response['status'] == 'error':
            print(f"Error: {response['error_message']}")
        
        if response['is_final']:
            break
```

### Django Integration

```python
def handle_message(channel_uuid, contact_urn, text):
    with MessageStreamingClient(
        host=settings.GRPC_HOST,
        port=settings.GRPC_PORT
    ) as client:
        
        for response in client.stream_messages_with_setup(
            msg_id=generate_id(),
            channel_uuid=channel_uuid,
            contact_urn=contact_urn,
            messages=[text]
        ):
            # Process response
            if response['is_final']:
                return response
```

## Files

- `streaming_client.py` - Main client implementation
- `test_utils.py` - Mock client for testing
- `message_stream_service.proto` - Service definition
- `generated/` - Auto-generated Python code from .proto
- `generate_grpc_code.sh` - Script to regenerate Python code

## Methods

### `stream_messages_with_setup()`
Sends setup message first, then optional content messages via bidirectional streaming.

**Args:** `msg_id`, `channel_uuid`, `contact_urn`, `messages` (optional), `project_uuid`, `metadata`

**Yields:** Response dicts with `status`, `message`, `is_final`, etc.

### `send_delta_message()` ⭐
Send delta messages after setup (for streaming content chunks).

**Args:** `msg_id`, `content`, `channel_uuid`, `contact_urn`, `project_uuid`, `metadata`, `timeout`

**Returns:** Response dict with `status`, `message`, etc.

### `send_completed_message()` ⭐
Send completion message after all deltas (signals end of stream).

**Args:** `msg_id`, `content`, `channel_uuid`, `contact_urn`, `project_uuid`, `metadata`, `timeout`

**Returns:** Response dict with `status`, `message`, etc.

**Complete Flow Example:**
```python
# 1. Setup once
for _ in client.stream_messages_with_setup(msg_id="session-123", ...):
    pass

# 2. Send multiple deltas
for i, chunk in enumerate(content_chunks):
    client.send_delta_message(
        msg_id=f"delta-{i}",
        content=chunk,
        channel_uuid="uuid",
        contact_urn="urn"
    )

# 3. Send completion
client.send_completed_message(
    msg_id="session-123",
    content="Done",
    channel_uuid="uuid",
    contact_urn="urn"
)
```

### `send_single_message()`
Send a single message (unary RPC, not streaming).

### `check_connection()`
Test if server is reachable.

## Testing

### Prevent gRPC calls in tests (Recommended)

```python
from inline_agents.backends.openai.grpc import is_grpc_enabled

def handle_message(channel_uuid, contact_urn, text):
    # Automatically False in test environments
    if not is_grpc_enabled():
        logger.info("gRPC disabled in tests")
        return {'status': 'skipped'}
    
    # Make real gRPC call
    with MessageStreamingClient(...) as client:
        ...
```

### Use mock client in tests

```python
from inline_agents.backends.openai.grpc.test_utils import MockMessageStreamingClient
from unittest.mock import patch

def test_my_function(self):
    with patch('my_module.MessageStreamingClient', MockMessageStreamingClient):
        result = my_function()
        self.assertEqual(result['status'], 'success')
```

### Environment variables

- `GRPC_ENABLED=false` - Disable gRPC (tests set this automatically)
- `TESTING=true` - Auto-detected test environment
- Tests using pytest or Django test module are auto-detected

## Production Checklist

- [ ] Use `use_secure_channel=True`
- [ ] Configure TLS certificates
- [ ] Add authentication via metadata
- [ ] Implement error handling and retry logic
- [ ] Set up monitoring/logging
- [ ] Test with production load

## Troubleshooting

**Cannot connect:** Check host/port, verify server is running
**Import errors:** Run `./generate_grpc_code.sh` to regenerate Python code
**Timeout:** Adjust `max_message_length` or connection options
**Tests fail with gRPC errors:** Add `is_grpc_enabled()` check or use `MockMessageStreamingClient`
