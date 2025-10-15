from typing import List
from router.classifiers.interfaces import Classifier
from django.conf import settings


def classify(
    classifier: Classifier,
    message: str,
    flows: List,
    language: str = None
) -> str:
    if language is None:
        from django.conf import settings
        language = settings.WENIGPT_DEFAULT_LANGUAGE
        
    return classifier.predict(message, flows, language)
