from django.urls import re_path

from nexus.projects.websockets.consumers import PreviewConsumer, WebsocketMessageConsumer

# TODO: Create a separeted consumer for simulation channel any behavior changes.
websocket_urlpatterns = [
    re_path(r"ws/monitoring/(?P<project>[0-9a-f-]+)/$", WebsocketMessageConsumer.as_asgi()),
    re_path(r"ws/preview/(?P<project>[0-9a-f-]+)/$", PreviewConsumer.as_asgi()),
    re_path(r"ws/(?P<project>[0-9a-f-]+)/simulation/$", PreviewConsumer.as_asgi()),
]
