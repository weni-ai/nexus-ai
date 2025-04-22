from rest_framework.pagination import CursorPagination


class CustomCursorPagination(CursorPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 50
    ordering = "created_at"


class InlineConversationsCursorPagination(CursorPagination):
    page_size = 12
    ordering = 'created_at'
    page_size_query_param = 'page_size'
    cursor_query_param = 'cursor'
