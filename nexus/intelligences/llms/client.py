from abc import ABC

class LLMClient(ABC):

    @classmethod
    def get_by_type(cls, type):
        return filter(lambda llm: llm.code==type, cls.__subclasses__())

    def request_gpt(self):
        pass
