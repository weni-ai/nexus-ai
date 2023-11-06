import pytest

from nexus.db.models import BaseModel, SoftDeleteModel


@pytest.mark.django_db
def test_create_base_model(create_user):
    with pytest.raises(AttributeError):
        test_user = create_user
        BaseModel.objects.create(created_by=test_user)


@pytest.mark.django_db
def test_create_soft_delete_model():
    with pytest.raises(AttributeError):
        SoftDeleteModel.objects.create()
