from typing import Optional

from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver
from nexus.event_domain.recent_activity.create import create_recent_activity
from nexus.event_domain.recent_activity.external_activities import intelligence_activity_message
from nexus.event_domain.recent_activity.msg_handler import recent_activity_message
from nexus.event_domain.recent_activity.recent_activities_dto import CreateRecentActivityDTO
from nexus.intelligences.models import IntegratedIntelligence


def _update_comparison_fields(
    old_model_data: dict,
    new_model_data: dict,
):
    action_details = {}
    for key, old_value in old_model_data.items():
        new_value = new_model_data.get(key)
        if old_value != new_value:
            action_details[key] = {"old": old_value, "new": new_value}
    return action_details


@observer("intelligence_create_activity")
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
                action_details={},
            )
            create_recent_activity(intelligence, dto=dto)

        recent_activity_message(
            org=org,
            user=user,
            entity_name=intelligence.name,
            action="CREATE",
            intelligence_activity_message=self.intelligence_activity_message,
        )


@observer("llm_update_activity")
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
            action_type="U", project=project, created_by=user, intelligence=intelligence, action_details=action_details
        )
        create_recent_activity(llm, dto=dto)


@observer("contentbase_file_activity")
class ContentBaseFileObserver(EventObserver):
    def perform(
        self,
        content_base_file,
        user,
        action_type: str,
        action_details: Optional[dict] = None,
    ):
        if action_details is None:
            action_details = {}
        content_base = content_base_file.content_base
        intelligence = content_base.intelligence

        if content_base.is_router:
            integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
            project = integrated_intelligence.project
            if not action_details:
                action_details = {"old": "", "new": content_base_file.created_file_name}
            dto = CreateRecentActivityDTO(
                action_type=action_type,
                project=project,
                created_by=user,
                intelligence=intelligence,
                action_details=action_details,
            )
            create_recent_activity(content_base_file, dto=dto)
        else:
            org = intelligence.org
            project_list = org.projects.all()
            for project in project_list:
                dto = CreateRecentActivityDTO(
                    action_type=action_type,
                    project=project,
                    created_by=user,
                    intelligence=intelligence,
                    action_details=action_details,
                )
                create_recent_activity(content_base_file, dto=dto)


@observer("contentbase_agent_activity")
class ContentBaseAgentObserver(EventObserver):
    def perform(self, user, content_base_agent, action_type: str, **kwargs):
        intelligence = content_base_agent.content_base.intelligence
        integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
        project = integrated_intelligence.project

        if action_type == "U":
            old_model_data = kwargs.get("old_agent_data")
            new_model_data = kwargs.get("new_agent_data")
            action_details = _update_comparison_fields(old_model_data, new_model_data)
        else:
            action_details = kwargs.get("action_details", {"old": "", "new": content_base_agent.agent})

        if action_details != {}:
            dto = CreateRecentActivityDTO(
                action_type="U",
                project=project,
                created_by=user,
                intelligence=intelligence,
                action_details=action_details,
            )
            create_recent_activity(content_base_agent, dto=dto)


@observer("contentbase_instruction_activity")
class ContentBaseInstructionObserver(EventObserver):
    def perform(self, user, content_base_instruction, action_type: str = "U", **kwargs):
        intelligence = content_base_instruction.content_base.intelligence
        integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
        project = integrated_intelligence.project

        if action_type == "U":
            old_model_data = kwargs.get("old_instruction_data")
            new_model_data = kwargs.get("new_instruction_data")
            action_details = _update_comparison_fields(old_model_data, new_model_data)
        else:
            action_details = kwargs.get("action_details", {"old": "", "new": content_base_instruction.instruction})

        if not (action_details == {} and action_type == "U"):
            dto = CreateRecentActivityDTO(
                action_type=action_type,
                project=project,
                created_by=user,
                intelligence=intelligence,
                action_details=action_details,
            )
            create_recent_activity(content_base_instruction, dto=dto)


@observer("contentbase_link_activity")
class ContentBaseLinkObserver(EventObserver):
    def perform(self, user, content_base_link, action_type: str, **kwargs):
        content_base = content_base_link.content_base
        intelligence = content_base.intelligence
        action_details = kwargs.get("action_details", {"old": "", "new": content_base_link.link})

        if content_base.is_router:
            integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
            project = integrated_intelligence.project
            dto = CreateRecentActivityDTO(
                action_type=action_type,
                project=project,
                created_by=user,
                intelligence=intelligence,
                action_details=action_details,
            )
            create_recent_activity(content_base_link, dto=dto)
        else:
            org = intelligence.org
            project_list = org.projects.all()
            for project in project_list:
                dto = CreateRecentActivityDTO(
                    action_type=action_type,
                    project=project,
                    created_by=user,
                    intelligence=intelligence,
                    action_details=action_details,
                )
                create_recent_activity(content_base_link, dto=dto)


@observer("contentbase_text_activity")
class ContentBaseTextObserver(EventObserver):
    def perform(self, user, content_base_text, action_type: str, **kwargs):
        content_base = content_base_text.content_base

        intelligence = content_base.intelligence

        if action_type == "U":
            old_model_data = kwargs.get("old_contentbasetext_data")
            new_model_data = kwargs.get("new_contentbase_data")
            action_details = _update_comparison_fields(old_model_data, new_model_data)
        else:
            action_details = kwargs.get("action_details", {})

        if content_base.is_router:
            integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
            project = integrated_intelligence.project
            dto = CreateRecentActivityDTO(
                action_type="U",
                project=project,
                created_by=user,
                intelligence=intelligence,
                action_details=action_details,
            )
            create_recent_activity(content_base_text, dto=dto)
        else:
            org = intelligence.org
            project_list = org.projects.all()
            for project in project_list:
                dto = CreateRecentActivityDTO(
                    action_type="U",
                    project=project,
                    created_by=user,
                    intelligence=intelligence,
                    action_details=action_details,
                )
                create_recent_activity(content_base_text, dto=dto)


@observer("contentbase_activity")
class ContentBaseObserver(EventObserver):
    def __init__(
        self,
        intelligence_activity_message=intelligence_activity_message,
    ) -> None:
        self.intelligence_activity_message = intelligence_activity_message

    def perform(self, contentbase, user, action_type: str, **kwargs):
        action_details = kwargs.get("action_details", {})

        if action_type == "U":
            old_model_data = kwargs.get("old_contentbase_data")
            new_model_data = kwargs.get("new_contentbase_data")
            action_details = _update_comparison_fields(old_model_data, new_model_data)

        if not contentbase.is_router:
            org = contentbase.intelligence.org
            project_list = org.projects.all()
            for project in project_list:
                dto = CreateRecentActivityDTO(
                    action_type=action_type,
                    project=project,
                    created_by=user,
                    intelligence=contentbase.intelligence,
                    action_details=action_details,
                )
                create_recent_activity(contentbase, dto=dto)

            recent_activity_message(
                org=org,
                user=user,
                entity_name=contentbase.title,
                action=action_type,
                intelligence_activity_message=self.intelligence_activity_message,
            )
