from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FlowsIntelligencesApiView,
    IntelligencesViewset,
    ContentBaseViewset,
    ContentBaseTextViewset,
    ContentBaseFileViewset,
    ContentBaseLinkViewset,
    SentenxIndexerUpdateFile,
    GenerativeIntelligenceQuestionAPIView,
    QuickTestAIAPIView,
    DownloadFileViewSet,
    LogsViewSet,
    RouterContentBaseViewSet,
    LLMViewset,
    LLMDefaultViewset,
    ContentBasePersonalizationViewSet,
    ContentBaseFilePreview,
    UploadFileView,
    RouterRetailViewSet,
    CommerceHasAgentBuilder,
    InlineContentBaseFileViewset
)


org_router = DefaultRouter()
intelligence_router = DefaultRouter()
content_base_router = DefaultRouter()

org_router.register(r'', IntelligencesViewset, basename='intelligences')
intelligence_router.register(
    r'content-bases',
    ContentBaseViewset,
    basename='content-bases'
)
content_base_router.register(
    r'content-bases-text',
    ContentBaseTextViewset,
    basename='content-bases-text'
)

content_base_router.register(
    r'content-bases-file',
    ContentBaseFileViewset,
    basename='content-base-file'
)

content_base_router.register(
    r'content-bases-link',
    ContentBaseLinkViewset,
    basename='content-base-link'
)

urlpatterns = [
    path('<org_uuid>/intelligences/', include(org_router.urls)),
    path('<intelligence_uuid>/', include(intelligence_router.urls)),
    path('<content_base_uuid>/', include(content_base_router.urls)),
    path('<project_uuid>/inline-content-base-file/', InlineContentBaseFileViewset.as_view(), name="inline-content-base-file"),
    path('<project_uuid>/router/', RouterContentBaseViewSet.as_view(), name="project-content-bases"),
    path('<project_uuid>/commerce-router/', RouterRetailViewSet.as_view(), name="project-commerce-router"),
    path('<project_uuid>/llm/', LLMViewset.as_view(), name='llm'),
    path('<project_uuid>/llm-default/', LLMDefaultViewset.as_view(), name='llm'),
    path('<project_uuid>/document-preview/', ContentBaseFilePreview.as_view(), name="document-preview"),
    path('v1/intelligences/content_bases/<project_uuid>/', FlowsIntelligencesApiView.as_view(), name="project-intelligences"),
    path('v1/content-base-file', SentenxIndexerUpdateFile.as_view(), name="sentenx-content-base-file"),
    path('v1/wenigpt_question', GenerativeIntelligenceQuestionAPIView.as_view(), name="wenigpt-question"),
    path('v1/wenigpt_question/quick-test', QuickTestAIAPIView.as_view(), name="wenigpt-quick-test"),
    path('v1/download-file', DownloadFileViewSet.as_view(), name="download-file"),
    path('<content_base_uuid>/content-base-logs/<log_uuid>', LogsViewSet.as_view(), name="content-base-logs"),
    path('<project_uuid>/customization/', ContentBasePersonalizationViewSet.as_view({'get': 'list', 'put': 'update', 'delete': 'destroy'}), name='content-base-personalization'),
    path('<project_uuid>/upload-file', UploadFileView.as_view(), name='upload-file'),
    path('commerce/check-exists-agent-builder', CommerceHasAgentBuilder.as_view(), name='check-exists-agent-builder')
]
