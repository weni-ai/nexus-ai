from dataclasses import dataclass


@dataclass
class OrgCreationDTO:
    uuid: str
    name: str
    authorizations: list


@dataclass
class OrgAuthCreationDTO:
    user_email: str
    org_uuid: str
    role: int
