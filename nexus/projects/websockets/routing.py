from django.urls import re_path

from nexus.projects.websockets.consumers import WebsocketMessageConsumer


websocket_urlpatterns = [
    re_path(r'ws/socket-server/project/(?P<project>[0-9a-f-]+)/$', WebsocketMessageConsumer.as_asgi())
]
