# Evolve AI — Personal Growth OS (MVP)

A scoped-down, actually-shippable version of the full "Evolve AI" concept: one AI-driven
loop (journal → mood detection → habit tracking → weekly insight → growth score) instead
of a multi-service SaaS. Single FastAPI service, SQLite, zero external API keys, one
frontend file. Runs locally in under a minute and deploys to Railway/Render in one command.

## What it does

- **Journal**: write freeform text, mood is detected automatically (positive/neutral/negative
  + a -1 to +1 score) using a lexicon-based analyzer with negation handling — no LLM API key needed.
- **Habits**: add habits, check them off daily, streaks and 7-day completion rates are computed.
- **Growth score (0-100)**: transparent, explainable formula — 40% journal consistency,
  30% average mood, 30% habit completion, all over the trailing 7 days.
- **Weekly insight**: mood trend (improving/declining/steady vs. the prior week), best day,
  habit completion rate, and one rule-based coaching line grounded in your actual data
  (e.g. "your weakest habit this week is X — try scheduling it earlier").
- **Identity**: username-only, no password. Good enough for a live demo; swap in real auth
  (Clerk/Supabase) later if you want to productionize further.

## Real API integrations

Three genuine third-party APIs are wired in, each with a tested fallback so the app
never breaks without a key:

**LLM (mood analysis, weekly coaching, affirmations)** — `backend/ai_service.py`.
Supports either provider, picked automatically from whichever key is set:
```bash
export GROQ_API_KEY="gsk_..."        # groq.com — often the faster free-tier option
# or
export ANTHROPIC_API_KEY="sk-ant-..."
```
If neither is set (or a call fails), mood detection drops to the local lexicon
analyzer (`mood.py`), advice drops to a rule-based line, affirmations drop to a
small rotating set. Check `GET /health` for `{"ai_enabled", "provider", "model"}`.

**Weather** — `backend/weather.py`. Calls Open-Meteo, which needs **no API key**,
so judges can see the feature work with zero setup. Feeds into the weekly AI
advice when the frontend has location permission.

**Voice journal** — uses the browser's native Web Speech API (Chrome/Edge) to
transcribe speech into the journal textarea client-side. No server key needed;
this one's a browser capability rather than a hosted API, called out here for
transparency.

## Exports

- **`GET /insights/weekly/card`** — a shareable 1080×1080 PNG growth card (Pillow),
  rendered server-side. "Share card" button on the dashboard.
- **`GET /reports/weekly.pdf`** — a full one-page PDF report (reportlab): stats,
  AI coaching line, and recent journal entries. "PDF report" button on the dashboard.

## Run it locally

```bash
cd backend
pip install -r requirements.txt
export GROQ_API_KEY="gsk_..."   # optional — omit to run on the local fallback
uvicorn main:app --reload
```

Open **http://localhost:8000** — the FastAPI app serves the frontend directly, no separate
frontend server or build step needed.

## Deploy (Railway — recommended, free tier works)

1. Push this folder to a GitHub repo.
2. On [railway.app](https://railway.app): New Project → Deploy from GitHub repo.
3. Set the root directory to `backend/` (Railway auto-detects the `Procfile`).
4. Deploy. Railway assigns a public URL — that's your live link for interviews/resume.

By default it uses SQLite (a file on disk). SQLite works fine for a demo but resets if the
container restarts. To persist data properly, add a `DATABASE_URL` environment variable
pointing at a free Postgres instance (Railway's own Postgres plugin, or
[Neon](https://neon.tech)) — the code already reads `DATABASE_URL` and switches automatically,
no code changes required.

Also set `ANTHROPIC_API_KEY` as an environment variable in Railway's project settings so the
deployed version runs on the real API rather than the local fallback.

## Deploy (Render — alternative)

1. New Web Service → connect the repo, root directory `backend/`.
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn main:main --host 0.0.0.0 --port $PORT` *(Render sets `$PORT` for you)*

## Project structure

```
evolve-ai/
├── backend/
│   ├── main.py          # FastAPI app + all routes
│   ├── models.py        # SQLAlchemy models (User, JournalEntry, Habit, HabitLog)
│   ├── schemas.py        # Pydantic request/response schemas
│   ├── ai_service.py     # real Anthropic API calls (mood, advice, affirmations) + fallback
│   ├── mood.py           # lexicon-based sentiment fallback (no API key)
│   ├── database.py       # SQLite by default, Postgres via DATABASE_URL
│   ├── requirements.txt
│   └── Procfile           # for Railway/Render
├── static/
│   └── index.html         # single-file frontend (no build step)
└── README.md
```

## API reference

| Method | Path                     | Purpose                              |
|--------|--------------------------|---------------------------------------|
| POST   | `/journal`               | create a journal entry (mood auto-detected) |
| GET    | `/journal?username=`     | list an user's entries               |
| POST   | `/habit`                 | create a habit                        |
| GET    | `/habits?username=`      | list active habits with streak data   |
| POST   | `/habit/{id}/checkin`    | toggle today's completion             |
| DELETE | `/habit/{id}?username=`  | archive a habit                       |
| GET    | `/insights/weekly?username=` | weekly mood/habit/growth summary (optional `lat`,`lon` for weather) |
| GET    | `/insights/weekly/card?username=` | shareable weekly growth card (PNG) |
| GET    | `/reports/weekly.pdf?username=`   | full weekly report (PDF) |
| GET    | `/weather?lat=&lon=`     | current conditions (Open-Meteo, no key)|
| GET    | `/dashboard?username=`   | combined dashboard payload            |
| POST   | `/affirmation`            | AI-generated personalized affirmation |
| GET    | `/health`                | health check + `ai_enabled`/`provider` status |

## What was deliberately cut from the original full-SaaS plan

To make this shippable in days instead of weeks: no third-party auth provider (Clerk/Firebase),
no push notifications, no admin analytics dashboard, no multi-agent LLM pipeline, no Postgres
requirement (SQLite by default), no separate React build. Every one of these is a clean,
isolated add-on if you want to extend the project later — the API contract won't need to change.

## Resume line

> Built Evolve AI, an AI-powered personal growth platform with automatic mood detection from
> journal entries, habit streak tracking, and weekly insight generation via a transparent
> growth-scoring model. FastAPI + SQLAlchemy backend, deployed on Railway with a documented
> REST API.
