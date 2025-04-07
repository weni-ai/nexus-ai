from nexus.inline_agents.backends import Supervisor


class BedrockSupervisorRepository():
    @classmethod
    def get_supervisor(
        self,
    ) -> dict:

        supervisor = Supervisor.objects.order_by('id').last()

        supervisor_dict = {
            "prompt_override_configuration": supervisor.prompt_override_configuration,
            "instruction": supervisor.instruction,
            "action_groups": supervisor.action_groups,
            "foundation_model": supervisor.foundation_model,
            "knowledge_bases": supervisor.knowledge_bases,
            "agent_collaboration": self._get_agent_collaboration(),
        }

        return supervisor_dict

    def _get_agent_collaboration(self) -> str:
        # if there is agents in the team return "SUPERVISOR"
        return "DISABLED"
