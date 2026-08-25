"""Financial sentiment analysis with a zero-cost fallback chain.

1. FinBERT (Hugging Face transformers, runs locally) if installed.
2. Otherwise a deterministic, finance-tuned lexicon scorer with basic
   negation handling - no downloads, no API keys, fully offline.
Both paths return (label, score) where score is in [-1, 1].
"""
from __future__ import annotations

import threading

POSITIVE: dict[str, float] = {
    "surge": 0.8, "surges": 0.8, "soar": 0.9, "soars": 0.9, "beat": 0.7,
    "beats": 0.7, "upgrade": 0.8, "upgraded": 0.8, "rally": 0.8,
    "record": 0.6, "growth": 0.6, "profit": 0.7, "profits": 0.7,
    "bullish": 0.9, "outperform": 0.8, "gain": 0.6, "gains": 0.6,
    "jump": 0.7, "jumps": 0.7, "strong": 0.6, "buy": 0.5, "breakout": 0.8,
    "recovery": 0.6, "dividend": 0.4, "expansion": 0.5, "optimism": 0.6,
    "tops": 0.6, "raises": 0.6, "boost": 0.6, "momentum": 0.5,
}
NEGATIVE: dict[str, float] = {
    "plunge": -0.9, "plunges": -0.9, "miss": -0.7, "misses": -0.7,
    "downgrade": -0.8, "downgraded": -0.8, "lawsuit": -0.6, "fraud": -0.95,
    "loss": -0.7, "losses": -0.7, "bearish": -0.9, "decline": -0.6,
    "weak": -0.6, "cut": -0.5, "cuts": -0.5, "crash": -0.95,
    "bankruptcy": -1.0, "probe": -0.5, "investigation": -0.6,
    "slump": -0.8, "drop": -0.6, "drops": -0.6, "fall": -0.5,
    "falls": -0.5, "warning": -0.5, "layoffs": -0.6, "sell-off": -0.7,
    "tumble": -0.8, "risk": -0.3, "default": -0.8, "recall": -0.6,
}
NEGATORS = {"not", "no", "never", "without", "despite"}


class SentimentAnalyzer:
    """Thread-safe lazy singleton; falls back to the lexicon on any
    transformers/model failure so scoring NEVER raises to callers."""

    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._attempted = False

    def _try_load_finbert(self):  # pragma: no cover - optional dependency
        if self._attempted or self._model is not None:
            return self._model
        with self._lock:
            if self._attempted:
                return self._model
            self._attempted = True
            try:
                from transformers import pipeline  # optional extra
                self._model = pipeline(
                    "sentiment-analysis",
                    model="ProsusAI/finbert",
                    truncation=True, max_length=256)
            except Exception:  # noqa: BLE001 - any failure -> lexicon mode
                self._model = None
        return self._model

    @staticmethod
    def _lexicon_score(text: str) -> float:
        tokens = [t.strip(".,!?;:()\"'").lower() for t in text.split()]
        score, window_negation = 0.0, 0
        for token in tokens:
            if token in NEGATORS:
                # A negator flips the polarity of sentiment words found
                # within the next 3 tokens.
                window_negation = 3
                continue
            polarity = POSITIVE.get(token, NEGATIVE.get(token))
            if polarity is None:
                continue
            if window_negation > 0:
                polarity *= -1.0
                window_negation -= 1
            score += polarity
        # Squash to [-1, 1] and dampen short/noisy inputs.
        magnitude = min(abs(score) / 4.0, 1.0)
        return round(magnitude * (1 if score >= 0 else -1), 4)

    def analyze(self, text: str) -> tuple[str, float]:
        text = (text or "").strip()
        if not text:
            return "NEUTRAL", 0.0
        model = self._try_load_finbert()
        if model is not None:  # pragma: no cover - optional path
            try:
                result = model(text[:1000])[0]
                label_raw, conf = result["label"], float(result["score"])
                mapping = {"positive": ("BULLISH", min(conf, 1.0)),
                           "negative": ("BEARISH", -min(conf, 1.0)),
                           "neutral": ("NEUTRAL",
                                       (conf - 0.5) * 0.2)}
                return mapping[label_raw]
            except Exception:  # noqa: BLE001 - never break callers
                pass
        score = self._lexicon_score(text)
        if score >= 0.15:
            return "BULLISH", score
        if score <= -0.15:
            return "BEARISH", score
        return "NEUTRAL", score


_analyzer = SentimentAnalyzer()


def analyze_sentiment(text: str) -> tuple[str, float]:
    return _analyzer.analyze(text)
