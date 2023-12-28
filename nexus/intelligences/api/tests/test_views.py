import json

from django.test import TestCase
from rest_framework.test import force_authenticate
from rest_framework.test import APIRequestFactory

from ..views import (
    IntelligencesViewset,
    ContentBaseViewset,
    ContentBaseTextViewset
)

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
            'delete': 'destroy',
        })
        self.intelligence = IntelligenceFactory()
        self.user = self.intelligence.created_by
        self.org = self.intelligence.org
        self.url = f'{self.org.uuid}/intelligences/'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)

        response = self.view(
            request,
            org_uuid=str(self.org.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):

        url_retrieve = f'{self.url}/{self.intelligence.uuid}/'

        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)

        response = IntelligencesViewset.as_view({'get': 'retrieve'})(
            request,
            org_uuid=str(self.org.uuid),
            intelligence_uuid=str(self.intelligence.uuid),
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'name': 'intelligence_name',
            'description': 'intelligence_description'
        }
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)

        response = self.view(request, org_uuid=str(self.org.uuid))
        self.assertEqual(response.status_code, 201)

    def test_update(self):

        url_put = f'{self.url}/{self.intelligence.uuid}/'
        data = {
            'name': 'intelligence_name',
            'description': 'intelligence_description',
            'intelligence_uuid': str(self.intelligence.uuid),
        }
        request = self.factory.put(
            url_put,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], data['name'])

    def test_delete(self):
        url_delete = f'{self.url}/{self.intelligence.uuid}/'
        data = {
            'intelligence_uuid': str(self.intelligence.uuid),
        }

        request = self.factory.delete(
            url_delete,
            json.dumps(data),
            content_type='application/json'
        )
        force_authenticate(request, user=self.user)

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
        self.contentbase = ContentBaseFactory()
        self.user = self.contentbase.created_by
        self.intelligence = self.contentbase.intelligence

        self.url = f'{self.intelligence.uuid}/content-bases'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            intelligence_uuid=str(self.intelligence.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):

        url_retrieve = f'{self.url}/{self.contentbase.uuid}/'
        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)
        response = ContentBaseViewset.as_view({'get': 'retrieve'})(
            request,
            intelligence_uuid=str(self.intelligence.uuid),
            content_base_uuid=str(self.contentbase.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'title': 'title'
        }
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)
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
        force_authenticate(request, user=self.user)
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
        force_authenticate(request, user=self.user)
        response = self.view(request)
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
        self.contentbasetext = ContentBaseTextFactory()
        self.user = self.contentbasetext.created_by
        self.content_base = self.contentbasetext.content_base
        self.intelligence = self.content_base.intelligence
        self.url = f'{self.content_base.uuid}/content-bases-text'

    def test_get_queryset(self):

        request = self.factory.get(self.url)
        force_authenticate(request, user=self.user)
        response = self.view(
            request,
            contentbase_uuid=str(self.content_base.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_retrieve(self):

        url_retrieve = f'{self.url}/{self.contentbasetext.uuid}/'
        request = self.factory.get(url_retrieve)
        force_authenticate(request, user=self.user)
        response = ContentBaseTextViewset.as_view({'get': 'retrieve'})(
            request,
            contentbase_uuid=str(self.content_base.uuid),
            content_base_text_uuid=str(self.contentbasetext.uuid)
        )
        self.assertEqual(response.status_code, 200)

    def test_create(self):
        data = {
            'text': 'text',
            'intelligence_uuid': str(self.intelligence.uuid),
        }
        request = self.factory.post(self.url, data)
        force_authenticate(request, user=self.user)
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
        force_authenticate(request, user=self.user)
        response = self.view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['text'], data['text'])
