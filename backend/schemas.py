import datetime as dt
from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=40)


class UserOut(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True


class JournalCreate(BaseModel):
    username: str
    text: str = Field(..., min_length=1, max_length=5000)


class JournalOut(BaseModel):
    id: int
    text: str
    mood_score: float
    mood_label: str
    ai_reflection: str | None = None
    created_at: dt.datetime

    class Config:
        from_attributes = True


class HabitCreate(BaseModel):
    username: str
    name: str = Field(..., min_length=1, max_length=100)


class HabitOut(BaseModel):
    id: int
    name: str
    archived: bool
    current_streak: int
    completions_last_7_days: int
    done_today: bool

    class Config:
        from_attributes = True


class CheckinRequest(BaseModel):
    username: str


class AffirmationOut(BaseModel):
    text: str


class WeeklyInsight(BaseModel):
    avg_mood_score: float
    mood_trend: str
    habit_completion_rate: float
    growth_score: int
    most_positive_day: str | None
    recommendation: str
    journal_entries_this_week: int
    weather_temp_c: float | None = None
    weather_condition: str | None = None


class DashboardOut(BaseModel):
    username: str
    streak_days: int
    growth_score: int
    today_mood_label: str | None
    journal_count: int
    habits: list[HabitOut]
    ai_advice: str
