from nexus.event_domain.event_manager import EventManager

from nexus.intelligences.observer import (
    IntelligenceCreateObserver,
    LLMUpdateObserver,
    ContentBaseFileObserver,
    ContentBaseAgentObserver,
    ContentBaseInstructionObserver,
    ContentBaseLinkObserver,
    ContentBaseTextObserver,
    ContentBaseObserver
)
from nexus.logs.observers import (
    ZeroShotHealthCheckObserver,
    ZeroShotClassificationHealthCheckObserver,
    GolfinhoHealthCheckObserver
)

from nexus.projects.observer import ProjectObserver

event_manager = EventManager()

event_manager.subscribe(
    event="intelligence_create_activity",
    observer=[IntelligenceCreateObserver()]
)

event_manager.subscribe(
    event="llm_update_activity",
    observer=[LLMUpdateObserver()]
)

event_manager.subscribe(
    event="contentbase_file_activity",
    observer=[ContentBaseFileObserver()]
)

event_manager.subscribe(
    event="contentbase_agent_activity",
    observer=[ContentBaseAgentObserver()]
)

event_manager.subscribe(
    event="contentbase_instruction_activity",
    observer=[ContentBaseInstructionObserver()]
)

event_manager.subscribe(
    event="contentbase_link_activity",
    observer=[ContentBaseLinkObserver()]
)

event_manager.subscribe(
    event="contentbase_text_activity",
    observer=[ContentBaseTextObserver()]
)

event_manager.subscribe(
    event="contentbase_activity",
    observer=[ContentBaseObserver()]
)

event_manager.subscribe(
    event="health_check",
    observer=[
        ZeroShotHealthCheckObserver(),
        GolfinhoHealthCheckObserver()
    ]
)

event_manager.subscribe(
    event="classification_health_check",
    observer=[
        ZeroShotClassificationHealthCheckObserver()
    ]
)

event_manager.subscribe(
    event="project_activity",
    observer=[ProjectObserver()]
)
