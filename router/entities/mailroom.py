from pydantic import BaseModel


class Message(BaseModel):
    project_uuid: str
    text: str
    contact_urn: str

    def dict(self):
        return {key: value for key, value in self.__dict__.items() if value is not None}