# Validation: Data Lake Duplicate Events (Recent vs Long-Standing)

## Finding: Long-standing behavior (not a recent regression)

| Behavior | File | Commit | Author | Date |
|----------|------|--------|--------|------|
| `on_tool_end` calls `await self.tool_started(...)` (CollaboratorHooks) | hooks.py | eb43ff197 | Alisson | 2025-09-12 |
| `on_tool_end` calls `await self.tool_started(...)` (SupervisorHooks) | hooks.py | eb43ff197 | Alisson | 2025-09-12 |
| Tool result sent with `use_delay=False` (sync) | adapter.py | 6c31e5dff | RuanHeleno | 2025-12-19 |

**Conclusion**: The two-events-per-tool pattern (tool_call + tool_result) and the synchronous tool_result send have been in place for **months** (since Sept–Dec 2025). This is **not** a recent regression; treat as a product/design change when fixing.
