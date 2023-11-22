import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory
from ..views import IntelligencesViewset, ContentBaseViewset

from nexus.orgs.models import Org
from nexus.users.models import User
from nexus.intelligences.models import Intelligence, ContentBase


class TestIntelligencesViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = IntelligencesViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy'
        })
        self.user = User.objects.create(
            email='test3@user.com',
            language='en'
        )
        self.org = Org.objects.create(
            name='Test Org',
            created_by=self.user,
        )
        self.intelligence = Intelligence.objects.create(
            name='Test Intelligence',
            description='Test Intelligence Description',
            created_by=self.user,
            org=self.org
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

    def test_update(self):
        data = {
            'name': 'intelligence_name',
            'description': 'intelligence_description',
            'intelligence_uuid': str(self.intelligence.uuid),
        }
        url_put = f'{self.url}/{self.intelligence.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], data['name'])

    def test_delete(self):
        data = {
            'intelligence_uuid': str(self.intelligence.uuid),
        }
        url_delete = f'{self.url}/{self.intelligence.uuid}/'
        request = self.factory.delete(
            url_delete,
            json.dumps(data),
            content_type='application/json'
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 204)


class TestContentBaseViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ContentBaseViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy'
        })
        self.user = User.objects.create(
            email='test3@user.com',
            language='en'
        )
        self.org = Org.objects.create(
            name='Test Org',
            created_by=self.user,
        )
        self.intelligence = Intelligence.objects.create(
            name='Test Intelligence',
            description='Test Intelligence Description',
            created_by=self.user,
            org=self.org
        )
        self.contentbase = ContentBase.objects.create(
            intelligence=self.intelligence,
            created_by=self.user,
            title="title"
        )
        self.url = f'{self.org.uuid}/intelligences/'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'title': 'title',
            'email': self.user.email
        }
        request = self.factory.post(self.url, data)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid)
        )
        self.assertEqual(response.status_code, 201)

    def test_update(self):
        data = {
            'title': 'title',
            'description': 'description',
            'contentbase_uuid': str(self.contentbase.uuid),
        }
        url_put = f'{self.url}/{self.contentbase.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], data['title'])

    def test_delete(self):
        data = {
            'contentbase_uuid': str(self.contentbase.uuid),
        }
        url_delete = f'{self.url}/{self.contentbase.uuid}/'
        request = self.factory.delete(
            url_delete,
            json.dumps(data),
            content_type='application/json'
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 204)
