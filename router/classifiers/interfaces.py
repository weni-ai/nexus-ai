from abc import ABC, abstractmethod
from typing import List


class Classifier(ABC):
    CLASSIFICATION_OTHER = "other"
    @abstractmethod
    def predict(self, message: str, flows: List, language: str = "por"):
        pass
