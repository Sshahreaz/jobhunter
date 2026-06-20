import sqlite3
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
import streamlit as st

from agents.fetcher import JobFetcher
from storage.db import Database

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="JobHunter — Daily Job Search Agent",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state bootstrap
# ---------------------------------------------------------------------------


def _init_state() -> None:
    if "db" not in st.session_state:
        st.session_state.db = Database()
    if "jobs" not in st.session_state:
        st.session_state.jobs = []
    if "statuses" not in st.session_state:
        st.session_state.statuses = {}
    if "initialized" not in st.session_state:
        _load_from_db()
        st.session_state.initialized = True


def _load_from_db() -> None:
    db: Database = st.session_state.db
    st.session_state.jobs = db.get_jobs()
    try:
        conn = sqlite3.connect(db.path)
        rows = conn.execute("SELECT job_id, status FROM application_status").fetchall()
        conn.close()
        st.session_state.statuses = {r[0]: r[1] for r in rows}
    except Exception:
        st.session_state.statuses = {}


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _run_pipeline(keywords_raw: str, locations_raw: str, companies_raw: str) -> None:
    keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
    locations = [l.strip() for l in locations_raw.split(",") if l.strip()]
    companies = [c.strip() for c in companies_raw.split(",") if c.strip()]
    keyword = " ".join(keywords) if keywords else "data analyst"

    db: Database = st.session_state.db
    fetcher = JobFetcher()
    fetcher.load_seen_jobs(db)

    with st.spinner("Fetching jobs from Adzuna, USAJobs, Greenhouse, and JSearch…"):
        try:
            new_jobs = fetcher.fetch(keyword, locations, companies)
        except Exception as exc:
            st.error(f"Fetch failed: {exc}")
            return

    if not new_jobs:
        st.info("No new jobs found since last refresh.")
        return

    for job in new_jobs:
        db.save_job(job)

    st.session_state.jobs = db.get_jobs()
    st.toast(f"Done — {len(new_jobs)} new jobs fetched.", icon="✅")


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def _source_badge(source: str) -> str:
    if not source:
        return ""
    return (
        f' <span style="background:#e8f4f8;color:#1a7fa8;border-radius:4px;'
        f'padding:1px 7px;font-size:0.72rem;font-weight:600;'
        f'vertical-align:middle">{source}</span>'
    )


def _render_job_card(job: dict) -> None:
    with st.container(border=True):
        left, right = st.columns([5, 1])
        with left:
            title = job.get("title", "Unknown Title")
            badge = _source_badge(job.get("source", ""))
            st.markdown(f"**{title}**{badge}", unsafe_allow_html=True)
            st.caption(
                f"{job.get('company', '')} · {job.get('location', '')} · "
                f"{(job.get('posted_date') or '')[:10] or 'date unknown'}"
            )
        with right:
            if job.get("apply_url"):
                st.link_button("Apply →", job["apply_url"])


# ---------------------------------------------------------------------------
# App layout
# ---------------------------------------------------------------------------

_init_state()

st.title("JobHunter — Daily Job Search Agent")

# ── Sidebar ─────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Configuration")

    keywords_input = st.text_input("Keywords (comma-separated)", value="data analyst")
    locations_input = st.text_input(
        "Locations (comma-separated)",
        value="New York,New Jersey,Connecticut,Virginia",
    )
    companies_input = st.text_input(
        "Greenhouse Companies (comma-separated)",
        placeholder="stripe,figma,retool",
    )

    st.divider()

    if st.button("Refresh Jobs", type="primary", use_container_width=True):
        _run_pipeline(keywords_input, locations_input, companies_input)

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_today, tab_saved = st.tabs(["Today's Jobs", "Saved Jobs"])

# ── Tab 1: Today's Jobs ──────────────────────────────────────────────────────

with tab_today:
    today_prefix = date.today().isoformat()
    today_jobs = [
        j for j in st.session_state.jobs
        if (j.get("fetched_at") or "").startswith(today_prefix)
    ]

    if not today_jobs:
        st.info("No jobs fetched today yet. Click **Refresh Jobs** in the sidebar.")
    else:
        st.subheader(f"{len(today_jobs)} job{'s' if len(today_jobs) != 1 else ''} found today")
        for job in today_jobs:
            _render_job_card(job)

# ── Tab 2: Saved Jobs ────────────────────────────────────────────────────────

with tab_saved:
    all_jobs = st.session_state.jobs
    if not all_jobs:
        st.info("No jobs loaded yet. Click **Refresh Jobs** to fetch.")
    else:
        st.subheader("All Jobs")

        job_ids = [j["id"] for j in all_jobs]
        rows = [
            {
                "Applied": st.session_state.statuses.get(j["id"], "saved") == "applied",
                "Company": j.get("company", ""),
                "Title": j.get("title", ""),
                "Location": j.get("location", ""),
                "Posted": (j.get("posted_date") or "")[:10],
                "Apply": j.get("apply_url", ""),
            }
            for j in all_jobs
        ]

        df_before = pd.DataFrame(rows)

        edited_df = st.data_editor(
            df_before,
            column_config={
                "Applied": st.column_config.CheckboxColumn("Applied", help="Check when you've applied"),
                "Company": st.column_config.TextColumn("Company", disabled=True),
                "Title": st.column_config.TextColumn("Title", disabled=True),
                "Location": st.column_config.TextColumn("Location", disabled=True),
                "Posted": st.column_config.TextColumn("Posted", disabled=True),
                "Apply": st.column_config.LinkColumn("Apply", display_text="Apply →"),
            },
            hide_index=True,
            use_container_width=True,
        )

        db: Database = st.session_state.db
        for i, (before, after) in enumerate(
            zip(df_before.itertuples(index=False), edited_df.itertuples(index=False))
        ):
            if before.Applied != after.Applied:
                job_id = job_ids[i]
                new_status = "applied" if after.Applied else "saved"
                db.update_status(job_id, new_status)
                st.session_state.statuses[job_id] = new_status
