import pytest

from nexus.db.models import BaseModel, SoftDeleteModel
from nexus.users.models import User


@pytest.mark.django_db
def test_create_base_model():
    test_user = User.objects.create_user('test@user.com')
    BaseModel.objects.create(created_by=test_user)
    assert BaseModel.objects.count() == 1


@pytest.mark.django_db
def test_create_soft_delete_model():
    obj = SoftDeleteModel.objects.create()
    assert obj.is_active
    assert SoftDeleteModel.objects.count() == 1
