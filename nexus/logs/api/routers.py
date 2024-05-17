from django.urls import path
from nexus.logs.api.views import LogsViewset


urlpatterns = [
    path('<project_uuid>/logs/', LogsViewset.as_view({'get': 'list'}), name='list-logs')
]
