"""Greenhouse public job board adapter.

Greenhouse exposes a per-company JSON API at:
  GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true

No auth required. Rate-limit: be polite — max 5 concurrent requests.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import UTC, datetime

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from job_agent.domain.models.job import Job
from job_agent.infrastructure.sources._company_lists import GREENHOUSE_SLUGS

log = structlog.get_logger()

_BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
_TIMEOUT = httpx.Timeout(15.0)
_MAX_CONCURRENT = 5
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _TAG_RE.sub(" ", html).strip()


def _content_hash(company: str, title: str, location: str, description: str) -> str:
    raw = f"{company}:{title}:{location}:{description[:200]}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()


def _is_remote(location: str) -> bool:
    return "remote" in location.lower()


def _keyword_match(title: str, query: str, description: str = "") -> bool:
    """Match if ANY query word appears in the title, or ALL appear across title+description."""
    words = query.lower().split()
    title_lower = title.lower()
    # Fast path: any word in the title is a match
    if any(w in title_lower for w in words):
        return True
    # Fallback: all words present across title + description
    combined = title_lower + " " + description.lower()
    return all(w in combined for w in words)


class GreenhouseSource:
    """Discovers jobs from Greenhouse-hosted company boards."""

    source_name = "greenhouse"

    def __init__(self, slugs: list[str] | None = None) -> None:
        self._slugs = slugs or GREENHOUSE_SLUGS

    async def discover(self, user_id: uuid.UUID, query: str, remote: bool = False) -> list[Job]:
        sem = asyncio.Semaphore(_MAX_CONCURRENT)
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            tasks = [
                self._fetch_company(client, sem, user_id, slug, query, remote)
                for slug in self._slugs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        jobs: list[Job] = []
        for slug, result in zip(self._slugs, results, strict=False):
            if isinstance(result, BaseException):
                log.debug("greenhouse.skip", slug=slug, error=str(result))
            else:
                jobs.extend(result)

        log.info("greenhouse.discover.done", query=query, remote=remote, total=len(jobs))
        return jobs

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def _fetch_company(
        self,
        client: httpx.AsyncClient,
        sem: asyncio.Semaphore,
        user_id: uuid.UUID,
        slug: str,
        query: str,
        remote: bool,
    ) -> list[Job]:
        async with sem:
            url = _BASE_URL.format(slug=slug) + "?content=true"
            resp = await client.get(url)
            if resp.status_code in (404, 422):
                return []
            resp.raise_for_status()

        payload = resp.json()
        raw_jobs = payload.get("jobs", [])
        jobs: list[Job] = []

        for item in raw_jobs:
            title: str = item.get("title", "")
            description = _strip_html(item.get("content", ""))
            if not _keyword_match(title, query, description):
                continue

            location: str = item.get("location", {}).get("name", "")
            is_remote = _is_remote(location)
            if remote and not is_remote:
                continue
            company = slug.replace("-", " ").title()
            external_id = str(item.get("id", ""))
            url_field: str = item.get("absolute_url", "")

            jobs.append(
                Job(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    source="greenhouse",
                    external_id=external_id,
                    content_hash=_content_hash(company, title, location, description),
                    title=title,
                    company=company,
                    location=location,
                    remote=is_remote,
                    url=url_field,
                    description=description,
                    ats_type="greenhouse",
                    discovered_at=datetime.now(UTC),
                )
            )

        return jobs
