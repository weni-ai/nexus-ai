import json
import logging
import threading
from typing import Any, Optional

from inline_agents.backends.openai.adapter import OpenAITeamAdapter
from inline_agents.backends.openai.entities import Context, HooksState

logger = logging.getLogger(__name__)

# Thread-local storage for passing credentials to _get_context
_thread_local = threading.local()


class WorkflowTeamAdapter(OpenAITeamAdapter):
    """
    Workflow-optimized team adapter that uses pre-fetched credentials.

    Avoids the DB query in _get_context by using credentials passed via to_external.
    """

    @classmethod
    def to_external(cls, *args, credentials: Optional[dict] = None, **kwargs):
        """
        Override to_external to accept pre-fetched credentials.

        If credentials are provided, they're stored in thread-local storage
        and used by _get_context instead of querying the database.
        """
        _thread_local.credentials = credentials

        try:
            return super().to_external(*args, **kwargs)
        finally:
            _thread_local.credentials = None

    @classmethod
    def _get_context(
        cls,
        project_uuid: str,
        contact_urn: str,
        auth_token: str,
        channel_uuid: str,
        contact_name: str,
        content_base_uuid: str,
        contact_fields: str,
        globals_dict: Optional[dict] = None,
        session: Optional[Any] = None,
        input_text: str = "",
        hooks_state: Optional[HooksState] = None,
    ) -> Context:
        if globals_dict is None:
            globals_dict = {}

        try:
            contact_fields = json.loads(contact_fields)
        except json.JSONDecodeError:
            contact_fields = {}

        # Use pre-fetched credentials if available, otherwise fetch from DB
        credentials = getattr(_thread_local, "credentials", None)
        if credentials is None:
            credentials = cls._get_credentials(project_uuid)
            logger.debug(f"[WorkflowTeamAdapter] Fetched credentials from DB for {project_uuid}")
        else:
            logger.debug(f"[WorkflowTeamAdapter] Using pre-fetched credentials for {project_uuid}")

        contact = {"urn": contact_urn, "channel_uuid": channel_uuid, "name": contact_name, "fields": contact_fields}
        project = {"uuid": project_uuid, "auth_token": auth_token}
        content_base = {"uuid": content_base_uuid}

        return Context(
            credentials=credentials,
            globals=globals_dict,
            contact=contact,
            project=project,
            content_base=content_base,
            session=session,
            input_text=input_text,
            hooks_state=hooks_state,
        )
