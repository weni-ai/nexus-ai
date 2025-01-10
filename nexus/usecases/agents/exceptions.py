from rest_framework.exceptions import APIException


class AgentInstructionsTooShort(APIException):
    status_code = 400
    default_detail = "Agent instructions are too short, minimum is 40 characters."
    default_code = "agent_instructions_too_short"
