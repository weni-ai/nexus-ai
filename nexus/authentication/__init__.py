from django.conf import settings
from nexus.authentication.authentication import ExternalTokenAuthentication
from mozilla_django_oidc.contrib.drf import OIDCAuthentication


FLOWS_AUTHENTICATION_CLASSES = [ExternalTokenAuthentication]
AUTHENTICATION_CLASSES = [ExternalTokenAuthentication, OIDCAuthentication]
