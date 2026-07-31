"""Tests for Celery Prometheus metrics exporter."""

import os
from io import BytesIO
from unittest.mock import patch

from django.test import SimpleTestCase

from nexus.celery_prometheus_exporter import (
    PROMETHEUS_METRICS_PATHS,
    _authorize_request,
    create_prometheus_wsgi_app,
)


class CeleryPrometheusExporterTestCase(SimpleTestCase):
    def _call_wsgi(self, app, path="/api/prometheus/", auth_header="Bearer secret"):
        environ = {
            "PATH_INFO": path,
            "HTTP_AUTHORIZATION": auth_header,
            "wsgi.input": BytesIO(b""),
            "REQUEST_METHOD": "GET",
        }
        status_headers = {}

        def start_response(status, headers, exc_info=None):
            status_headers["status"] = status
            status_headers["headers"] = dict(headers)

        body = b"".join(app(environ, start_response))
        return status_headers["status"], body, status_headers["headers"]

    def test_metrics_paths_defined(self):
        self.assertIn("/api/prometheus/", PROMETHEUS_METRICS_PATHS)

    def test_authorize_request_requires_bearer_token(self):
        with patch.dict(os.environ, {"PROMETHEUS_AUTH_TOKEN": "secret"}, clear=False):
            self.assertTrue(_authorize_request({"HTTP_AUTHORIZATION": "Bearer secret"}))
            self.assertFalse(_authorize_request({"HTTP_AUTHORIZATION": "Bearer wrong"}))
            self.assertFalse(_authorize_request({}))

    def test_wsgi_returns_404_for_unknown_path(self):
        app = create_prometheus_wsgi_app()
        status, _, _ = self._call_wsgi(app, path="/metrics")
        self.assertEqual(status, "404 Not Found")

    def test_wsgi_returns_403_without_auth(self):
        app = create_prometheus_wsgi_app()
        with patch.dict(os.environ, {"PROMETHEUS_AUTH_TOKEN": "secret"}, clear=False):
            status, body, _ = self._call_wsgi(app, auth_header="")
            self.assertEqual(status, "403 Forbidden")
            self.assertEqual(body, b"Acesso negado")

    @patch("nexus.celery_prometheus_exporter._render_metrics", return_value=b"inline_agent_turn_duration_seconds_count 1\n")
    def test_wsgi_returns_metrics_with_auth(self, _mock_render):
        app = create_prometheus_wsgi_app()
        with patch.dict(os.environ, {"PROMETHEUS_AUTH_TOKEN": "secret"}, clear=False):
            status, body, headers = self._call_wsgi(app)
            self.assertEqual(status, "200 OK")
            self.assertIn(b"inline_agent_turn_duration_seconds_count", body)
            self.assertTrue(headers["Content-Type"].startswith("text/plain; version=0.0.4"))
