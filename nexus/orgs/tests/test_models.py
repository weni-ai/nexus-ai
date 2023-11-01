import pytest

from nexus.orgs.models import Org


@pytest.mark.django_db
def test_create_org(create_user):
    org_name = 'Test Org'
    user = create_user
    org = Org.objects.create(created_by=user, name=org_name)
    assert Org.objects.count() == 1
    assert org.is_active
    assert org.name == org_name
