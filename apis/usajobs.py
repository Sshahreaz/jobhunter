import os
import requests

BASE_URL = "https://data.usajobs.gov/api/search"
MAX_RESULTS = 50


class USAJobsClient:
    """Client for the USAJobs.gov federal job search API."""

    def __init__(self):
        self.auth_key = os.environ["USAJOBS_AUTH_KEY"]
        self.headers = {
            "Authorization-Key": self.auth_key,
            "User-Agent": "jobhunter-app",
        }

    def search(self, keyword: str, location_codes: list[str]) -> list[dict]:
        """Search across all provided location names and return up to 50 deduplicated results."""
        seen_ids = set()
        jobs = []

        for location in location_codes:
            if len(jobs) >= MAX_RESULTS:
                break
            batch = self._fetch(keyword, location)
            for job in batch:
                if job["id"] not in seen_ids:
                    seen_ids.add(job["id"])
                    jobs.append(job)
                    if len(jobs) >= MAX_RESULTS:
                        break

        return jobs

    def _fetch(self, keyword: str, location: str) -> list[dict]:
        params = {
            "Keyword": keyword,
            "LocationName": location,
            "ResultsPerPage": MAX_RESULTS,
        }
        response = requests.get(BASE_URL, headers=self.headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        items = data.get("SearchResult", {}).get("SearchResultItems", [])
        return [self._normalize(item) for item in items]

    def _normalize(self, item: dict) -> dict:
        matched = item.get("MatchedObjectDescriptor", {})
        position_location = matched.get("PositionLocation", [])
        remuneration = matched.get("PositionRemuneration", [])

        location_str = self._extract_location(position_location)
        salary_min, salary_max = self._extract_salary(remuneration)

        return {
            "id": matched.get("PositionID", ""),
            "title": matched.get("PositionTitle", ""),
            "company": matched.get("OrganizationName", ""),
            "location": location_str,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": matched.get("UserArea", {}).get("Details", {}).get("JobSummary", ""),
            "apply_url": matched.get("ApplyURI", [""])[0] if matched.get("ApplyURI") else "",
            "posted_date": matched.get("PublicationStartDate", ""),
        }

    def _extract_location(self, position_location: list) -> str:
        if not position_location:
            return ""
        parts = []
        for loc in position_location:
            city = loc.get("CityName", "")
            state = loc.get("CountrySubDivisionCode", "")
            if city and state:
                parts.append(f"{city}, {state}")
            elif city:
                parts.append(city)
        return "; ".join(parts) if parts else ""

    def _extract_salary(self, remuneration: list) -> tuple[float | None, float | None]:
        if not remuneration:
            return None, None
        pay = remuneration[0]
        try:
            salary_min = float(pay["MinimumRange"]) if pay.get("MinimumRange") else None
            salary_max = float(pay["MaximumRange"]) if pay.get("MaximumRange") else None
        except (ValueError, TypeError):
            salary_min, salary_max = None, None
        return salary_min, salary_max
