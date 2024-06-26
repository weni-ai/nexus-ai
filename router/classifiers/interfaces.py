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
