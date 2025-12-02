from mozilla_django_oidc.contrib.drf import OIDCAuthentication

from nexus.authentication.authentication import ExternalTokenAuthentication

FLOWS_AUTHENTICATION_CLASSES = [ExternalTokenAuthentication]
AUTHENTICATION_CLASSES = [ExternalTokenAuthentication, OIDCAuthentication]
