from dataclasses import dataclass


@dataclass
class ProjectDTO:
    uuid: str
    name: str
    indexer_database: str
