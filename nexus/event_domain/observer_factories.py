"""
Factory functions for creating observer instances with proper dependencies.

These factories enable dependency injection for observers, making them easier to test
and allowing for better separation of concerns.
"""

import logging
from typing import Type

import boto3

from nexus.environment import env
from nexus.event_domain.event_observer import EventObserver

logger = logging.getLogger(__name__)


def create_rationale_observer(observer_class: Type[EventObserver]) -> EventObserver:
    """
    Factory for creating RationaleObserver with dependencies.

    This factory creates the necessary dependencies (bedrock_client, typing_usecase)
    and injects them into the observer, making it easier to test and mock.

    Dependencies are lazy-loaded to avoid circular imports.

    Args:
        observer_class: The RationaleObserver class

    Returns:
        RationaleObserver instance with dependencies injected
    """
    # Lazy imports to avoid circular dependencies
    from django.conf import settings

    from nexus.usecases.inline_agents.typing import TypingUsecase

    # Create bedrock client
    try:
        region_name = env.str("AWS_BEDROCK_REGION_NAME")
        bedrock_client = boto3.client("bedrock-runtime", region_name=region_name)
    except Exception as e:
        logger.warning(f"Failed to create bedrock client: {e}. Observer will create its own.")
        bedrock_client = None

    # Create typing usecase
    typing_usecase = TypingUsecase()

    # Get model ID from settings
    model_id = settings.AWS_RATIONALE_MODEL

    # Create observer with dependencies
    return observer_class(
        bedrock_client=bedrock_client,
        model_id=model_id,
        typing_usecase=typing_usecase,
    )


def create_default_observer(observer_class: Type[EventObserver]) -> EventObserver:
    """
    Default factory that creates observers with no arguments.

    This is used for observers that don't need dependencies or have defaults.

    Args:
        observer_class: The observer class

    Returns:
        Observer instance created with no arguments
    """
    return observer_class()
