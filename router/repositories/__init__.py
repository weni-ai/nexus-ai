from abc import ABC, abstractmethod


class Repository(ABC):
    @abstractmethod
    def get(self, uuid: str):
        raise NotImplementedError

    @abstractmethod
    def get_all(self):
        raise NotImplementedError

    @abstractmethod
    def add(self):
        raise NotImplementedError

    @abstractmethod
    def update(self, uuid: str):
        raise NotImplementedError

    @abstractmethod
    def delete(self, uuid: str):
        raise NotImplementedError