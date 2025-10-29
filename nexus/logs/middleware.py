import os

from django.http import HttpResponseForbidden


class PrometheusAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/prometheus/"):
            auth_token = request.headers.get("Authorization")
            prometheus_auth_token = os.environ.get("PROMETHEUS_AUTH_TOKEN")

            expected_token = f"Bearer {prometheus_auth_token}"
            if not auth_token or auth_token != expected_token:
                return HttpResponseForbidden("Acesso negado")

        response = self.get_response(request)
        return response
