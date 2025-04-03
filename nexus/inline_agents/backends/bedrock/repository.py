from nexus.inline_agents.backends import Supervisor


class BedrockSupervisorRepository():
    @classmethod
    def get_supervisor(
        self,
    ) -> dict:

        supervisor = Supervisor.objects.order_by('id').last()

        supervisor_dict = {
            "promptOverrideConfiguration": supervisor.promptOverrideConfiguration,
            "instruction": supervisor.instruction,
            "actionGroups": supervisor.actionGroups,
            "foundationModel": supervisor.foundationModel,
            "agentCollaboration": supervisor.agentCollaboration,
            "knowledgeBases": supervisor.knowledgeBases,
        }

        return supervisor_dict

    def _get_action_groups(self, supervisor: Supervisor) -> list:
        return supervisor.actionGroups

    def _get_instruction(self, supervisor: Supervisor) -> str:
        return supervisor.instruction

    def _get_foundation_model(self, supervisor: Supervisor) -> str:
        return supervisor.foundationModel

    def _get_agent_collaboration(self, supervisor: Supervisor) -> str:
        return supervisor.agentCollaboration

    def _get_knowledge_bases(self, supervisor: Supervisor) -> list:
        return supervisor.knowledgeBases

    def _get_prompt_override_configuration(self, supervisor: Supervisor) -> str:
        return supervisor.promptOverrideConfiguration
