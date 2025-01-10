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
