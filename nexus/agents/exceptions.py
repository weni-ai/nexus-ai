from rest_framework.exceptions import APIException


class BaseCredentialException(APIException):
    status_code = 400

    def __init__(self, detail=None, code=None, field_name=None):
        if detail is None:
            detail = self.default_detail
        if field_name:
            detail = f"Invalid value for field: {field_name}. {detail}"
        super().__init__(detail, code)


class CredentialKeyInvalid(BaseCredentialException):
    default_detail = "Credential key must be a string."
    default_code = "credential_key_invalid"

    @classmethod
    def length_exceeded(cls, field_name=None):
        return cls("Credential key exceeds maximum length of 255 characters.", field_name=field_name)


class CredentialLabelInvalid(BaseCredentialException):
    default_detail = "Credential label must be a string."
    default_code = "credential_label_invalid"

    @classmethod
    def length_exceeded(cls, field_name=None):
        return cls("Credential label exceeds maximum length of 255 characters.", field_name=field_name)


class CredentialValueInvalid(BaseCredentialException):
    default_detail = "Credential value must be a string."
    default_code = "credential_value_invalid"

    @classmethod
    def length_exceeded(cls, field_name=None):
        return cls("Credential value exceeds maximum length of 8192 characters.", field_name=field_name)


class CredentialPlaceholderInvalid(BaseCredentialException):
    default_detail = "Credential placeholder must be a string when provided."
    default_code = "credential_placeholder_invalid"

    @classmethod
    def length_exceeded(cls, field_name=None):
        return cls("Credential placeholder exceeds maximum length of 255 characters.", field_name=field_name)


class CredentialIsConfidentialInvalid(BaseCredentialException):
    default_detail = "Credential is_confidential must be a boolean value."
    default_code = "credential_is_confidential_invalid"
