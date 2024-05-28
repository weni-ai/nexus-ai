from rest_framework.exceptions import APIException


class ProjectDoesNotExist(BaseException):
    pass


class ProjectAuthorizationDenied(APIException):
    status_code = 403
    default_detail = 'You do not have permission to perform this action.'
    default_code = 'permission_denied'
