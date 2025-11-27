from typing import Dict

from nexus.inline_agents.models import Guardrail


class GuardrailsUsecase:
    @staticmethod
    def get_guardrail_as_dict(project_uuid: str) -> Dict[str, str]:
        try:
            guardrails = Guardrail.objects.get(project__uuid=project_uuid)
        except Guardrail.DoesNotExist:
            guardrails = Guardrail.objects.filter(current_version=True).order_by("created_on").last()

        return {"guardrailIdentifier": guardrails.identifier, "guardrailVersion": str(guardrails.version)}
