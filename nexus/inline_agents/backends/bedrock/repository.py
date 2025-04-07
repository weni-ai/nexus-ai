from nexus.inline_agents.backends import Supervisor


class BedrockSupervisorRepository():

    @classmethod
    def get_supervisor(
        cls,
    ) -> dict:

        supervisor = Supervisor.objects.order_by('id').last()

        supervisor_dict = {
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "instruction": supervisor.instruction,
            "action_groups": supervisor.action_groups,
            "foundation_model": supervisor.foundation_model,
            "knowledge_bases": supervisor.knowledge_bases,
            "agent_collaboration": cls._get_agent_collaboration(),
        }

        return supervisor_dict

    @classmethod
    def _get_agent_collaboration(cls) -> str:
        # if there is agents in the team return "SUPERVISOR"
        return "DISABLED"
