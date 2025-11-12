from rest_framework.pagination import CursorPagination, PageNumberPagination


class CustomCursorPagination(CursorPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50
    ordering = "created_at"


class InlineConversationsCursorPagination(CursorPagination):
    page_size = 12
    ordering = "-created_at"
    page_size_query_param = "page_size"
    cursor_query_param = "cursor"


class SupervisorPagination(PageNumberPagination):
    """Custom pagination for SupervisorViewset that works with lists of dictionaries"""

    page_size = 12
    page_size_query_param = "page_size"
    max_page_size = 50
    page_query_param = "page"
