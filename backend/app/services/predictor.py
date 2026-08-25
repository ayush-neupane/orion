"""ORION Predictive Analysis Engine.

Hybrid model = Technical indicators (RSI, MACD, Bollinger Bands) blended
with news sentiment, producing:
- Probability of upward movement (%) per symbol
- BUY / HOLD / SELL recommendation
- "Potential Breakout" underdog score (1-100)

Two inference paths:
1. Trained gradient-boosting classifier (XGBoost if installed, else
   scikit-learn) when >= MIN_TRAIN_BARS of history exists.
2. A deterministic, fully unit-tested heuristic vote for short histories,
   guaranteeing every symbol ALWAYS gets a prediction.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

MIN_TRAIN_BARS = 80


# ---------------------------------------------------------------------------
# Indicator primitives (pure functions - unit tested)
# ---------------------------------------------------------------------------

def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period,
                                   adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period,
                                      adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # Edge cases: a pure uptrend has zero loss -> RSI 100;
    # a pure downtrend has zero gain -> RSI 0.
    rsi = rsi.mask((loss == 0) & (gain > 0), 100.0)
    rsi = rsi.mask((gain == 0) & (loss > 0), 0.0)
    return rsi.fillna(50.0)


def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26,
                 signal: int = 9) -> pd.DataFrame:
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": macd_line, "signal": signal_line,
                         "hist": macd_line - signal_line})


def compute_bollinger(close: pd.Series, window: int = 20,
                      num_std: float = 2.0) -> pd.DataFrame:
    middle = close.rolling(window=window, min_periods=2).mean()
    std = close.rolling(window=window, min_periods=2).std().fillna(0)
    return pd.DataFrame({"upper": middle + num_std * std,
                         "middle": middle,
                         "lower": middle - num_std * std})


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def bars_to_frame(bars: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(bars)
    if frame.empty:
        return frame
    frame = frame.sort_values("time").reset_index(drop=True)
    for col in ("open", "high", "low", "close"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["volume"] = pd.to_numeric(frame.get("volume", 0),
                                    errors="coerce").fillna(0)
    return frame.dropna(subset=["close"])


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Indicator feature matrix; drops warm-up rows with undefined values."""
    close = frame["close"]
    feats = pd.DataFrame(index=frame.index)
    feats["rsi"] = compute_rsi(close)
    macd = compute_macd(close)
    feats["macd_hist"] = macd["hist"]
    bb = compute_bollinger(close)
    band_width = (bb["upper"] - bb["lower"]).replace(0, np.nan)
    feats["bb_pctb"] = ((close - bb["lower"]) / band_width).clip(-0.5, 1.5)
    feats["return_1d"] = close.pct_change().fillna(0)
    feats["return_5d"] = close.pct_change(5).fillna(0)
    vol_mean = frame["volume"].rolling(10, min_periods=3).mean()
    feats["volume_ratio"] = (frame["volume"] / vol_mean.replace(
        0, np.nan)).fillna(1.0)
    feats["sma_ratio"] = (close / close.rolling(20, min_periods=5).mean()
                          ).sub(1).fillna(0)
    feats["target_up"] = (close.shift(-5) > close).astype(float)
    defined = feats.dropna(subset=["rsi", "macd_hist", "bb_pctb",
                                   "volume_ratio"])
    return defined


def volume_trend_3d(frame: pd.DataFrame) -> float:
    """% change of mean volume last 3 bars vs prior 3 bars."""
    vol = frame["volume"]
    if len(vol) < 6 or vol.mean() == 0:
        return 0.0
    recent = vol.tail(3).mean()
    prior = vol.tail(6).head(3).mean()
    if not prior:
        return 0.0
    return round((recent - prior) / prior * 100.0, 2)


# ---------------------------------------------------------------------------
# Heuristic probability (always available, deterministic, testable)
# ---------------------------------------------------------------------------

def heuristic_probability(rsi: float, macd_hist: float, bb_pctb: float,
                          return_5d: float, volume_ratio: float,
                          sentiment: float = 0.0) -> float:
    votes = 0.0
    if rsi < 30:
        votes += 1.0          # oversold -> mean reversion up
    elif rsi < 45:
        votes += 0.4
    elif rsi > 70:
        votes -= 1.0          # overbought
    elif rsi > 55:
        votes -= 0.2
    else:
        votes += 0.1

    votes += 1.0 if macd_hist > 0 else -1.0
    votes += 1.0 if bb_pctb < 0.1 else (0.2 if bb_pctb <= 0.9 else -0.8)

    if return_5d > 0.05:
        votes -= 0.5          # short-term overheated
    elif return_5d > 0:
        votes += 0.3
    else:
        votes += 0.2

    votes += min(volume_ratio, 2.0) * 0.25      # accumulation signal
    votes += sentiment * 1.5                    # news sentiment blend

    prob = 1 / (1 + math.exp(-votes))           # logistic squash
    return round(min(max(prob, 0.02), 0.98), 4)


def recommend(prob_up: float) -> str:
    if prob_up >= 0.58:
        return "BUY"
    if prob_up <= 0.42:
        return "SELL"
    return "HOLD"

# ---------------------------------------------------------------------------
# Trained model path (XGBoost -> sklearn fallback)
# ---------------------------------------------------------------------------


def train_updown_model(features: pd.DataFrame):
    X = features.drop(columns=["target_up"]).values
    y = features["target_up"].values
    try:
        from xgboost import XGBClassifier
        model = XGBClassifier(n_estimators=150, max_depth=4,
                              learning_rate=0.08, subsample=0.9,
                              eval_metric="logloss", verbosity=0)
    except ImportError:  # pragma: no cover - xgboost optional
        from sklearn.ensemble import GradientBoostingClassifier
        model = GradientBoostingClassifier(n_estimators=120, max_depth=3,
                                           learning_rate=0.08)
    model.fit(X, y)
    return model


def trained_probability(model, row: pd.Series) -> float:
    X = np.array([row.drop(labels=["target_up"]).astype(float)])
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)[0]
        return round(float(proba[list(model.classes_).index(1)]
                           if 1 in list(model.classes_) else proba[-1]), 4)
    return round(float(model.predict(X)[0]), 4)


# ---------------------------------------------------------------------------
# Underdog "Potential Breakout" score (1-100)
# ---------------------------------------------------------------------------

def breakout_score(pe_ratio: float | None, volume_trend_pct: float,
                   sentiment_score: float, momentum_5d: float) -> int:
    """Low P/E + rising volume + positive sentiment + early momentum."""
    pe_component = 30.0
    if pe_ratio is not None and pe_ratio > 0:
        # P/E of 5 -> ~28 pts; P/E of 40+ -> near 0.
        pe_component = max(0.0, min(30.0, 34.0 - math.log(pe_ratio) * 8))
    vol_component = min(max(volume_trend_pct, -100.0), 200.0) / 200.0 * 30.0
    sent_component = (min(max(sentiment_score, -1.0), 1.0) + 1.0) / 2 * 25.0
    mom_component = min(max(momentum_5d, -20.0), 20.0) / 20.0 * 15.0
    total = pe_component + vol_component + sent_component + mom_component
    return int(round(min(100.0, max(1.0, total))))


# ---------------------------------------------------------------------------
# Engine facade used by routers and Celery tasks
# ---------------------------------------------------------------------------

class PredictionEngine:
    def predict_symbol(self, bars: list[dict], sentiment: float = 0.0,
                       pe_ratio: float | None = None) -> dict:
        frame = bars_to_frame(bars)
        if frame.empty or len(frame) < 10:
            raise ValueError("insufficient price history for prediction")
        feats = build_features(frame)
        last = feats.iloc[-1]
        vtrend = volume_trend_3d(frame)
        momentum = float(frame["close"].pct_change(5).iloc[-1] * 100)

        prob = heuristic_probability(
            rsi=float(last["rsi"]), macd_hist=float(last["macd_hist"]),
            bb_pctb=float(last["bb_pctb"]),
            return_5d=float(last["return_5d"]),
            volume_ratio=float(last["volume_ratio"]),
            sentiment=sentiment)

        if len(feats) >= MIN_TRAIN_BARS and feats["target_up"].nunique() > 1:
            try:
                model = train_updown_model(feats)
                ml_prob = trained_probability(model, last)
                # Blend heuristic + ML (hybrid model).
                prob = round(0.45 * prob + 0.55 * ml_prob, 4)
            except Exception as exc:  # noqa: BLE001 - degrade gracefully
                log_warning_train(exc)

        return {
            "prob_up": prob,
            "recommendation": recommend(prob),
            "breakout_score": breakout_score(
                pe_ratio, vtrend, sentiment, momentum),
            "volume_trend_3d": vtrend,
            "sentiment_score": sentiment,
            "pe_ratio": pe_ratio,
            "rsi": round(float(last["rsi"]), 2),
            "macd_hist": round(float(last["macd_hist"]), 4),
            "bb_pctb": round(float(last["bb_pctb"]), 4),
        }

    def compute_fear_greed(self, index_bars: list[dict]) -> dict:
        """FREE 'Fear & Greed' index computed from index momentum,
        volatility and RSI breadth - no external API required."""
        frame = bars_to_frame(index_bars)
        if frame.empty or len(frame) < 30:
            return {"score": 50, "label": "Neutral", "components": {}}
        close = frame["close"]
        rsi = float(compute_rsi(close).iloc[-1])
        ret20 = float((close.iloc[-1] / close.iloc[-21] - 1) * 100)
        daily = close.pct_change().dropna()
        vol = float(daily.tail(20).std() * 100)
        momentum_pts = min(max(ret20, -12.0), 12.0) / 12.0 * 100
        rsi_pts = min(max(rsi - 50.0, -35.0), 35.0) / 35.0 * 100
        vol_pts = max(0.0, 100.0 - vol * 28)   # low vol = greed
        score = int(round(momentum_pts * 0.4 + rsi_pts * 0.3 +
                          vol_pts * 0.3))
        score = min(95, max(5, score))
        label = ("Extreme Fear" if score < 25 else
                 "Fear" if score < 45 else "Neutral" if score < 56 else
                 "Greed" if score < 76 else "Extreme Greed")
        return {"score": score, "label": label,
                "components": {"momentum": round(momentum_pts, 1),
                               "rsi_strength": round(rsi_pts, 1),
                               "low_volatility": round(vol_pts, 1)}}


def log_warning_train(error: Exception) -> None:
    from app.utils.logger import get_logger
    get_logger(__name__).warning("ml_training_failed_using_heuristic",
                                 error=str(error))


engine = PredictionEngine()
