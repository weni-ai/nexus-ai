from django.urls import path

from nexus.users.api.views import UserDetailsView

urlpatterns = [
    path("users/details/", UserDetailsView.as_view(), name="user-details"),
]
