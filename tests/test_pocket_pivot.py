"""포켓 피벗 탐지기 테스트 (합성 데이터)."""
import numpy as np
import pandas as pd
import pytest

from chart_screener.config import Config
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.pocket_pivot import PocketPivotConfig, detect
from synthetic import add_value, make_context, make_ohlcv, set_bar

UP = [(0, 10000), (200, 15000)]


def _base(wps=UP, seed=4, **kw):
    """기준 데이터: 하락일 1.2M, 상승일 1.0M 고정 → 우연한 포켓 피벗 없음."""
    df = make_ohlcv(wps, seed=seed, **kw)
    down = df["close"].diff() < 0
    df["volume"] = np.where(down, 1.2e6, 1.0e6)
    return add_value(df)


def _pp(df, i, vol=4e6, gain=0.025, low=0.993):
    c = float(df["close"].iloc[i - 1])
    return set_bar(df, i, open=c * 0.999, low=c * low, high=c * (1 + gain + 0.003), close=c * (1 + gain),
                   volume=vol)


def _quiet(df, i, f, vol=0.6e6):
    """신호 이후 조용한 봉: 전일 종가 × f 로 마감, 저거래량."""
    c = float(df["close"].iloc[i - 1])
    return set_bar(df, i, open=c, high=max(c, c * f) * 1.003, low=min(c, c * f) * 0.997, close=c * f, volume=vol)


# ---------------------------------------------------------------- (a) 교과서형
def test_textbook_last_bar():
    df = _pp(_base(), -1)
    r = detect(make_context(df, rs=90))
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT
    expected = float(df["close"].iloc[-2]) * 1.028
    assert abs(r.pivot / expected - 1) < 0.03
    assert r.pivot == pytest.approx(float(df["high"].iloc[-1]))
    entry = float(df["close"].iloc[-1])
    assert r.stop < entry and r.stop >= entry * 0.92 - 1e-6
    assert r.metrics["entry_close"] == pytest.approx(entry, abs=0.01)
    assert r.breakout_date == df.index[-1].strftime("%Y-%m-%d")
    assert r.metrics["bars_ago"] == 0 and r.metrics["vol_vs_down_max"] > 3
    assert r.score >= 60
    assert all(s.startswith("✔ ") for s in r.reasons)
    assert all(w.startswith("✘ ") for w in r.warnings)
    kinds = {a["kind"] for a in r.annotations}
    assert {"hline", "marker", "box", "segment"} <= kinds


def test_count_accumulation():
    df = _base()
    for i in (-21, -11, -1):
        df = _pp(df, i)
    r = detect(make_context(df))
    assert r.detected
    assert r.metrics["pp_count_30"] == 3
    assert any("매집" in s for s in r.reasons)


# ---------------------------------------------------------------- (b) 단계
def test_stage_breakout_one_bar_ago():
    df = _quiet(_pp(_base(), -2), -1, 0.997)
    r = detect(make_context(df))
    assert r.detected and r.stage == BREAKOUT
    assert r.metrics["bars_ago"] == 1


def test_stage_near_pivot():
    df = _pp(_base(), -4)
    for i, f in zip((-3, -2, -1), (0.998, 1.003, 0.999)):
        df = _quiet(df, i, f)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT and r.metrics["bars_ago"] == 3


def test_stage_extended():
    df = _pp(_base(), -4)
    for i in (-3, -2, -1):
        df = _quiet(df, i, 1.03)
    r = detect(make_context(df))
    assert r.detected and r.stage == EXTENDED


def test_stage_forming():
    # 넓은 범위의 신호일 후 피벗 -5% 아래로 눌렸지만 손절가(신호일 저가) 위
    df = _base()
    c = float(df["close"].iloc[-4])
    df = set_bar(df, -3, open=c * 0.999, low=c * 0.985, high=c * 1.06, close=c * 1.05, volume=4e6)
    df = _quiet(df, -2, 0.97)
    df = set_bar(df, -1, open=c * 1.02, high=c * 1.021, low=c * 0.994, close=c * 0.995, volume=0.6e6)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.stage == FORMING
    assert r.stop < float(df["close"].iloc[-1]) < r.pivot * 0.95


def test_stage_failed():
    df = _pp(_base(), -3)
    lo = float(df["low"].iloc[-3])
    df = _quiet(df, -2, 0.985)
    c = float(df["close"].iloc[-2])
    df = set_bar(df, -1, open=c, high=c * 1.001, low=lo * 0.97, close=lo * 0.98, volume=1.1e6)
    r = detect(make_context(df))
    assert r.detected and r.stage == FAILED


def test_signal_older_than_window_not_detected():
    df = _pp(_base(), -7)
    for i in range(-6, 0):
        df = _quiet(df, i, 1.0)
    assert not detect(make_context(df)).detected


def test_walk_forward_no_lookahead():
    df = _pp(_base(), -1)
    assert not detect(make_context(df.iloc[:-1])).detected   # 신호 전날까지 → 없음
    assert detect(make_context(df)).detected


# ---------------------------------------------------------------- (c) 음성 사례
def test_volume_below_down_day_max():
    df = _base()
    c = float(df["close"].iloc[-6])
    df = set_bar(df, -5, open=c, high=c * 1.002, low=c * 0.985, close=c * 0.99, volume=5e6)  # 대량 하락일
    df = _pp(df, -1, vol=4e6)
    r = detect(make_context(df))
    assert not r.detected
    assert any("하락일 최대 거래량" in w for w in r.warnings)


def test_down_day_with_big_volume_is_not_pp():
    df = _base()
    c = float(df["close"].iloc[-2])
    df = set_bar(df, -1, open=c * 1.01, high=c * 1.012, low=c * 0.985, close=c * 0.99, volume=5e6)
    assert not detect(make_context(df)).detected


def test_close_in_lower_part_of_range():
    df = _base()
    c = float(df["close"].iloc[-2])
    df = set_bar(df, -1, open=c * 0.999, high=c * 1.04, low=c * 0.995, close=c * 1.004, volume=4e6)
    r = detect(make_context(df))
    assert not r.detected
    _only_reason(r, "종가 위치")


def test_downtrend_rejected():
    df = _pp(_base([(0, 15000), (200, 10000)]), -1)
    r = detect(make_context(df))
    assert not r.detected
    assert any("상승 추세 아님" in w for w in r.warnings)


def test_below_200dma_bottom_fishing_rejected():
    # 하락 후 반등: 50일선 위·50일선 상승이지만 200일선 아래 (Stage 2 아님)
    df = _pp(_base([(0, 15000), (150, 9000), (200, 10500)]), -1)
    r = detect(make_context(df))
    assert not r.detected
    _only_reason(r, "Stage 2")
    cfg = Config(patterns={"pocket_pivot": PocketPivotConfig(require_stage2=False)})
    assert detect(make_context(df, cfg=cfg)).detected


def test_too_far_above_50dma_rejected():
    # 가파른 상승: 10일선 근처(전일 이격 <5%)지만 종가가 50일선 +25% 초과
    df = _base([(0, 10000), (140, 12000), (200, 26000)], smooth=False)
    c = float(df["close"].iloc[-2])
    s10 = float(df["close"].iloc[-11:-1].mean())
    s50 = float(df["close"].iloc[-50:].mean())
    assert c / s10 - 1 < 0.05 and c / s50 - 1 > 0.25
    df = set_bar(df, -1, open=c * 0.999, high=c * 1.028, low=s10 * 1.005, close=c * 1.025, volume=4e6)
    r = detect(make_context(df))
    assert not r.detected
    _only_reason(r, "50일선 대비")


def _only_reason(r, key):
    why = [w for w in r.warnings if "거래량 조건 충족했으나" in w]
    assert len(why) == 1 and key in why[0], why


def test_extended_above_10dma_rejected():
    # 급등으로 전일 종가가 10일선 +5% 초과 — 당일 저가는 10일선까지 눌려(근접 조건 충족) 이격만 위반
    df = _base([(0, 10000), (190, 14000), (199, 15800), (200, 15800)])
    c = float(df["close"].iloc[-2])
    s10 = float(df["close"].iloc[-11:-1].mean())
    assert c / s10 - 1 > 0.05
    df = set_bar(df, -1, open=c, high=c * 1.02, low=s10 * 1.01, close=c * 1.015, volume=4e6)
    r = detect(make_context(df))
    assert not r.detected
    _only_reason(r, "이격")


def test_v_shape_from_deep_below_50dma_rejected():
    # 장기 상승 → 50일선 -9% 급락 → 8봉 만에 수직 회복, 50일선·10일선 부근에서 포켓 피벗 (V자 조건만 위반)
    df = _base([(0, 10000), (180, 16000), (185, 13800), (188, 13800), (196, 15500), (200, 15500)], smooth=False)
    df = _pp(df, -1, low=0.99)
    r = detect(make_context(df))
    assert not r.detected
    _only_reason(r, "V자")


def test_far_from_moving_averages_rejected():
    df = _base()
    c = float(df["close"].iloc[-2])
    df = set_bar(df, -1, open=c * 1.035, high=c * 1.06, low=c * 1.035, close=c * 1.055, volume=4e6)  # 갭 상승
    r = detect(make_context(df))
    assert not r.detected
    _only_reason(r, "근처가 아님")


# ---------------------------------------------------------------- (d) 견고성
def test_short_history():
    df = make_ohlcv([(0, 100), (59, 120)], seed=1)
    r = detect(make_context(df))
    assert not r.detected and r.warnings[0].startswith("✘ ")


def test_flat_line():
    df = make_ohlcv([(0, 5000), (300, 5000)], noise=0.0, wick=0.0)
    r = detect(make_context(df))
    assert not r.detected and r.warnings


def test_random_walk_no_raise():
    for seed in range(5):
        rng = np.random.default_rng(seed)
        c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.02, 400)))
        idx = pd.bdate_range("2022-01-03", periods=400)
        df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                           "volume": rng.integers(1e5, 1e6, 400).astype(float)}, index=idx)
        df["value"] = df["close"] * df["volume"]
        r = detect(make_context(df))
        assert isinstance(r.detected, bool)


def test_nan_zero_volume_and_limit_up_no_raise():
    df = _pp(_base(), -1)
    df.iloc[150, df.columns.get_loc("close")] = np.nan
    df.iloc[160, df.columns.get_loc("low")] = 0.0
    r = detect(make_context(df, rs=None))
    assert isinstance(r.detected, bool)
    df2 = _base()
    df2["volume"] = 0.0
    df2["value"] = 0.0
    assert not detect(make_context(df2)).detected
    # 상한가 잠김 봉 (시가=고가=저가=종가, +30%) — 범위 0
    df3 = _base()
    c = float(df3["close"].iloc[-2])
    df3 = set_bar(df3, -1, open=c * 1.3, high=c * 1.3, low=c * 1.3, close=c * 1.3, volume=4e6)
    assert isinstance(detect(make_context(df3)).detected, bool)


def test_config_override_lookback():
    df = _pp(_base(), -4)
    for i, f in zip((-3, -2, -1), (0.998, 1.003, 0.999)):
        df = _quiet(df, i, f)
    cfg = Config(patterns={"pocket_pivot": PocketPivotConfig(lookback_bars=2)})
    assert not detect(make_context(df, cfg=cfg)).detected


def test_heavy_reversal_bar_caveat():
    """직전 10일 안의 '상승 마감이지만 장중 반전(하단 마감)' 대량 봉은 하락일이 아니어도 매물 경고·감점."""
    clean = detect(make_context(_pp(_base(), -1)))
    df = _base()
    c = float(df["close"].iloc[-5])
    df = set_bar(df, -4, open=c * 1.15, high=c * 1.2, low=c * 1.004, close=c * 1.005, volume=9e6)
    df = _pp(df, -1)
    r = detect(make_context(df))
    assert r.detected
    assert any("매물" in w for w in r.warnings)
    assert r.score < clean.score


def test_halt_and_volume_jump_caveats():
    df = _pp(_base(), -1)
    df.attrs["halt_dates"] = [df.index[-5].strftime("%Y-%m-%d")]
    r = detect(make_context(df))
    assert r.detected and any("거래정지" in w for w in r.warnings)
    df2 = _base()
    df2.loc[df2.index[-12]:, "volume"] *= 8    # 액면분할로 원시 거래량 수준 급변
    df2 = _pp(add_value(df2), -1, vol=4e7)
    r2 = detect(make_context(df2))
    assert r2.detected and any("거래량 수준 급변" in w for w in r2.warnings)


# ---------------------------------------------------------------- 리뷰 회귀 테스트
def test_reversed_signal_is_not_breakout():
    """신호 직후라도 종가가 매수가 -3%·피벗 -5% 아래로 되밀리면 breakout 이 아니다 (이글루형)."""
    df = _pp(_base(), -2, low=0.96)          # 신호일 저가(손절)가 매수가 -6% 부근 → 되밀려도 failed 아님
    entry = float(df["close"].iloc[-2])
    df = set_bar(df, -1, open=entry * 0.99, high=entry * 0.995, low=entry * 0.94, close=entry * 0.945, volume=1.1e6)
    assert float(df["close"].iloc[-1]) > float(df["low"].iloc[-2])
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.stage == FORMING and r.metrics["bars_ago"] == 1
    assert any("돌파 단계 아님" in w for w in r.warnings)
    # 피벗 -5% 이내지만 매수가 -3% 아래 → near_pivot
    df2 = _pp(_base(), -2, gain=0.04)
    e2 = float(df2["close"].iloc[-2])
    df2 = set_bar(df2, -1, open=e2, high=e2 * 1.002, low=e2 * 0.962, close=e2 * 0.965, volume=1.1e6)
    r2 = detect(make_context(df2))
    assert r2.stage == NEAR_PIVOT and r2.pivot * 0.95 <= float(df2["close"].iloc[-1]) < e2 * 0.97


def test_signal_day_long_upper_wick_not_breakout():
    """신호일 자체가 긴 윗꼬리(종가가 고가 -8%)면 신호일이라도 breakout 이 아니다."""
    df = _base()
    c = float(df["close"].iloc[-2])
    df = set_bar(df, -1, open=c * 0.999, low=c * 0.995, high=c * 1.17, close=c * 1.07, volume=4e6)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.metrics["bars_ago"] == 0 and r.stage == FORMING


def test_near_test_uses_prior_day_moving_average():
    """'이평선 근처'는 시가 시점의 선(전일 10일선) 기준 — 신호일 대량 상승 종가가 끌어올린 당일 10일선은 쓰지 않는다."""
    df = _base()
    s10p = float(df["close"].iloc[-11:-1].mean())
    c = float(df["close"].iloc[-2])
    low = s10p * 1.03
    close = c * 1.12
    df = set_bar(df, -1, open=low, low=low, high=close * 1.004, close=close, volume=4e6)
    s10_same = float(df["close"].iloc[-10:].mean())
    assert low / s10_same - 1 < 0.02 < low / s10p - 1      # 당일 10일선 기준이면 '근처'(허용 2%)
    r = detect(make_context(df))
    assert not r.detected
    _only_reason(r, "근처가 아님")


def test_heavy_reversal_bar_scaled_penalty_and_exclusion():
    """직전 10일의 하단 마감 대량 반전봉: 신호일 대비 배수에 비례해 감점, 3배 초과면 분산 직후로 제외."""
    def with_reversal(mult):
        df = _base()
        c = float(df["close"].iloc[-5])
        df = set_bar(df, -4, open=c * 1.15, high=c * 1.2, low=c * 1.004, close=c * 1.005, volume=4e6 * mult)
        return _pp(df, -1)
    clean = detect(make_context(_pp(_base(), -1)))
    mild, heavy = detect(make_context(with_reversal(1.5))), detect(make_context(with_reversal(2.8)))
    assert mild.detected and heavy.detected
    assert -15 <= heavy.metrics["score_supply"] < mild.metrics["score_supply"] <= -5
    assert heavy.score < mild.score < clean.score
    dump = detect(make_context(with_reversal(4.0)))           # 동국제강형: 신호일의 4배 반전봉
    assert not dump.detected
    _only_reason(dump, "분산 직후")


@pytest.mark.parametrize("scale", [0.13, 1.0, 7.3, 41.0])
def test_stops_on_krx_tick(scale):
    df = _base()
    for k in ("open", "high", "low", "close"):
        df[k] = df[k] * scale
    df = _pp(add_value(df), -1)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    t = _krx_tick(r.stop)
    assert abs(r.stop / t - round(r.stop / t)) < 1e-9, r.stop
    assert r.stop >= r.metrics["entry_close"] * 0.92 - 1e-6     # -8% 한도는 올림


def test_fifty_day_stop_on_tick_and_capped():
    """50일선 포켓 피벗: 손절 = min(신호일 저가, 50일선 -1%) 를 호가 단위로 내림, 매수가 -8% 한도(올림)."""
    df = _base([(0, 8000), (100, 10000), (270, 16000), (300, 15300), (315, 15300)])
    s50p = float(df["close"].iloc[-51:-1].mean())
    close = max(float(df["close"].iloc[-2]) * 1.02, s50p * 1.02)
    df = set_bar(df, -1, open=s50p * 1.002, low=s50p * 0.996, high=close * 1.004, close=close, volume=4e6)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.metrics["ref_ma"] == "50일선"
    t = _krx_tick(r.stop)
    assert abs(r.stop / t - round(r.stop / t)) < 1e-9
    assert r.metrics["entry_close"] * 0.92 - 1e-6 <= r.stop < float(df["low"].iloc[-1])


def _krx_tick(p):
    from chart_screener.patterns.double_bottom import krx_tick
    return krx_tick(p)
