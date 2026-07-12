"""
Generates a one-page weekly PDF report using reportlab. Separate from card.py
(which makes a square social-share PNG) — this is a denser, printable/emailable
report: full stats table, recent journal entries, and the AI coaching line.
"""
from io import BytesIO
import datetime as dt

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit

BG = HexColor("#0e140f")
PANEL = HexColor("#161f18")
LINE = HexColor("#2a362c")
TEXT = HexColor("#eaf2ec")
MUTED = HexColor("#8fa396")
ACCENT = HexColor("#7cffb2")
AMBER = HexColor("#ffb454")


def render_weekly_pdf(*, username: str, growth_score: int, streak_days: int,
                       avg_mood_score: float, mood_trend: str,
                       habit_completion_rate: float, best_day: str | None,
                       recommendation: str, journal_entries_this_week: int,
                       recent_entries: list[dict]) -> bytes:
    buf = BytesIO()
    W, H = letter
    c = canvas.Canvas(buf, pagesize=letter)

    # background
    c.setFillColor(BG)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    margin = 0.75 * inch
    y = H - margin

    # header
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "EVOLVE AI")
    y -= 16
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"Weekly growth report · @{username} · generated {dt.date.today().isoformat()}")
    y -= 34

    # growth score headline
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 40)
    c.drawString(margin, y - 30, f"{growth_score}")
    c.setFont("Helvetica", 12)
    c.setFillColor(MUTED)
    c.drawString(margin + 70, y - 18, "/ 100")
    c.drawString(margin + 70, y - 32, "GROWTH SCORE")
    y -= 60

    # stats panel
    stats = [
        ("Streak", f"{streak_days} day{'s' if streak_days != 1 else ''}"),
        ("Avg mood score", f"{avg_mood_score:+.2f}"),
        ("Mood trend", mood_trend.capitalize()),
        ("Habit completion", f"{habit_completion_rate:.0f}%"),
        ("Best day", best_day or "—"),
        ("Journal entries this week", str(journal_entries_this_week)),
    ]
    row_h = 24
    panel_h = row_h * len(stats) + 20
    c.setFillColor(PANEL)
    c.roundRect(margin, y - panel_h, W - 2 * margin, panel_h, 8, fill=1, stroke=1)
    c.setStrokeColor(LINE)
    ry = y - 22
    c.setFont("Helvetica", 11)
    for label, val in stats:
        c.setFillColor(MUTED)
        c.drawString(margin + 20, ry, label)
        c.setFillColor(TEXT)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(W - margin - 20, ry, val)
        c.setFont("Helvetica", 11)
        ry -= row_h
    y -= panel_h + 24

    # AI coach panel
    advice_h = 90
    c.setFillColor(PANEL)
    c.setStrokeColor(ACCENT)
    c.roundRect(margin, y - advice_h, W - 2 * margin, advice_h, 8, fill=1, stroke=1)
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin + 20, y - 22, "AI COACH")
    c.setFillColor(TEXT)
    c.setFont("Helvetica", 11)
    lines = simpleSplit(recommendation, "Helvetica", 11, W - 2 * margin - 40)
    ly = y - 42
    for line in lines[:4]:
        c.drawString(margin + 20, ly, line)
        ly -= 16
    y -= advice_h + 24

    # recent entries
    c.setFillColor(TEXT)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, y, "Recent journal entries")
    y -= 20
    c.setFont("Helvetica", 10)
    for entry in recent_entries[:6]:
        if y < margin + 40:
            break
        date_str = entry["created_at"].strftime("%b %d, %I:%M %p")
        c.setFillColor(MUTED)
        c.drawString(margin, y, f"{date_str}  ·  {entry['mood_label'].upper()}")
        y -= 14
        c.setFillColor(TEXT)
        text_lines = simpleSplit(entry["text"], "Helvetica", 10, W - 2 * margin)
        for tl in text_lines[:2]:
            c.drawString(margin, y, tl)
            y -= 13
        y -= 8

    c.setFillColor(MUTED)
    c.setFont("Helvetica", 8)
    c.drawString(margin, margin / 2, "evolve-ai · personal growth OS")

    c.showPage()
    c.save()
    return buf.getvalue()
