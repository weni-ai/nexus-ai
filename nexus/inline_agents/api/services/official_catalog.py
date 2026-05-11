"""Official v1 catalog: pagination, cache, and novo retorno rows (plan Phase 3)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.cache import cache
from django.db.models import OuterRef, Q, Subquery

from nexus.inline_agents.api.serializers.catalog import build_official_group_row
from nexus.inline_agents.models import Agent, Version

CACHE_GEN_KEY = "official_catalog:cache_gen"
CACHE_KEY_PREFIX = "official_catalog:v1"
MAX_PAGE_SIZE = 20
CACHE_TTL_SECONDS = 120


def bump_official_catalog_cache_generation() -> None:
    """Increment generation so catalog cache keys miss after mutations."""
    try:
        cache.incr(CACHE_GEN_KEY)
    except ValueError:
        cache.set(CACHE_GEN_KEY, 1, timeout=None)


def _cache_generation() -> int:
    return int(cache.get(CACHE_GEN_KEY) or 0)


def _word_prefix_match_q(lookup: str, needle: str) -> Q:
    if not needle:
        return Q(pk__in=[])

    q = Q(**{f"{lookup}__istartswith": needle})
    for sep in (" ", "_", "(", "/", "["):
        q |= Q(**{f"{lookup}__icontains": f"{sep}{needle}"})
    return q


def _official_agents_v1_name_filter_q(name_filter: str) -> Q:
    needle = name_filter.strip()
    if not needle:
        return Q(pk__in=[])

    modal_title_set = Q(group__modal__agent_name__isnull=False) & ~Q(group__modal__agent_name__exact="")
    modal_title_unset = (
        Q(group__modal__isnull=True) | Q(group__modal__agent_name__isnull=True) | Q(group__modal__agent_name__exact="")
    )

    return Q(group__isnull=False) & (
        (modal_title_set & _word_prefix_match_q("group__modal__agent_name", needle))
        | (modal_title_unset & _word_prefix_match_q("group__name", needle))
    )


def build_official_catalog_queryset(
    *,
    project_uuid: str | None,
    name_filter: str,
    type_filter: str | None,
    group_filter: str | None,
    category_filter: str | None,
    system_filter: str | None,
) -> Any:
    latest_version_skills = Subquery(
        Version.objects.filter(agent=OuterRef("pk"))
        .order_by("-created_on")
        .values_list("display_skills", flat=True)[:1]
    )

    agents = (
        Agent.objects.filter(is_official=True, source_type=Agent.PLATFORM, group__isnull=False)
        .select_related("group", "group__modal")
        .prefetch_related("systems", "mcps", "mcps__system", "mcps__config_options", "mcps__credential_templates")
        .annotate(latest_display_skills=latest_version_skills)
    )

    if name_filter:
        agents = agents.filter(_official_agents_v1_name_filter_q(name_filter))
    if type_filter:
        agents = agents.filter(agent_type__slug__iexact=type_filter)
    if group_filter:
        agents = agents.filter(group__slug__iexact=group_filter)
    if category_filter:
        if category_filter.lower() == "others":
            agents = agents.filter(category__isnull=True)
        else:
            agents = agents.filter(category__slug__iexact=category_filter)
    if system_filter:
        agent_uuids = list(
            agents.filter(systems__slug__iexact=system_filter).distinct("uuid").values_list("uuid", flat=True)
        )
        agents = (
            Agent.objects.filter(
                uuid__in=agent_uuids, is_official=True, source_type=Agent.PLATFORM, group__isnull=False
            )
            .select_related("group", "group__modal")
            .prefetch_related("systems", "mcps", "mcps__system", "mcps__config_options", "mcps__credential_templates")
            .annotate(latest_display_skills=latest_version_skills)
        )

    return agents


def _ordered_distinct_group_slugs(agents_qs) -> list[str]:
    return list(dict.fromkeys(agents_qs.order_by("group__name", "group__slug").values_list("group__slug", flat=True)))


def _cache_key(params: dict[str, Any], generation: int) -> str:
    canonical = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical.encode()).hexdigest()[:48]
    return f"{CACHE_KEY_PREFIX}:g{generation}:{digest}"


def list_official_catalog_page(
    query_params: dict[str, Any],
    *,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    if page_size > MAX_PAGE_SIZE or page_size < 1:
        raise ValueError(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    if page < 1:
        raise ValueError("page must be >= 1")

    project_uuid = query_params.get("project_uuid")
    name_filter = (query_params.get("name") or "").strip()
    type_filter = query_params.get("type")
    group_filter = query_params.get("group")
    category_filter = query_params.get("category")
    system_filter = query_params.get("system")

    key_params: dict[str, Any] = {
        "project_uuid": project_uuid,
        "name": name_filter,
        "type": type_filter,
        "group": group_filter,
        "category": category_filter,
        "system": system_filter,
        "page": page,
        "page_size": page_size,
    }
    gen = _cache_generation()
    ck = _cache_key(key_params, gen)
    cached = cache.get(ck)
    if cached is not None:
        return cached

    agents_qs = build_official_catalog_queryset(
        project_uuid=project_uuid,
        name_filter=name_filter,
        type_filter=type_filter,
        group_filter=group_filter,
        category_filter=category_filter,
        system_filter=system_filter,
    )

    ordered_slugs = _ordered_distinct_group_slugs(agents_qs)
    total = len(ordered_slugs)
    start = (page - 1) * page_size
    page_slugs = ordered_slugs[start : start + page_size]

    results: list[dict[str, Any]] = []
    for slug in page_slugs:
        group_qs = (
            Agent.objects.filter(
                group__slug=slug,
                is_official=True,
                source_type=Agent.PLATFORM,
            )
            .select_related("group", "group__modal")
            .prefetch_related("systems", "mcps", "mcps__system", "mcps__config_options", "mcps__credential_templates")
        )
        group_agents = list(group_qs)
        if not group_agents:
            continue
        results.append(build_official_group_row(group_agents, slug, project_uuid))

    payload = {
        "count": total,
        "page": page,
        "page_size": page_size,
        "results": results,
    }
    cache.set(ck, payload, CACHE_TTL_SECONDS)
    return payload
