from nexus.projects.models import IntegratedFeature
from nexus.usecases.projects.retrieve import get_integrated_feature


def delete_integrated_feature(project_uuid: str, feature_uuid: str) -> bool:
    try:
        integrated_feature = get_integrated_feature(project_uuid, feature_uuid)
        integrated_feature.delete()
        return True
    except IntegratedFeature.DoesNotExist as e:
        raise ValueError("IntegratedFeature does not exists") from e
