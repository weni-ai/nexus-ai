# Architecture Improvement Plan: start_inline_agents Refactoring

## Executive Summary

This document outlines a plan to refactor the monolithic `start_inline_agents` Celery task into a more modular, scalable, and maintainable architecture. The proposed solution breaks the task into three distinct phases (Pre-Generation, Generation, Post-Generation) and leverages the **existing Observer infrastructure** in the codebase for cross-cutting concerns.

### Key Infrastructure Already Available

✅ **Observer Pattern** - Fully implemented (`nexus.event_domain`)
  - `EventManager` and `AsyncEventManager` 
  - `@observer` decorator for automatic registration
  - Error isolation (`isolate_errors=True`)
  - Middleware (Sentry, performance monitoring)
  - Factory pattern for dependency injection
  - Event validation

✅ **Existing Examples** - `RationaleObserver`, `SaveTracesObserver`

**Reference:** See `nexus/event_domain/OBSERVER_GUIDE.md` for complete documentation.

---

## Current Implementation Status (January 2025)

### ✅ Completed

| Feature | Branch | Status |
|---------|--------|--------|
| Cache Service | `feature/cache-service` | ✅ Merged |
| Pre-Generation Service | `feature/pre-generation-service` | ✅ Merged |
| Cache Invalidation Observers | `feature/cache-invalidation` | ✅ Merged |
| Admin Cache Invalidation | `feature/admin-cache-invalidation` | ✅ Merged |
| **Workflow Foundation** | `feature/workflow-foundation` | ✅ Merged |
| **Workflow Orchestrator** | `feature/workflow-orchestrator` | ✅ Merged |
| **Observer Registration App** | `feature/workflow-orchestrator` | ✅ Merged |
| Sentry Performance Tracking | `feature/sentry-performance` | 🔒 Local only |

### Branch Merge Order

```
main (or staging)
  └── feature/cache-service
        ├── feature/pre-generation-service
        └── feature/cache-invalidation
              └── feature/admin-cache-invalidation
                    └── feature/workflow-foundation
                          └── feature/workflow-orchestrator
```

### Key Achievements

1. **Cache-First Architecture** - All project/content_base/team data is now cached in Redis
2. **Dictionary-Based Data** - Backend uses JSON-serializable dicts instead of Django objects
3. **Automatic Cache Invalidation** - Changes via API or Admin auto-invalidate cache
4. **Async Event Handling** - `notify_async()` bridges sync code with async observers
5. **Clean Backend Code** - Removed unused fallback code and parameters
6. **Workflow Orchestrator** - Three-phase workflow (Pre-Generation → Generation → Post-Generation)
7. **Workflow State Management** - Redis-based workflow state with task tracking
8. **Task Revocation** - Automatic revocation of pending workflows on new messages
9. **Message Concatenation** - Handles rapid user inputs by concatenating messages
10. **Observer Registration App** - Centralized observer registration in `nexus/observers/`

### What's Next

- **Phase 3:** Extract Generation and Post-Generation into separate Celery tasks
- **Phase 4:** Implement additional observers (DataLake, Metrics, Tracing)
- **Phase 5:** Feature flag rollout and migration

---

## Current Architecture Problems

### 1. **Monolithic Task**
- Single large task handles everything sequentially
- Long execution time (300-360 seconds timeout)
- Difficult to scale, test, and maintain
- All-or-nothing execution (can't cancel early)

### 2. **Sequential Processing**
- Guardrails/complexity checks block main flow
- External calls add latency without parallelization
- No early exit on validation failures

### 3. **Tight Coupling**
- Business logic mixed with infrastructure concerns
- Hard to test individual components
- Difficult to add new features

### 4. **Limited Observability**
- Hard to track progress through pipeline
- Difficult to add new monitoring/logging points
- No clear separation of concerns

---

## Proposed Architecture

### Overview

Split the monolithic task into three independent, composable tasks:

1. **Workflow Orchestrator** - Manages workflow state, pending tasks, and message concatenation
2. **Pre-Generation Task** - Validation, setup, and preparation
3. **Generation Task** - Core agent invocation (minimal dependencies)
4. **Post-Generation Task** - Persistence, logging, and cleanup

Additionally, introduce an **Observer Pattern** for cross-cutting concerns like:
- Tracing/Logging
- Data Lake events
- Metrics collection
- Error handling
- Preview mode handling

### Workflow State Management

**Critical Consideration:** When a user sends a new message while a workflow is in progress, we need to:
- Revoke all 3 tasks (Pre-Generation, Generation, Post-Generation) in the current workflow
- Concatenate the new message with any pending messages
- Start a new workflow

This requires **workflow-level state management** that happens **BEFORE** Pre-Generation.

---

## Phase 0: Workflow Orchestrator

### Purpose
Manage workflow state, handle pending tasks, and coordinate the three-phase execution. This runs **BEFORE** Pre-Generation to handle concurrent message scenarios.

### Responsibilities
- Check for existing workflow for the contact URN
- Revoke all tasks in existing workflow (Pre-Generation, Generation, Post-Generation)
- Handle message concatenation for rapid user inputs
- Create workflow state and store all task IDs
- Coordinate task execution (chain or async)
- Handle workflow cleanup on completion/error

### Execution Flow

```
Workflow Orchestrator (Entry Point)
├── Check for existing workflow
│   ├── Get workflow state from Redis
│   └── If exists: Revoke all tasks in workflow
├── Handle message concatenation
│   ├── Get pending messages
│   └── Concatenate with new message
├── Create workflow state
│   ├── Generate workflow ID
│   ├── Store workflow metadata
│   └── Reserve task IDs (if using Celery Canvas)
├── Execute workflow
│   ├── Start Pre-Generation task
│   ├── Chain to Generation (on success)
│   └── Chain to Post-Generation (on success)
└── Store workflow state
    ├── Store all task IDs
    ├── Store workflow status
    └── Store contact URN mapping
```

### Task Signature

```python
@celery_app.task(
    bind=True,
    soft_time_limit=10,  # Very short - just orchestration
    time_limit=15,
    max_retries=2,
)
def inline_agent_workflow_orchestrator(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
) -> Dict:
    """
    Orchestrates the three-phase inline agent workflow.
    
    Returns:
    {
        "workflow_id": str,
        "status": "started" | "blocked" | "failed",
        "pre_generation_task_id": str,
        "generation_task_id": str | None,  # Set when chained
        "post_generation_task_id": str | None,  # Set when chained
        "final_message_text": str,  # After concatenation
        "error": str | None,
    }
    """
```

### Workflow State Structure

```python
# Stored in Redis
workflow_state = {
    "workflow_id": "workflow-{uuid}",
    "project_uuid": str,
    "contact_urn": str,
    "status": "pre_generation" | "generation" | "post_generation" | "completed" | "failed" | "revoked",
    "task_ids": {
        "pre_generation": str,
        "generation": str | None,
        "post_generation": str | None,
    },
    "created_at": datetime,
    "updated_at": datetime,
    "final_message_text": str,  # After concatenation
}
```

### Enhanced RedisTaskManager Methods

```python
class RedisTaskManager(TaskManager):
    # Existing methods...
    
    def get_workflow_state(self, project_uuid: str, contact_urn: str) -> Optional[Dict]:
        """Get current workflow state for a contact."""
        workflow_key = f"workflow:{project_uuid}:{contact_urn}"
        state = self.redis_client.get(workflow_key)
        return json.loads(state.decode("utf-8")) if state else None
    
    def store_workflow_state(self, workflow_state: Dict) -> None:
        """Store workflow state."""
        workflow_key = f"workflow:{workflow_state['project_uuid']}:{workflow_state['contact_urn']}"
        self.redis_client.setex(
            workflow_key,
            self.CACHE_TIMEOUT,
            json.dumps(workflow_state, default=str)
        )
    
    def revoke_workflow_tasks(self, workflow_state: Dict) -> None:
        """Revoke all tasks in a workflow."""
        task_ids = workflow_state.get("task_ids", {})
        for phase, task_id in task_ids.items():
            if task_id:
                try:
                    celery_app.control.revoke(task_id, terminate=True)
                except Exception as e:
                    logger.warning(f"Failed to revoke task {task_id}: {e}")
    
    def clear_workflow_state(self, project_uuid: str, contact_urn: str) -> None:
        """Clear workflow state."""
        workflow_key = f"workflow:{project_uuid}:{contact_urn}"
        self.redis_client.delete(workflow_key)
        # Also clear old single-task keys for backwards compatibility
        self.clear_pending_tasks(project_uuid, contact_urn)
    
    def handle_workflow_message_concatenation(
        self, 
        project_uuid: str, 
        contact_urn: str, 
        new_message_text: str
    ) -> str:
        """
        Handle message concatenation for workflows.
        Returns final concatenated message text.
        """
        workflow_state = self.get_workflow_state(project_uuid, contact_urn)
        
        if workflow_state:
            # Revoke existing workflow
            self.revoke_workflow_tasks(workflow_state)
            
            # Get pending message from workflow state
            pending_text = workflow_state.get("final_message_text", "")
            if pending_text:
                final_message = f"{pending_text}\n{new_message_text}"
            else:
                final_message = new_message_text
        else:
            # Check old single-task format for backwards compatibility
            pending_response = self.get_pending_response(project_uuid, contact_urn)
            if pending_response:
                final_message = f"{pending_response}\n{new_message_text}"
            else:
                final_message = new_message_text
        
        return final_message
```

### Implementation Example

```python
def inline_agent_workflow_orchestrator(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
) -> Dict:
    task_manager = get_task_manager()
    project_uuid = message.get("project_uuid")
    contact_urn = message.get("contact_urn")
    
    # Handle message concatenation and revoke existing workflow
    final_message_text = task_manager.handle_workflow_message_concatenation(
        project_uuid=project_uuid,
        contact_urn=contact_urn,
        new_message_text=message.get("text", "")
    )
    
    # Create workflow state
    workflow_id = f"workflow-{uuid.uuid4()}"
    workflow_state = {
        "workflow_id": workflow_id,
        "project_uuid": project_uuid,
        "contact_urn": contact_urn,
        "status": "pre_generation",
        "task_ids": {
            "pre_generation": None,
            "generation": None,
            "post_generation": None,
        },
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "final_message_text": final_message_text,
    }
    
    # Update message with concatenated text
    message["text"] = final_message_text
    
    # Start Pre-Generation task
    pre_gen_result = pre_generation_task.delay(
        message=message,
        preview=preview,
        language=language,
        workflow_id=workflow_id,
    )
    
    # Store workflow state with Pre-Generation task ID
    workflow_state["task_ids"]["pre_generation"] = pre_gen_result.id
    task_manager.store_workflow_state(workflow_state)
    
    # Chain Generation and Post-Generation tasks
    workflow = chain(
        pre_generation_task.s(message, preview, language, workflow_id),
        generation_task.s(message, preview, language, user_email, workflow_id),
        post_generation_task.s(message, preview, language, user_email, workflow_id),
    )
    
    # Execute workflow
    workflow_result = workflow.apply_async()
    
    # Update workflow state with task IDs (if available immediately)
    # Note: Celery Canvas chain provides task IDs, but we may need to extract them
    # The individual tasks will update their own IDs in the workflow state
    
    return {
        "workflow_id": workflow_id,
        "status": "started",
        "pre_generation_task_id": pre_gen_result.id,
        "final_message_text": final_message_text,
    }
```

### Alternative: Workflow State Updates in Each Task

Since Celery Canvas chains may not expose all task IDs upfront, we can update workflow state in each task:

```python
# In pre_generation_task
def pre_generation_task(self, message: Dict, workflow_id: str, **kwargs):
    task_manager = get_task_manager()
    workflow_state = task_manager.get_workflow_state_by_id(workflow_id)
    
    if not workflow_state:
        raise ValueError(f"Workflow {workflow_id} not found")
    
    # Update workflow state
    workflow_state["task_ids"]["pre_generation"] = self.request.id
    workflow_state["status"] = "pre_generation"
    task_manager.store_workflow_state(workflow_state)
    
    # ... pre-generation logic ...
    
    # On success, workflow state will be updated by Generation task
    return result

# In generation_task
def generation_task(self, pre_result: Dict, message: Dict, workflow_id: str, **kwargs):
    task_manager = get_task_manager()
    workflow_state = task_manager.get_workflow_state_by_id(workflow_id)
    
    if not workflow_state:
        raise ValueError(f"Workflow {workflow_id} not found")
    
    # Update workflow state
    workflow_state["task_ids"]["generation"] = self.request.id
    workflow_state["status"] = "generation"
    task_manager.store_workflow_state(workflow_state)
    
    # ... generation logic ...
    
    return result

# In post_generation_task
def post_generation_task(self, gen_result: Dict, pre_result: Dict, message: Dict, workflow_id: str, **kwargs):
    task_manager = get_task_manager()
    workflow_state = task_manager.get_workflow_state_by_id(workflow_id)
    
    if not workflow_state:
        raise ValueError(f"Workflow {workflow_id} not found")
    
    # Update workflow state
    workflow_state["task_ids"]["post_generation"] = self.request.id
    workflow_state["status"] = "post_generation"
    task_manager.store_workflow_state(workflow_state)
    
    # ... post-generation logic ...
    
    # Clear workflow state on completion
    workflow_state["status"] = "completed"
    task_manager.store_workflow_state(workflow_state)
    
    # Optionally: Clear after a delay to allow for error recovery
    # task_manager.clear_workflow_state(workflow_state["project_uuid"], workflow_state["contact_urn"])
    
    return True
```

### Pros
- ✅ Handles concurrent messages correctly
- ✅ Revokes entire workflow (all 3 tasks)
- ✅ Message concatenation before processing
- ✅ Workflow state tracking
- ✅ Can recover from partial failures
- ✅ Clear separation of orchestration from business logic

### Cons
- ❌ Additional complexity (workflow state management)
- ❌ Requires Redis for state storage
- ❌ Need to handle workflow state cleanup
- ❌ More failure points (but more granular control)

---

## Caching Strategy

**Status:** ✅ **FULLY IMPLEMENTED** (December 2024)
- `CacheService` (`router/services/cache_service.py`) - ✅ Complete
- `PreGenerationService` (`router/services/pre_generation_service.py`) - ✅ Complete
- Cache invalidation observers (`router/services/cache_invalidation_observers.py`) - ✅ Complete
- Project-level caching with TTL management - ✅ Complete
- Cache invalidation on data updates (API + Admin) - ✅ Complete
- `CachedProjectData` dataclass for type-safe cached data - ✅ Complete
- Backend integration (OpenAI) using cached dictionaries - ✅ Complete

### Purpose
Cache data fetched in Pre-Generation that is needed by Generation and Post-Generation tasks, avoiding redundant database queries and improving performance. The cache system is **already implemented** and will be integrated into Pre-Generation in Phase 1.

### Cacheable Data

#### 1. **Project Data** (High Priority)
- **Fetched in:** Pre-Generation
- **Used in:** Generation, Post-Generation
- **Cache Key:** `workflow:{workflow_id}:project`
- **TTL:** Workflow duration (cleared on completion)
- **Size:** ~1-5 KB per project
- **Benefit:** Avoids 1-2 database queries per workflow

**Data to Cache:**
```python
{
    "uuid": str,
    "agents_backend": str,
    "use_components": bool,
    "rationale_switch": bool,
    "use_prompt_creation_configurations": bool,
    "conversation_turns_to_include": int | None,
    "exclude_previous_thinking_steps": bool,
    "default_supervisor_foundation_model": str,
    "human_support": bool,
    "human_support_prompt": str | None,
    # Serialize Django model to dict
}
```

#### 2. **Content Base Data** (High Priority)
- **Fetched in:** Pre-Generation
- **Used in:** Generation
- **Cache Key:** `workflow:{workflow_id}:content_base`
- **TTL:** Workflow duration
- **Size:** ~2-10 KB per content base
- **Benefit:** Avoids 2-3 database queries with joins

**Data to Cache:**
```python
{
    "uuid": str,
    "title": str,
    "intelligence_uuid": str,
    "agent": {
        "name": str,
        "role": str,
        "personality": str,
        "goal": str,
    },
    "instructions": [
        {"instruction": str, "order": int},
        # ... all instructions
    ],
}
```

#### 3. **Team Data** (High Priority)
- **Fetched in:** Pre-Generation
- **Used in:** Generation
- **Cache Key:** `workflow:{workflow_id}:team`
- **TTL:** Workflow duration
- **Size:** ~10-50 KB per team (depends on number of agents)
- **Benefit:** Avoids complex query with multiple joins and transformations

**Data to Cache:**
```python
[
    {
        "agentName": str,
        "instruction": str,
        "actionGroups": [...],
        "foundationModel": str,
        "agentCollaboration": str,
        "collaborator_configurations": str,
        "agentDisplayName": str | None,  # OpenAI only
    },
    # ... all agents
]
```

#### 4. **Inline Agent Configuration** (Medium Priority)
- **Fetched in:** Pre-Generation
- **Used in:** Generation (OpenAI backend only)
- **Cache Key:** `workflow:{workflow_id}:inline_agent_config`
- **TTL:** Workflow duration
- **Size:** ~1-5 KB
- **Benefit:** Avoids 1 database query (OpenAI only)

**Data to Cache:**
```python
{
    "agents_backend": str,
    "configuration": dict | None,  # Full config dict
}
```

#### 5. **Action Clients Configuration** (Medium Priority)
- **Created in:** Pre-Generation
- **Used in:** Post-Generation
- **Cache Key:** `workflow:{workflow_id}:action_clients_config`
- **TTL:** Workflow duration
- **Size:** ~0.5 KB
- **Benefit:** Avoids recreating clients (though lightweight)

**Note:** Can't cache client instances (not serializable), but can cache config:
```python
{
    "preview": bool,
    "multi_agents": bool,
    "project_use_components": bool,
    # Clients will be recreated in Post-Generation using this config
}
```

#### 6. **Guardrails Configuration** (Low Priority - Optional)
- **Fetched in:** Pre-Generation
- **Used in:** Pre-Generation only (but could be reused)
- **Cache Key:** `project:{project_uuid}:guardrails`
- **TTL:** 1 hour (longer TTL - project-level cache)
- **Size:** ~0.5 KB
- **Benefit:** Avoids database query if multiple workflows for same project

**Data to Cache:**
```python
{
    "guardrailIdentifier": str,
    "guardrailVersion": str,
}
```

### Implementation

#### Enhanced RedisTaskManager Methods

```python
class RedisTaskManager(TaskManager):
    # ... existing methods ...
    
    # Cache TTL - matches workflow timeout
    WORKFLOW_CACHE_TTL = 600  # 10 minutes (longer than max workflow time)
    PROJECT_CACHE_TTL = 3600  # 1 hour for project-level caches
    
    def cache_workflow_data(
        self,
        workflow_id: str,
        data_type: str,
        data: Dict | List,
        ttl: int = None
    ) -> None:
        """Cache data for a workflow."""
        cache_key = f"workflow:{workflow_id}:{data_type}"
        ttl = ttl or self.WORKFLOW_CACHE_TTL
        
        # Serialize data (handle Django models, datetime, etc.)
        serialized = self._serialize_data(data)
        
        self.redis_client.setex(
            cache_key,
            ttl,
            json.dumps(serialized, default=str)
        )
    
    def get_workflow_cached_data(
        self,
        workflow_id: str,
        data_type: str
    ) -> Optional[Dict | List]:
        """Get cached data for a workflow."""
        cache_key = f"workflow:{workflow_id}:{data_type}"
        cached = self.redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached.decode("utf-8"))
        return None
    
    def cache_project_data(
        self,
        project_uuid: str,
        data_type: str,
        data: Dict,
        ttl: int = None
    ) -> None:
        """Cache project-level data (longer TTL)."""
        cache_key = f"project:{project_uuid}:{data_type}"
        ttl = ttl or self.PROJECT_CACHE_TTL
        
        serialized = self._serialize_data(data)
        self.redis_client.setex(
            cache_key,
            ttl,
            json.dumps(serialized, default=str)
        )
    
    def get_project_cached_data(
        self,
        project_uuid: str,
        data_type: str
    ) -> Optional[Dict]:
        """Get cached project-level data."""
        cache_key = f"project:{project_uuid}:{data_type}"
        cached = self.redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached.decode("utf-8"))
        return None
    
    def clear_workflow_cache(self, workflow_id: str) -> None:
        """Clear all cached data for a workflow."""
        pattern = f"workflow:{workflow_id}:*"
        keys = self.redis_client.keys(pattern)
        if keys:
            self.redis_client.delete(*keys)
    
    def _serialize_data(self, data: Any) -> Any:
        """Serialize data for Redis storage."""
        if isinstance(data, (dict, list)):
            # Recursively serialize
            if isinstance(data, dict):
                return {k: self._serialize_data(v) for k, v in data.items()}
            else:
                return [self._serialize_data(item) for item in data]
        elif hasattr(data, '__dict__'):
            # Django model or object - convert to dict
            return self._serialize_data(data.__dict__)
        elif hasattr(data, 'isoformat'):
            # datetime objects
            return data.isoformat()
        else:
            return data
```

#### Usage in Pre-Generation Task

**Note:** The cache system is already implemented in `CacheService`. This example shows how it will be integrated in Phase 1.

```python
def pre_generation_task(self, message: Dict, workflow_id: str, **kwargs):
    from router.services.cache_service import CacheService
    
    cache_service = CacheService()
    project_uuid = message.get("project_uuid")
    
    # Use CacheService for project-level caching (already implemented)
    # This will check cache first, fetch if miss, and cache the result
    project_dict = cache_service.get_project_data(
        project_uuid,
        fetch_func=lambda uuid: _project_to_dict(get_project_and_content_base_data(uuid)[0])
    )
    
    content_base_dict = cache_service.get_content_base_data(
        project_uuid,
        fetch_func=lambda uuid: _content_base_to_dict(get_project_and_content_base_data(uuid)[1])
    )
    
    # Get agents_backend from cached project data
    agents_backend = project_dict.get("agents_backend")
    
    # Use CacheService for team data (already implemented)
    team = cache_service.get_team_data(
        project_uuid,
        agents_backend,
        fetch_func=lambda uuid, backend: ORMTeamRepository(
            agents_backend=backend,
            project=project_obj
        ).get_team(uuid)
    )
    
    # Use CacheService for guardrails (already implemented)
    guardrails_config = cache_service.get_guardrails_config(
        project_uuid,
        fetch_func=lambda uuid: GuardrailsUsecase.get_guardrail_as_dict(uuid)
    )
    
    # Get inline agent config if available
    inline_agent_config = cache_service.get_inline_agent_config(
        project_uuid,
        fetch_func=lambda uuid: _get_inline_agent_config(get_project_and_content_base_data(uuid)[2])
    )
    
    # ... rest of pre-generation logic using cached data ...
    
    return {
        "status": "success",
        "workflow_id": workflow_id,
        # Don't return large data - it's in cache
        "project_uuid": project_uuid,
        "agents_backend": agents_backend,
        # ... other metadata ...
    }
```

**Key Benefits:**
- ✅ Cache hit = No database queries
- ✅ Cache miss = Fetch once, cache for future requests
- ✅ Automatic invalidation via observers when data changes
- ✅ Project-level caching shared across all workflows for same project

#### Usage in Generation Task

```python
def generation_task(self, pre_result: Dict, message: Dict, workflow_id: str, **kwargs):
    task_manager = get_task_manager()
    
    # Retrieve cached data
    project_dict = task_manager.get_workflow_cached_data(workflow_id, "project")
    content_base_dict = task_manager.get_workflow_cached_data(workflow_id, "content_base")
    team = task_manager.get_workflow_cached_data(workflow_id, "team")
    inline_agent_config = task_manager.get_workflow_cached_data(
        workflow_id, "inline_agent_config"
    )
    
    if not all([project_dict, content_base_dict, team]):
        raise ValueError(f"Missing cached data for workflow {workflow_id}")
    
    # Deserialize to objects if needed, or work with dicts
    # (Depending on backend requirements)
    
    # ... generation logic using cached data ...
    
    return {
        "status": "success",
        "response": response_text,
        "session_id": session_id,
        # ... other results ...
    }
```

#### Usage in Post-Generation Task

```python
def post_generation_task(self, gen_result: Dict, pre_result: Dict, message: Dict, workflow_id: str, **kwargs):
    task_manager = get_task_manager()
    
    # Retrieve cached data
    project_dict = task_manager.get_workflow_cached_data(workflow_id, "project")
    action_clients_config = task_manager.get_workflow_cached_data(
        workflow_id, "action_clients_config"
    )
    
    # Recreate action clients from config
    broadcast, flow_start = get_action_clients(**action_clients_config)
    
    # ... post-generation logic ...
    
    # Clear workflow cache on completion
    task_manager.clear_workflow_cache(workflow_id)
    
    return True
```

### Extended Caching Strategy: Project-Level Caching

**Status:** ✅ Already implemented in `CacheService`

Since `start_inline_agents` is called for **every message** from a user, we cache project-level configuration data for longer periods. This data changes infrequently and can be shared across multiple workflows and messages. The `CacheService` already implements this strategy with appropriate TTLs.

#### Project-Level Cache TTLs

| Data Type | TTL | Reason |
|-----------|-----|--------|
| Project Data | 1 hour | Changes infrequently (backend, flags, config) |
| Content Base Data | 30 minutes | May change when instructions are updated |
| Team Data | 15 minutes | Agents may be added/removed, but not frequently |
| Inline Agent Config | 1 hour | Configuration changes are rare |
| Guardrails Config | 1 hour | Guardrails are updated infrequently |
| Action Clients Config | N/A | Derived from project data, no separate cache needed |

#### Benefits of Extended Caching

1. **Reduced Database Load:** Multiple messages from same project reuse cached data
2. **Faster Response Times:** No database queries for configuration data
3. **Better Scalability:** Handles high message volume more efficiently
4. **Cost Savings:** Fewer database queries = lower costs

#### Cache Key Strategy

**Project-Level Caches:**
- `project:{project_uuid}:data` - Project configuration
- `project:{project_uuid}:content_base` - Content base data
- `project:{project_uuid}:team` - Team/agents data
- `project:{project_uuid}:inline_agent_config` - Inline agent configuration
- `project:{project_uuid}:guardrails` - Guardrails configuration

**Workflow-Level Caches (short-lived):**
- `workflow:{workflow_id}:project` - Project data (fallback if project cache miss)
- `workflow:{workflow_id}:content_base` - Content base data (fallback)
- `workflow:{workflow_id}:team` - Team data (fallback)
- `workflow:{workflow_id}:action_clients_config` - Action clients config

### Cache Invalidation Strategy

#### 1. **Workflow Completion**
- Clear all workflow-specific caches when workflow completes
- Keep project-level caches (they're still valid)

#### 2. **Workflow Failure/Revocation**
- Clear workflow caches on error or revocation
- Project-level caches remain (may be useful for retry)

#### 3. **Project Data Updates** (Manual Invalidation)
When project data changes (via admin/API), invalidate project-level caches:

```python
# In project update handlers
def invalidate_project_cache(project_uuid: str):
    """Invalidate all project-level caches."""
    patterns = [
        f"project:{project_uuid}:data",
        f"project:{project_uuid}:content_base",
        f"project:{project_uuid}:team",
        f"project:{project_uuid}:inline_agent_config",
        f"project:{project_uuid}:guardrails",
    ]
    
    for pattern in patterns:
        keys = redis_client.keys(pattern)
        if keys:
            redis_client.delete(*keys)
```

#### 4. **TTL-Based Expiration**
- Project-level caches expire after TTL (1 hour, 30 min, 15 min)
- Automatic refresh on next access after expiration
- No manual cleanup needed for expired caches

### Implementation Details

**Note:** The cache system is already implemented in `CacheService` (`router/services/cache_service.py`). The following shows the structure, but the actual implementation uses `CacheService` methods.

#### CacheService Methods (Already Implemented)

The `CacheService` class provides all necessary methods:

```python
# Already implemented in router/services/cache_service.py
class CacheService:
    def get_project_data(project_uuid, fetch_func) -> Dict
    def get_content_base_data(project_uuid, fetch_func) -> Dict
    def get_team_data(project_uuid, agents_backend, fetch_func) -> List[Dict]
    def get_guardrails_config(project_uuid, fetch_func) -> Dict
    def get_inline_agent_config(project_uuid, fetch_func) -> Optional[Dict]
    def invalidate_project_cache(project_uuid, fetch_funcs, agents_backend)
    # ... and more
```

#### Legacy Implementation Reference (For Context)

The following shows how caching was originally planned via `RedisTaskManager`, but the actual implementation uses `CacheService`:

```python
# NOTE: This is for reference only. Actual implementation uses CacheService.
class RedisTaskManager(TaskManager):
    # Cache TTLs
    WORKFLOW_CACHE_TTL = 600  # 10 minutes (workflow-specific)
    PROJECT_DATA_TTL = 3600  # 1 hour (project data)
    CONTENT_BASE_TTL = 1800  # 30 minutes (content base)
    TEAM_DATA_TTL = 900  # 15 minutes (team data)
    INLINE_AGENT_CONFIG_TTL = 3600  # 1 hour
    GUARDRAILS_TTL = 3600  # 1 hour
    
    def get_project_data_cached(self, project_uuid: str) -> Optional[Dict]:
        """Get project data from project-level cache."""
        return self.get_project_cached_data(project_uuid, "data")
    
    def cache_project_data_extended(
        self,
        project_uuid: str,
        data_type: str,
        data: Dict | List,
        ttl: int = None
    ) -> None:
        """Cache project-level data with extended TTL."""
        # Determine TTL based on data type
        ttl_map = {
            "data": self.PROJECT_DATA_TTL,
            "content_base": self.CONTENT_BASE_TTL,
            "team": self.TEAM_DATA_TTL,
            "inline_agent_config": self.INLINE_AGENT_CONFIG_TTL,
            "guardrails": self.GUARDRAILS_TTL,
        }
        
        ttl = ttl or ttl_map.get(data_type, self.PROJECT_DATA_TTL)
        self.cache_project_data(project_uuid, data_type, data, ttl)
    
    def get_or_fetch_project_data(
        self,
        project_uuid: str,
        fetch_func: Callable
    ) -> Dict:
        """
        Get project data from cache, or fetch and cache if not available.
        
        Args:
            project_uuid: Project UUID
            fetch_func: Function to fetch data if cache miss
        
        Returns:
            Project data dict
        """
        # Try project-level cache first
        cached = self.get_project_data_cached(project_uuid)
        if cached:
            return cached
        
        # Fetch from database
        project_data = fetch_func(project_uuid)
        
        # Cache for future use
        self.cache_project_data_extended(
            project_uuid, "data", project_data
        )
        
        return project_data
    
    def get_or_fetch_content_base(
        self,
        project_uuid: str,
        fetch_func: Callable
    ) -> Dict:
        """Get content base from cache or fetch."""
        cached = self.get_project_cached_data(project_uuid, "content_base")
        if cached:
            return cached
        
        content_base_data = fetch_func(project_uuid)
        self.cache_project_data_extended(
            project_uuid, "content_base", content_base_data
        )
        
        return content_base_data
    
    def get_or_fetch_team(
        self,
        project_uuid: str,
        agents_backend: str,
        fetch_func: Callable
    ) -> List[Dict]:
        """Get team data from cache or fetch."""
        # Team cache key includes backend (different backends = different teams)
        cache_key = f"team:{agents_backend}"
        cached = self.get_project_cached_data(project_uuid, cache_key)
        if cached:
            return cached
        
        team_data = fetch_func(project_uuid, agents_backend)
        self.cache_project_data_extended(
            project_uuid, cache_key, team_data, ttl=self.TEAM_DATA_TTL
        )
        
        return team_data
    
    def invalidate_project_cache(self, project_uuid: str) -> None:
        """Invalidate all project-level caches for a project."""
        patterns = [
            f"project:{project_uuid}:*",
        ]
        
        for pattern in patterns:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
```

#### Pre-Generation Task with CacheService Integration (Phase 1)

**Note:** This will be implemented in Phase 1 using the already-created `CacheService`.

```python
def pre_generation_task(self, message: Dict, workflow_id: str, **kwargs):
    from router.services.cache_service import CacheService
    from nexus.usecases.intelligences.get_by_uuid import get_project_and_content_base_data
    from nexus.inline_agents.team.repository import ORMTeamRepository
    from nexus.usecases.guardrails.guardrails_usecase import GuardrailsUsecase
    
    cache_service = CacheService()
    project_uuid = message.get("project_uuid")
    
    # Helper functions to convert to dict (for caching)
    def _project_to_dict(proj):
        return {
            "uuid": str(proj.uuid),
            "agents_backend": proj.agents_backend,
            "use_components": proj.use_components,
            # ... other fields
        }
    
    def _content_base_to_dict(cb):
        return {
            "uuid": str(cb.uuid),
            "title": cb.title,
            "intelligence_uuid": str(cb.intelligence.uuid),
        }
    
    # Use CacheService - automatically checks cache, fetches if miss, caches result
    project_dict = cache_service.get_project_data(
        project_uuid,
        fetch_func=lambda uuid: _project_to_dict(get_project_and_content_base_data(uuid)[0])
    )
    
    content_base_dict = cache_service.get_content_base_data(
        project_uuid,
        fetch_func=lambda uuid: _content_base_to_dict(get_project_and_content_base_data(uuid)[1])
    )
    
    # Get agents_backend from cached project data
    agents_backend = project_dict["agents_backend"]
    
    # Use CacheService for team data
    team = cache_service.get_team_data(
        project_uuid,
        agents_backend,
        fetch_func=lambda uuid, backend: ORMTeamRepository(
            agents_backend=backend,
            project=project_obj
        ).get_team(uuid)
    )
    
    # Use CacheService for guardrails
    guardrails_config = cache_service.get_guardrails_config(
        project_uuid,
        fetch_func=lambda uuid: GuardrailsUsecase.get_guardrail_as_dict(uuid)
    )
    
    # Get inline agent config if available
    inline_agent_config = cache_service.get_inline_agent_config(
        project_uuid,
        fetch_func=lambda uuid: _get_inline_agent_config(get_project_and_content_base_data(uuid)[2])
    )
    
    # ... rest of pre-generation logic using cached data ...
    
    return {
        "status": "success",
        "workflow_id": workflow_id,
        "project_uuid": project_uuid,
        "agents_backend": agents_backend,
        # ... other metadata ...
    }
```

**Key Points:**
- ✅ Uses existing `CacheService` (already implemented)
- ✅ Automatic cache-first strategy (check cache → fetch if miss → cache result)
- ✅ Project-level caching (shared across workflows)
- ✅ Automatic invalidation via observers when data changes
- ✅ No manual cache management needed

### Cache Size Estimation (Extended)

**Per Project (project-level caches):**
- Project data: ~2 KB
- Content base: ~5 KB
- Team data: ~20 KB (5 agents)
- Inline agent config: ~2 KB
- Guardrails: ~0.5 KB
- **Total per project: ~30 KB**

**For 1000 active projects: ~30 MB**

**Per Workflow (workflow-level caches - short-lived):**
- Same as above, but only for active workflows
- **For 100 concurrent workflows: ~3 MB**

**Total Redis Memory: ~33 MB** (very manageable)

### Pros of Extended Caching

- ✅ **Massive database load reduction** - One cache hit serves hundreds of messages
- ✅ **Faster response times** - No database queries for configuration
- ✅ **Better scalability** - Handles high message volume efficiently
- ✅ **Cost savings** - Fewer database queries
- ✅ **Improved user experience** - Faster message processing
- ✅ **Reduced database connection pool pressure**

### Cons of Extended Caching

- ❌ **Stale data risk** - Data may be outdated if project is updated
- ❌ **Memory usage** - More Redis memory (but still manageable)
- ❌ **Cache invalidation complexity** - Need to invalidate on updates
- ❌ **Debugging complexity** - Need to check cache vs database

### Recommendations

1. **Start with Extended TTLs:**
   - Project data: 1 hour
   - Content base: 30 minutes
   - Team data: 15 minutes

2. **Implement Cache Invalidation:**
   - Add invalidation hooks in project update handlers
   - Monitor cache hit rates

3. **Monitor Cache Performance:**
   - Track cache hit/miss rates
   - Monitor Redis memory usage
   - Alert on low hit rates

4. **Gradual Rollout:**
   - Start with shorter TTLs (15-30 min)
   - Increase based on hit rates and data update frequency
   - Monitor for stale data issues

5. **Fallback Strategy:**
   - Always have database fetch as fallback
   - Log cache misses for analysis
   - Consider cache versioning for critical updates

---

## Phase 1: Pre-Generation Task

### Purpose
Handle all validation, setup, and preparation work that can be done in parallel or before the main invocation.

### Responsibilities
- Send typing indicator
- Fetch project/content_base/team data
- Run guardrails/complexity checks
- Preprocess message (attachments, products)
- Validate message (empty text, unsafe content)
- Prepare action clients
- Manage pending tasks (revoke old, handle concatenation)

### Execution Flow

```
Pre-Generation Task
├── Parallel Execution:
│   ├── Send typing indicator (non-blocking)
│   ├── Fetch project data (DB)
│   └── Get action clients (factory)
├── Sequential:
│   ├── Run guardrails/complexity (Lambda)
│   ├── Preprocess message
│   └── Validate message
└── Output:
    ├── Validated message
    ├── Project/ContentBase/Team data
    ├── Action clients
    ├── Foundation model (if Bedrock)
    └── Turn off rationale flag
```

### Task Signature

```python
@celery_app.task(
    bind=True,
    soft_time_limit=60,  # Shorter timeout
    time_limit=90,
    max_retries=3,
)
def pre_generation_task(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    workflow_id: str = None,  # From orchestrator
) -> Dict:
    """
    Returns:
    {
        "status": "success" | "failed" | "blocked",
        "message": processed_message,
        "project": project_obj,
        "content_base": content_base_obj,
        "team": team_list,
        "action_clients": (broadcast, flow_start),
        "foundation_model": str | None,
        "turn_off_rationale": bool,
        "error": str | None,  # If blocked by guardrails
        "task_id": str,
    }
    """
```

### Early Exit Conditions
- **Guardrails block**: Returns `status="blocked"` with error message
- **Empty text**: Raises exception
- **Invalid project**: Raises exception

### Pros
- ✅ Can fail fast before expensive operations
- ✅ Parallel execution of independent operations
- ✅ Clear separation of validation logic
- ✅ Can be cached/optimized independently
- ✅ Easier to test validation logic

### Cons
- ❌ Adds task orchestration complexity
- ❌ Requires data serialization between tasks
- ❌ Additional Redis/database state management
- ❌ More failure points (but more granular)

---

## Phase 2: Generation Task

### Purpose
Execute the core agent invocation with minimal dependencies. This is the critical path that should start as quickly as possible.

### Responsibilities
- Create message DTO
- Get backend instance
- Invoke agents (core logic)
- Return response

### Execution Flow

```
Generation Task
├── Input Validation (minimal)
├── Create message DTO
├── Get backend from registry
├── Invoke agents
│   ├── Session setup (Redis)
│   ├── Supervisor setup
│   ├── Team adaptation
│   └── Agent execution
└── Output:
    ├── Response text
    ├── Session ID
    ├── Trace events (if any)
    └── Metadata
```

### Task Signature

```python
@celery_app.task(
    bind=True,
    soft_time_limit=240,  # Most of the time budget
    time_limit=300,
    max_retries=2,  # Fewer retries (expensive operation)
)
def generation_task(
    self,
    pre_generation_result: Dict,  # From pre-generation task
    message: Dict,  # Original message
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
    workflow_id: str = None,  # From orchestrator
) -> Dict:
    """
    Returns:
    {
        "status": "success" | "failed",
        "response": str,
        "session_id": str,
        "trace_events": List[Dict],
        "metadata": Dict,
        "error": str | None,
    }
    """
```

### Minimal Dependencies
- Only requires validated data from pre-generation
- No external validation calls
- No database queries (data already fetched)
- Focused on agent execution only

### Pros
- ✅ Fast start (no blocking operations)
- ✅ Clear single responsibility
- ✅ Can be optimized independently
- ✅ Easier to scale (most CPU-intensive)
- ✅ Can be retried independently

### Cons
- ❌ Requires pre-generation to complete first
- ❌ Depends on data serialization
- ❌ Still a large method (but more focused)

---

## Phase 3: Post-Generation Task

### Purpose
Handle all persistence, logging, and cleanup operations that don't block the user response.

### Responsibilities
- Save messages to database (DynamoDB + PostgreSQL)
- Save trace events
- Send data lake events
- Clear pending tasks
- Dispatch response to user
- Handle preview mode
- Cleanup resources

### Execution Flow

```
Post-Generation Task
├── Parallel Execution:
│   ├── Save message to DB (async)
│   ├── Save trace events (async)
│   └── Send data lake events (async)
├── Sequential:
│   ├── Clear pending tasks
│   ├── Dispatch response
│   └── Cleanup
└── Output:
    └── Success status
```

### Task Signature

```python
@celery_app.task(
    bind=True,
    soft_time_limit=60,
    time_limit=90,
    max_retries=3,
)
def post_generation_task(
    self,
    pre_generation_result: Dict,
    generation_result: Dict,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
    workflow_id: str = None,  # From orchestrator
) -> bool:
    """
    Returns:
    bool - Success status
    """
```

### Pros
- ✅ Non-blocking for user response
- ✅ Can be retried independently
- ✅ Parallel persistence operations
- ✅ Clear separation of concerns
- ✅ Can be optimized for throughput

### Cons
- ❌ Adds orchestration complexity
- ❌ Requires data from previous tasks
- ❌ More failure points (but non-critical)

---

## Observer Pattern for Cross-Cutting Concerns

### Purpose
Decouple infrastructure concerns (logging, tracing, metrics) from business logic using the **existing Observer infrastructure** in the codebase.

### Existing Infrastructure

The codebase already has a robust observer system:
- **EventManager** (`nexus.events.event_manager`) - Synchronous events
- **AsyncEventManager** (`nexus.events.async_event_manager`) - Asynchronous events
- **@observer decorator** - Automatic registration
- **Error isolation** - Built-in (`isolate_errors=True`)
- **Middleware** - Sentry and performance monitoring already included
- **Validators** - Event payload validation
- **Factory pattern** - Dependency injection support

**Reference:** See `nexus/event_domain/OBSERVER_GUIDE.md` for full documentation.

### Architecture

```
Existing EventManager (nexus.events)
├── Observers (using @observer decorator):
│   ├── TracingObserver (Langfuse) - NEW
│   ├── DataLakeObserver (Data Lake events) - NEW
│   ├── LoggingObserver (Application logs) - NEW
│   ├── MetricsObserver (Prometheus/StatsD) - NEW
│   ├── PreviewObserver (Websocket updates) - NEW
│   └── RationaleObserver (existing) - Already implemented
└── Events:
    ├── inline_agent_pre_generation_started
    ├── inline_agent_pre_generation_completed
    ├── inline_agent_generation_started
    ├── inline_agent_generation_completed
    ├── inline_agent_post_generation_started
    ├── inline_agent_post_generation_completed
    ├── inline_agent_guardrails_blocked
    ├── inline_agent_error_occurred
    └── inline_trace_observers (existing) - Already in use
```

### Implementation Examples

#### 1. TracingObserver (Langfuse)

```python
from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver

@observer("inline_agent_generation_started", isolate_errors=True)
class TracingObserver(EventObserver):
    def perform(self, **kwargs):
        project_uuid = kwargs.get("project_uuid")
        contact_urn = kwargs.get("contact_urn")
        input_text = kwargs.get("input_text")
        
        # Create Langfuse trace
        from langfuse import get_client
        langfuse_client = get_client()
        
        with langfuse_client.start_as_current_span(
            name="Inline Agent Generation",
            metadata={
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
            }
        ) as span:
            span.update(input=input_text)
```

#### 2. DataLakeObserver

```python
@observer("inline_agent_tool_called", isolate_errors=True, manager="async")
class DataLakeObserver(EventObserver):
    async def perform(self, **kwargs):
        # Send to data lake asynchronously
        from weni_datalake_sdk.clients.client import send_event_data
        
        await send_event_data(
            project_uuid=kwargs.get("project_uuid"),
            contact_urn=kwargs.get("contact_urn"),
            tool_call_data=kwargs.get("tool_call_data"),
            agent_data=kwargs.get("agent_data"),
        )
```

#### 3. LoggingObserver

```python
@observer("inline_agent_pre_generation_started", isolate_errors=True)
class LoggingObserver(EventObserver):
    def perform(self, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(
            "Inline agent pre-generation started",
            extra={
                "project_uuid": kwargs.get("project_uuid"),
                "contact_urn": kwargs.get("contact_urn"),
                "preview": kwargs.get("preview", False),
            }
        )
```

#### 4. MetricsObserver

```python
@observer("inline_agent_generation_completed", isolate_errors=True)
class MetricsObserver(EventObserver):
    def perform(self, **kwargs):
        # Send metrics to Prometheus/StatsD
        from prometheus_client import Counter, Histogram
        
        task_duration = Histogram(
            'inline_agent_generation_duration_seconds',
            'Time spent in generation task'
        )
        task_success = Counter(
            'inline_agent_generation_total',
            'Total generation tasks',
            ['status']
        )
        
        duration = kwargs.get("duration", 0)
        status = kwargs.get("status", "unknown")
        
        task_duration.observe(duration)
        task_success.labels(status=status).inc()
```

#### 5. PreviewObserver (Websocket Updates)

```python
@observer("inline_agent_generation_started", isolate_errors=True)
class PreviewObserver(EventObserver):
    def perform(self, **kwargs):
        preview = kwargs.get("preview", False)
        user_email = kwargs.get("user_email")
        
        if not preview or not user_email:
            return
        
        from nexus.projects.websockets.consumers import send_preview_message_to_websocket
        
        send_preview_message_to_websocket(
            project_uuid=kwargs.get("project_uuid"),
            user_email=user_email,
            message_data={
                "type": "status",
                "content": "Starting agent processing",
                "session_id": kwargs.get("session_id"),
            },
        )
```

### Usage in Tasks

```python
from nexus.events import event_manager, async_event_manager

# In pre_generation_task
def pre_generation_task(self, message: Dict, **kwargs):
    event_manager.notify(
        "inline_agent_pre_generation_started",
        project_uuid=message.get("project_uuid"),
        contact_urn=message.get("contact_urn"),
        preview=kwargs.get("preview", False),
        task_id=self.request.id,
    )
    
    try:
        # ... pre-generation logic ...
        
        event_manager.notify(
            "inline_agent_pre_generation_completed",
            project_uuid=message.get("project_uuid"),
            contact_urn=message.get("contact_urn"),
            status="success",
            task_id=self.request.id,
        )
    except UnsafeMessageException as e:
        event_manager.notify(
            "inline_agent_guardrails_blocked",
            project_uuid=message.get("project_uuid"),
            contact_urn=message.get("contact_urn"),
            error_message=str(e),
            task_id=self.request.id,
        )
        raise

# In generation_task (async operations)
async def generation_task_async(self, pre_result: Dict, **kwargs):
    await async_event_manager.notify(
        "inline_agent_generation_started",
        project_uuid=pre_result.get("project_uuid"),
        contact_urn=pre_result.get("contact_urn"),
        input_text=pre_result.get("message", {}).get("text"),
        task_id=self.request.id,
    )
    
    # ... generation logic ...
    
    await async_event_manager.notify(
        "inline_agent_generation_completed",
        project_uuid=pre_result.get("project_uuid"),
        contact_urn=pre_result.get("contact_urn"),
        response=result.get("response"),
        duration=time.time() - start_time,
        task_id=self.request.id,
    )
```

### Pros
- ✅ **Uses existing infrastructure** - No new code needed
- ✅ **Automatic registration** - `@observer` decorator handles it
- ✅ **Error isolation built-in** - `isolate_errors=True` for non-critical observers
- ✅ **Middleware included** - Sentry and performance monitoring already work
- ✅ **Async support** - `async_event_manager` for async observers
- ✅ **Factory pattern** - Dependency injection already supported
- ✅ **Tested and proven** - Already used in production (e.g., `RationaleObserver`)
- ✅ **Follows existing patterns** - Consistent with codebase conventions

### Cons
- ❌ Event names need to be consistent (use naming convention)
- ❌ Observers must be imported to register (auto-import on module load)
- ❌ Debugging can be harder (indirect calls via event manager)

---

## Task Orchestration

### Option 1: Sequential Chain (Simple)

```python
@celery_app.task
def start_inline_agents_orchestrator(
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
):
    # Step 1: Pre-generation
    pre_result = pre_generation_task.delay(message, preview, language).get()
    
    if pre_result["status"] == "blocked":
        # Handle guardrails block
        return handle_blocked_message(pre_result, message, preview, user_email)
    
    # Step 2: Generation
    gen_result = generation_task.delay(
        pre_result, message, preview, language, user_email
    ).get()
    
    # Step 3: Post-generation (fire and forget)
    post_generation_task.delay(
        pre_result, gen_result, message, preview, language, user_email
    )
    
    return gen_result["response"]
```

**Pros:**
- Simple to implement
- Easy to understand
- Sequential execution

**Cons:**
- Blocks on each step
- No parallelization
- Slower overall

### Option 2: Celery Canvas with Workflow Orchestrator (Recommended)

```python
from celery import chain

@celery_app.task
def start_inline_agents_orchestrator(
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
):
    # Use the workflow orchestrator which handles state management
    return inline_agent_workflow_orchestrator.delay(
        message=message,
        preview=preview,
        language=language,
        user_email=user_email,
    )

# The orchestrator creates the chain internally
def inline_agent_workflow_orchestrator(
    self,
    message: Dict,
    preview: bool = False,
    language: str = "en",
    user_email: str = "",
):
    # Handle pending tasks and message concatenation
    task_manager = get_task_manager()
    final_message_text = task_manager.handle_workflow_message_concatenation(...)
    message["text"] = final_message_text
    
    # Create workflow state
    workflow_id = create_workflow_state(...)
    
    # Create task chain with workflow_id
    workflow = chain(
        pre_generation_task.s(message, preview, language, workflow_id),
        generation_task.s(message, preview, language, user_email, workflow_id),
        post_generation_task.s(message, preview, language, user_email, workflow_id),
    )
    
    # Execute with error handling
    try:
        result = workflow.apply_async()
        return result.get()
    except Exception as e:
        handle_workflow_error(e, workflow_id, message, preview, user_email)
```

**Pros:**
- Built-in Celery support
- Automatic retry handling
- Better error propagation
- Can use callbacks

**Cons:**
- Requires Celery Canvas knowledge
- Less flexible than custom orchestration

---

## Implementation Phases

### Phase 0: Cache System Integration (Week 1)
**Status:** ✅ **COMPLETED** (December 2024)

#### Completed Work

**Branch: `feature/cache-service`** (Base implementation)
- ✅ `CacheService` (`router/services/cache_service.py`) - Complete
- ✅ Cache repositories (Redis implementation with `RedisCacheRepository`)
- ✅ Cache key strategy with project-level TTLs
- ✅ `CachedProjectData` dataclass for type-safe cache data handling

**Branch: `feature/pre-generation-service`** (Based on `feature/cache-service`)
- ✅ `PreGenerationService` (`router/services/pre_generation_service.py`) - Complete
- ✅ Integrated `CacheService` for project/content_base/team/agent data fetching
- ✅ Returns `CachedProjectData` with all cached dictionaries (no Django objects)
- ✅ Helper methods for converting Django objects to dictionaries:
  - `_project_to_dict()` - Converts Project model to dict
  - `_content_base_to_dict()` - Converts ContentBase model to dict
  - `_instructions_to_list()` - Converts Instructions queryset to list
  - `_agent_to_dict()` - Converts Agent model to dict
  - `_get_inline_agent_config()` - Gets inline agent configuration
- ✅ Integrated into `start_inline_agents` task via `CachedProjectData`
- ✅ Backend integration (OpenAI) uses cached data via dictionaries
- ✅ Removed unused Django object parameters from backend methods

**Branch: `feature/cache-invalidation`** (Based on `feature/cache-service`)
- ✅ Cache invalidation observers (`router/services/cache_invalidation_observers.py`)
- ✅ Async event handling with `notify_async()` helper in `nexus/events.py`
- ✅ Observers for: `cache_invalidation:project`, `cache_invalidation:content_base`, `cache_invalidation:team`
- ✅ All cache invalidation call sites updated to use `notify_async()`
- ✅ Updated usecases: projects, intelligences (create/update/delete)

**Branch: `feature/admin-cache-invalidation`** (Based on `feature/cache-invalidation`)
- ✅ Django Admin hooks for cache invalidation
- ✅ `save_model` hook in `ProjectAdmin` triggers `cache_invalidation:project`
- ✅ `save_model` hook in `InlineAgentsConfigurationAdmin` triggers `cache_invalidation:project`
- ✅ `save_model` and `delete_model` hooks in `AgentAdmin` trigger `cache_invalidation:team`

**Branch: `feature/sentry-performance`** (Independent - preserved locally, not merged)
- ✅ Sentry transaction tracking via context manager
- ✅ `traces_sampler` for manual transaction sampling
- ✅ `CeleryIntegration` added to Sentry
- ✅ Colored debug logging for transaction tracking
- ⚠️ **Status:** Preserved locally, can be merged later when needed

#### Key Changes Summary

| Component | Before | After |
|-----------|--------|-------|
| Data Fetching | Direct Django ORM queries | Cache-first via `CacheService` |
| Data Format | Django objects | Dictionaries (JSON-serializable) |
| Backend Params | `project`, `content_base` objects | `cached_data: CachedProjectData` |
| Cache Invalidation | None | Async observers via `notify_async()` |
| Admin Updates | No cache handling | Auto-invalidation on save/delete |

#### Files Modified/Created

**Core Cache Infrastructure:**
- `router/services/cache_service.py` - Cache service with Redis backend
- `router/services/pre_generation_service.py` - Pre-generation with caching
- `router/tasks/invocation_context.py` - `CachedProjectData` dataclass
- `router/tasks/invoke.py` - Updated to use `CachedProjectData`

**Cache Invalidation:**
- `router/services/cache_invalidation_observers.py` - Async invalidation observers
- `nexus/events.py` - Added `notify_async()` helper function
- Various usecases updated to use `notify_async()` for cache events

**Admin Integration:**
- `nexus/projects/admin.py` - Project admin cache invalidation
- `nexus/inline_agents/admin.py` - InlineAgents admin cache invalidation

**Backend Updates:**
- `inline_agents/backends/openai/adapter.py` - Uses dict data, removed unused params
- `inline_agents/backends/openai/backend.py` - Removed unused params
- `inline_agents/backends/openai/repository.py` - Removed fallback code

#### Utility Scripts
- `nexus/staticfiles/cache/clear_pregeneration_cache.py` - Script to clear cache (for Django shell)

#### Remaining Work (Phase 0)
- ⏳ Cache usage patterns documented
- ⏳ Cache hit/miss rate monitoring (observers ready, metrics integration pending)
- ⏳ Unit tests for cache integration (see `test_suite_plan.md`)
- ⏳ Performance benchmarks (see `test_suite_plan.md`)

**Test Suite:** See `test_suite_plan.md` for comprehensive testing strategy.

---

### Phase 1: Pre-Generation Task Extraction (Week 1-2)
**Status:** ✅ **COMPLETED** (January 2025)

#### Completed
- ✅ Pre-Generation logic extracted into `PreGenerationService`
- ✅ Cache-first strategy implemented
- ✅ Returns `CachedProjectData` for downstream use
- ✅ Integrated into `start_inline_agents` task
- ✅ **Extracted into separate Celery task** (`pre_generation_task`)
- ✅ **Integrated with Workflow Orchestrator**
- ✅ **Serialization/deserialization of cached data between tasks**

**Deliverables:**
- ✅ Pre-Generation service with cache integration
- ✅ Cache-aware data fetching (project, content_base, team, guardrails, agent)
- ✅ Pre-Generation as separate Celery task (`router/tasks/pre_generation.py`)
- ✅ `serialize_cached_data()` / `deserialize_cached_data()` for task communication
- ✅ Event notifications for workflow stages

**Key Files:**
- `router/tasks/pre_generation.py` - Pre-Generation Celery task
- `router/services/pre_generation_service.py` - Core service logic
- `router/tasks/invocation_context.py` - `CachedProjectData` dataclass

### Phase 2: Workflow Orchestration (Week 2-3)
**Status:** ✅ **COMPLETED** (January 2025)

#### Completed
- ✅ Enhanced `RedisTaskManager` with workflow state management
- ✅ Implemented workflow orchestrator task (`inline_agent_workflow`)
- ✅ Workflow state storage/retrieval methods
- ✅ Pre-Generation integrated with workflow orchestrator
- ✅ Task revocation on new messages (with self-exclusion for retries)
- ✅ Message concatenation for rapid user inputs
- ✅ Feature flag (`WORKFLOW_ARCHITECTURE_PROJECTS`) for gradual rollout

**Deliverables:**
- ✅ Enhanced `RedisTaskManager` with workflow methods (`router/tasks/redis_task_manager.py`)
- ✅ `inline_agent_workflow` task (`router/tasks/workflow_orchestrator.py`)
- ✅ `WorkflowContext` dataclass for workflow state
- ✅ Workflow observers (`router/tasks/workflow_observers.py`)
- ✅ Observer registration app (`nexus/observers/`)
- ✅ Unit tests for workflow management

**Key Files:**
- `router/tasks/workflow_orchestrator.py` - Main orchestrator task
- `router/tasks/redis_task_manager.py` - Workflow state management
- `router/tasks/workflow_observers.py` - Typing indicator observer
- `nexus/observers/apps.py` - Centralized observer registration

**Workflow State Structure (Implemented):**
```python
workflow_state = {
    "workflow_id": "workflow-{uuid}",
    "project_uuid": str,
    "contact_urn": str,
    "status": "pre_generation" | "generation" | "post_generation" | "completed" | "failed",
    "task_ids": {
        "pre_generation": str | None,
        "generation": str | None,
        "post_generation": str | None,
    },
    "created_at": str,
    "updated_at": str,
    "final_message_text": str,
}
```

### Phase 3: Core Refactoring (Week 3-4)
**Status:** 🔄 **PARTIALLY COMPLETE** - Generation and Post-Generation are inline in orchestrator

#### Completed
- ✅ Three-phase workflow structure implemented
- ✅ Cache data sharing between phases via serialization
- ✅ Full workflow chain working end-to-end
- ✅ Error handling and cleanup

#### Current State
Generation and Post-Generation phases are currently **inline functions** within the workflow orchestrator (`_run_generation`, `_run_post_generation`). This works correctly but doesn't allow independent scaling/retry of these phases.

#### Remaining (Optional - for future scaling needs)
1. ⏳ Extract Generation into separate Celery task
2. ⏳ Extract Post-Generation into separate Celery task
3. ⏳ Use Celery Canvas chain for task orchestration

**Note:** Current inline implementation is simpler and works well. Extraction to separate tasks is optional and should only be done if independent scaling/retry is needed.

**Deliverables:**
- ✅ Full workflow chain integration (inline)
- ✅ Cache data sharing between Pre-Generation and Generation
- ✅ End-to-end workflow tests (staging)
- ⏳ Generation as separate Celery task (optional)
- ⏳ Post-Generation as separate Celery task (optional)

### Phase 4: Observer Integration & Optimization (Week 4-5)
**Status:** 🔄 **PARTIALLY COMPLETE**

#### Completed
- ✅ Observer registration infrastructure (`nexus/observers/apps.py`)
- ✅ Typing indicator observer (`TypingIndicatorObserver`)
- ✅ Cache invalidation observers (project, content_base, team)
- ✅ Existing observers working (RationaleObserver, SaveTracesObserver)

#### Remaining
1. ⏳ DataLakeObserver - Send events to data lake
2. ⏳ MetricsObserver - Prometheus/StatsD metrics
3. ⏳ TracingObserver - Langfuse integration
4. ⏳ LoggingObserver - Structured logging
5. ⏳ Cache hit/miss rate monitoring

**Observer Registration (Implemented):**
```python
# nexus/observers/apps.py
OBSERVER_MODULES = [
    "nexus.actions.observers",
    "nexus.intelligences.observer",
    "nexus.logs.observers",
    "nexus.projects.observer",
    "router.services.cache_invalidation_observers",
    "router.tasks.workflow_observers",
    "router.traces_observers.rationale.observer",
    "router.traces_observers.save_traces",
    "router.traces_observers.summary",
]
```

**Deliverables:**
- ✅ Observer registration app (`nexus/observers/`)
- ✅ Workflow observers (typing indicator)
- ⏳ Additional observers (DataLake, Metrics, Tracing, Logging)
- ⏳ Cache performance monitoring
- ⏳ Performance benchmarks

### Phase 5: Migration & Rollout (Week 5-6)
**Status:** 🔄 **IN PROGRESS** - Feature flag implemented, testing on staging

#### Completed
- ✅ Feature flag implemented (`WORKFLOW_ARCHITECTURE_PROJECTS`)
- ✅ Per-project rollout capability
- ✅ Testing on staging environment

#### Current State
The workflow architecture is controlled by `WORKFLOW_ARCHITECTURE_PROJECTS` environment variable (list of project UUIDs). Projects in this list use the new workflow; others use the legacy `start_inline_agents`.

**Feature Flag Implementation:**
```python
# In start_inline_agents task
if message_obj.project_uuid in settings.WORKFLOW_ARCHITECTURE_PROJECTS:
    return inline_agent_workflow.run(...)  # New workflow
else:
    # Legacy implementation
```

#### Remaining
1. ⏳ Add more projects to staging testing
2. ⏳ Monitor performance metrics
3. ⏳ Production rollout (gradual)
4. ⏳ Full migration (all projects)
5. ⏳ Remove legacy code

**Deliverables:**
- ✅ Feature flag (`WORKFLOW_ARCHITECTURE_PROJECTS`)
- ✅ Staging testing
- ⏳ Production rollout plan
- ⏳ Performance comparison metrics
- ⏳ Rollback plan documentation

---

## Migration Strategy

### Feature Flag Approach (Implemented)

The migration uses a **per-project feature flag** (`WORKFLOW_ARCHITECTURE_PROJECTS`) for granular rollout:

```python
# In settings.py
WORKFLOW_ARCHITECTURE_PROJECTS = env.list("WORKFLOW_ARCHITECTURE_PROJECTS", default=[])

# In start_inline_agents task (router/tasks/invoke.py)
@celery_app.task(bind=True, ...)
def start_inline_agents(self, message: Dict, preview: bool = False, ...):
    message_obj = message_factory.from_dict(message)
    
    # Check if project uses new workflow architecture
    if message_obj.project_uuid in settings.WORKFLOW_ARCHITECTURE_PROJECTS:
        from router.tasks.workflow_orchestrator import inline_agent_workflow
        return inline_agent_workflow.run(
            message=message,
            preview=preview,
            language=language,
            user_email=user_email,
        )
    
    # Legacy implementation continues below...
```

### Gradual Rollout Plan
1. **Staging** - ✅ Testing specific projects
2. **Production pilot** - Add 1-2 low-traffic projects
3. **Gradual expansion** - Add more projects based on monitoring
4. **Full migration** - Move all projects to new architecture
5. **Cleanup** - Remove legacy code and feature flag

---

## Known Limitations

### Lambda Tool Retry (Not Implemented)

When a Lambda function (tool) fails with transient errors (e.g., `ConnectionResetError`), there is **no automatic retry**. The agent receives the error and informs the user. This is pre-existing behavior from `start_inline_agents`, not introduced by the new workflow.

**Impact:** Users may need to retry their request if a tool fails due to network issues.

**Future Improvement:** Add tenacity retry decorator to Lambda invocation in `inline_agents/backends/openai/adapter.py`.

### Data Lake Serialization Error

When processing data lake events, `LitellmModel` objects are not JSON serializable:
```
Error processing data lake event async: Object of type LitellmModel is not JSON serializable
```

**Impact:** Data lake events may fail to send for some agent interactions.

**Future Fix:** Add custom JSON encoder or exclude non-serializable objects from data lake payloads.

---

## Risk Mitigation

### Risks

1. **Task Orchestration Complexity**
   - **Mitigation:** Use Celery Canvas (proven pattern)
   - **Fallback:** Keep orchestrator simple, add complexity gradually

2. **Data Serialization Issues**
   - **Mitigation:** Use JSON-serializable data structures
   - **Fallback:** Store intermediate results in Redis

3. **Performance Regression**
   - **Mitigation:** Benchmark before/after
   - **Fallback:** Optimize hot paths, add caching

4. **Observer Overhead**
   - **Mitigation:** Use `isolate_errors=True` for non-critical observers, use `async_event_manager` for async operations
   - **Fallback:** Disable non-critical observers via feature flags

5. **Error Handling Complexity**
   - **Mitigation:** Centralized error handling in orchestrator
   - **Fallback:** Comprehensive error logging and monitoring

---

## Success Metrics

### Performance
- **P50 latency**: < current baseline
- **P95 latency**: < current baseline
- **P99 latency**: < current baseline
- **Task success rate**: > 99%

### Maintainability
- **Code complexity**: Reduced by 30%
- **Test coverage**: > 80%
- **Cyclomatic complexity**: < 10 per function

### Observability
- **Trace coverage**: 100% of tasks
- **Error visibility**: All errors logged with context
- **Metrics**: All key operations instrumented

---

## References

### External Documentation
- [Celery Canvas Documentation](https://docs.celeryproject.org/en/stable/userguide/canvas.html)
- [Observer Pattern](https://refactoring.guru/design-patterns/observer)
- [Event-Driven Architecture](https://martinfowler.com/articles/201701-event-driven.html)

### Internal Documentation
- **Observer Infrastructure:** `nexus/event_domain/OBSERVER_GUIDE.md`
- **Observer Examples:** 
  - `router/traces_observers/rationale/observer.py` (RationaleObserver)
  - `router/traces_observers/save_traces.py` (SaveTracesObserver)

### Key Implementation Files (January 2025)

**Cache Infrastructure:**
- `router/services/cache_service.py` - Cache service with Redis backend
- `router/services/pre_generation_service.py` - Pre-generation with caching
- `router/services/cache_invalidation_observers.py` - Async invalidation observers
- `router/tasks/invocation_context.py` - `CachedProjectData` dataclass

**Workflow Infrastructure:**
- `router/tasks/workflow_orchestrator.py` - **Main workflow orchestrator task**
- `router/tasks/pre_generation.py` - **Pre-generation Celery task**
- `router/tasks/redis_task_manager.py` - **Workflow state management**
- `router/tasks/workflow_observers.py` - **Typing indicator observer**
- `router/tasks/invoke.py` - Entry point (`start_inline_agents`)

**Observer Infrastructure:**
- `nexus/observers/apps.py` - **Centralized observer registration**
- `nexus/events.py` - Event managers and `notify_async()` helper

### Utility Scripts
- **Clear Cache:** `nexus/staticfiles/cache/clear_pregeneration_cache.py` (for Django shell)
- **Test Invalidation:** `nexus/staticfiles/inline_agents_refactor/test_invalidate.py` (for Django shell)

### Testing Documentation
- **Test Suite Plan:** `nexus/staticfiles/inline_agents_refactor/test_suite_plan.md`

### Admin Integration
- `nexus/projects/admin.py` - Project admin with cache invalidation
- `nexus/inline_agents/admin.py` - InlineAgents admin with cache invalidation
