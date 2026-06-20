import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from apis.adzuna import AdzunaClient
from apis.usajobs import USAJobsClient
from apis.greenhouse import GreenhouseClient
from apis.jsearch import JSearchClient

logger = logging.getLogger(__name__)

SEEN_WINDOW_DAYS = 30
# Sentinel for unparseable dates — sorts to the bottom
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

# ISO-8601 formats seen across the three APIs
_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%S%z",   # 2024-03-15T12:00:00+00:00  (Adzuna, USAJobs)
    "%Y-%m-%dT%H:%M:%SZ",    # 2024-03-15T12:00:00Z
    "%Y-%m-%dT%H:%M:%S.%f%z",# 2024-03-15T12:00:00.000+00:00
    "%Y-%m-%d",               # 2024-03-15
]


def _parse_date(value: str) -> datetime:
    if not value:
        return _EPOCH
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return _EPOCH


class JobFetcher:
    """Aggregates job listings from Adzuna, USAJobs, Greenhouse, and JSearch in parallel."""

    def __init__(self):
        self._seen_ids: set[str] = set()

    def load_seen_jobs(self, db) -> None:
        """Pre-populate seen IDs from jobs saved within the last 30 days."""
        self._seen_ids.update(db.get_seen_job_ids(days=SEEN_WINDOW_DAYS))

    def fetch(self, keyword: str, locations: list[str], company_names: list[str]) -> list[dict]:
        """Fetch from all sources in parallel, deduplicate, and sort newest-first."""
        raw_results = self._fetch_parallel(keyword, locations, company_names)
        unique = self._deduplicate(raw_results)
        unique.sort(key=lambda j: _parse_date(j.get("posted_date", "")), reverse=True)
        return unique

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_parallel(self, keyword: str, locations: list[str], company_names: list[str]) -> list[dict]:
        loc = locations[0] if locations else ""
        tasks = {
            "adzuna": lambda: AdzunaClient().search(keyword, loc),
            "usajobs": lambda: USAJobsClient().search(keyword, locations),
            "greenhouse": lambda: GreenhouseClient().search(keyword, company_names),
            "jsearch": lambda: JSearchClient().search(keyword, loc),
        }

        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(fn): name for name, fn in tasks.items()}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    jobs = future.result()
                    for job in jobs:
                        job.setdefault("source", source)
                    results.extend(jobs)
                except Exception as e:
                    logger.warning("Error fetching from %s: %s", source, e)

        return results

    def _deduplicate(self, jobs: list[dict]) -> list[dict]:
        seen_titles: set[tuple[str, str]] = set()
        unique: list[dict] = []

        for job in jobs:
            # Skip jobs we've already stored (by apply URL)
            apply_url = job.get("apply_url", "")
            if apply_url and apply_url in self._seen_ids:
                continue

            # Deduplicate within this batch by normalised (company, title)
            key = (
                job.get("company", "").strip().lower(),
                job.get("title", "").strip().lower(),
            )
            if key in seen_titles:
                continue

            seen_titles.add(key)
            if apply_url:
                self._seen_ids.add(apply_url)
            unique.append(job)

        return unique
