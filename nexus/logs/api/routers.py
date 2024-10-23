from django.urls import path, include
from nexus.logs.api.views import LogsViewset, RecentActivitiesViewset, MessageHistoryViewset


urlpatterns = [
    path('<project_uuid>/logs/', LogsViewset.as_view({'get': 'list'}), name='list-logs'),
    path('<project_uuid>/logs/<log_id>', LogsViewset.as_view({'get': 'retrieve'}), name='retrieve-logs'),
    path('<project_uuid>/activities/', RecentActivitiesViewset.as_view({'get': 'list'}), name='list-activities'),
    path('<project_uuid>/message_history/', MessageHistoryViewset.as_view({'get': 'list'}), name='list-message-history'),
]

urlpatterns.append(path('prometheus/', include('django_prometheus.urls')))
