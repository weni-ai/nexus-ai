from rest_framework.exceptions import APIException


class ProjectDoesNotExist(Exception):
    pass


class ProjectAuthorizationDenied(APIException):
    status_code = 403
    default_detail = "You do not have permission to perform this action."
    default_code = "permission_denied"


class ResolutionCriterionNotFound(Exception):
    pass


class UnauthorizedBaseCriterionChange(Exception):
    pass


class ResolutionCriterionValidationError(Exception):
    def __init__(self, code: str, message: str, rules: list | None = None):
        self.code = code
        self.message = message
        self.rules = rules or []
        super().__init__(message)


class LambdaValidationFailedError(Exception):
    def __init__(self, message: str = "The criterion could not be validated due to a technical issue"):
        self.message = message
        super().__init__(message)
