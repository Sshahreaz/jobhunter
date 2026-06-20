import os
import math
import requests

BASE_URL = "https://jsearch.p.rapidapi.com/search"
RESULTS_PER_PAGE = 10
MAX_RESULTS = 50


class JSearchClient:
    """Client for the JSearch API (LinkedIn + Indeed via RapidAPI)."""

    def __init__(self):
        self.api_key = os.environ["JSEARCH_API_KEY"]
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        }

    def search(self, keyword: str, location: str) -> list[dict]:
        """Search jobs and return up to 50 results across paginated responses."""
        jobs = []
        pages_needed = math.ceil(MAX_RESULTS / RESULTS_PER_PAGE)

        for page in range(1, pages_needed + 1):
            batch, total_pages = self._fetch_page(keyword, location, page)
            jobs.extend(batch)
            if len(batch) < RESULTS_PER_PAGE:
                break
            if page >= total_pages:
                break
            if len(jobs) >= MAX_RESULTS:
                break

        return jobs[:MAX_RESULTS]

    def _fetch_page(self, keyword: str, location: str, page: int) -> tuple[list[dict], int]:
        params = {
            "query": f"{keyword} in {location}",
            "page": page,
            "num_pages": 1,
        }
        response = requests.get(BASE_URL, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        jobs = [self._normalize(job) for job in data.get("data", [])]
        # JSearch doesn't expose total page count; infer from result count
        total_pages = math.ceil(MAX_RESULTS / RESULTS_PER_PAGE)
        return jobs, total_pages

    def _normalize(self, raw: dict) -> dict:
        city = raw.get("job_city", "")
        state = raw.get("job_state", "")
        country = raw.get("job_country", "")
        location_parts = [p for p in (city, state, country) if p]

        return {
            "id": raw.get("job_id", ""),
            "title": raw.get("job_title", ""),
            "company": raw.get("employer_name", ""),
            "location": ", ".join(location_parts),
            "description": raw.get("job_description", ""),
            "apply_url": raw.get("job_apply_link", ""),
            "posted_date": raw.get("job_posted_at_datetime_utc", ""),
            "source": raw.get("job_publisher", ""),
        }
