"""
Renders the weekly insight into a shareable PNG card (1080x1080, Instagram-square)
using Pillow. Pure server-side image generation — no browser screenshot hacks — so
the same endpoint works for any client.
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")

BG = (14, 20, 15)
PANEL = (22, 31, 24)
LINE = (42, 54, 44)
TEXT = (234, 242, 236)
MUTED = (143, 163, 150)
ACCENT = (124, 255, 178)
AMBER = (255, 180, 84)
NEG = (255, 138, 122)

W = H = 1080


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(ASSETS_DIR, name), size)


def _score_color(score: int):
    if score >= 70:
        return ACCENT
    if score >= 40:
        return AMBER
    return NEG


def _draw_gauge(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, score: int, width: int = 22):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=LINE, width=width)
    start = -90
    end = start + (score / 100) * 360
    color = _score_color(score)
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=start, end=end, fill=color, width=width)


def render_weekly_card(*, username: str, growth_score: int, streak_days: int,
                        avg_mood_score: float, mood_trend: str,
                        habit_completion_rate: float, best_day: str | None,
                        recommendation: str) -> bytes:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    display_bold = "DejaVuSerif-Bold.ttf"
    body = "DejaVuSans.ttf"
    body_bold = "DejaVuSans-Bold.ttf"

    # eyebrow + title
    draw.text((64, 56), "EVOLVE AI", font=_font(body_bold, 22), fill=ACCENT)
    draw.text((64, 92), f"Weekly growth report · @{username}", font=_font(body, 22), fill=MUTED)

    # gauge
    gauge_cx, gauge_cy, gauge_r = W // 2, 340, 170
    _draw_gauge(draw, gauge_cx, gauge_cy, gauge_r, growth_score)
    score_text = str(growth_score)
    f_score = _font(display_bold, 96)
    bbox = draw.textbbox((0, 0), score_text, font=f_score)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((gauge_cx - tw / 2, gauge_cy - th / 2 - bbox[1]), score_text, font=f_score, fill=TEXT)
    f_sub = _font(body, 24)
    sub = "GROWTH SCORE / 100"
    bbox2 = draw.textbbox((0, 0), sub, font=f_sub)
    draw.text((gauge_cx - (bbox2[2] - bbox2[0]) / 2, gauge_cy + 62), sub, font=f_sub, fill=MUTED)

    # stat rows
    rows = [
        ("Streak", f"{streak_days} day{'s' if streak_days != 1 else ''}"),
        ("Avg mood score", f"{avg_mood_score:+.2f}"),
        ("Mood trend", mood_trend.capitalize()),
        ("Habit completion", f"{habit_completion_rate:.0f}%"),
        ("Best day", best_day or "—"),
    ]
    y = 560
    row_h = 62
    panel_top = y - 24
    panel_bottom = y + len(rows) * row_h - 6
    draw.rounded_rectangle([64, panel_top, W - 64, panel_bottom], radius=16, fill=PANEL, outline=LINE, width=1)
    f_label = _font(body, 26)
    f_val = _font(body_bold, 26)
    for label, val in rows:
        draw.text((96, y), label, font=f_label, fill=MUTED)
        vb = draw.textbbox((0, 0), val, font=f_val)
        draw.text((W - 96 - (vb[2] - vb[0]), y), val, font=f_val, fill=TEXT)
        if (label, val) != rows[-1]:
            draw.line([96, y + row_h - 18, W - 96, y + row_h - 18], fill=LINE, width=1)
        y += row_h

    # advice card
    advice_top = panel_bottom + 36
    advice_bottom = advice_top + 160
    draw.rounded_rectangle([64, advice_top, W - 64, advice_bottom], radius=16, fill=PANEL, outline=ACCENT, width=2)
    draw.text((96, advice_top + 24), "AI COACH", font=_font(body_bold, 20), fill=ACCENT)
    # wrap recommendation text manually
    f_rec = _font(body, 26)
    max_width = W - 192
    words = recommendation.split()
    lines, cur = [], ""
    for w_ in words:
        trial = (cur + " " + w_).strip()
        if draw.textlength(trial, font=f_rec) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    ly = advice_top + 58
    for line in lines[:3]:
        draw.text((96, ly), line, font=f_rec, fill=TEXT)
        ly += 34

    # footer
    draw.text((64, H - 56), "evolve-ai · personal growth OS", font=_font(body, 18), fill=MUTED)

    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
