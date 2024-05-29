from nexus.usecases.logs.create import create_recent_activity
from nexus.usecases.logs.logs_dto import CreateRecentActivityDTO
from nexus.event_domain.event_observer import EventObserver
from nexus.usecases.event_driven.recent_activities import intelligence_activity_message
from nexus.usecases.intelligences.publishers_msg import recent_activity_message
from nexus.intelligences.models import IntegratedIntelligence

from django.forms.models import model_to_dict


def _update_comparison_fields(
    old_model_data,
    new_model_data,
):
    old_model_dict = model_to_dict(old_model_data)
    new_model_dict = model_to_dict(new_model_data)

    action_details = {}
    for key, old_value in old_model_dict.items():
        new_value = new_model_dict.get(key)
        if old_value != new_value:
            action_details[key] = {'old': old_value, 'new': new_value}
    return action_details


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
        action_type: str,
        action_details: dict = {},
    ):
        user = user
        content_base = content_base_file.content_base
        intelligence = content_base.intelligence

        if content_base.is_router:
            project = intelligence.integrated_intelligence.project
            dto = CreateRecentActivityDTO(
                action_type=action_type,
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
                    action_type=action_type,
                    project=project,
                    created_by=user,
                    intelligence=intelligence,
                    action_details=action_details
                )
                create_recent_activity(content_base_file, dto=dto)


class ContentBaseAgentObserver(EventObserver):

    def perform(
        self,
        user,
        content_base_agent,
        action_type: str,
        **kwargs
    ):
        intelligence = content_base_agent.content_base.intelligence
        integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
        project = integrated_intelligence.project

        if action_type == "U":
            old_model_data = kwargs.get('old_agent_data')
            new_model_data = kwargs.get('new_agent_data')
            action_details = _update_comparison_fields(old_model_data, new_model_data)
        else:
            action_details = kwargs.get('action_details', {})

        dto = CreateRecentActivityDTO(
            action_type="U",
            project=project,
            created_by=user,
            intelligence=intelligence,
            action_details=action_details
        )
        create_recent_activity(content_base_agent, dto=dto)


class ContentBaseInstructionObserver(EventObserver):

    def perform(
        self,
        user,
        content_base_instruction,
        action_type: str,
        **kwargs
    ):
        intelligence = content_base_instruction.content_base.intelligence
        integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
        project = integrated_intelligence.project

        if action_type == "U":
            old_model_data = kwargs.get('old_instruction_data')
            new_model_data = kwargs.get('new_instruction_data')
            action_details = _update_comparison_fields(old_model_data, new_model_data)
        else:
            action_details = kwargs.get('action_details', {})

        dto = CreateRecentActivityDTO(
            action_type="U",
            project=project,
            created_by=user,
            intelligence=intelligence,
            action_details=action_details
        )
        create_recent_activity(content_base_instruction, dto=dto)


class ContentBaseLinkObserver(EventObserver):
    # TODO: Implement this observer to handle the methods: Create and delete
    def perform(self):
        pass


class ContentBaseTextObserver(EventObserver):

    def perform(
        self,
        user,
        content_base_text,
        action_type: str,
        **kwargs
    ):
        content_base = content_base_text.content_base

        intelligence = content_base.intelligence

        if action_type == "U":
            old_model_data = kwargs.get('old_contentbasetext_data')
            new_model_data = kwargs.get('new_contentbase_data')
            action_details = _update_comparison_fields(old_model_data, new_model_data)
        else:
            action_details = kwargs.get('action_details', {})

        if content_base.is_router:
            integrated_intelligence = IntegratedIntelligence.objects.get(intelligence=intelligence)
            project = integrated_intelligence.project
            dto = CreateRecentActivityDTO(
                action_type="U",
                project=project,
                created_by=user,
                intelligence=intelligence,
                action_details=action_details
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
                    action_details=action_details
                )
                create_recent_activity(content_base_text, dto=dto)


class ContentBaseObserver(EventObserver):
    # TODO: Implement this observer to handle the methods: Create, Update and delete
    def perform(self):
        pass
