import re
from typing import Any, Optional

from django.db.models import Q

from nexus.projects.models import Project, SpecializedKnowledgeEntry

_TOKEN = re.compile(r"\w+", re.UNICODE)
_CANDIDATE_LIMIT = 200


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text or "")}


def _score(query: str, content: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    overlap = query_tokens & _tokens(content)
    return len(overlap) / len(query_tokens)


def _metadata(entry: SpecializedKnowledgeEntry) -> dict[str, Any]:
    return {
        "room_uuid": entry.room_uuid or None,
        "project": str(entry.project_id),
        "origin": entry.origin,
        "demand": entry.demand or None,
        "category": entry.category or None,
        "relevance": entry.relevance or None,
        "tags": entry.tags or None,
    }


def to_retrieve_item(entry: SpecializedKnowledgeEntry, score: float) -> dict[str, Any]:
    return {
        "content": entry.content,
        "score": round(score, 4),
        "source": entry.source,
        "metadata": _metadata(entry),
    }


def create_specialized_knowledge_entry(
    project: Project,
    *,
    content: str,
    source: str = "",
    metadata: Optional[dict] = None,
) -> SpecializedKnowledgeEntry:
    metadata = metadata or {}
    entry = SpecializedKnowledgeEntry(
        project=project,
        content=content,
        source=source or "",
        room_uuid=str(metadata.get("room_uuid") or ""),
        origin=metadata.get("origin") or "agent",
        demand=metadata.get("demand") or "",
        category=metadata.get("category") or "",
        relevance=metadata.get("relevance") or "",
        tags=[] if metadata.get("tags") is None else metadata.get("tags"),
    )
    entry.full_clean()
    entry.save()
    return entry


def retrieve_specialized_knowledge(
    *,
    project_uuid: str,
    query: str,
    top_k: int = 5,
    filters: Optional[dict] = None,
) -> list[dict]:
    """Return specialized KB passages. Errors propagate; callers decide the fallback.

    ``top_k`` must be an integer from 1 to 20. ``None`` uses the default of 5.
    """
    if not project_uuid or not (query or "").strip():
        return []

    if top_k is None:
        top_k = 5
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
        raise ValueError(f"top_k must be between 1 and 20, got {top_k}")
    filters = filters or {}
    queryset = SpecializedKnowledgeEntry.objects.filter(project_id=project_uuid)
    room_uuid = filters.get("room_uuid")
    category = filters.get("category")
    relevance = filters.get("relevance")
    if room_uuid:
        queryset = queryset.filter(Q(room_uuid="") | Q(room_uuid=str(room_uuid)))
    if category:
        queryset = queryset.filter(category=category)
    if relevance:
        queryset = queryset.filter(relevance=relevance)

    requested_tags = filters.get("tags") or []
    scored: list[tuple[float, SpecializedKnowledgeEntry]] = []
    for entry in queryset.order_by("-created_on")[:_CANDIDATE_LIMIT]:
        if requested_tags:
            entry_tags = set(entry.tags or [])
            if not set(requested_tags).issubset(entry_tags):
                continue
        score = _score(query, entry.content)
        if score <= 0:
            continue
        scored.append((score, entry))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [to_retrieve_item(entry, score) for score, entry in scored[:top_k]]
