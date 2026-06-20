import re
import requests

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"
TAG_RE = re.compile(r"<[^>]+>")


class GreenhouseClient:
    """Client for public Greenhouse job board APIs."""

    def search(self, keyword: str, company_names: list[str]) -> list[dict]:
        """Search each company board and return all roles matching keyword."""
        results = []
        for company in company_names:
            try:
                jobs = self._fetch_company(company)
                results.extend(self._filter(jobs, keyword, company))
            except requests.HTTPError as e:
                # 404 means the board token doesn't exist; skip silently
                if e.response is not None and e.response.status_code == 404:
                    continue
                raise
        return results

    def _fetch_company(self, company: str) -> list[dict]:
        url = f"{BASE_URL}/{company}/jobs"
        response = requests.get(url, params={"content": "true"}, timeout=10)
        response.raise_for_status()
        return response.json().get("jobs", [])

    def _filter(self, jobs: list[dict], keyword: str, company: str) -> list[dict]:
        kw = keyword.lower()
        matched = []
        for job in jobs:
            title = job.get("title", "")
            content = job.get("content", "")
            if kw in title.lower() or kw in content.lower():
                matched.append(self._normalize(job, company))
        return matched

    def _normalize(self, raw: dict, company: str) -> dict:
        location = self._extract_location(raw.get("location", {}))
        salary_min, salary_max = self._extract_salary(raw)

        return {
            "id": str(raw.get("id", "")),
            "title": raw.get("title", ""),
            "company": company,
            "location": location,
            "salary_min": salary_min,
            "salary_max": salary_max,
            "description": self._strip_html(raw.get("content", "")),
            "apply_url": raw.get("absolute_url", ""),
            "posted_date": raw.get("updated_at", ""),
        }

    def _extract_location(self, location: dict | str) -> str:
        if isinstance(location, dict):
            return location.get("name", "")
        return str(location) if location else ""

    def _extract_salary(self, raw: dict) -> tuple[float | None, float | None]:
        # Greenhouse has no standard salary field; some boards embed it in
        # metadata or custom fields under `metadata`
        for field in raw.get("metadata", []):
            name = (field.get("name") or "").lower()
            if "salary" not in name and "compensation" not in name:
                continue
            value = field.get("value")
            if not value:
                continue
            # Value may be a range string like "120000 - 160000" or a plain number
            if isinstance(value, (int, float)):
                return float(value), float(value)
            parts = re.split(r"\s*[-–to]+\s*", str(value).replace(",", ""), maxsplit=1)
            try:
                nums = [float(p.strip("$£€ ")) for p in parts if p.strip("$£€ ")]
                if len(nums) == 2:
                    return nums[0], nums[1]
                if len(nums) == 1:
                    return nums[0], nums[0]
            except ValueError:
                pass
        return None, None

    def _strip_html(self, html: str) -> str:
        return TAG_RE.sub("", html).strip()
