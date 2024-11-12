from django.urls import path
from .views import ProjectUpdateViewset


urlpatterns = [
    path('<project_uuid>/project', ProjectUpdateViewset.as_view(), name="project-update"),
]
