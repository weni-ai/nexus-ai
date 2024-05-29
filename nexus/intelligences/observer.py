from nexus.usecases.logs.create import create_recent_activity
from nexus.usecases.logs.logs_dto import CreateRecentActivityDTO
from nexus.event_domain.event_observer import EventObserver
from nexus.usecases.event_driven.recent_activities import intelligence_activity_message
from nexus.usecases.intelligences.publishers_msg import recent_activity_message


class IntelligenceCreateObserver(EventObserver):

    def __init__(
        self,
        intelligence_activity_message=intelligence_activity_message,
    ) -> None:
        self.intelligence_activity_message = intelligence_activity_message

    def perform(self, intelligence):
        org = intelligence.org
        project_list = org.projects.all()
        user = intelligence.created_by

        for project in project_list:
            dto = CreateRecentActivityDTO(
                action_type="C",
                project=project,
                created_by=intelligence.created_by,
                intelligence=intelligence,
                action_details={}
            )
            create_recent_activity(intelligence, dto=dto)

        recent_activity_message(
            org=org,
            user=user,
            entity_name=intelligence.name,
            action="CREATE",
            intelligence_activity_message=self.intelligence_activity_message
        )


class LLMUpdateObserver(EventObserver):

    def perform(
        self,
        llm,
        user,
        action_details: dict,
    ):
        project = llm.integrated_intelligence.project
        intelligence = llm.integrated_intelligence.intelligence
        dto = CreateRecentActivityDTO(
            action_type="U",
            project=project,
            created_by=user,
            intelligence=intelligence,
            action_details=action_details
        )
        create_recent_activity(llm, dto=dto)


class ContentBaseFileObserver(EventObserver):

    def perform(
        self,
        content_base_file,
        user,
        action: str,
        action_details: dict = {},
    ):
        user = user
        content_base = content_base_file.content_base
        intelligence = content_base.intelligence

        if content_base.is_router:
            project = intelligence.integrated_intelligence.project
            dto = CreateRecentActivityDTO(
                action_type=action,
                project=project,
                created_by=user,
                intelligence=intelligence,
                action_details=action_details
            )
            create_recent_activity(content_base_file, dto=dto)
        else:
            org = intelligence.org
            project_list = org.projects.all()
            for project in project_list:
                dto = CreateRecentActivityDTO(
                    action_type=action,
                    project=project,
                    created_by=user,
                    intelligence=intelligence,
                    action_details=action_details
                )
                create_recent_activity(content_base_file, dto=dto)
