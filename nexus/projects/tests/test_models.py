import pytest

from nexus.projects.models import Project


@pytest.mark.django_db
def test_create_project(create_user, create_org):
    project_name = 'Test Project'
    org = create_org
    user = create_user
    project = Project.objects.create(
        name=project_name, org=org, created_by=user
    )

    assert Project.objects.count() == 1
    assert project.is_active
    assert project.name == project_name
    assert project.org == org
    assert project.created_by == user


@pytest.mark.django_db
def test_create_template_project(
    create_user, create_org, create_template_type
):
    project_name = 'Test Template Project'
    org = create_org
    user = create_user
    template_type = create_template_type

    project = Project.objects.create(
        name=project_name,
        org=org,
        created_by=user,
        is_template=True,
        template_type=template_type,
    )

    assert (
        template_type.__str__()
        == f'{template_type.uuid} - {template_type.name}'
    )
    assert Project.objects.count() == 1
    assert project.is_active
    assert project.is_template
    assert project.name == project_name
    assert project.org == org
    assert project.created_by == user
    assert (
        project.__str__()
        == f'{project.uuid} - Project: {project.name} - Org: {project.org.name}'
    )
