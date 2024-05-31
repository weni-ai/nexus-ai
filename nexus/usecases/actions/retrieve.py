from nexus.actions.models import Flow


class FlowDoesNotExist(Exception):
    pass


class RetrieveFlowsUseCase():
    def retrieve_flow_by_uuid(self, flow_uuid: str) -> Flow:
        try:
            return Flow.objects.get(uuid=flow_uuid)
        except Flow.DoesNotExist:
            raise FlowDoesNotExist
