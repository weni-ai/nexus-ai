from dataclasses import dataclass, field
from typing import List, Dict

from nexus.projects.models import IntegratedFeature
from nexus.actions.models import TemplateAction
from nexus.usecases.actions.create import CreateFlowDTO
from nexus.usecases.actions.update import UpdateIntegratedFlowDTO


from nexus.usecases.projects.retrieve import get_integrated_feature


@dataclass
class UpdateProjectDTO:
    user_email: str
    uuid: str
    brain_on: str = False

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class IntegratedFeatureFlowDTO:
    project_uuid: str
    feature_uuid: str
    flows: List[Dict[str, str]]
    integrated_feature: IntegratedFeature = field(init=False)

    def __post_init__(self):
        self.integrated_feature = get_integrated_feature(self.project_uuid, self.feature_uuid)

    @property
    def action_dto(self) -> List[CreateFlowDTO]:
        if not self.integrated_feature or not self.integrated_feature.current_version_setup:
            return []

        create_flow_dtos = []
        for current_setup_action in self.integrated_feature.current_version_setup:
            matching_flow = next(
                (flow for flow in self.flows if flow.get('base_uuid') == current_setup_action.get('root_flow_uuid')),
                None
            )

            if matching_flow:
                template_uuid = current_setup_action.get('type', None)
                template_action = None
                if template_uuid is not None:
                    template_action = TemplateAction.objects.get(uuid=current_setup_action.get('type'))

                create_flow_dtos.append(
                    CreateFlowDTO(
                        flow_uuid=matching_flow.get("uuid"),
                        name=current_setup_action.get("name"),
                        prompt=current_setup_action.get('prompt'),
                        project_uuid=self.project_uuid,
                        template=template_action if template_uuid else None,
                        editable=False
                    )
                )

        return create_flow_dtos

    @property
    def update_dto(self) -> List[UpdateIntegratedFlowDTO]:
        if not self.integrated_feature or not self.integrated_feature.current_version_setup:
            return []

        update_flow_dtos = []
        for current_setup_action in self.integrated_feature.current_version_setup:
            matching_flow = next(
                (flow for flow in self.flows if flow.get('base_uuid') == current_setup_action.get('root_flow_uuid')),
                None
            )

            if matching_flow:
                update_flow_dtos.append(UpdateIntegratedFlowDTO(
                    flow_uuid=matching_flow.get("uuid"),
                    name=current_setup_action.get("name"),
                    prompt=current_setup_action.get('prompt'),
                ))

        return update_flow_dtos


@dataclass
class UpdateIntegratedFeatureFlowDTO:
    current_version_setup: Dict[str, str]

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class IntegratedFeatureDTO:
    feature_uuid: str
    project_uuid: str
    current_version_setup: List[Dict[str, str]]
