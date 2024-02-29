from .template_type_dto import TemplateTypeDTO
from nexus.projects.models import TemplateType, Project


class TemplateTypeUseCase:

    def get_intelligences_info_by_project(self, project):
        info = {"intelligences": []}
        org = project.org
        for intelligence in org.intelligences.all():
            info["intelligences"].append(
                {
                    "uuid": intelligence.uuid
                }
            )
        return info

    def create_template_type(self, template_type_dto: TemplateTypeDTO):  # pragma: no cover
        from nexus.usecases.projects.projects_use_case import ProjectsUseCase
        try:
            project = ProjectsUseCase().get_by_uuid(project_uuid=template_type_dto.project_uuid)
        except Project.DoesNotExist:
            raise Exception(f"Project `{template_type_dto.project_uuid}` does not exists!")
        setup = self.get_setup(project=project)  # Not implemented
        template_type, created = TemplateType.objects.get_or_create(uuid=template_type_dto.uuid, defaults=dict(name=template_type_dto.name, setup=setup))
        if not created:
            template_type.setup = setup
            template_type.name = template_type_dto.name
            template_type.save()
        return template_type

    def get_by_uuid(self, template_type_uuid: str):
        try:
            template_type = TemplateType.objects.get(uuid=template_type_uuid)
        except TemplateType.DoesNotExist:
            raise Exception(f"Template Type `{template_type_uuid}` does not exists!")
        return template_type
