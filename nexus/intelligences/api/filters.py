from django_filters import rest_framework as filters

from nexus.intelligences.models import Conversation


class ConversationFilter(filters.FilterSet):
    """Filter for Conversation model"""

    start_date = filters.DateFilter(
        field_name="start_date", lookup_expr="gte", input_formats=["%d-%m-%Y"], method="filter_start_date"
    )
    end_date = filters.DateFilter(
        field_name="end_date", lookup_expr="lte", input_formats=["%d-%m-%Y"], method="filter_end_date"
    )
    csat = filters.BaseInFilter(field_name="csat")
    resolution = filters.BaseInFilter(field_name="resolution")
    topics = filters.BaseInFilter(field_name="topic__name")
    has_chats_room = filters.BooleanFilter(field_name="has_chats_room")
    nps = filters.NumberFilter(field_name="nps")
    search = filters.CharFilter(method="search_filter")

    class Meta:
        model = Conversation
        fields = {
            "csat": ["exact", "in"],
            "resolution": ["exact", "in"],
            "has_chats_room": ["exact"],
            "nps": ["exact"],
        }

    def search_filter(self, queryset, name, value):
        """Custom search filter for contact_name and contact_urn"""
        from django.db.models import Q

        return queryset.filter(Q(contact_name__icontains=value) | Q(contact_urn__icontains=value))

    def filter_start_date(self, queryset, name, value):
        """Filter by start date with default value if not provided"""
        print(f"DEBUG: filter_start_date called with value: {value}, type: {type(value)}")
        if value:
            result = queryset.filter(start_date__date__gte=value)
            print(f"DEBUG: start_date filter result count: {result.count()}")
            return result
        # Only apply default if no start_date parameter was provided at all
        # Don't apply default if the parameter was provided but invalid
        return queryset

    def filter_end_date(self, queryset, name, value):
        """Filter by end date with default value if not provided"""
        print(f"DEBUG: filter_end_date called with value: {value}, type: {type(value)}")
        if value:
            result = queryset.filter(end_date__date__lte=value)
            print(f"DEBUG: end_date filter result count: {result.count()}")
            return result
        # Only apply default if no end_date parameter was provided at all
        # Don't apply default if the parameter was provided but invalid
        return queryset

    def filter(self, queryset):
        """Override filter method to handle validation errors gracefully"""
        print(f"DEBUG: filter method called, initial queryset count: {queryset.count()}")
        try:
            result = super().filter(queryset)
            print(f"DEBUG: filter method result count: {result.count()}")

            # Debug: Check what resolution values are in the database
            if "resolution" in self.data:
                print(f"DEBUG: Resolution filter requested: {self.data['resolution']}")
                resolutions = list(queryset.values_list("resolution", flat=True))
                print(f"DEBUG: Available resolutions in DB: {resolutions}")

            return result
        except Exception as e:
            print(f"DEBUG: filter method exception: {type(e).__name__}: {e}")
            # Return empty queryset for validation errors
            return queryset.none()
