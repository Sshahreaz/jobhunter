import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "jobhunter.db"


class Database:
    """SQLite-backed persistence for jobs, analyses, and application tracking."""

    def __init__(self, path: str = str(DB_PATH)):
        self.path = path
        self.create_tables()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def create_tables(self) -> None:
        with self._connect() as conn:
            # Migrate existing DB — ADD COLUMN is a no-op if already present
            try:
                conn.execute("ALTER TABLE jobs ADD COLUMN source TEXT DEFAULT ''")
                conn.commit()
            except sqlite3.OperationalError:
                pass

            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id          TEXT PRIMARY KEY,
                    company     TEXT,
                    title       TEXT,
                    location    TEXT,
                    description TEXT,
                    apply_url   TEXT,
                    posted_date TEXT,
                    fetched_at  TEXT,
                    source      TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS analyses (
                    job_id                  TEXT PRIMARY KEY,
                    match_score             INTEGER,
                    extracted_requirements  TEXT,
                    salary_min              REAL,
                    salary_max              REAL,
                    red_flags               TEXT,
                    tailored_resume         TEXT,
                    interview_prep_prompt   TEXT
                );

                CREATE TABLE IF NOT EXISTS application_status (
                    job_id       TEXT PRIMARY KEY,
                    status       TEXT DEFAULT 'saved',
                    applied_date TEXT,
                    notes        TEXT
                );
            """)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------

    def save_job(self, job_dict: dict) -> None:
        """Insert a job; silently skip if the id already exists."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO jobs
                   (id, company, title, location, description, apply_url, posted_date, fetched_at, source)
                   VALUES (:id, :company, :title, :location, :description, :apply_url, :posted_date, :fetched_at, :source)""",
                {
                    "id": job_dict.get("id", ""),
                    "company": job_dict.get("company", ""),
                    "title": job_dict.get("title", ""),
                    "location": job_dict.get("location", ""),
                    "description": job_dict.get("description", ""),
                    "apply_url": job_dict.get("apply_url", ""),
                    "posted_date": job_dict.get("posted_date", ""),
                    "fetched_at": job_dict.get(
                        "fetched_at",
                        datetime.now(tz=timezone.utc).isoformat(),
                    ),
                    "source": job_dict.get("source", ""),
                },
            )

    def get_jobs(self, days: int = 0) -> list[dict]:
        """
        Return all jobs, optionally filtered to the last `days` days.
        days=0 (default) returns every job.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if days > 0:
                cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE fetched_at >= ? ORDER BY fetched_at DESC",
                    (cutoff,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY fetched_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def get_seen_job_ids(self, days: int = 30) -> set[str]:
        """
        Return the set of apply_urls for jobs fetched within the last `days` days.
        Used by JobFetcher to skip already-seen listings.
        """
        cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT apply_url FROM jobs WHERE fetched_at >= ? AND apply_url != ''",
                (cutoff,),
            ).fetchall()
            return {row[0] for row in rows}

    # ------------------------------------------------------------------
    # Analyses
    # ------------------------------------------------------------------

    def save_analysis(self, job_id: str, analysis_dict: dict) -> None:
        """Upsert a Claude analysis for a job."""
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO analyses
                   (job_id, match_score, extracted_requirements, salary_min, salary_max,
                    red_flags, tailored_resume, interview_prep_prompt)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id,
                    analysis_dict.get("match_score"),
                    json.dumps(analysis_dict.get("extracted_requirements", [])),
                    _salary_component(analysis_dict.get("salary_range"), 0),
                    _salary_component(analysis_dict.get("salary_range"), 1),
                    json.dumps(analysis_dict.get("red_flags", [])),
                    analysis_dict.get("tailored_resume", ""),
                    analysis_dict.get("interview_prep_prompt", ""),
                ),
            )

    def get_analysis(self, job_id: str) -> dict | None:
        """Return the analysis for a job, or None if not yet analysed."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM analyses WHERE job_id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            result = dict(row)
            result["extracted_requirements"] = json.loads(result["extracted_requirements"] or "[]")
            result["red_flags"] = json.loads(result["red_flags"] or "[]")
            result["salary_range"] = (result.pop("salary_min"), result.pop("salary_max"))
            return result

    # ------------------------------------------------------------------
    # Application status
    # ------------------------------------------------------------------

    def update_status(self, job_id: str, status: str, applied_date: str = "", notes: str = "") -> None:
        """Upsert the application status for a job."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO application_status (job_id, status, applied_date, notes)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(job_id) DO UPDATE SET
                       status       = excluded.status,
                       applied_date = COALESCE(NULLIF(excluded.applied_date, ''), applied_date),
                       notes        = COALESCE(NULLIF(excluded.notes, ''), notes)""",
                (job_id, status, applied_date, notes),
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _salary_component(salary_range, index: int) -> float | None:
    if salary_range is None:
        return None
    try:
        return salary_range[index]
    except (IndexError, TypeError):
        return None
