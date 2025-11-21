"""
ASGI config for nexus project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/asgi/
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")
django.setup()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from django.core.asgi import get_asgi_application  # noqa: E402

from nexus.authentication.authentication import (  # noqa: E402
    TokenAuthMiddleware,
)
from nexus.projects.websockets import routing  # noqa: E402

application = ProtocolTypeRouter(
    {"http": get_asgi_application(), "websocket": TokenAuthMiddleware(URLRouter(routing.websocket_urlpatterns))}
)
