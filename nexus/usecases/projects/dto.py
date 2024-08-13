from dataclasses import dataclass
from typing import List, Dict
from nexus.usecases.actions.create import CreateFlowDTO


@dataclass
class UpdateProjectDTO:
    user_email: str
    uuid: str
    brain_on: str = False

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class FeatureVersionDTO:
    uuid: str
    setup: dict

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}


@dataclass
class IntegratedFeatureVersionDTO:
    project_uuid: str
    feature_version_uuid: str
    actions: List[Dict[str, str]]

    @property
    def actions_dto(self) -> List[CreateFlowDTO]:
        list_actions_dto = []
        action: Dict[str, str]

        for action in self.actions:
            list_actions_dto.append(
                CreateFlowDTO(
                    name=action.get("name"),
                    prompt=action.get("description"),
                    flow_uuid=action.get("flow_uuid"),
                    project_uuid=self.project_uuid
                )
            )
        return list_actions_dto
