from django.urls import path, include
from nexus.logs.api.views import LogsViewset


urlpatterns = [
    path('<project_uuid>/logs/', LogsViewset.as_view({'get': 'list'}), name='list-logs'),
    path('<project_uuid>/logs/<log_id>', LogsViewset.as_view({'get': 'retrieve'}), name='retrieve-logs'),
]

urlpatterns.append(path('prometheus/', include('django_prometheus.urls')))
