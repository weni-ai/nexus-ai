from django.urls import path
from .views import ProjectUpdateViewset, ProjectPromptCreationConfigurationsViewset


urlpatterns = [
    path('<project_uuid>/project', ProjectUpdateViewset.as_view(), name="project-update"),
    path('<project_uuid>/prompt-creation-configurations', ProjectPromptCreationConfigurationsViewset.as_view(), name="project-prompt-creation-configurations"),
]
