from django.test import TestCase
from rest_framework.test import APIRequestFactory
from ..views import IntelligencesViewset

from nexus.orgs.models import Org
from nexus.users.models import User


class TestIntelligencesViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = IntelligencesViewset.as_view({
            'get': 'list',
            'post': 'create'
        })
        self.user = User.objects.create(
            email='test3@user.com',
            language='en'
        )
        self.org = Org.objects.create(
            name='Test Org',
            created_by=self.user,
        )
        self.url = f'{self.org.uuid}/intelligences/'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        response = self.view(request, org_uuid=str(self.org.uuid))
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'name': 'intelligence_name',
            'description': 'intelligence_description',
            'email': self.user.email
        }
        request = self.factory.post(self.url, data)
        response = self.view(request, org_uuid=str(self.org.uuid))
        self.assertEqual(response.status_code, 201)
