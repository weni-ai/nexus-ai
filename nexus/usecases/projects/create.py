from nexus.usecases.projects.get_by_uuid import get_project_by_uuid

from nexus.projects.models import ProjectAuth, IntegratedFeature
from nexus.projects.project_dto import ProjectAuthCreationDTO
from nexus.usecases.projects.dto import IntegratedFeatureDTO
from nexus.usecases.actions.create import CreateFlowsUseCase
from nexus.usecases.actions.update import UpdateFlowDTO, UpdateFlowsUseCase

from nexus.users.models import User

from nexus.projects.exceptions import ProjectDoesNotExist


class ProjectAuthUseCase:

    def auth_dto_from_dict(
        self,
        consumer_msg: dict
    ) -> ProjectAuthCreationDTO:
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

        return ProjectAuthCreationDTO(
            user=user,
            project=project,
            role=role
        )

    def create_project_auth(
        self,
        consumer_msg: dict
    ) -> ProjectAuth:

        try:
            auth_dto = self.auth_dto_from_dict(consumer_msg)
            action = consumer_msg.get("action")  # create, update, delete

            project_auth = ProjectAuth.objects.get(
                project=auth_dto.project,
                user=auth_dto.user
            )

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

        except ProjectAuth.DoesNotExist:
            if action != "delete":
                project_auth = ProjectAuth.objects.create(
                    project=auth_dto.project,
                    user=auth_dto.user,
                    role=auth_dto.role
                )
                return project_auth
            raise ValueError("Project auth does not exists")
        except Exception as exception:
            raise exception


class CreateIntegratedFeatureUseCase:

    def create_integrated_feature(
        self,
        consumer_msg: dict
    ) -> IntegratedFeature:

        project_uuid = consumer_msg.get("project_uuid")
        feature_uuid = consumer_msg.get("feature_uuid")
        action = consumer_msg.get("action")

        if action is None:
            raise ValueError("Action is required")

        try:
            project = get_project_by_uuid(project_uuid=project_uuid)
        except ProjectDoesNotExist as e:
            raise e
        except Exception as e:
            raise e

        integrated_feature, created = IntegratedFeature.objects.get_or_create(
            project=project,
            feature_uuid=feature_uuid,
            current_version_setup=action
        )

        if not created and integrated_feature.is_integrated:
            raise ValueError("Integrated feature already exists")

        return integrated_feature

    def integrate_feature_flows(self, consumer_msg: dict):
        integrated_feature_dto = IntegratedFeatureDTO(
            project_uuid=consumer_msg.get("project_uuid"),
            feature_uuid=consumer_msg.get("feature_uuid"),
            flows=consumer_msg.get("flows")
        )
        flows = integrated_feature_dto.flows

        for flow in flows:
            if 'new_uuid' in flow:
                return self._update_flow(flow, integrated_feature_dto)
            else:
                return self._create_flow(integrated_feature_dto)

    def _update_flow(self, flow, integrated_feature_dto):
        integrated_feature = integrated_feature_dto.integrated_feature
        update_dto = UpdateFlowDTO(
            flow_uuid=flow.get("new_uuid"),
            name=integrated_feature.current_version_setup.get("name"),
            prompt=integrated_feature.current_version_setup.get("prompt"),
        )
        usecase = UpdateFlowsUseCase()
        return usecase.update_flow(flow_dto=update_dto)

    def _create_flow(self, integrated_feature_dto):
        create_flow_dto = integrated_feature_dto.action_dto

        if not create_flow_dto:
            raise ValueError("Flows not found")

        usecase = CreateFlowsUseCase()
        created_flow = usecase.create_flow(create_flow_dto)

        integrated_feature = integrated_feature_dto.integrated_feature
        integrated_feature.is_integrated = True
        integrated_feature.save(update_fields=["is_integrated"])

        return created_flow
