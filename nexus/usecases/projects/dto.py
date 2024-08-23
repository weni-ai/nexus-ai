from dataclasses import dataclass, field
from typing import List, Dict

from nexus.projects.models import IntegratedFeature
from nexus.usecases.actions.create import CreateFlowDTO
from nexus.usecases.actions.update import UpdateFlowDTO


from nexus.usecases.projects.retrieve import get_integrated_feature


@dataclass
class UpdateProjectDTO:
    user_email: str
    uuid: str
    brain_on: str = False

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


class IntegratedFeatureDTO:
    project_uuid: str
    feature_uuid: str
    imported_flows: List[Dict[str, str]]
    integrated_feature: IntegratedFeature = field(init=False)

    def __post_init__(self):
        self.integrated_feature = get_integrated_feature(self.project.uuid, self.feature_uuid)

    @property
    def action_dto(self) -> CreateFlowDTO:

        if not self.integrated_feature or not self.integrated_feature.current_version_setup:
            return None

        current_setup_action = self.integrated_feature.current_version_setup
        matching_flow = next(
            (flow for flow in self.imported_flows if flow.get('base_uuid') == current_setup_action.get('uuid')),
            None
        )

        if matching_flow:
            return CreateFlowDTO(
                flow_uuid=matching_flow.get("uuid"),
                name=matching_flow.get("name"),
                prompt=current_setup_action.get('description'),
                project_uuid=self.project.uuid
            )
        return None


@dataclass
class UpdateIntegratedFeatureDTO:
    current_version_setup: Dict[str, str]

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}
