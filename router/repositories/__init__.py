from abc import ABC, abstractmethod


class Repository(ABC):

    def check_connection(self):
        message_started.send(sender=self)
        try:
            db_conn = connections['default']
            db_conn.cursor()
        finally:
            message_finished.send(sender=self)

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