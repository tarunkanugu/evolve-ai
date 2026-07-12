"""
Real external API integration: calls an LLM API (Groq or Anthropic) for mood
analysis and AI coaching advice.

Provider selection: if GROQ_API_KEY is set, Groq is used (OpenAI-compatible
endpoint, no extra SDK dependency — plain httpx). Otherwise, if
ANTHROPIC_API_KEY is set, Anthropic is used. If neither is set, everything
falls back to local rule-based logic. This lets you pick either provider
without touching code — useful for a hackathon where Groq's free tier is
often easier to get a key for quickly.

Design choice: every function here has a rule-based fallback (from mood.py /
local heuristics). If no key is set, or the API call fails or times out, we
fall back automatically instead of crashing the request.
"""
import json
import os
import logging

import httpx

from mood import analyze_mood

logger = logging.getLogger("evolve.ai_service")

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"

_GROQ_KEY = os.getenv("GROQ_API_KEY")
_ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")

if _GROQ_KEY:
    PROVIDER = "groq"
elif _ANTHROPIC_KEY:
    PROVIDER = "anthropic"
else:
    PROVIDER = None

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        try:
            import anthropic
            _anthropic_client = anthropic.Anthropic(api_key=_ANTHROPIC_KEY)
        except Exception as e:  # noqa: BLE001
            logger.warning("Anthropic client failed to initialize: %s", e)
            return None
    return _anthropic_client


def _call_llm(prompt: str, max_tokens: int) -> str | None:
    """
    Routes to whichever provider is configured. Returns the raw text response,
    or None if no provider is configured or the call fails for any reason.
    """
    if PROVIDER == "groq":
        try:
            resp = httpx.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {_GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("Groq call failed: %s", e)
            return None

    if PROVIDER == "anthropic":
        client = _get_anthropic_client()
        if client is None:
            return None
        try:
            resp = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(block.text for block in resp.content if block.type == "text").strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("Anthropic call failed: %s", e)
            return None

    return None


def analyze_mood_ai(text: str) -> tuple[float, str, str]:
    """
    Returns (score in [-1,1], label in {positive,neutral,negative}, one_line_reflection).
    Falls back to the local lexicon analyzer (mood.py) on any failure, in which
    case the reflection is empty rather than AI-generated.
    """
    prompt = (
        "You analyze the emotional tone of a personal journal entry. "
        "Respond with ONLY a JSON object, no markdown fences, no preamble, "
        "in exactly this shape:\n"
        '{"score": <float from -1.0 (very negative) to 1.0 (very positive)>, '
        '"label": "<positive|neutral|negative>", '
        '"reflection": "<one short supportive sentence, under 20 words, '
        'reflecting back what the entry seems to be about>"}\n\n'
        f"Journal entry:\n{text}"
    )
    raw = _call_llm(prompt, max_tokens=200)
    if raw is None:
        score, label = analyze_mood(text)
        return score, label, ""

    try:
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        score = max(-1.0, min(1.0, float(data["score"])))
        label = data["label"] if data["label"] in ("positive", "neutral", "negative") else "neutral"
        reflection = str(data.get("reflection", ""))[:200]
        return round(score, 3), label, reflection
    except Exception as e:  # noqa: BLE001
        logger.warning("analyze_mood_ai response parsing failed, using local fallback: %s", e)
        score, label = analyze_mood(text)
        return score, label, ""


def generate_weekly_advice_ai(context: dict, fallback: str) -> str:
    """
    context: {
      "avg_mood_score": float, "mood_trend": str, "habit_completion_rate": float,
      "weakest_habit": str | None, "journal_entries_this_week": int,
      "current_weather": {"temp_c": float, "condition": str} (optional),
    }
    Falls back to the provided rule-based advice string on any failure.
    """
    prompt = (
        "You are a concise, encouraging personal-growth coach. Based on this "
        "week's data, write ONE short coaching sentence (under 30 words), "
        "specific and actionable, no generic platitudes. If weather data is "
        "present, you may weave it in naturally if genuinely relevant (e.g. "
        "suggesting an outdoor habit on a clear day) — don't force it. Respond "
        "with plain text only, no quotes, no markdown.\n\n"
        f"Data: {json.dumps(context)}"
    )
    text = _call_llm(prompt, max_tokens=100)
    return text if text else fallback


_FALLBACK_AFFIRMATIONS = [
    "Progress doesn't have to be loud to be real — showing up today already counts.",
    "One honest entry, one small habit — that's the whole system working.",
    "You don't need a perfect week, just a slightly better one than last week.",
    "Consistency beats intensity. Keep the streak, not the pressure.",
]


def generate_affirmation_ai(context: dict) -> str:
    """
    context: {"recent_mood": str|None, "habit_count": int, "growth_score": int}
    Falls back to a rotating static line (keyed off growth_score so it's at least
    a little context-aware) if no provider is configured or the call fails.
    """
    prompt = (
        "Write ONE short, specific, non-generic affirmation (under 25 words) for "
        "someone using a personal-growth journaling app, based on this context. "
        "No emojis, no quotes around it, plain text only.\n\n"
        f"Context: {json.dumps(context)}"
    )
    text = _call_llm(prompt, max_tokens=80)
    if text:
        return text
    idx = int(context.get("growth_score", 0)) % len(_FALLBACK_AFFIRMATIONS)
    return _FALLBACK_AFFIRMATIONS[idx]


def ai_status() -> dict:
    model = GROQ_MODEL if PROVIDER == "groq" else (ANTHROPIC_MODEL if PROVIDER == "anthropic" else None)
    return {"ai_enabled": PROVIDER is not None, "provider": PROVIDER, "model": model}
