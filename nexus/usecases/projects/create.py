from django.db import IntegrityError

from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.projects.models import IntegratedFeature, ProjectAuth
from nexus.projects.project_dto import (
    ProjectAuthCreationDTO,
)
from nexus.usecases.actions.create import CreateFlowsUseCase
from nexus.usecases.actions.update import UpdateFlowsUseCase
from nexus.usecases.projects.dto import IntegratedFeatureDTO, IntegratedFeatureFlowDTO
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid
from nexus.users.models import User


class ProjectAuthUseCase:
    def auth_dto_from_dict(self, consumer_msg: dict) -> ProjectAuthCreationDTO:
        role = consumer_msg.get("role")
        user_email = consumer_msg.get("user")
        project_uuid = consumer_msg.get("project")

        if not role:
            raise ValueError("Role is required")

        user, created = User.objects.get_or_create(email=user_email)

        try:
            project = get_project_by_uuid(project_uuid=project_uuid)
        except ProjectDoesNotExist as e:
            raise e
        except Exception as e:
            raise e

        return ProjectAuthCreationDTO(user=user, project=project, role=role)

    def create_project_auth(self, consumer_msg: dict) -> ProjectAuth:
        try:
            auth_dto = self.auth_dto_from_dict(consumer_msg)
            action = consumer_msg.get("action")  # create, update, delete

            project_auth = ProjectAuth.objects.get(project=auth_dto.project, user=auth_dto.user)

            if action == "delete":
                project_auth.delete()
                return project_auth

            if project_auth.role != auth_dto.role:
                project_auth.role = auth_dto.role
                project_auth.save(update_fields=["role"])
                return project_auth

            return project_auth

        except ProjectDoesNotExist as e:
            raise e

        except ProjectAuth.DoesNotExist as e:
            if action != "delete":
                project_auth = ProjectAuth.objects.create(
                    project=auth_dto.project, user=auth_dto.user, role=auth_dto.role
                )
                return project_auth
            raise ValueError("Project auth does not exists") from e
        except Exception as exception:
            raise exception from None


class CreateIntegratedFeatureUseCase:
    def create_integrated_feature(self, integrated_feature_dto: IntegratedFeatureDTO) -> IntegratedFeature:
        project_uuid = integrated_feature_dto.project_uuid
        feature_uuid = integrated_feature_dto.feature_uuid
        action_list = integrated_feature_dto.current_version_setup

        if not action_list:
            raise ValueError("Action is required")

        try:
            project = get_project_by_uuid(project_uuid=project_uuid)

            integrated_feature = IntegratedFeature.objects.create(
                project=project, feature_uuid=feature_uuid, current_version_setup=action_list
            )
            return integrated_feature

        except ProjectDoesNotExist as e:
            raise e

        except IntegrityError as e:
            raise ValueError(
                f"Integrated feature for project `{project_uuid}` and feature `{feature_uuid}` already exists."
            ) from e

    def integrate_feature_flows(self, integrated_feature_flow_dto: IntegratedFeatureFlowDTO):
        flows = integrated_feature_flow_dto.flows
        existing_integration = integrated_feature_flow_dto.integrated_feature

        if existing_integration and not existing_integration.is_integrated:
            created_flows = self._create_flows(integrated_feature_flow_dto)
            return created_flows

        updated_flows = []
        for flow in flows:
            if existing_integration and existing_integration.is_integrated:
                updated_flow = self._update_flow(flow, integrated_feature_flow_dto)
                updated_flows.append(updated_flow)

        if not updated_flows:
            raise ValueError("No valid flows found")

        return updated_flows

    def _update_flow(self, flow, integrated_feature_flow_dto):
        update_flow_dtos = integrated_feature_flow_dto.update_dto

        if not update_flow_dtos:
            raise ValueError("No update DTOs found")

        for update_dto in update_flow_dtos:
            if update_dto.flow_uuid == flow.get("uuid"):
                usecase = UpdateFlowsUseCase()
                updated_flow = usecase.update_integrated_flow(flow_dto=update_dto)
                return updated_flow

        raise ValueError("No matching flow found for update")

    def _create_flows(self, integrated_feature_flow_dto):
        create_flow_dtos = integrated_feature_flow_dto.action_dto

        if not create_flow_dtos:
            raise ValueError("Flows not found")

        project = get_project_by_uuid(integrated_feature_flow_dto.project_uuid)
        usecase = CreateFlowsUseCase()

        created_flows = []
        for create_flow_dto in create_flow_dtos:
            created_flow = usecase.create_flow(create_dto=create_flow_dto, project=project)
            created_flows.append(created_flow)

        integrated_feature = integrated_feature_flow_dto.integrated_feature
        integrated_feature.is_integrated = True
        integrated_feature.save(update_fields=["is_integrated"])

        return created_flows
