from django.urls import path
from .views import ProjectUpdateViewset, MessageDetailViewSet


urlpatterns = [
    path('<project_uuid>/project', ProjectUpdateViewset.as_view(), name="project-update"),
    path('<project_uuid>/message-detail/<message_uuid>', MessageDetailViewSet.as_view(), name="message-detail"),
]
