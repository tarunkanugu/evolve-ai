import datetime as dt
import os
from collections import Counter

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
import schemas
from database import engine, get_db
from mood import analyze_mood
import ai_service
import weather as weather_service
import card as card_service
import report as report_service

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Evolve AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


# ---------- helpers ----------

def get_or_create_user(db: Session, username: str) -> models.User:
    username = username.strip().lower()
    if not username:
        raise HTTPException(400, "username required")
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        user = models.User(username=username)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def habit_to_out(habit: models.Habit) -> schemas.HabitOut:
    dates = sorted({log.date for log in habit.logs}, reverse=True)
    today = dt.date.today()

    # current streak: consecutive days ending today or yesterday
    streak = 0
    cursor = today
    date_set = set(dates)
    if today not in date_set:
        cursor = today - dt.timedelta(days=1)
    while cursor in date_set:
        streak += 1
        cursor -= dt.timedelta(days=1)

    week_ago = today - dt.timedelta(days=6)
    completions_last_7 = sum(1 for d in dates if d >= week_ago)

    return schemas.HabitOut(
        id=habit.id,
        name=habit.name,
        archived=habit.archived,
        current_streak=streak,
        completions_last_7_days=completions_last_7,
        done_today=today in date_set,
    )


def compute_growth_score(db: Session, user: models.User) -> int:
    """
    Growth score (0-100) = journal consistency (40%) + mood (30%) + habit completion (30%)
    over the trailing 7 days. Simple, explainable, no black-box weighting.
    """
    week_ago = dt.datetime.utcnow() - dt.timedelta(days=7)

    entries = (
        db.query(models.JournalEntry)
        .filter(models.JournalEntry.user_id == user.id, models.JournalEntry.created_at >= week_ago)
        .all()
    )
    journal_days = len({e.created_at.date() for e in entries})
    journal_component = min(journal_days / 7, 1.0) * 40

    if entries:
        avg_mood = sum(e.mood_score for e in entries) / len(entries)
    else:
        avg_mood = 0.0
    mood_component = ((avg_mood + 1) / 2) * 30  # map [-1,1] -> [0,30]

    habits = db.query(models.Habit).filter(models.Habit.user_id == user.id, models.Habit.archived == False).all()  # noqa: E712
    if habits:
        rates = []
        for h in habits:
            week_ago_date = dt.date.today() - dt.timedelta(days=6)
            completions = sum(1 for log in h.logs if log.date >= week_ago_date)
            rates.append(min(completions / 7, 1.0))
        habit_component = (sum(rates) / len(rates)) * 30
    else:
        habit_component = 15  # neutral baseline if no habits set up yet

    return round(journal_component + mood_component + habit_component)


def build_advice(db: Session, user: models.User) -> str:
    """Rule-based coaching line grounded in the user's actual last-7-days data."""
    week_ago = dt.datetime.utcnow() - dt.timedelta(days=7)
    entries = (
        db.query(models.JournalEntry)
        .filter(models.JournalEntry.user_id == user.id, models.JournalEntry.created_at >= week_ago)
        .order_by(models.JournalEntry.created_at)
        .all()
    )
    habits = db.query(models.Habit).filter(models.Habit.user_id == user.id, models.Habit.archived == False).all()  # noqa: E712

    if not entries and not habits:
        return "Log your first journal entry or habit to get personalized advice."

    if entries:
        neg_days = sum(1 for e in entries if e.mood_label == "negative")
        if neg_days >= 3:
            return "Mood has dipped on several days this week — consider a lighter day or an earlier wind-down tonight."

    # find the habit with the weakest completion rate
    weakest = None
    weakest_rate = 1.1
    week_ago_date = dt.date.today() - dt.timedelta(days=6)
    for h in habits:
        completions = sum(1 for log in h.logs if log.date >= week_ago_date)
        rate = completions / 7
        if rate < weakest_rate:
            weakest_rate = rate
            weakest = h
    if weakest and weakest_rate < 0.5:
        return f'"{weakest.name}" has the lowest completion rate this week — try scheduling it earlier in the day.'

    if entries:
        return "Consistent week — keep the streak going and consider raising one habit's target."

    return "Set up a habit to start tracking your consistency alongside your journal."


# ---------- routes ----------

@app.post("/auth/register", response_model=schemas.UserOut)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    user = get_or_create_user(db, payload.username)
    return user


@app.post("/journal", response_model=schemas.JournalOut)
def create_journal_entry(payload: schemas.JournalCreate, db: Session = Depends(get_db)):
    user = get_or_create_user(db, payload.username)
    # analyze_mood_ai calls the real Anthropic API when ANTHROPIC_API_KEY is set,
    # and transparently falls back to the local lexicon analyzer (mood.py) otherwise
    # or if the API call fails, so this route never breaks on an API outage.
    score, label, reflection = ai_service.analyze_mood_ai(payload.text)
    entry = models.JournalEntry(
        user_id=user.id,
        text=payload.text,
        mood_score=score,
        mood_label=label,
        ai_reflection=reflection or None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@app.get("/journal", response_model=list[schemas.JournalOut])
def list_journal_entries(username: str, db: Session = Depends(get_db)):
    user = get_or_create_user(db, username)
    return (
        db.query(models.JournalEntry)
        .filter(models.JournalEntry.user_id == user.id)
        .order_by(models.JournalEntry.created_at.desc())
        .limit(50)
        .all()
    )


@app.post("/habit", response_model=schemas.HabitOut)
def create_habit(payload: schemas.HabitCreate, db: Session = Depends(get_db)):
    user = get_or_create_user(db, payload.username)
    habit = models.Habit(user_id=user.id, name=payload.name.strip())
    db.add(habit)
    db.commit()
    db.refresh(habit)
    return habit_to_out(habit)


@app.get("/habits", response_model=list[schemas.HabitOut])
def list_habits(username: str, db: Session = Depends(get_db)):
    user = get_or_create_user(db, username)
    habits = db.query(models.Habit).filter(models.Habit.user_id == user.id, models.Habit.archived == False).all()  # noqa: E712
    return [habit_to_out(h) for h in habits]


@app.post("/habit/{habit_id}/checkin", response_model=schemas.HabitOut)
def checkin_habit(habit_id: int, payload: schemas.CheckinRequest, db: Session = Depends(get_db)):
    user = get_or_create_user(db, payload.username)
    habit = db.query(models.Habit).filter(models.Habit.id == habit_id, models.Habit.user_id == user.id).first()
    if not habit:
        raise HTTPException(404, "habit not found")

    today = dt.date.today()
    existing = next((log for log in habit.logs if log.date == today), None)
    if existing:
        db.delete(existing)  # tapping again un-checks it
    else:
        db.add(models.HabitLog(habit_id=habit.id, date=today))
    db.commit()
    db.refresh(habit)
    return habit_to_out(habit)


@app.delete("/habit/{habit_id}")
def archive_habit(habit_id: int, username: str, db: Session = Depends(get_db)):
    user = get_or_create_user(db, username)
    habit = db.query(models.Habit).filter(models.Habit.id == habit_id, models.Habit.user_id == user.id).first()
    if not habit:
        raise HTTPException(404, "habit not found")
    habit.archived = True
    db.commit()
    return {"ok": True}


@app.get("/weather")
def get_weather(lat: float, lon: float):
    """
    Real external API call (Open-Meteo, no key required). Returns None fields if the
    upstream call fails — never a 500, since weather is enrichment, not core data.
    """
    data = weather_service.get_current_weather(lat, lon)
    if data is None:
        return {"available": False, "temp_c": None, "condition": None}
    return {"available": True, **data}


@app.get("/insights/weekly", response_model=schemas.WeeklyInsight)
def weekly_insight(username: str, db: Session = Depends(get_db), lat: float | None = None, lon: float | None = None):
    user = get_or_create_user(db, username)
    week_ago = dt.datetime.utcnow() - dt.timedelta(days=7)
    entries = (
        db.query(models.JournalEntry)
        .filter(models.JournalEntry.user_id == user.id, models.JournalEntry.created_at >= week_ago)
        .all()
    )
    prev_week_ago = dt.datetime.utcnow() - dt.timedelta(days=14)
    prev_entries = (
        db.query(models.JournalEntry)
        .filter(
            models.JournalEntry.user_id == user.id,
            models.JournalEntry.created_at >= prev_week_ago,
            models.JournalEntry.created_at < week_ago,
        )
        .all()
    )

    avg_mood = sum(e.mood_score for e in entries) / len(entries) if entries else 0.0
    prev_avg_mood = sum(e.mood_score for e in prev_entries) / len(prev_entries) if prev_entries else avg_mood

    if avg_mood - prev_avg_mood > 0.1:
        trend = "improving"
    elif prev_avg_mood - avg_mood > 0.1:
        trend = "declining"
    else:
        trend = "steady"

    habits = db.query(models.Habit).filter(models.Habit.user_id == user.id, models.Habit.archived == False).all()  # noqa: E712
    week_ago_date = dt.date.today() - dt.timedelta(days=6)
    if habits:
        rates = []
        for h in habits:
            completions = sum(1 for log in h.logs if log.date >= week_ago_date)
            rates.append(completions / 7)
        completion_rate = round((sum(rates) / len(rates)) * 100, 1)
    else:
        completion_rate = 0.0

    best_day = None
    if entries:
        by_day = Counter()
        totals = Counter()
        for e in entries:
            day_name = e.created_at.strftime("%A")
            by_day[day_name] += e.mood_score
            totals[day_name] += 1
        avgs = {d: by_day[d] / totals[d] for d in by_day}
        best_day = max(avgs, key=avgs.get)

    growth_score = compute_growth_score(db, user)
    rule_based_advice = build_advice(db, user)

    weakest_habit = None
    if habits:
        weakest_rate = 1.1
        for h in habits:
            completions = sum(1 for log in h.logs if log.date >= week_ago_date)
            rate = completions / 7
            if rate < weakest_rate:
                weakest_rate = rate
                weakest_habit = h.name

    ai_context = {
        "avg_mood_score": round(avg_mood, 3),
        "mood_trend": trend,
        "habit_completion_rate": completion_rate,
        "weakest_habit": weakest_habit,
        "journal_entries_this_week": len(entries),
    }
    weather_data = None
    if lat is not None and lon is not None:
        weather_data = weather_service.get_current_weather(lat, lon)
        if weather_data:
            ai_context["current_weather"] = weather_data
    # generate_weekly_advice_ai calls Claude for a specific coaching line grounded
    # in this week's real numbers (and today's weather, if available); falls back
    # to the rule-based line above on any failure.
    advice = ai_service.generate_weekly_advice_ai(ai_context, fallback=rule_based_advice)

    return schemas.WeeklyInsight(
        avg_mood_score=round(avg_mood, 3),
        mood_trend=trend,
        habit_completion_rate=completion_rate,
        growth_score=growth_score,
        most_positive_day=best_day,
        recommendation=advice,
        journal_entries_this_week=len(entries),
        weather_temp_c=weather_data["temp_c"] if weather_data else None,
        weather_condition=weather_data["condition"] if weather_data else None,
    )


@app.get("/insights/weekly/card")
def weekly_card(username: str, db: Session = Depends(get_db)):
    """Renders the current weekly insight as a shareable 1080x1080 PNG (see card.py)."""
    insight = weekly_insight(username, db)
    user = get_or_create_user(db, username)
    streak = dashboard(username, db).streak_days
    png_bytes = card_service.render_weekly_card(
        username=user.username,
        growth_score=insight.growth_score,
        streak_days=streak,
        avg_mood_score=insight.avg_mood_score,
        mood_trend=insight.mood_trend,
        habit_completion_rate=insight.habit_completion_rate,
        best_day=insight.most_positive_day,
        recommendation=insight.recommendation,
    )
    return Response(content=png_bytes, media_type="image/png", headers={
        "Content-Disposition": f'inline; filename="evolve-ai-{user.username}-weekly.png"'
    })


@app.get("/reports/weekly.pdf")
def weekly_pdf(username: str, db: Session = Depends(get_db)):
    """Full printable/emailable weekly PDF report (see report.py)."""
    insight = weekly_insight(username, db)
    user = get_or_create_user(db, username)
    streak = dashboard(username, db).streak_days

    recent = (
        db.query(models.JournalEntry)
        .filter(models.JournalEntry.user_id == user.id)
        .order_by(models.JournalEntry.created_at.desc())
        .limit(6)
        .all()
    )
    recent_dicts = [
        {"created_at": e.created_at, "mood_label": e.mood_label, "text": e.text}
        for e in recent
    ]

    pdf_bytes = report_service.render_weekly_pdf(
        username=user.username,
        growth_score=insight.growth_score,
        streak_days=streak,
        avg_mood_score=insight.avg_mood_score,
        mood_trend=insight.mood_trend,
        habit_completion_rate=insight.habit_completion_rate,
        best_day=insight.most_positive_day,
        recommendation=insight.recommendation,
        journal_entries_this_week=insight.journal_entries_this_week,
        recent_entries=recent_dicts,
    )
    return Response(content=pdf_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="evolve-ai-{user.username}-weekly-report.pdf"'
    })


@app.get("/dashboard", response_model=schemas.DashboardOut)
def dashboard(username: str, db: Session = Depends(get_db)):
    user = get_or_create_user(db, username)
    habits = db.query(models.Habit).filter(models.Habit.user_id == user.id, models.Habit.archived == False).all()  # noqa: E712
    journal_count = db.query(func.count(models.JournalEntry.id)).filter(models.JournalEntry.user_id == user.id).scalar()

    today_entry = (
        db.query(models.JournalEntry)
        .filter(models.JournalEntry.user_id == user.id, func.date(models.JournalEntry.created_at) == dt.date.today())
        .order_by(models.JournalEntry.created_at.desc())
        .first()
    )

    # streak = consecutive days with at least one journal entry
    all_dates = sorted(
        {e.created_at.date() for e in db.query(models.JournalEntry).filter(models.JournalEntry.user_id == user.id).all()},
        reverse=True,
    )
    date_set = set(all_dates)
    today = dt.date.today()
    streak = 0
    cursor = today if today in date_set else today - dt.timedelta(days=1)
    while cursor in date_set:
        streak += 1
        cursor -= dt.timedelta(days=1)

    return schemas.DashboardOut(
        username=user.username,
        streak_days=streak,
        growth_score=compute_growth_score(db, user),
        today_mood_label=today_entry.mood_label if today_entry else None,
        journal_count=journal_count or 0,
        habits=[habit_to_out(h) for h in habits],
        ai_advice=build_advice(db, user),
    )


@app.post("/affirmation", response_model=schemas.AffirmationOut)
def get_affirmation(payload: schemas.CheckinRequest, db: Session = Depends(get_db)):
    """
    A short, personalized affirmation generated from the user's real recent context
    (latest mood, weakest habit) rather than a static quote bank. Calls the Anthropic
    API; falls back to a small rotating set of generic lines if no key is set or the
    call fails.
    """
    user = get_or_create_user(db, payload.username)

    latest_entry = (
        db.query(models.JournalEntry)
        .filter(models.JournalEntry.user_id == user.id)
        .order_by(models.JournalEntry.created_at.desc())
        .first()
    )
    habits = db.query(models.Habit).filter(models.Habit.user_id == user.id, models.Habit.archived == False).all()  # noqa: E712

    context = {
        "recent_mood": latest_entry.mood_label if latest_entry else None,
        "habit_count": len(habits),
        "growth_score": compute_growth_score(db, user),
    }
    text = ai_service.generate_affirmation_ai(context)
    return schemas.AffirmationOut(text=text)


@app.get("/health")
def health():
    return {"status": "ok", **ai_service.ai_status()}


# ---------- serve frontend ----------
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
