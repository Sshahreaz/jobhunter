# JobHunter — AI-Powered Daily Job Search Agent

JobHunter aggregates job listings from Adzuna, USAJobs, Greenhouse, and JSearch (LinkedIn + Indeed), then uses Claude to score each role against your resume, rewrite your resume bullets to match the job description, and generate a custom interview prep prompt — all presented in a Streamlit dashboard.

## What it does

- **Fetches jobs in parallel** from four sources: Adzuna (commercial), USAJobs.gov (federal), any Greenhouse company board, and JSearch (LinkedIn + Indeed via RapidAPI)
- **Deduplicates** across sources and skips listings seen in the past 30 days
- **Shows source badges** on each job card indicating where the listing came from (e.g. LinkedIn, Indeed)
- **Analyzes each job** with Claude (`claude-sonnet-4-6`) using tool use to extract structured results: match score, required skills, red flags, tailored resume bullets, and an interview prep prompt
- **Persists everything** to a local SQLite database (`jobhunter.db`)
- **Tracks your applications** with a status column (saved → applied → interview → rejected / offer)

## Quickstart

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
# Adzuna — https://developer.adzuna.com/
export ADZUNA_APP_ID=your_app_id
export ADZUNA_API_KEY=your_api_key

# USAJobs — https://developer.usajobs.gov/
export USAJOBS_AUTH_KEY=your_auth_key

# JSearch via RapidAPI — https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch
export JSEARCH_API_KEY=your_rapidapi_key

# Anthropic — https://console.anthropic.com/
export ANTHROPIC_API_KEY=your_api_key
```

On Windows (PowerShell):

```powershell
$env:ADZUNA_APP_ID     = "your_app_id"
$env:ADZUNA_API_KEY    = "your_api_key"
$env:USAJOBS_AUTH_KEY  = "your_auth_key"
$env:JSEARCH_API_KEY   = "your_rapidapi_key"
$env:ANTHROPIC_API_KEY = "your_api_key"
```

### 3. Run the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

## Usage

1. Paste or upload your resume in the sidebar
2. Set your keywords (e.g. `data analyst, SQL developer`), locations, and any Greenhouse company slugs (e.g. `stripe,figma,retool`)
3. Click **Refresh Jobs** — the app fetches and analyzes all new listings
4. Browse **Today's Jobs** sorted by match score
5. Open **Job Details** to read the full JD, tailored resume, and interview prep prompt
6. Track your applications in the **Application Tracker** tab

## Architecture

```
app.py                      Streamlit UI — sidebar, three tabs, session state cache
│
├── agents/
│   ├── fetcher.py          JobFetcher — parallel fetch, deduplication, date sorting
│   └── analyzer.py         JobAnalyzer — Claude tool_use for structured analysis
│
├── apis/
│   ├── adzuna.py           AdzunaClient — paginated REST search (up to 50 results)
│   ├── usajobs.py          USAJobsClient — USAJobs.gov API, multi-location support
│   ├── greenhouse.py       GreenhouseClient — public Greenhouse board API, keyword filter
│   └── jsearch.py          JSearchClient — LinkedIn + Indeed via RapidAPI JSearch (up to 50 results)
│
├── storage/
│   └── db.py               Database — SQLite via stdlib sqlite3, WAL mode, three tables:
│                               jobs, analyses, application_status
│
└── utils/
    └── parsers.py          Shared helpers (date parsing, HTML stripping)
```

## Database schema

| Table | Key columns |
|---|---|
| `jobs` | `id TEXT PK`, `company`, `title`, `location`, `description`, `apply_url`, `posted_date`, `fetched_at`, `source` |
| `analyses` | `job_id TEXT PK`, `match_score`, `extracted_requirements` (JSON), `salary_min/max`, `red_flags` (JSON), `tailored_resume`, `interview_prep_prompt` |
| `application_status` | `job_id TEXT PK`, `status` (saved/applied/interview/rejected/offer), `applied_date`, `notes` |

## Environment variables reference

| Variable | Source | Purpose |
|---|---|---|
| `ADZUNA_APP_ID` | developer.adzuna.com | Adzuna API application ID |
| `ADZUNA_API_KEY` | developer.adzuna.com | Adzuna API key |
| `USAJOBS_AUTH_KEY` | developer.usajobs.gov | USAJobs authorization key |
| `JSEARCH_API_KEY` | rapidapi.com → JSearch | RapidAPI key for LinkedIn + Indeed search |
| `ANTHROPIC_API_KEY` | console.anthropic.com | Claude API key |
