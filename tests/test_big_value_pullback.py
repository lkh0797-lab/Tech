"""300억 장대양봉 후 눌림목 (big_value_pullback) 테스트."""
import math
import time

import numpy as np
import pandas as pd
import pytest

from chart_screener.config import Config
from chart_screener.patterns import REGISTRY, run_all
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.big_value_pullback import BigValuePullbackConfig, detect
from chart_screener.patterns.flat_base import krx_tick
from synthetic import make_context, make_ohlcv, set_bar

N = 300
CANDLE = dict(chg=0.10, vol=3_000_000, gap=0.005, wick=0.005)   # +10%, 거래량 ~10배, 거래대금 ~500억


def uptrend(n=N, seed=1, start=8000.0, end=16000.0) -> pd.DataFrame:
    """정배열 상승 추세 (20>60>120일선, 52주 고점 근처, 트렌드 템플릿 8/8 — RS 90 가정)."""
    return make_ohlcv([(0, start), (n - 1, end)], n=n, seed=seed, vol_base=300_000, noise=0.004, smooth=False)


def downtrend(n=N, seed=2) -> pd.DataFrame:
    return make_ohlcv([(0, 20000), (n - 1, 12000)], n=n, seed=seed, vol_base=300_000, noise=0.004, smooth=False)


def extend(df: pd.DataFrame, bars: list[dict]) -> pd.DataFrame:
    """df 뒤에 봉을 이어 붙인다. bars: [{open, high, low, close, volume}, ...]"""
    for b in bars:
        idx = pd.bdate_range(df.index[-1], periods=2)[1:]
        row = pd.DataFrame({k: [df[k].iloc[-1]] for k in df.columns}, index=idx)
        df = set_bar(pd.concat([df, row]), len(df), **b)
    return df


def candle_bar(prev: float, chg=0.10, vol=3_000_000, gap=0.005, wick=0.005, low=None) -> dict:
    o = prev * (1 + gap)
    c = prev * (1 + chg)
    return dict(open=o, high=c * (1 + wick), low=prev * 0.998 if low is None else low, close=c, volume=vol)


def px(prev: float, o, h, l, c, v=1_200_000) -> dict:
    """전일(장대양봉 전) 종가 prev 의 배수로 봉 지정."""
    return dict(open=prev * o, high=prev * h, low=prev * l, close=prev * c, volume=v)


def with_candle(df=None, after=(), **kw):
    """상승 추세 끝에 장대양봉 + 이후 봉들(after: 전일 종가 배수 튜플 (o, h, l, c[, v]))."""
    df = uptrend() if df is None else df
    p = float(df["close"].iloc[-1])
    df = extend(df, [candle_bar(p, **{**CANDLE, **kw})])
    df = extend(df, [px(p, *b) for b in after])
    return df, p


def run(df, rs=90, cfg=None, **kw):
    return detect(make_context(df, rs=rs, cfg=cfg, **kw))


def support_of(p, chg=0.10, gap=0.005):
    return (p * (1 + gap) + p * (1 + chg)) / 2


def is_tick(price):
    return abs(price / krx_tick(price) - round(price / krx_tick(price))) < 1e-9


# 눌림 경로: 1봉째 소폭 조정(눌림 미인정), 2봉째 저가가 지지선(≈1.0525P) +3% 이내 도달, 3봉째 지지선 위 마감
PULLBACK = [(1.10, 1.105, 1.088, 1.092), (1.09, 1.092, 1.070, 1.078), (1.076, 1.08, 1.058, 1.066)]


# ---------------------------------------------------------------- 교과서 사례
def test_registered():
    assert REGISTRY["big_value_pullback"][0] == "300억 장대양봉 후 눌림목"


def test_textbook_pullback_near_pivot():
    df, p = with_candle(after=PULLBACK)
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT
    m = r.metrics
    sup = support_of(p)
    cd = df.index[-4].strftime("%Y-%m-%d")
    assert r.start_date == m["candle_date"] == cd
    assert m["support"] == pytest.approx(sup)
    assert m["candle_change"] == pytest.approx(0.10)
    assert m["value_eok"] >= 300
    assert m["days_since_candle"] == 3
    assert m["stage2_ok"] is True and m["limit_up"] is False
    assert m["post_state"] == "pullback"
    assert m["pullback_date"] == df.index[-2].strftime("%Y-%m-%d")      # 2봉째 첫 도달
    assert m["pullback_low_vs_support"] == pytest.approx(1.058 / (sup / p) - 1, rel=1e-6)
    # 피벗 = 50%선(호가 반올림), 손절 = max(지지선 -3%, 장대양봉 저가) 호가 내림
    assert r.pivot == pytest.approx(sup, abs=krx_tick(sup)) and is_tick(r.pivot)
    fail = max(sup * 0.97, p * 0.998)
    assert r.stop <= fail < r.stop + krx_tick(fail) + 1e-6 and is_tick(r.stop)
    assert r.breakout_date is None
    assert 50 <= r.score <= 100
    assert any("눌림 매수 구간" in s for s in r.reasons)
    kinds = [(a["kind"], a.get("text") or a.get("label")) for a in r.annotations]
    assert ("marker", "300억+ · +10.0%") in kinds
    assert ("hline", "50%선 (지지)") in kinds and ("hline", "손절") in kinds
    assert ("marker", "50%선 눌림") in kinds


def test_forming_waiting_above_support():
    df, p = with_candle(after=[(1.10, 1.125, 1.095, 1.12), (1.12, 1.13, 1.11, 1.125)])   # 지지선 +5% ≈ 1.105P 위
    r = run(df)
    assert r.detected and r.stage == FORMING
    assert r.metrics["post_state"] == "waiting" and r.metrics["pullback_date"] is None
    assert r.pivot == pytest.approx(support_of(p), abs=krx_tick(p))
    assert any("지정가" in s for s in r.reasons)


def test_candle_today_is_forming():
    df, p = with_candle()
    r = run(df)
    assert r.detected and r.stage == FORMING
    assert r.metrics["days_since_candle"] == 0
    assert r.metrics["pullback_low_vs_support"] is None


def test_next_day_dip_is_not_pullback():
    """장대양봉 다음날 바로 밀린 저가는 눌림으로 치지 않는다 (2봉째부터)."""
    df, p = with_candle(after=[(1.10, 1.10, 1.06, 1.095)])
    r = run(df)
    assert r.detected and r.stage == FORMING
    assert r.metrics["pullback_date"] is None


def test_failed_below_support():
    df, p = with_candle(after=PULLBACK[:2] + [(1.06, 1.06, 1.0, 1.005)])     # 종가 < 지지선 -3%
    r = run(df)
    assert r.detected and r.stage == FAILED
    assert any("50%선 이탈" in w for w in r.warnings)
    # 실패는 이후 회복해도 유지 (구조 붕괴)
    df2 = extend(df, [px(p, 1.01, 1.09, 1.01, 1.08)])
    assert run(df2).stage == FAILED


def test_fail_line_is_candle_low_for_gap_candle():
    """갭 상승 장대양봉: 장대양봉 저가가 지지선 -3% 보다 높으면 저가가 실패선."""
    df, p = with_candle(gap=0.08, chg=0.14, low=None)
    df = set_bar(df, -1, low=p * 1.078)
    sup = (p * 1.08 + p * 1.14) / 2
    r = run(df)
    assert r.metrics["fail_line"] == pytest.approx(p * 1.078)
    assert r.metrics["fail_line"] > sup * 0.97
    df2 = extend(df, [px(p, 1.12, 1.12, 1.08, 1.10), px(p, 1.09, 1.09, 1.07, 1.077)])
    assert run(df2).stage == FAILED


def test_rebreak_breakout():
    df, p = with_candle(after=PULLBACK + [(1.07, 1.10, 1.068, 1.095), (1.10, 1.125, 1.098, 1.12)])
    r = run(df)
    assert r.detected and r.stage == BREAKOUT, (r.stage, r.warnings)
    level = max(df["high"].iloc[-6:-4])                 # 장대양봉~눌림 직전 최고가
    assert r.metrics["rebreak_level"] == pytest.approx(level)
    assert r.pivot == pytest.approx(level, abs=krx_tick(level))
    assert r.breakout_date == df.index[-1].strftime("%Y-%m-%d")
    assert any("재돌파" in s for s in r.reasons)


def test_rebreak_far_above_is_extended():
    df, p = with_candle(after=PULLBACK + [(1.10, 1.20, 1.10, 1.19)])
    r = run(df)
    assert r.stage == EXTENDED and r.metrics["post_state"] == "rebreak_extended"


def test_extended_without_pullback():
    df, p = with_candle(after=[(1.11, 1.14, 1.105, 1.13), (1.13, 1.18, 1.125, 1.175)])
    r = run(df)
    assert r.detected and r.stage == EXTENDED
    assert r.metrics["post_state"] == "extended"
    assert any("추격" in w for w in r.warnings)


def test_bounced_after_pullback():
    # +14% 장대양봉: 지지선 ≈1.0725P, 매수 구간 상단 ≈1.105P, 지지선 +5% ≈1.126P, 고가 ≈1.146P
    after = [(1.13, 1.135, 1.12, 1.125), (1.12, 1.12, 1.10, 1.11), (1.115, 1.14, 1.12, 1.135)]
    df, p = with_candle(chg=0.14, after=after)
    r = run(df)
    assert r.stage == FORMING and r.metrics["post_state"] == "bounced"
    assert r.metrics["pullback_date"] is not None


# ---------------------------------------------------------------- 연속 장대양봉
def test_cluster_uses_first_candle():
    df, p = with_candle(after=[(1.10, 1.11, 1.095, 1.105), (1.105, 1.11, 1.09, 1.10)])
    q = float(df["close"].iloc[-1])
    df = extend(df, [candle_bar(q, chg=0.09)])                # 3봉 뒤 두 번째 장대양봉
    r = run(df)
    m = r.metrics
    assert m["legs"] == 2
    assert m["candle_date"] == df.index[-4].strftime("%Y-%m-%d")
    assert m["last_leg_date"] == df.index[-1].strftime("%Y-%m-%d")
    assert m["support"] == pytest.approx(support_of(p))


def test_new_cluster_after_failure():
    df, p = with_candle(after=[(1.06, 1.06, 0.99, 1.0)])      # 다음날 바로 실패
    q = float(df["close"].iloc[-1])
    df = extend(df, [candle_bar(q, chg=0.09)])
    r = run(df)
    assert r.metrics["legs"] == 1
    assert r.metrics["candle_date"] == df.index[-1].strftime("%Y-%m-%d")


def test_old_candle_expires():
    df, p = with_candle(after=[(1.10, 1.11, 1.095, 1.10)] * 16)
    r = run(df)
    assert not r.detected
    assert any("장대양봉" in w for w in r.warnings)


# ---------------------------------------------------------------- 탈락 (관찰만)
def test_no_stage2_context_watch_only():
    df, p = with_candle(df=downtrend(), after=PULLBACK)
    r = run(df, rs=30)
    assert not r.detected and r.score == 0
    assert r.metrics["stage2_ok"] is False
    assert any("Stage 2" in w for w in r.warnings)
    assert r.stage == NEAR_PIVOT                         # 단계·지지선은 참고용으로 채움


def test_value_below_threshold():
    df, p = with_candle(vol=1_500_000, after=PULLBACK)  # 거래대금 ~260억
    r = run(df)
    assert not r.detected
    assert any("거래대금" in w for w in r.warnings)


def test_change_below_7pct():
    df, p = with_candle(chg=0.05, after=PULLBACK)
    r = run(df)
    assert not r.detected
    assert any("+7%" in w for w in r.warnings)


def test_long_upper_wick_not_candle():
    df, p = with_candle(wick=0.12, after=PULLBACK)      # 종가 위치 ≈0.44 < 0.5
    r = run(df)
    assert not r.detected
    assert any("종가 위치" in w for w in r.warnings)


def test_big_change_watch_only():
    df, p = with_candle(chg=0.18, after=[(1.17, 1.18, 1.12, 1.13)] * 3)
    r = run(df)
    assert not r.detected and r.metrics["too_big"] is True
    assert any("관찰만" in w for w in r.warnings)


def test_limit_up_support_includes_gap():
    df = uptrend()
    p = float(df["close"].iloc[-1])
    c = p * 1.30
    df = extend(df, [dict(open=c, high=c, low=c, close=c, volume=2_000_000)])   # 점상한가 (고저폭 0)
    r = run(df)
    m = r.metrics
    assert m["limit_up"] is True and m["close_pos"] == 1.0
    assert m["support"] == pytest.approx((p + c) / 2)
    assert not r.detected


def test_config_override_value_threshold():
    cfg = Config(patterns={"big_value_pullback": BigValuePullbackConfig(min_value_eok=100)})
    df, p = with_candle(vol=1_500_000, after=PULLBACK)
    assert run(df, cfg=cfg).detected


# ---------------------------------------------------------------- 워크포워드·견고성
def test_no_lookahead_truncation():
    """체결일까지 자른 결과는 이후 봉(실패 포함)을 붙여도 그 시점 판정이 바뀌지 않는다."""
    df, p = with_candle(after=PULLBACK + [(1.0, 1.0, 0.95, 0.96)])
    cut = df.iloc[:-2]
    r_cut = run(cut)
    assert r_cut.stage == NEAR_PIVOT and r_cut.metrics["pullback_date"] == cut.index[-1].strftime("%Y-%m-%d")
    assert run(df).stage == FAILED
    prev = run(df.iloc[:-3])                              # 체결 전날: 아직 눌림 없음
    assert prev.metrics["pullback_date"] is None and prev.stage == FORMING


@pytest.mark.parametrize("n", [1, 2, 5, 60])
def test_short_history(n):
    df = make_ohlcv([(0, 10000), (n, 11000)], n=n, vol_base=300_000)
    if n >= 2:
        df = set_bar(df, -1, open=float(df["close"].iloc[-2]), close=float(df["close"].iloc[-2]) * 1.1,
                     high=float(df["close"].iloc[-2]) * 1.105, volume=5_000_000)
    r = run(df)
    assert not r.detected


def test_nan_and_zero_prices():
    df, p = with_candle(after=PULLBACK)
    df.iloc[100, df.columns.get_loc("close")] = np.nan
    df.iloc[150, df.columns.get_loc("low")] = 0
    r = run(df)
    assert r.metrics.get("candle_date") is not None
    assert any("보정" in w for w in r.warnings)


def test_flat_prices():
    idx = pd.bdate_range("2023-01-02", periods=300)
    df = pd.DataFrame({"open": 5000.0, "high": 5000.0, "low": 5000.0, "close": 5000.0, "volume": 1e6}, index=idx)
    df["value"] = df["close"] * df["volume"]
    r = run(df)
    assert not r.detected and r.warnings


def test_volume_all_nan():
    """거래량이 전부 결측이어도(거래대금 열은 유지) 예외 없이 동작, 거래량 비율은 NaN."""
    df, p = with_candle(after=PULLBACK)
    df["volume"] = np.nan
    r = run(df)
    assert r.detected and r.stage == NEAR_PIVOT
    assert not math.isfinite(r.metrics["pullback_vol_ratio"]) and not math.isfinite(r.metrics["vol_mult_50d"])


def test_run_all_includes_pattern():
    df, p = with_candle(after=PULLBACK)
    out = run_all(make_context(df, rs=90), ["big_value_pullback"])
    assert out["big_value_pullback"].detected


def test_runtime_under_budget():
    df, p = with_candle(df=uptrend(n=750), after=PULLBACK)
    detect(make_context(df, rs=90))                      # 워밍업
    t0 = time.perf_counter()
    for _ in range(20):
        detect(make_context(df, rs=90))
    assert (time.perf_counter() - t0) / 20 < 0.03        # 실측 수 ms (여유 있게 30ms)
