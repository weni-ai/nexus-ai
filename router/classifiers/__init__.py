from typing import List
from router.classifiers.interfaces import Classifier


def classify(classifier: Classifier, message: str, flows: List) -> str:
    return classifier.predict(message, flows)