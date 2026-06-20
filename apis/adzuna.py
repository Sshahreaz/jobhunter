import os
import math
import requests

RESULTS_PER_PAGE = 10
MAX_RESULTS = 50


class AdzunaClient:
    """Client for the Adzuna job search API."""

    BASE_URL = "https://api.adzuna.com/v1/api/jobs"

    def __init__(self, country: str = "us"):
        self.app_id = os.environ["ADZUNA_APP_ID"]
        self.app_key = os.environ["ADZUNA_API_KEY"]
        self.country = country

    def search(self, keyword: str, location: str, full_time_only: bool = True) -> list[dict]:
        """Search jobs and return up to 50 results across paginated responses."""
        jobs = []
        pages_needed = math.ceil(MAX_RESULTS / RESULTS_PER_PAGE)

        for page in range(1, pages_needed + 1):
            batch = self._fetch_page(keyword, location, page, full_time_only)
            jobs.extend(batch)
            if len(batch) < RESULTS_PER_PAGE:
                break  # no more results
            if len(jobs) >= MAX_RESULTS:
                break

        return jobs[:MAX_RESULTS]

    def _fetch_page(self, keyword: str, location: str, page: int, full_time_only: bool) -> list[dict]:
        url = f"{self.BASE_URL}/{self.country}/search/{page}"
        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": keyword,
            "where": location,
            "results_per_page": RESULTS_PER_PAGE,
        }
        if full_time_only:
            params["full_time"] = 1

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        return [self._normalize(job) for job in data.get("results", [])]

    def _normalize(self, raw: dict) -> dict:
        company = raw.get("company", {})
        location = raw.get("location", {})
        salary_min = raw.get("salary_min")
        salary_max = raw.get("salary_max")

        return {
            "id": str(raw.get("id", "")),
            "title": raw.get("title", ""),
            "company": company.get("display_name", "") if isinstance(company, dict) else "",
            "location": location.get("display_name", "") if isinstance(location, dict) else "",
            "salary_min": float(salary_min) if salary_min is not None else None,
            "salary_max": float(salary_max) if salary_max is not None else None,
            "description": raw.get("description", ""),
            "apply_url": raw.get("redirect_url", ""),
            "posted_date": raw.get("created", ""),
        }
