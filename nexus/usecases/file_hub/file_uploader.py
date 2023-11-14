from abc import ABC, abstractmethod

class FileUploader(ABC):

    def __init__(self, file):
        self.file = file

    @abstractmethod
    def upload_content_file(self):
        ...
