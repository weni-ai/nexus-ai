import json

from django.test import TestCase
from rest_framework.test import APIRequestFactory
from ..views import (
    IntelligencesViewset,
    ContentBaseViewset,
    ContentBaseTextViewset
)

from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.orgs.tests.org_factory import OrgFactory
from nexus.usecases.intelligences.tests.intelligence_factory import (
    IntelligenceFactory,
    ContentBaseFactory,
    ContentBaseTextFactory
)


class TestIntelligencesViewset(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = IntelligencesViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy'
        })
        self.user = UserFactory()
        self.org = OrgFactory(
            created_by=self.user
        )
        self.intelligence = IntelligenceFactory(
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
        self.user = UserFactory()
        self.org = OrgFactory(
            created_by=self.user
        )
        self.intelligence = IntelligenceFactory(
            created_by=self.user,
            org=self.org
        )
        self.contentbase = ContentBaseFactory(
            created_by=self.user,
            intelligence=self.intelligence
        )
        self.url = f'{self.intelligence.uuid}/content-bases'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid)
        )
        print("List response: ", response.data)
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
        print("Create response: ", response.data)
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
        print("Update response: ", response.data)
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
        print("Delete response: ", response.data)
        self.assertEqual(response.status_code, 204)


class TestContentBaseTextViewset(TestCase):

    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = ContentBaseTextViewset.as_view({
            'get': 'list',
            'post': 'create',
            'put': 'update',
            'delete': 'destroy'
        })
        self.user = UserFactory()
        self.org = OrgFactory(
            created_by=self.user
        )
        self.intelligence = IntelligenceFactory(
            created_by=self.user,
            org=self.org
        )
        self.content_base = ContentBaseFactory(
            created_by=self.user,
            intelligence=self.intelligence
        )
        self.contentbasetext = ContentBaseTextFactory(
            created_by=self.user,
            content_base=self.content_base
        )
        self.url = f'{self.org.uuid}/intelligences/content-bases-text'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        response = self.view(
            request,
            contentbase_uuid=str(self.content_base.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'text': 'text',
            'email': self.user.email,
            'intelligence_uuid': str(self.intelligence.uuid),
        }
        request = self.factory.post(self.url, data)
        response = self.view(
            request,
            contentbase_uuid=str(self.content_base.uuid)
        )
        self.assertEqual(response.status_code, 201)

    def test_update(self):
        data = {
            'text': 'text',
            'contentbasetext_uuid': str(self.contentbasetext.uuid),
        }
        url_put = f'{self.url}/{self.contentbasetext.uuid}/'
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['text'], data['text'])