from nexus.actions.models import Flow


class FlowDoesNotExist(Exception):
    pass


class RetrieveFlowsUseCase():
    def retrieve_flow_by_uuid(self, flow_uuid: str) -> Flow:
        try:
            return Flow.objects.get(uuid=flow_uuid)
        except Flow.DoesNotExist:
            raise FlowDoesNotExist


def get_flow_by_action_type(
    content_base,
    action_type: str,
) -> Flow:
    try:
        return Flow.objects.get(
            action_type=action_type,
            content_base=content_base
        )
    except Flow.DoesNotExist:
        raise FlowDoesNotExist
