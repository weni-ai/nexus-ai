from django.urls import path
from .views import ProjectUpdateViewset, ProjectIndexerView


urlpatterns = [
    path('<project_uuid>/project', ProjectUpdateViewset.as_view(), name="project-update"),
    path('<project_uuid>/project-indexer', ProjectIndexerView.as_view(), name="project-indexer"),
]
