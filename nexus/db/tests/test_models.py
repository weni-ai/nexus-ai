import pytest

from nexus.db.models import BaseModel, SoftDeleteModel


@pytest.mark.django_db
def test_create_base_model(create_user):
    test_user = create_user
    BaseModel.objects.create(created_by=test_user)
    assert BaseModel.objects.count() == 1


@pytest.mark.django_db
def test_create_soft_delete_model():
    obj = SoftDeleteModel.objects.create()
    assert obj.is_active
    assert SoftDeleteModel.objects.count() == 1
