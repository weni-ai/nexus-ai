"""Backfill Project.timezone from Connect internals API.

Copy this file onto the pod (app workdir) and run:

    python scripts/sync_project_timezones.py --start-page 1
    python scripts/sync_project_timezones.py --start-page N --after-uuid <uuid> --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import requests
import sentry_sdk
from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_PAGE_SIZE = 100
PAGE_FETCH_RETRIES = 3
PAGE_FETCH_RETRY_SLEEP_SECONDS = 1.0


class ProjectClient:
    def __init__(self):
        self.base_url = getattr(settings, "PROJECTS_API_BASE_URL", None) or settings.CONNECT_REST_ENDPOINT
        self.token = getattr(settings, "PROJECTS_API_TOKEN", None)
        self.page_size = getattr(settings, "PROJECTS_PAGE_SIZE", DEFAULT_PAGE_SIZE)
        self._auth = None
        if not self.token:
            from nexus.internals import InternalAuthentication

            self._auth = InternalAuthentication()

    def _get_headers(self) -> dict:
        if self._auth is not None:
            return self._auth.headers
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get_projects_paginated(self, page: int = 1, page_size: int = None) -> dict:
        if page_size is None:
            page_size = self.page_size

        url = f"{str(self.base_url).rstrip('/')}/v2/internals/connect/projects"
        params = {"page": page, "page_size": page_size, "ordering": "uuid"}

        try:
            if self._auth is not None:
                response = self._auth.make_request_with_retry(
                    "GET",
                    url,
                    params=params,
                    timeout=30,
                )
            else:
                response = requests.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=30,
                )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            sentry_sdk.capture_exception(e)
            logger.error(
                "[ProjectClient] Error fetching projects page=%s page_size=%s error=%s",
                page,
                page_size,
                e,
                exc_info=True,
            )
            raise


@dataclass
class PageSyncResult:
    updated: int = 0
    skipped_missing: int = 0
    skipped_unchanged: int = 0
    skipped_empty: int = 0
    last_uuid: str | None = None
    to_update: list[Any] = field(default_factory=list)


def _row_uuid(row: dict) -> str | None:
    raw = row.get("uuid")
    if raw in (None, ""):
        return None
    try:
        return str(UUID(str(raw)))
    except (ValueError, TypeError, AttributeError):
        return None


def _row_timezone(row: dict) -> str | None:
    value = row.get("timezone")
    if value in (None, ""):
        return None
    timezone = str(value).strip()
    return timezone or None


def sort_results_by_uuid(results: list[dict]) -> list[dict]:
    dated = []
    for row in results or []:
        uid = _row_uuid(row)
        if uid is None:
            continue
        dated.append((uid, row))
    dated.sort(key=lambda item: item[0])
    return [row for _, row in dated]


def apply_after_uuid(results: list[dict], after_uuid: str | None) -> list[dict]:
    if not after_uuid:
        return results
    try:
        threshold = str(UUID(str(after_uuid)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Invalid --after-uuid: {after_uuid}") from None
    return [row for row in results if (_row_uuid(row) or "") > threshold]


def prepare_page_updates(results: list[dict], local_by_uuid: dict[str, Any]) -> PageSyncResult:
    page = PageSyncResult()
    for row in results:
        uid = _row_uuid(row)
        if uid is None:
            page.skipped_empty += 1
            continue
        page.last_uuid = uid
        timezone = _row_timezone(row)
        if timezone is None:
            page.skipped_empty += 1
            continue
        project = local_by_uuid.get(uid)
        if project is None:
            page.skipped_missing += 1
            continue
        if project.timezone == timezone:
            page.skipped_unchanged += 1
            continue
        project.timezone = timezone
        page.to_update.append(project)
        page.updated += 1
    return page


def fetch_page_with_retry(client: ProjectClient, page: int, page_size: int) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, PAGE_FETCH_RETRIES + 1):
        try:
            payload = client.get_projects_paginated(page=page, page_size=page_size)
            if not isinstance(payload, dict):
                raise requests.RequestException(f"Unexpected payload type: {type(payload).__name__}")
            return payload
        except requests.RequestException as exc:
            last_error = exc
            logger.warning(
                "[sync_project_timezones] page fetch failed page=%s attempt=%s/%s error=%s",
                page,
                attempt,
                PAGE_FETCH_RETRIES,
                exc,
            )
            if attempt < PAGE_FETCH_RETRIES:
                time.sleep(PAGE_FETCH_RETRY_SLEEP_SECONDS)
    raise last_error


def sync_page(
    results: list[dict],
    *,
    project_model,
    dry_run: bool,
    after_uuid: str | None,
    batch_size: int,
) -> PageSyncResult:
    ordered = apply_after_uuid(sort_results_by_uuid(results), after_uuid)
    uuids = [uid for uid in (_row_uuid(row) for row in ordered) if uid]
    local_qs = project_model.objects.filter(uuid__in=uuids).only("uuid", "timezone")
    local_by_uuid = {str(project.uuid): project for project in local_qs}
    page = prepare_page_updates(ordered, local_by_uuid)
    if not dry_run and page.to_update:
        project_model.objects.bulk_update(page.to_update, ["timezone"], batch_size=batch_size)
    return page


def print_checkpoint(page: int, result: PageSyncResult, totals: dict[str, int], has_next: bool) -> None:
    last_uuid = result.last_uuid or "-"
    if has_next:
        resume = f"--start-page {page + 1}"
        if result.last_uuid:
            resume += f" (or --start-page {page} --after-uuid {result.last_uuid})"
    else:
        resume = "finished"
    print(
        "CHECKPOINT "
        f"page={page} last_uuid={last_uuid} done={not has_next} "
        f"updated={totals['updated']} missing={totals['missing']} "
        f"unchanged={totals['unchanged']} empty={totals['empty']} "
        f"resume: {resume}",
        flush=True,
    )


def run_sync(*, start_page: int, after_uuid: str | None, dry_run: bool, page_size: int | None) -> dict[str, int]:
    from nexus.projects.models import Project

    client = ProjectClient()
    if page_size is None:
        page_size = client.page_size

    totals = {"updated": 0, "missing": 0, "unchanged": 0, "empty": 0}
    page = start_page
    pending_after_uuid = after_uuid

    while True:
        payload = fetch_page_with_retry(client, page, page_size)
        results = payload.get("results") or []
        if not results:
            print(
                f"CHECKPOINT page={page} last_uuid=- done=true empty_page resume: --start-page {page}",
                flush=True,
            )
            break

        result = sync_page(
            results,
            project_model=Project,
            dry_run=dry_run,
            after_uuid=pending_after_uuid,
            batch_size=page_size,
        )
        pending_after_uuid = None
        totals["updated"] += result.updated
        totals["missing"] += result.skipped_missing
        totals["unchanged"] += result.skipped_unchanged
        totals["empty"] += result.skipped_empty

        has_next = bool(payload.get("next"))
        print_checkpoint(page, result, totals, has_next=has_next)
        if not has_next:
            break
        page += 1

    return totals


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill Project.timezone from Connect")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--after-uuid", default=None)
    parser.add_argument("--page-size", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def setup_django() -> None:
    root = Path(__file__).resolve().parent.parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus.settings")
    import django

    django.setup()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.start_page < 1:
        parser.error("--start-page must be >= 1")

    setup_django()
    totals = run_sync(
        start_page=args.start_page,
        after_uuid=args.after_uuid,
        dry_run=args.dry_run,
        page_size=args.page_size,
    )
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"DONE mode={mode} updated={totals['updated']} missing={totals['missing']} "
        f"unchanged={totals['unchanged']} empty={totals['empty']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
