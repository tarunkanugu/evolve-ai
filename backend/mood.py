"""
Zero-dependency, zero-API-key sentiment analyzer for journal entries.

This is intentionally rule-based (word-list + negation handling) rather than
calling an LLM: it keeps the MVP deployable with no API keys and no per-request
cost, while still producing a defensible mood_score in [-1, 1].

Swap-in point: if/when you want LLM-quality mood detection, replace
`analyze_mood()`'s body with a call to your model of choice and keep the same
return contract (score: float, label: str) so nothing else has to change.
"""
import re

POSITIVE_WORDS = {
    "happy", "good", "great", "excellent", "amazing", "awesome", "proud",
    "confident", "calm", "relaxed", "grateful", "thankful", "motivated",
    "excited", "energized", "productive", "accomplished", "peaceful",
    "hopeful", "strong", "focused", "love", "loved", "joy", "joyful",
    "success", "successful", "win", "won", "better", "improved", "progress",
    "rested", "refreshed", "fun", "grew", "growth", "achieved", "clarity",
    "enjoyed", "enjoy", "enjoying", "wonderful", "delighted",
    "pleased", "satisfied", "content", "cheerful", "glad", "nice", "lovely",
    "smooth", "easy", "relieved", "optimistic", "inspired", "blessed",
}

NEGATIVE_WORDS = {
    "sad", "bad", "terrible", "awful", "anxious", "anxiety", "stressed",
    "stress", "tired", "exhausted", "overwhelmed", "frustrated", "angry",
    "upset", "worried", "worry", "fear", "afraid", "lonely", "alone",
    "depressed", "hopeless", "failed", "failure", "lost", "stuck", "hate",
    "hated", "bored", "burnout", "burned out", "sick", "hurt", "pain",
    "disappointed", "insecure", "doubt", "doubting", "behind", "rejected",
    "rejection", "cried", "crying",
}

NEGATIONS = {"not", "no", "never", "cant", "can't", "didnt", "didn't", "wasnt", "wasn't", "isnt", "isn't", "wont", "won't"}

INTENSIFIERS = {"very", "really", "extremely", "so", "super", "incredibly"}


def analyze_mood(text: str) -> tuple[float, str]:
    tokens = re.findall(r"[a-zA-Z']+", text.lower())

    score = 0.0
    hits = 0
    for i, tok in enumerate(tokens):
        polarity = 0
        if tok in POSITIVE_WORDS:
            polarity = 1
        elif tok in NEGATIVE_WORDS:
            polarity = -1
        else:
            continue

        # look back up to 2 tokens for a negation, which flips polarity
        window = tokens[max(0, i - 2):i]
        if any(w in NEGATIONS for w in window):
            polarity *= -1

        # a preceding intensifier gives it a bit more weight
        weight = 1.5 if any(w in INTENSIFIERS for w in window) else 1.0

        score += polarity * weight
        hits += 1

    if hits == 0:
        normalized = 0.0
    else:
        # normalize into [-1, 1], softened by hit count so a single word
        # doesn't swing straight to +/-1 on a long entry
        raw = score / hits
        normalized = max(-1.0, min(1.0, raw))

    if normalized > 0.15:
        label = "positive"
    elif normalized < -0.15:
        label = "negative"
    else:
        label = "neutral"

    return round(normalized, 3), label
