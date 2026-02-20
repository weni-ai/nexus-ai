from django.utils import timezone
from rest_framework import authentication, permissions
from rest_framework.exceptions import AuthenticationFailed

from nexus.users.models import UserApiToken


class UserGlobalTokenAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization", "")
        if not isinstance(auth_header, str) or not auth_header.startswith(f"{self.keyword} "):
            return None

        try:
            raw_token = auth_header.split(" ", 1)[1].strip()
        except IndexError:
            return None

        # To avoid timing attacks, the prefix should be constant length
        prefix_length = 8
        if len(raw_token) <= prefix_length:
            return None

        prefix = raw_token[:prefix_length]

        # Use filter() to handle potential prefix collisions gracefully
        tokens = UserApiToken.objects.select_related("user").filter(token_prefix=prefix, enabled=True)

        for token_obj in tokens:
            if token_obj.matches(raw_token):
                if token_obj.expires_at and token_obj.expires_at <= timezone.now():
                    raise AuthenticationFailed("Token expired")

                # Update last used
                token_obj.last_used_at = timezone.now()
                token_obj.save(update_fields=["last_used_at"])

                return (token_obj.user, token_obj)

        return None


class UserGlobalTokenPermission(permissions.BasePermission):
    """
    Permission class that grants access if the request was authenticated via UserGlobalToken.
    """

    def has_permission(self, request, view):
        # Check if user is authenticated and the auth method was UserGlobalTokenAuthentication
        # DRF sets request.auth to the second element returned by authenticate()
        if request.user and request.user.is_authenticated:
            if isinstance(request.auth, UserApiToken):
                return True
        return False
