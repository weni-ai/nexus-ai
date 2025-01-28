from django.urls import re_path

from nexus.projects.websockets.consumers import (
    WebsocketMessageConsumer,
    PreviewMultiagentsConsumer
)


websocket_urlpatterns = [
    re_path(r'ws/monitoring/(?P<project>[0-9a-f-]+)/$', WebsocketMessageConsumer.as_asgi()),
    re_path(r'ws/preview/(?P<project>[0-9a-f-]+)/$', PreviewMultiagentsConsumer.as_asgi())
]
