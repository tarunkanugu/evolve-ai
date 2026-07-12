"""
SQLAlchemy models. Kept intentionally small (4 tables) for a fast, legible MVP:
User, JournalEntry, Habit, HabitLog.
"""
import datetime as dt
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Date
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    journal_entries = relationship("JournalEntry", back_populates="user", cascade="all, delete-orphan")
    habits = relationship("Habit", back_populates="user", cascade="all, delete-orphan")


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(String, nullable=False)
    mood_score = Column(Float, nullable=False)   # -1.0 (very negative) to +1.0 (very positive)
    mood_label = Column(String, nullable=False)  # e.g. "positive", "neutral", "negative"
    ai_reflection = Column(String, nullable=True)  # short line from the Claude API, blank if AI disabled/fell back
    created_at = Column(DateTime, default=dt.datetime.utcnow)

    user = relationship("User", back_populates="journal_entries")


class Habit(Base):
    __tablename__ = "habits"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    archived = Column(Boolean, default=False)

    user = relationship("User", back_populates="habits")
    logs = relationship("HabitLog", back_populates="habit", cascade="all, delete-orphan")


class HabitLog(Base):
    __tablename__ = "habit_logs"

    id = Column(Integer, primary_key=True, index=True)
    habit_id = Column(Integer, ForeignKey("habits.id"), nullable=False)
    date = Column(Date, default=dt.date.today, nullable=False)

    habit = relationship("Habit", back_populates="logs")
