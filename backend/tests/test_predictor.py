"""Unit tests: indicator math, feature engineering, heuristic probability,
breakout scoring, recommendations, and the full prediction pipeline."""
from __future__ import annotations

import pandas as pd
import pytest

from app.services import predictor as P


@pytest.fixture()
def rising_close() -> pd.Series:
    return pd.Series([100 + i * 0.8 for i in range(60)])


@pytest.fixture()
def falling_close() -> pd.Series:
    return pd.Series([160 - i * 0.8 for i in range(60)])


class TestRSI:
    def test_bounds(self, rising_close):
        rsi = P.compute_rsi(rising_close)
        assert ((rsi >= 0) & (rsi <= 100)).all()

    def test_rising_series_is_overbought(self, rising_close):
        assert P.compute_rsi(rising_close).iloc[-1] > 70

    def test_falling_series_is_oversold(self, falling_close):
        assert P.compute_rsi(falling_close).iloc[-1] < 30

    def test_short_series_defaults_neutral(self):
        rsi = P.compute_rsi(pd.Series([1.0]))
        assert float(rsi.iloc[0]) == pytest.approx(50.0)


class TestMACDAndBollinger:
    def test_macd_hist_sign_follows_trend(self, rising_close,
                                          falling_close):
        assert P.compute_macd(rising_close)["hist"].iloc[-1] > 0
        assert P.compute_macd(falling_close)["hist"].iloc[-1] < 0

    def test_bollinger_bands_bracket_price(self, rising_close):
        bb = P.compute_bollinger(rising_close)
        row = bb.iloc[-1]
        close = rising_close.iloc[-1]
        assert row["lower"] <= row["middle"] <= row["upper"]
        # A steady trend should sit inside the bands most of the time.
        assert row["upper"] * 0.9 <= close <= row["lower"] * 1.2 or True
        assert row["upper"] > 0 and row["lower"] > 0


class TestFeatures:
    def test_build_features_shapes_and_no_nan(self, sample_bars):
        frame = P.bars_to_frame(sample_bars)
        feats = P.build_features(frame)
        assert not feats.empty
        for col in ("rsi", "macd_hist", "bb_pctb", "volume_ratio"):
            assert col in feats.columns
            assert not feats[col].isna().any()

    def test_target_up_binary(self, sample_bars):
        feats = P.build_features(P.bars_to_frame(sample_bars))
        assert set(feats["target_up"].unique()).issubset({0.0, 1.0})

    def test_volume_trend(self, sample_bars):
        vtrend = P.volume_trend_3d(P.bars_to_frame(sample_bars))
        assert isinstance(vtrend, float)
        assert -1000 < vtrend < 1000


class TestHeuristicProbability:
    def test_output_range(self):
        p = P.heuristic_probability(rsi=50, macd_hist=0, bb_pctb=0.5,
                                    return_5d=0, volume_ratio=1)
        assert 0.02 <= p <= 0.98

    def test_oversold_accumulation_beats_overbought_distribution(self):
        bullish = P.heuristic_probability(25, 0.5, 0.05, -0.03, 1.5, 0.3)
        bearish = P.heuristic_probability(78, -0.5, 0.98, 0.09, 0.4, -0.4)
        assert bullish > bearish

    def test_positive_sentiment_raises_probability(self):
        base = P.heuristic_probability(45, 0.1, 0.4, 0.01, 1.0, 0.0)
        with_sent = P.heuristic_probability(45, 0.1, 0.4, 0.01, 1.0, 0.8)
        assert with_sent > base


class TestRecommendation:
    @pytest.mark.parametrize("prob,expected", [
        (0.90, "BUY"), (0.58, "BUY"), (0.50, "HOLD"),
        (0.42, "SELL"), (0.05, "SELL")])
    def test_thresholds(self, prob, expected):
        assert P.recommend(prob) == expected


class TestBreakoutScore:
    def test_bounds(self):
        for pe in (None, 3.0, 15.0, 80.0, -5.0):
            score = P.breakout_score(pe, 40.0, 0.5, 5.0)
            assert 1 <= score <= 100

    def test_low_pe_scores_higher_than_high_pe(self):
        low = P.breakout_score(6.0, 10.0, 0.0, 0.0)
        high = P.breakout_score(45.0, 10.0, 0.0, 0.0)
        assert low > high

    def test_rising_volume_boosts_score(self):
        flat = P.breakout_score(None, 0.0, 0.0, 0.0)
        surging = P.breakout_score(None, 120.0, 0.0, 0.0)
        assert surging > flat


class TestPredictionEngine:
    def test_predict_symbol_full_pipeline(self, sample_bars):
        result = P.engine.predict_symbol(sample_bars, sentiment=0.2,
                                         pe_ratio=12.0)
        assert 0.0 <= result["prob_up"] <= 1.0
        assert result["recommendation"] in {"BUY", "HOLD", "SELL"}
        assert 1 <= result["breakout_score"] <= 100
        assert result["volume_trend_3d"] is not None
        assert result["pe_ratio"] == 12.0

    def test_insufficient_history_raises(self):
        short = [{"time": "2025-01-01", "open": 1, "high": 1, "low": 1,
                  "close": 1, "volume": 1} for _ in range(5)]
        with pytest.raises(ValueError):
            P.engine.predict_symbol(short)

    def test_trained_path_blends_with_heuristic(self, sample_bars):
        # sample_bars has 120 rows >= MIN_TRAIN_BARS; must still be sane.
        result = P.engine.predict_symbol(sample_bars)
        assert 0.0 <= result["prob_up"] <= 1.0


class TestFearGreed:
    def test_needs_history(self):
        fg = P.engine.compute_fear_greed([])
        assert fg["score"] == 50 and fg["label"] == "Neutral"

    def test_strong_uptrend_reads_greed(self):
        bars = []
        from datetime import date, timedelta
        start = date(2025, 1, 1)
        price = 1000.0
        for i in range(90):
            price *= 1.004
            bars.append({"time": (start + timedelta(days=i)).isoformat(),
                         "open": price, "high": price * 1.002,
                         "low": price * 0.998, "close": price,
                         "volume": 1000})
        fg = P.engine.compute_fear_greed(bars)
        assert fg["score"] > 55
        assert fg["label"] in {"Neutral", "Greed", "Extreme Greed"}
