from django.apps import AppConfig


class KeycloakAdminConfig(AppConfig):
    name = "weni_django_keycloak_admin"
    verbose_name = "Weni Django Keycloak Admin"

    def ready(self):
        from . import checks  # noqa: F401
