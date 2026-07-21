"""Temporary debug flags to isolate components prompts vs tools (stg experiments)."""

import logging
from typing import Tuple

from django.conf import settings

logger = logging.getLogger(__name__)


def resolve_components_prompt_and_tools(use_components: bool) -> Tuple[bool, bool]:
    """
    Split use_components into prompt vs tool features for A/B isolation.

    Delivery (broadcast/gRPC) still uses the project use_components flag.
    Defaults keep current behavior (both True when use_components is True).
    """
    include_prompts = bool(use_components) and bool(getattr(settings, "COMPONENTS_DEBUG_INCLUDE_PROMPTS", True))
    include_tools = bool(use_components) and bool(getattr(settings, "COMPONENTS_DEBUG_INCLUDE_TOOLS", True))
    if use_components and (not include_prompts or not include_tools):
        logger.info(
            "[ProgressiveFeedback] components debug isolation use_components=%s " "include_prompts=%s include_tools=%s",
            use_components,
            include_prompts,
            include_tools,
        )
    return include_prompts, include_tools
