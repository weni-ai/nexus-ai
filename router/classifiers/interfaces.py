from abc import ABC, abstractmethod
from typing import List


class Classifier(ABC):
    CLASSIFICATION_OTHER = "other"

    @abstractmethod
    def predict(self, message: str, flows: List, language: str = "por"):
        pass  # pragma: no cover


class OpenAIClientInterface(ABC):
    @abstractmethod
    def chat_completions_create(self, model, messages, tools, tool_choice):
        pass  # pragma: no cover


class ModelVersionReflection(ABC):

    @abstractmethod
    def request_reflection(
        self,
        prompt: str,
    ):
        pass

    @abstractmethod
    def format_prompt(self) -> str:
        pass

    @abstractmethod
    def basic_reflection_strategy(
        self,
        prompt: str
    ) -> str:
        pass

    @abstractmethod
    def reflect(
        self,
        message_to_reflect: str
    ) -> str:
        # Should return only a strig with the reflected message
        pass
