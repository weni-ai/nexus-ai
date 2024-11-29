from nexus.projects.models import IntegratedFeature
from nexus.usecases.actions.delete import DeleteFlowDTO, DeleteFlowsUseCase
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from nexus.usecases.projects.retrieve import get_integrated_feature


def delete_integrated_feature(
        project_uuid: str,
        feature_uuid: str,
        delete_actions: bool = True
) -> bool:
    try:
        integrated_feature = get_integrated_feature(project_uuid, feature_uuid)
        if delete_actions:
            for action in integrated_feature.current_version_setup:
                delete_integrated_action(
                    project_uuid=project_uuid,
                    action_uuid=action.get("root_flow_uuid")
                )
        integrated_feature.delete()
        return True
    except IntegratedFeature.DoesNotExist:
        raise ValueError("IntegratedFeature does not exists")


def delete_integrated_action(project_uuid: str, action_uuid: str):
    dto = DeleteFlowDTO(flow_uuid=action_uuid)

    project = get_project_by_uuid(project_uuid)
    usecase = DeleteFlowsUseCase()
    usecase.hard_delete_flow(
        flow_dto=dto,
        project=project,
    )
