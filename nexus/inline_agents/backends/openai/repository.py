import logging
from typing import Any, Dict, List, Optional

from inline_agents.repository import SupervisorRepository
from nexus.inline_agents.backends.openai.models import ManagerAgent, ProjectModelProvider
from nexus.inline_agents.backends.openai.models import OpenAISupervisor as Supervisor
from nexus.inline_agents.models import Agent

logger = logging.getLogger(__name__)


class OpenAISupervisorRepository(SupervisorRepository):
    @classmethod
    def get_supervisor(
        cls,
        foundation_model: str = None,
        # Cached data parameters (always provided from start_inline_agents)
        use_components: bool = None,
        human_support: bool = None,
        default_supervisor_foundation_model: str = None,
    ) -> Agent:
        supervisor = Supervisor.objects.order_by("id").last()

        if not supervisor:
            raise Supervisor.DoesNotExist()

        use_components_value = use_components if use_components is not None else False
        human_support_value = human_support if human_support is not None else False
        default_supervisor_foundation_model_value = default_supervisor_foundation_model

        supervisor_dict = {
            "instruction": cls._get_supervisor_instructions(supervisor=supervisor),
            "use_components": use_components_value,
            "use_human_support": human_support_value,
            "components_instructions": supervisor.components_prompt,
            "formatter_agent_components_instructions": supervisor.components_human_support_prompt,
            "components_instructions_up": supervisor.components_instructions_up_prompt,
            "human_support_instructions": supervisor.human_support_prompt,
            "tools": cls._get_supervisor_tools(supervisor=supervisor, human_support=human_support_value),
            "foundation_model": cls.get_foundation_model(
                supervisor=supervisor,
                foundation_model=foundation_model,
                default_supervisor_foundation_model=default_supervisor_foundation_model_value,
            ),
            "knowledge_bases": supervisor.knowledge_bases,
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "default_instructions_for_collaborators": supervisor.default_instructions_for_collaborators,
            "max_tokens": supervisor.max_tokens,
        }

        return supervisor_dict

    @classmethod
    def _get_supervisor_instructions(cls, supervisor) -> str:
        return supervisor.instruction

    @classmethod
    def _get_supervisor_tools(cls, supervisor=None, human_support: bool = None) -> list[dict]:
        human_support_value = human_support if human_support is not None else False
        if human_support_value:
            return supervisor.human_support_action_groups
        return supervisor.action_groups


class ManagerAgentRepository(SupervisorRepository):
    def _supervisor_to_dict(self, supervisor: ManagerAgent) -> Dict[str, Any]:
        supervisor_dict = supervisor.__dict__
        supervisor_dict.pop("_state")
        return supervisor_dict

    def _get_project_credentials(self, project_uuid: Optional[str], model_vendor: str) -> Dict[str, Any]:
        """Check for active project-level provider credentials."""
        if not project_uuid:
            return {}
        try:
            project_provider = ProjectModelProvider.objects.select_related("provider").get(
                project__uuid=project_uuid,
                provider__model_vendor__iexact=model_vendor,
                is_active=True,
            )
        except ProjectModelProvider.DoesNotExist:
            return {}

        decrypted = project_provider.decrypted_credentials
        cred_map = {}
        for field in decrypted:
            if isinstance(field, dict) and field.get("id") and field.get("value"):
                cred_map[field["id"]] = field["value"]

        if not cred_map:
            return {}

        logger.info("Using project-level credentials for project %s, vendor %s", project_uuid, model_vendor)
        return cred_map

    def get_supervisor(
        self,
        human_support: Optional[bool] = None,
        use_components: Optional[bool] = None,
        supervisor_agent_uuid: Optional[str] = None,
        project_uuid: Optional[str] = None,
    ) -> dict:
        def get_supervisor_object(supervisor_uuid: str) -> ManagerAgent:
            try:
                return ManagerAgent.objects.get(uuid=supervisor_uuid)
            except ManagerAgent.DoesNotExist:
                manager = ManagerAgent.objects.filter(default=True, public=True).order_by("created_on").last()
                if manager is None:
                    raise
                return manager

        supervisor_data = self._supervisor_to_dict(get_supervisor_object(supervisor_agent_uuid))

        use_human_support: bool = human_support
        use_components: bool = use_components

        project_creds = self._get_project_credentials(project_uuid, supervisor_data["model_vendor"])

        if project_creds:
            user_model_credentials = {
                "api_key": project_creds.get("api_key", ""),
                "api_base": project_creds.get("api_base", ""),
                "api_version": project_creds.get("api_version", ""),
            }
        elif supervisor_data["api_key"]:
            user_model_credentials = {
                "api_key": supervisor_data["api_key"],
                "api_base": supervisor_data["api_base"],
                "api_version": supervisor_data["api_version"],
            }
        else:
            user_model_credentials = {}

        manager_extra_args = supervisor_data["manager_extra_args"] or {}

        if project_creds and supervisor_data["model_vendor"].lower() == "vertex_ai":
            sa_json = project_creds.get("service_account_json", "")
            if sa_json:
                manager_extra_args = {**manager_extra_args, "vertex_credentials": sa_json}
                vertex_project = project_creds.get("vertex_project", "")
                if vertex_project:
                    manager_extra_args["vertex_project"] = vertex_project
                vertex_location = project_creds.get("vertex_location", "")
                if vertex_location:
                    manager_extra_args["vertex_location"] = vertex_location

        model_settings: Dict[str, Any] = {
            "model_has_reasoning": supervisor_data["model_has_reasoning"],
            "reasoning_effort": supervisor_data["reasoning_effort"],
            "reasoning_summary": supervisor_data["reasoning_summary"],
            "parallel_tool_calls": supervisor_data["parallel_tool_calls"],
            "manager_extra_args": manager_extra_args,
        }

        supervisor_dict = {
            "instruction": supervisor_data["base_prompt"],
            "use_components": use_components,
            "use_human_support": use_human_support,
            "components_instructions_up": supervisor_data["header_components_prompt"],
            "components_instructions": supervisor_data["footer_components_prompt"],
            "formatter_agent_components_instructions": supervisor_data["formatter_agent_prompt"],
            "human_support_instructions": supervisor_data["human_support_prompt"],
            "tools": self._get_supervisor_agent_tools(supervisor=supervisor_data, use_human_support=use_human_support),
            "foundation_model": supervisor_data["foundation_model"],
            "model_vendor": supervisor_data["model_vendor"],
            "model_settings": model_settings,
            "knowledge_bases": supervisor_data["knowledge_bases"],
            "max_tokens": {
                "supervisor": supervisor_data["max_tokens"],
                "collaborator": supervisor_data["collaborator_max_tokens"],
                "audio_orchestration": supervisor_data["audio_orchestration_max_tokens"],
                "audio_orchestration_collaborator": supervisor_data["audio_orchestration_collaborator_max_tokens"],
            },
            "formatter_agent_configurations": {
                "formatter_instructions": supervisor_data["formatter_agent_prompt"],
                "formatter_reasoning_effort": supervisor_data["formatter_agent_reasoning_effort"],
                "formatter_reasoning_summary": supervisor_data["formatter_agent_reasoning_summary"],
                "formatter_send_only_assistant_message": supervisor_data["formatter_agent_send_only_assistant_message"],
                "formatter_foundation_model": supervisor_data["formatter_agent_foundation_model"],
                "formatter_agent_model_has_reasoning": supervisor_data["formatter_agent_model_has_reasoning"],
                "formatter_tools_descriptions": supervisor_data["formatter_tools_descriptions"],
            },
            "user_model_credentials": user_model_credentials,
            "collaborator_configurations": {
                "override_collaborators_foundation_model": supervisor_data["override_collaborators_foundation_model"],
                "collaborators_foundation_model": supervisor_data["collaborators_foundation_model"],
                "default_instructions_for_collaborators": supervisor_data["default_instructions_for_collaborators"],
                "collaborator_extra_args": supervisor_data["collaborator_extra_args"],
                "append_manager_extra_args": supervisor_data["append_manager_extra_args"],
            },
        }

        return supervisor_dict

    def _get_supervisor_instructions(cls, supervisor) -> str:
        return supervisor.instruction

    def _get_supervisor_agent_tools(
        cls, supervisor: Dict[str, Any], use_human_support: bool = None
    ) -> List[Dict[str, Any]]:
        if use_human_support:
            return supervisor["human_support_tools"]
        return supervisor["tools"]

    def _get_supervisor_tools(cls, supervisor=None, human_support: bool = None) -> list[dict]:
        human_support_value = human_support if human_support is not None else False
        if human_support_value:
            return supervisor.human_support_action_groups
        return supervisor.action_groups
