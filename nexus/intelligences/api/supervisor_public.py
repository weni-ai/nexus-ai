import logging
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import pendulum
import requests
import sentry_sdk
from django.conf import settings
from django.db.models import Count
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
)
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from nexus.inline_agents.models import InlineAgentMessage
from nexus.intelligences.models import Conversation
from nexus.projects.api.project_api_token_auth import (
    ProjectApiKeyAuthentication,
    ProjectApiKeyPermission,
)
from router.services.message_service import MessageService

logger = logging.getLogger(__name__)

# Resolution choices matching nexus-conversations model (for status_summary keys)
NEXUS_CONVERSATIONS_RESOLUTION_KEYS = ("0", "1", "2", "3", "4")


class MessageSerializer(serializers.Serializer):
    text = serializers.CharField()
    source = serializers.CharField()
    created_at = serializers.CharField()


class SupervisorPublicConversationItemSerializer(serializers.Serializer):
    conversation_uuid = serializers.UUIDField()
    start_date = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    ended_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    topic = serializers.CharField(allow_null=True, allow_blank=True)
    channel_uuid = serializers.UUIDField(allow_null=True)
    contact_urn = serializers.CharField(allow_null=True, allow_blank=True)
    messages = MessageSerializer(many=True)


class SupervisorPublicConversationListSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    status_summary = serializers.DictField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = SupervisorPublicConversationItemSerializer(many=True)


class SupervisorPublicConversationsView(APIView):
    authentication_classes = [ProjectApiKeyAuthentication]
    permission_classes = [ProjectApiKeyPermission]

    def _apply_filters(self, qs, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")

        start_dt = None
        end_dt = None

        try:
            if start:
                start_dt = pendulum.parse(start).start_of("day")
            if end:
                end_dt = pendulum.parse(end).end_of("day")
        except pendulum.parsing.exceptions.ParserError:
            raise ValidationError({"date": "Invalid date format. Please use ISO 8601."}) from None

        if start_dt and end_dt:
            qs = qs.filter(start_date__gte=start_dt, start_date__lte=end_dt)
        elif start_dt:
            qs = qs.filter(start_date__gte=start_dt)
        elif end_dt:
            qs = qs.filter(start_date__lte=end_dt)

        return qs, start_dt, end_dt

    def _to_utc_iso(self, val):
        try:
            return pendulum.instance(val).in_timezone("UTC").format("YYYY-MM-DDTHH:mm:ss")
        except Exception:
            return str(val)

    def _get_messages(self, conv, project_uuid, start_dt, end_dt, message_service):
        messages = []
        fetch_start = start_dt or conv.start_date
        fetch_end = end_dt or conv.end_date

        can_fetch = bool(conv.contact_urn and fetch_start and fetch_end)
        if not can_fetch:
            return messages

        try:
            start_iso = self._to_utc_iso(fetch_start)
            end_iso = self._to_utc_iso(fetch_end)

            messages = message_service.get_messages_for_conversation(
                project_uuid=str(project_uuid),
                contact_urn=conv.contact_urn,
                channel_uuid=str(conv.channel_uuid),
                start_date=start_iso,
                end_date=end_iso,
                resolution_status=None,
            )
            if not messages:
                start_utc = pendulum.instance(fetch_start).in_timezone("UTC")
                end_utc = pendulum.instance(fetch_end).in_timezone("UTC")

                inline_qs = InlineAgentMessage.objects.filter(
                    project__uuid=str(project_uuid),
                    contact_urn=conv.contact_urn,
                    created_at__range=(start_utc, end_utc),
                ).order_by("created_at")

                if inline_qs.exists():
                    messages = [
                        {
                            "text": message.text,
                            "source": "user" if message.source_type == "user" else "agent",
                            "created_at": message.created_at.isoformat(),
                        }
                        for message in inline_qs
                    ]
        except Exception as e:
            logger.warning(
                f"Error fetching messages for conversation {conv.uuid}: {str(e)}",
                extra={
                    "project_uuid": project_uuid,
                    "conversation_uuid": str(conv.uuid),
                    "contact_urn": conv.contact_urn,
                    "channel_uuid": str(conv.channel_uuid) if conv.channel_uuid else None,
                },
            )
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.set_tag("conversation_uuid", str(conv.uuid))
            sentry_sdk.capture_exception(e)
        return messages

    @extend_schema(
        summary="List Conversations",
        description="Retrieve a list of conversations for a project with optional filtering by date range and status.",
        parameters=[
            OpenApiParameter(
                name="start",
                description="Start date (ISO 8601)",
                required=False,
                type=OpenApiTypes.DATE,
            ),
            OpenApiParameter(
                name="end",
                description="End date (ISO 8601)",
                required=False,
                type=OpenApiTypes.DATE,
            ),
            OpenApiParameter(
                name="status",
                description="Filter by resolution status",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="page",
                description="Page number",
                required=False,
                type=OpenApiTypes.INT,
            ),
            OpenApiParameter(
                name="page_size",
                description="Number of items per page",
                required=False,
                type=OpenApiTypes.INT,
            ),
        ],
        responses={200: SupervisorPublicConversationListSerializer},
    )
    def get(self, request, project_uuid):
        try:
            qs = Conversation.objects.filter(project__uuid=project_uuid).order_by("-created_at")
            qs, start_dt, end_dt = self._apply_filters(qs, request)

            # Calculate summary stats before pagination and status filtering
            status_summary = {str(key): 0 for key, _ in Conversation.RESOLUTION_CHOICES}
            status_counts = qs.values("resolution").annotate(count=Count("resolution")).order_by()
            for item in status_counts:
                res = str(item["resolution"])
                if res in status_summary:
                    status_summary[res] += item["count"]
                else:
                    # If resolution is None or not in choices, we map it to "3" (Unclassified)
                    status_summary["3"] += item["count"]

            status_param = request.query_params.get("status")
            if status_param:
                valid_statuses = [str(k) for k, _ in Conversation.RESOLUTION_CHOICES]
                if status_param not in valid_statuses:
                    raise ValidationError({"status": f"Invalid status. Choices are: {', '.join(valid_statuses)}"})
                qs = qs.filter(resolution=status_param)

            # Calculate summary stats before pagination
            total_count = qs.count()
            page_size = int(request.query_params.get("page_size", 50))
            if page_size < 1:
                page_size = 50
            total_pages = math.ceil(total_count / page_size) if page_size > 0 else 1

            page = int(request.query_params.get("page", 1))
            if page < 1:
                page = 1
            offset = (page - 1) * page_size
            results = []

            message_service = MessageService()
            for conv in qs[offset : offset + page_size]:
                messages = self._get_messages(conv, project_uuid, start_dt, end_dt, message_service)
                results.append(
                    {
                        "conversation_uuid": str(conv.uuid),
                        "start_date": conv.start_date.isoformat() if conv.start_date else None,
                        "created_at": conv.created_at.isoformat(),
                        "ended_at": conv.end_date.isoformat() if conv.end_date else None,
                        "status": conv.get_resolution_display(),
                        "topic": conv.get_topic() if conv.topic else None,
                        "channel_uuid": str(conv.channel_uuid) if conv.channel_uuid else None,
                        "contact_urn": conv.contact_urn,
                        "messages": messages,
                    }
                )

            return Response(
                {
                    "count": total_count,
                    "page": page,
                    "total_pages": total_pages,
                    "page_size": page_size,
                    "status_summary": status_summary,
                    "results": results,
                }
            )
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SupervisorPublicConversationListV2Serializer(serializers.Serializer):
    """V2 response includes cursor-based pagination (next/previous) from nexus-conversations."""

    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    status_summary = serializers.DictField()
    page_size = serializers.IntegerField()
    results = SupervisorPublicConversationItemSerializer(many=True)
    next = serializers.URLField(allow_null=True, required=False)
    previous = serializers.URLField(allow_null=True, required=False)


class SupervisorPublicConversationsViewV2(APIView):
    """
    V2 of SupervisorPublicConversationsView that fetches data from nexus-conversations
    instead of nexus-ai's local database.
    """

    authentication_classes = [ProjectApiKeyAuthentication]
    permission_classes = [ProjectApiKeyPermission]

    def _get_headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": f"Bearer {settings.CONVERSATIONS_TOKEN}",
        }

    def _call_conversations_api(self, project_uuid, params):
        """Call nexus-conversations list API."""
        endpoint = f"/api/v1/projects/{project_uuid}/conversations/"
        url = settings.CONVERSATIONS_REST_ENDPOINT.rstrip("/") + endpoint
        response = requests.get(url, headers=self._get_headers(), params=params, timeout=45)
        response.raise_for_status()
        return response.json()

    def _normalize_message(self, m):
        """Normalize one message to MessageSerializer format."""
        return {
            "text": m.get("text", ""),
            "source": m.get("source", ""),
            "created_at": m.get("created_at", ""),
        }

    def _append_page_messages(self, out, page_messages):
        """Append normalized messages from a page to out. Returns next_url or None."""
        if isinstance(page_messages, dict) and "results" in page_messages:
            for m in page_messages.get("results") or []:
                out.append(self._normalize_message(m))
            return page_messages.get("next")
        if isinstance(page_messages, list):
            for m in page_messages:
                out.append(self._normalize_message(m))
        return None

    def _fetch_conversation_messages(self, project_uuid, conversation_uuid):
        """
        Fetch messages for a single conversation from nexus-conversations detail endpoint.
        For 'In Progress' conversations, nexus-conversations fetches from DynamoDB.
        Normalizes on the fly into a single list to avoid holding raw + normalized in memory.
        """
        try:
            endpoint = f"/api/v1/projects/{project_uuid}/conversations/{conversation_uuid}/"
            url = settings.CONVERSATIONS_REST_ENDPOINT.rstrip("/") + endpoint
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning(
                "Failed to fetch messages for conversation %s: %s",
                conversation_uuid,
                str(e),
                extra={"project_uuid": project_uuid, "conversation_uuid": str(conversation_uuid)},
            )
            return []

        messages_data = data.get("messages")
        if not messages_data:
            return []

        out = []
        if isinstance(messages_data, dict) and "results" in messages_data:
            next_url = self._append_page_messages(out, messages_data)
            while next_url:
                try:
                    page_url = (
                        next_url
                        if next_url.startswith("http://") or next_url.startswith("https://")
                        else settings.CONVERSATIONS_REST_ENDPOINT.rstrip("/")
                        + (next_url if next_url.startswith("/") else f"/{next_url}")
                    )
                    page_response = requests.get(
                        page_url,
                        headers=self._get_headers(),
                        timeout=30,
                    )
                    page_response.raise_for_status()
                    page_data = page_response.json() or {}
                    page_messages = page_data.get("messages") or page_data
                    next_url = self._append_page_messages(out, page_messages)
                except Exception as e:
                    logger.warning(
                        "Failed to fetch paginated messages for conversation %s: %s",
                        conversation_uuid,
                        str(e),
                        extra={"project_uuid": project_uuid, "conversation_uuid": str(conversation_uuid)},
                    )
                    break
        elif isinstance(messages_data, list):
            self._append_page_messages(out, messages_data)
        return out

    def _transform_conversation(self, item, messages=None):
        """Transform nexus-conversations item to SupervisorPublicConversationItem format."""
        classification = item.get("classification") or {}
        topic = classification.get("topic") if isinstance(classification, dict) else None
        messages = messages if messages is not None else (item.get("messages") or [])

        return {
            "conversation_uuid": str(item.get("uuid", "")),
            "start_date": item.get("start_date"),
            "created_at": item.get("created_at"),
            "ended_at": item.get("end_date"),
            "status": item.get("status", ""),
            "topic": topic or "",
            "channel_uuid": str(item["channel_uuid"]) if item.get("channel_uuid") else None,
            "contact_urn": item.get("contact_urn") or "",
            "messages": messages,
        }

    def _fetch_messages_for_conversations(self, project_uuid, results_data, request):
        """Fetch messages for all conversations in parallel (from DynamoDB for In Progress)."""
        include_messages = request.query_params.get("include_messages", "true").lower() in (
            "true",
            "1",
            "yes",
        )
        if not include_messages or not results_data:
            return {}

        messages_by_uuid = {}
        max_workers = min(10, len(results_data))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_uuid = {
                executor.submit(
                    self._fetch_conversation_messages,
                    project_uuid,
                    str(item.get("uuid")),
                ): str(item.get("uuid"))
                for item in results_data
            }
            for future in as_completed(future_to_uuid):
                conv_uuid = future_to_uuid[future]
                try:
                    messages_by_uuid[conv_uuid] = future.result()
                except Exception as e:
                    logger.warning("Error fetching messages for %s: %s", conv_uuid, e)
                    messages_by_uuid[conv_uuid] = []
        return messages_by_uuid

    def _build_list_response(
        self,
        results,
        count,
        total_pages,
        status_summary,
        page_size,
        next_url,
        previous_url,
        request,
    ):
        """Build the paginated list response payload."""
        return {
            "count": count,
            "total_pages": total_pages,
            "status_summary": status_summary,
            "page_size": page_size,
            "results": results,
            "next": self._rewrite_pagination_url(next_url, request) if next_url else None,
            "previous": self._rewrite_pagination_url(previous_url, request) if previous_url else None,
        }

    def _parse_request_params(self, request):
        """Parse and validate query params for nexus-conversations API. Raises ValidationError on invalid input."""
        params = {}
        if request.query_params.get("start"):
            params["start_date"] = request.query_params.get("start")
        if request.query_params.get("end"):
            params["end_date"] = request.query_params.get("end")
        status_param = request.query_params.get("status")
        if status_param is not None:
            if status_param not in NEXUS_CONVERSATIONS_RESOLUTION_KEYS:
                raise ValidationError({"status": f"Invalid status '{status_param}'"})
            params["status"] = status_param
        if request.query_params.get("cursor"):
            params["cursor"] = request.query_params.get("cursor")
        try:
            page_size = int(request.query_params.get("page_size", 50))
            if page_size < 1:
                raise ValueError("page_size must be positive")
        except (ValueError, TypeError):
            raise ValidationError({"page_size": "Invalid page_size, must be a positive integer"}) from None
        params["page_size"] = page_size
        return params, page_size

    def _rewrite_pagination_url(self, url, request):
        """Rewrite pagination URL to point to nexus-ai v2 endpoint."""
        if not url:
            return None
        try:
            parsed_upstream = urlparse(url)
            query_params = parse_qs(parsed_upstream.query, keep_blank_values=True)
            if not query_params:
                return request.build_absolute_uri(request.path)

            base_url = request.build_absolute_uri(request.path)
            query_string = urlencode(query_params, doseq=True)
            parsed_base = urlparse(base_url)
            return urlunparse(("https", parsed_base.netloc, parsed_base.path, "", query_string, ""))
        except Exception as e:
            logger.warning("Error rewriting pagination URL: %s", e, exc_info=True)
            return None

    @extend_schema(
        summary="List Conversations (V2)",
        description=(
            "Retrieve a list of conversations from nexus-conversations. Uses cursor-based pagination. "
            "By default includes messages for each conversation; for 'In Progress' conversations "
            "messages are fetched from DynamoDB via nexus-conversations detail API."
        ),
        parameters=[
            OpenApiParameter(
                name="start",
                description="Start date (ISO 8601). Mapped to start_date filter on nexus-conversations.",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="end",
                description="End date (ISO 8601). Mapped to end_date filter on nexus-conversations.",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="status",
                description=(
                    "Filter by resolution status (0=Resolved, 1=Unresolved, 2=In Progress, "
                    "3=Unclassified, 4=Has Chat Room)"
                ),
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="cursor",
                description="Cursor for pagination (from previous response next/previous)",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(
                name="page_size",
                description="Number of items per page",
                required=False,
                type=OpenApiTypes.INT,
            ),
            OpenApiParameter(
                name="include_messages",
                description=(
                    "Include messages for each conversation. For 'In Progress' conversations, "
                    "messages are fetched from DynamoDB via nexus-conversations. Default: true."
                ),
                required=False,
                type=OpenApiTypes.BOOL,
            ),
        ],
        responses={200: SupervisorPublicConversationListV2Serializer},
    )
    def get(self, request, project_uuid):
        try:
            params, page_size = self._parse_request_params(request)
            data = self._call_conversations_api(project_uuid, params)
            results_data = data.get("results", [])
            next_url = data.get("next")
            previous_url = data.get("previous")

            messages_by_uuid = self._fetch_messages_for_conversations(project_uuid, results_data, request)
            results = [
                self._transform_conversation(
                    item,
                    messages=messages_by_uuid.get(str(item.get("uuid")), []),
                )
                for item in results_data
            ]

            # status_summary: count by resolution from current page (cursor API doesn't provide totals).
            status_summary = {k: 0 for k in NEXUS_CONVERSATIONS_RESOLUTION_KEYS}
            for item in results_data:
                res = str(item.get("resolution") or "")
                if res in status_summary:
                    status_summary[res] += 1

            # count/total_pages: cursor pagination does not provide total count.
            # Use len(results) as approximate; total_pages=1 when no next, else 2+ (unknown)
            count = len(results)
            has_next = bool(next_url)
            total_pages = 2 if has_next else 1

            return Response(
                self._build_list_response(
                    results=results,
                    count=count,
                    total_pages=total_pages,
                    status_summary=status_summary,
                    page_size=page_size,
                    next_url=next_url,
                    previous_url=previous_url,
                    request=request,
                ),
                status=status.HTTP_200_OK,
            )
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response else 500
            error_detail = str(e)
            if hasattr(e, "response") and e.response is not None and hasattr(e.response, "json"):
                try:
                    err_body = e.response.json()
                    error_detail = err_body.get("detail", err_body.get("error", error_detail))
                except Exception:
                    pass
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return Response({"error": error_detail}, status=status_code)
        except requests.exceptions.RequestException as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            return Response({"error": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception as e:
            sentry_sdk.set_tag("project_uuid", project_uuid)
            sentry_sdk.capture_exception(e)
            logger.exception("Error fetching conversations from nexus-conversations for project %s", project_uuid)
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
