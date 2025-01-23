from rest_framework.exceptions import APIException


class AgentInstructionsTooShort(APIException):
    status_code = 400
    default_detail = "Agent instructions are too short, minimum is 40 characters."
    default_code = "agent_instructions_too_short"


class AgentNameTooLong(APIException):
    satus_code = 400
    default_detail = "Agent name is too long, maximum is 20 characters."
    default_code = "agent_name_too_long"


class SkillNameTooLong(APIException):
    satus_code = 400
    default_detail = "Skill name is too long, maximum is 53 characters."
    default_code = "agent_name_too_long"


class SkillFileTooLarge(APIException):
    status_code = 400
    default_code = "skill_file_too_large"

    def __init__(self, filename):
        if filename:
            detail = f"Skill file: {filename} is too large, maximum size is 10485760 bytes (10MB)"
            super().__init__(detail)


class AgentAttributeNotAllowed(APIException):
    satus_code = 400
    default_detail = 'You are not allowed to add or update prompt_override_configuration, memory_configuration and foundationModel.'
    default_code = "agent_attribute_not_allowed"
