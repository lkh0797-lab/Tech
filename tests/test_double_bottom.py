"""더블 바텀(W) 탐지기 테스트 (합성 데이터)."""
import numpy as np
import pandas as pd
import pytest

from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.double_bottom import DoubleBottomConfig, detect, krx_tick
from synthetic import make_context, make_ohlcv, set_bar

# 선행 상승 +67% → 왼쪽 고점 10000 → A 7800 → M 9200 → B 7700 (언더컷 1.3%) → 회복
LEFT = [(0, 6000), (120, 10000), (150, 7800), (172, 9200), (195, 7700)]
VOLS = [(190, 200, 1.6), (215, 300, 0.6)]   # 2차 저점 대량 거래, 피벗 직전 거래량 감소


def _w(right, seed=1, vols=VOLS, **kw):
    return make_ohlcv(LEFT + right, seed=seed, vol_segments=vols, **kw)


def _mid_high(df):
    return float(df["high"].iloc[160:185].max())


def _breakout(df, i, close, vol=3.5e6):
    prev = float(df["close"].iloc[i - 1])
    return set_bar(df, i, open=prev * 1.002, high=close * 1.005, low=prev * 0.998, close=close, volume=vol)


# ---------------------------------------------------------------- (a) 교과서형
def test_textbook_near_pivot():
    df = _w([(225, 9000)])
    r = detect(make_context(df, rs=88))
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT
    assert abs(r.pivot / _mid_high(df) - 1) < 0.03
    assert abs(r.pivot / 9200 - 1) < 0.03
    m = r.metrics
    assert m["undercut_pct"] < 0                     # 언더컷
    assert 20 < m["depth_pct"] < 32
    assert m["duration_bars"] >= 35
    top = df["high"].iloc[100:140]
    assert df["high"].loc[r.start_date] >= top.max() * 0.97 and r.start_date >= top.idxmax().strftime("%Y-%m-%d")
    assert r.stop < r.pivot and r.stop >= r.pivot * 0.92 - 1e-6
    assert r.score >= 70
    assert all(s.startswith("✔ ") for s in r.reasons)
    kinds = {a["kind"] for a in r.annotations}
    assert {"hline", "segment", "marker"} <= kinds


def test_pivot_is_mid_high_plus_tick():
    df = _w([(225, 9000)])
    r = detect(make_context(df))
    mh = r.metrics["mid_high"]
    assert r.pivot == pytest.approx(mh + krx_tick(mh), abs=0.01)


# ---------------------------------------------------------------- (b) 단계
def test_stage_forming():
    df = _w([(225, 8400)])
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.stage == FORMING


def test_stage_breakout():
    df = _w([(225, 9000)], n=227)
    piv = _mid_high(df)
    df = _breakout(df, -1, piv * 1.025)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT
    assert r.breakout_date == df.index[-1].strftime("%Y-%m-%d")
    assert r.metrics["breakout_vol_ratio"] >= 1.4
    assert any("돌파" in s for s in r.reasons)
    assert any(a["kind"] == "marker" and a["text"] == "돌파" for a in r.annotations)


def test_stage_extended():
    df = _w([(225, 9000)], n=230)
    piv = _mid_high(df)
    df = _breakout(df, -4, piv * 1.02)
    for k, f in zip((-3, -2, -1), (1.05, 1.08, 1.11)):
        df = set_bar(df, k, open=piv * (f - 0.02), high=piv * (f + 0.005), low=piv * (f - 0.025), close=piv * f)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.stage == EXTENDED


def test_stage_failed():
    df = _w([(225, 9000)], n=230)
    piv = _mid_high(df)
    df = _breakout(df, -4, piv * 1.02)
    df = set_bar(df, -3, open=piv * 1.01, high=piv * 1.02, low=piv * 0.99, close=piv * 0.995)
    df = set_bar(df, -2, open=piv * 0.99, high=piv * 0.995, low=piv * 0.95, close=piv * 0.96)
    df = set_bar(df, -1, open=piv * 0.96, high=piv * 0.965, low=piv * 0.93, close=piv * 0.94)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.stage == FAILED


def test_handle_detected_and_reported():
    df = _w([(215, 9150), (224, 8800), (232, 8950)])
    r = detect(make_context(df))
    assert r.detected, r.warnings
    assert r.metrics["handle"] is True
    assert r.metrics["handle_pivot"] <= r.pivot
    assert r.stage == NEAR_PIVOT
    assert any(a["kind"] == "box" for a in r.annotations)


def test_second_low_above_first_is_weaker():
    good = detect(make_context(_w([(225, 9000)])))
    df = make_ohlcv([(0, 6000), (120, 10000), (150, 7800), (172, 9200), (195, 7920), (225, 9000)],
                    seed=1, vol_segments=VOLS)
    weak = detect(make_context(df))
    assert weak.detected, weak.warnings
    assert weak.metrics["undercut_pct"] > 0
    assert weak.score < good.score
    assert any("언더컷 없는" in w for w in weak.warnings)


def test_stale_breakout_not_detected():
    """오래전 돌파 후 크게 상승한 W 는 현재 패턴이 아님 (미래 참조/과거 패턴 방지)."""
    df = make_ohlcv(LEFT + [(225, 9000), (228, 9700), (290, 13000)], seed=1, vol_segments=VOLS)
    r = detect(make_context(df))
    assert not r.detected


def test_walk_forward_truncation_consistent():
    """잘린 데이터(과거 시점)에서도 같은 W 를 인식하고, 2차 저점 이전에는 탐지하지 않는다."""
    df = _w([(225, 9000)])
    early = detect(make_context(df.iloc[:190]))      # 2차 저점 형성 전
    assert not early.detected
    mid = detect(make_context(df.iloc[:221]))
    assert mid.detected and mid.stage in (FORMING, NEAR_PIVOT)


# ---------------------------------------------------------------- (c) 음성 사례
@pytest.mark.parametrize("wps,why", [
    # 선행 상승 없음 (횡보 후 W)
    ([(0, 10000), (120, 10000), (150, 7800), (172, 9200), (195, 7700), (225, 9000)], "선행 상승"),
    # 깊이 과다 (45%)
    ([(0, 6000), (120, 10000), (150, 5500), (172, 8000), (195, 5450), (225, 7600)], "깊이"),
    # 2차 저점이 1차 저점을 10% 이상 붕괴
    ([(0, 6000), (120, 10000), (150, 7800), (172, 9200), (195, 7000), (225, 8700)], "2차 저점"),
    # 2차 저점이 1차 저점보다 8% 위 (W 아님)
    ([(0, 6000), (120, 10000), (150, 7800), (172, 9200), (195, 8450), (225, 9000)], "2차 저점"),
    # 중간 고점이 왼쪽 고점 이상
    ([(0, 6000), (120, 10000), (150, 7800), (172, 10150), (195, 7700), (225, 9500)], "중간 고점"),
    # 중간 고점 반등이 너무 약함 (하락폭 20% 되돌림)
    ([(0, 6000), (120, 10000), (150, 7800), (172, 8250), (195, 7700), (225, 8100)], "반등"),
    # 기간 7주 미만 (뾰족한 왼쪽 고점 → 현재 26봉)
    ([(0, 6000), (120, 10000), (126, 8200), (132, 9300), (140, 8100), (146, 9100)], "기간"),
])
def test_negative_cases(wps, why):
    df = make_ohlcv(wps, seed=1, vol_segments=VOLS, smooth=False)
    r = detect(make_context(df))
    assert not r.detected, (r.metrics, r.reasons)
    assert r.warnings and r.warnings[0].startswith("✘ ")
    if why:
        assert why in r.warnings[0]


def test_v_bottom_is_not_w():
    df = make_ohlcv([(0, 6000), (120, 10000), (160, 7800), (200, 9500)], seed=2)
    assert not detect(make_context(df)).detected


def test_still_falling_second_low_not_detected():
    df = make_ohlcv(LEFT + [(197, 7650)], seed=1)
    r = detect(make_context(df))
    assert not r.detected


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
    rng = np.random.default_rng(7)
    for seed in range(5):
        rng = np.random.default_rng(seed)
        c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.02, 600)))
        idx = pd.bdate_range("2022-01-03", periods=600)
        df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                           "volume": rng.integers(1e5, 1e6, 600).astype(float)}, index=idx)
        df["value"] = df["close"] * df["volume"]
        r = detect(make_context(df))
        assert isinstance(r.detected, bool)


def test_nan_and_zero_volume_no_raise():
    df = _w([(225, 9000)])
    df.iloc[100, df.columns.get_loc("close")] = np.nan
    df.iloc[170, df.columns.get_loc("high")] = np.nan
    df["volume"] = 0.0
    df["value"] = 0.0
    r = detect(make_context(df, rs=None))
    assert isinstance(r.detected, bool)


def test_constant_volume_no_raise():
    df = _w([(225, 9000)])
    df["volume"] = 1e6
    r = detect(make_context(df))
    assert r.detected


def test_config_override():
    from chart_screener.config import Config
    cfg = Config(patterns={"double_bottom": DoubleBottomConfig(min_duration=200)})
    r = detect(make_context(_w([(225, 9000)]), cfg=cfg))
    assert not r.detected


def test_halt_and_volume_jump_caveats():
    df = _w([(225, 9000)])
    df.attrs["halt_dates"] = [df.index[180].strftime("%Y-%m-%d")]
    r = detect(make_context(df))
    assert r.detected and any("거래정지" in w for w in r.warnings)
    df2 = _w([(225, 9000)])
    df2.loc[df2.index[200]:, "volume"] *= 10   # 액면분할 후 원시 거래량 급증 모사
    r2 = detect(make_context(df2))
    assert any("거래량 수준 급변" in w for w in r2.warnings)


# ---------------------------------------------------------------- 리뷰 회귀 테스트
def _right_failed_handle(seed):
    """W 후 오른쪽이 피벗권(9180)까지 회복 → 13% 되밀림(B 보다 +4% 위 유지) → 새 오른쪽 고점 → 피벗 돌파."""
    wps = LEFT + [(207, 9180), (217, 8000), (229, 9230), (233, 9600)]
    return make_ohlcv(wps, seed=seed, noise=0.003, wick=0.004)


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_failed_handle_not_resurrected(seed):
    """손잡이 실패(피벗권 도달 후 12% 초과 되밀림)는 누적 판정 — 이후 새 고점·피벗 돌파로 되살아나지 않는다."""
    df = _right_failed_handle(seed)
    rh, pl = float(df["high"].iloc[200:212].max()), float(df["low"].iloc[212:222].min())
    assert pl / rh - 1 < -0.12 and pl > float(df["low"].iloc[190:200].min())   # B 위에서 12% 초과 되밀림
    for k in (222, 226, 230, 234):   # 되밀림 직후 / 회복 중 / 새 오른쪽 고점 / 피벗 위 종가
        r = detect(make_context(df.iloc[:k]))
        assert not r.detected, (k, r.stage, r.metrics.get("right_bars"))
    r = detect(make_context(df))
    assert any("손잡이 실패" in w for w in r.warnings), r.warnings


def test_rounded_top_uses_real_left_high():
    """둥근 천장: 왼쪽 고점은 실제 최고가(베이스 천장) — 중간 고점이 그보다 3~5% 낮은 W 를 놓치지 않는다."""
    hits = 0
    for seed in range(6):
        wps = [(0, 6000), (120, 10000), (128, 9900), (136, 9750), (160, 7800), (182, 9600), (205, 7700), (235, 9200)]
        df = make_ohlcv(wps, seed=seed, noise=0.004, wick=0.005)
        r = detect(make_context(df, rs=85))
        if not r.detected:
            continue
        hits += 1
        top = df["high"].iloc[100:160]
        assert r.start_date == top.idxmax().strftime("%Y-%m-%d")
        assert r.metrics["left_high"] == pytest.approx(float(top.max()))
        assert r.metrics["depth_pct"] == pytest.approx((1 - float(df["low"].iloc[190:215].min()) / top.max()) * 100,
                                                       abs=0.2)
        assert 3.0 <= r.metrics["mid_below_left_pct"] <= 6.5
    assert hits >= 5


def _spike_bar(df, i, mult):
    """i 번째 봉을 전일 종가 × mult 로 마감하는 1봉 스파이크(상한가성)로 바꾼다."""
    c = float(df["close"].iloc[i - 1])
    return set_bar(df, i, open=c * 1.01, high=c * mult, low=c * 0.995, close=c * mult * 0.995, volume=4e6)


def test_one_bar_spike_left_high_replaced():
    """왼쪽 고점이 1봉 스파이크면 실제 거래 수준(3봉 중앙값 고가)을 왼쪽 고점으로 쓴다 — 깊이 과대평가 방지."""
    df = make_ohlcv([(0, 6000), (110, 10000), (128, 10000), (150, 7800), (172, 9200), (195, 7700), (225, 9000)],
                    seed=1, vol_segments=VOLS)
    df = _spike_bar(df, 124, 1.18)
    r = detect(make_context(df))
    assert r.detected, r.warnings
    plateau = float(df["high"].iloc[110:140].drop(df.index[124]).max())
    assert r.metrics["left_high_raw"] == pytest.approx(float(df["high"].iloc[124]))
    assert r.metrics["left_high"] <= plateau + 1e-6 and r.metrics["left_spike_pct"] > 8
    assert r.metrics["depth_pct"] < 29                    # 스파이크 고가 기준이면 ~35%
    assert any("스파이크" in w for w in r.warnings)


def test_spike_top_over_range_is_not_w():
    """중간 고점보다 높은 것이 1봉 스파이크뿐인 박스권(파크시스템스형)은 W 가 아니다."""
    for seed in (1, 2, 3):
        df = make_ohlcv([(0, 6000), (100, 9000), (130, 9100), (150, 7800), (172, 9350), (195, 7700), (225, 9200)],
                        seed=seed, vol_segments=VOLS)
        df = _spike_bar(df, 128, 1.18)   # 9,100 박스에서 +18% 1봉 스파이크 후 급락 — 스파이크 고가 기준이면 W 로 보임
        r = detect(make_context(df))
        assert not r.detected, (seed, r.metrics, r.reasons)
        assert "중간 고점이 왼쪽 고점" in r.warnings[0]


def _launch_case(rise_bars, seed=1):
    """7,700 박스(1차 저점 7,800 아래 종가)에서 rise_bars 봉 만에 10,000 으로 상승한 뒤 W."""
    t = 140 + rise_bars
    wps = [(0, 6000), (100, 7700), (140, 7700), (t, 10000), (t + 25, 7800), (t + 47, 9200), (t + 70, 7700),
           (t + 100, 9000)]
    return make_ohlcv(wps, seed=seed, noise=0.003, wick=0.004, smooth=False)


def test_launch_from_base_low_rejected():
    """왼쪽 고점이 1차 저점 아래 종가에서 몇 봉 만에 치솟은 것이면(저점에서 출발한 스파이크) W 아님."""
    for seed in (1, 2, 3):
        assert not detect(make_context(_launch_case(3, seed))).detected
        ok = detect(make_context(_launch_case(30, seed)))     # 대조군: 30봉에 걸친 정상 선행 상승
        assert ok.detected, ok.warnings


def test_score_follow_through_penalty():
    near = detect(make_context(_w([(225, 9000)], n=230)))
    df = _w([(225, 9000)], n=230)
    piv = _mid_high(df)
    df = _breakout(df, -4, piv * 1.02)
    df = set_bar(df, -3, open=piv * 1.01, high=piv * 1.02, low=piv * 0.99, close=piv * 0.995)
    df = set_bar(df, -2, open=piv * 0.99, high=piv * 0.995, low=piv * 0.95, close=piv * 0.96)
    df = set_bar(df, -1, open=piv * 0.96, high=piv * 0.965, low=piv * 0.93, close=piv * 0.94)
    failed = detect(make_context(df))
    assert failed.stage == FAILED and failed.metrics["score_follow"] == -20
    assert failed.score < near.score - 10
    df2 = _w([(225, 9000)], n=232)
    df2 = _breakout(df2, -6, piv * 1.02)
    for k, f in zip((-5, -4, -3, -2, -1), (1.08, 1.14, 1.20, 1.26, 1.32)):
        df2 = set_bar(df2, k, open=piv * (f - 0.02), high=piv * (f + 0.005), low=piv * (f - 0.025), close=piv * f)
    ext = detect(make_context(df2))
    assert ext.stage == EXTENDED and ext.metrics["score_follow"] == pytest.approx(-15)


@pytest.mark.parametrize("scale", [0.13, 1.0, 7.3, 41.0])
def test_stop_on_krx_tick(scale):
    df = _w([(225, 9000)])
    for k in ("open", "high", "low", "close"):
        df[k] = df[k] * scale
    r = detect(make_context(df))
    assert r.detected, r.warnings
    t = krx_tick(r.stop)
    assert abs(r.stop / t - round(r.stop / t)) < 1e-9, r.stop
    assert r.stop >= r.pivot * 0.92 - 1e-6           # -8% 한도는 올림 → 한도 초과 없음


def test_partial_breakout_and_missing_volume_caveats():
    df = _w([(225, 9000)], n=227)
    piv = _mid_high(df)
    df = _breakout(df, -1, piv * 1.025)
    ctx = make_context(df)
    ctx.partial, ctx.session_frac = True, 0.5
    r = detect(ctx)
    assert r.stage == BREAKOUT and any("장중 미완성" in w for w in r.warnings)
    df2 = df.copy()
    df2["volume"] = 0.0
    df2["value"] = 0.0
    r2 = detect(make_context(df2))
    assert r2.detected and r2.stage == BREAKOUT
    assert any("비교 불가" in w for w in r2.warnings)
    assert not any("nan" in s for s in r2.warnings + r2.reasons)
