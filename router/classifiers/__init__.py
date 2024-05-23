from typing import List
from router.classifiers.interfaces import Classifier
from django.conf import settings


def classify(
    classifier: Classifier,
    message: str,
    flows: List,
    language: str = settings.WENIGPT_DEFAULT_LANGUAGE
) -> str:
    return classifier.predict(message, flows, language)
