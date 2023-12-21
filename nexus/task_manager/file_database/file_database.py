from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FileResponseDTO:
    status: int
    file_url: str
    err: str

class FileDataBase(ABC):

    @abstractmethod
    def add_file(file) -> FileResponseDTO:
        ...
