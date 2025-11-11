from dataclasses import dataclass


@dataclass
class CeleryContentBaseFileTaskManagerDTO:
    status: str
    uuid: str
    created_by: str
    content_base_file_uuid: str

    def to_json(self):
        return {
            "status": self.status,
            "uuid": self.uuid,
            "created_by": self.created_by,
            "content_base_file_uuid": self.content_base_file_uuid,
        }
