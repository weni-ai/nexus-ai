from rest_framework import status
from rest_framework.response import Response
from nexus.projects.exceptions import ProjectAuthorizationDenied
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from nexus.usecases.intelligences.exceptions import IntelligencePermissionDenied
from nexus.usecases.actions.retrieve import FlowDoesNotExist


class ExceptionHandlerMixin:
    @staticmethod
    def handle_exceptions(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except ProjectAuthorizationDenied:
                return Response(
                    {"detail": "You do not have permission to update this project"},
                    status=status.HTTP_403_FORBIDDEN
                )

            except ObjectDoesNotExist:
                return Response(
                    {"detail": "Resource not found"},
                    status=status.HTTP_404_NOT_FOUND
                )

            except IntelligencePermissionDenied:
                return Response(
                    {"detail": "You do not have permission to access this intelligence"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            except FlowDoesNotExist:
                return Response(
                    {"detail": "Flow does not exist"},
                    status=status.HTTP_404_NOT_FOUND
                )

            except PermissionDenied:
                return Response(
                    {"detail": "You do not have permission to access this resource"},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            except Exception as e:
                return Response(
                    {"detail": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        return wrapper