from django.conf import settings
from rest_framework import permissions


class ZeroshotTokenPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        token = request.META.get("HTTP_AUTHORIZATION")

        if token:
            return token == f"Bearer {settings.FLOWS_TOKEN_ZEROSHOT}"
        else:
            return False
