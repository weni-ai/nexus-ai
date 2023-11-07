from uuid import uuid4

from pytest import fixture

from nexus.intelligences.models import Intelligence
from nexus.orgs.models import Org
from nexus.projects.models import Project, TemplateType
from nexus.users.models import User


@fixture
def create_user():
    return User.objects.create_user('test@user.com')


@fixture
def create_org(create_user):
    org_name = 'Test Org'
    user = create_user
    return Org.objects.create(created_by=user, name=org_name)


@fixture
def create_template_type():
    return TemplateType.objects.create(
        uuid=uuid4(),
        name='Test Template Type',
    )


@fixture
def create_intelligence(create_org, create_user):
    org = create_org
    user = create_user
    return Intelligence.objects.create(
        name='Test Intelligence', org=org, created_by=user
    )


@fixture
def create_project(create_org, create_user):
    org = create_org
    user = create_user
    return Project.objects.create(
        name='Test Project', org=org, created_by=user
    )
