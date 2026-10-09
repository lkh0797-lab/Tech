"""바닥 투매 흡수(absorb) · 바닥 탈출(stage2) 관찰용 탐지기 테스트 — 합성 일봉, 네트워크 없음."""
import numpy as np
import pandas as pd
import pytest

from chart_screener import scoring
from chart_screener.patterns import REGISTRY
from chart_screener.patterns.absorb import AbsorbConfig, find_absorb
from chart_screener.patterns.absorb import detect as detect_absorb
from chart_screener.patterns.base import BREAKOUT, FORMING, NEAR_PIVOT
from chart_screener.patterns.stage2 import Stage2Config, evaluate
from chart_screener.patterns.stage2 import detect as detect_stage2
from synthetic import add_value, make_context


def frame(close, vol, spread=0.01) -> pd.DataFrame:
    """노이즈 없는 일봉: 시가 = 종가, 고가/저가 = 종가 ±spread/2."""
    c = np.asarray(close, dtype=float)
    idx = pd.bdate_range("2023-01-02", periods=len(c))
    df = pd.DataFrame({"open": c, "high": c * (1 + spread / 2), "low": c * (1 - spread / 2), "close": c,
                       "volume": np.asarray(vol, dtype=float)}, index=idx)
    return add_value(df)


def put(df, i, **kw) -> pd.DataFrame:
    """i 번째 봉 일부 값을 그대로 덮어쓴다 (OHLC 정합성 보정 없음 — 테스트가 직접 맞춘다)."""
    df = df.copy()
    for k, v in kw.items():
        df.iloc[i, df.columns.get_loc(k)] = float(v)
    return add_value(df)


# ================================================================ absorb
V0 = 100_000


def absorb_df(n=300, ago=19, after=10300, tail=None, k_vol=4.0) -> pd.DataFrame:
    """15,000 → 10,500 하락 뒤 k = 마지막 −ago 봉에 저가 9,900 · 종가 위치 0.8 · 거래량 k_vol 배 흡수봉,
    이후 종가 after 로 횡보 (저가 = after × 0.995 ≥ 9,900)."""
    k = n - 1 - ago
    c = np.concatenate([np.linspace(15000, 10500, k), np.full(n - k, float(after))])
    v = np.full(n, float(V0))
    df = frame(c, v)
    bar = dict(open=10300, high=10400, low=9900, close=10300, volume=V0 * k_vol)
    bar.update(tail or {})
    return put(df, k, **bar)


def run_absorb(df, cfg=None):
    return detect_absorb(make_context(df, cfg=cfg))


def test_absorb_near_pivot_detected():
    df = absorb_df()
    r = run_absorb(df)
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT                       # 10,300 / 9,900 − 1 = 4.0% ≤ 5%
    assert r.pivot == r.stop == 9900
    m = r.metrics
    assert m["days_since"] == 19 and m["vol_mult"] == pytest.approx(4.0)
    assert m["gap_pct"] == pytest.approx((10300 / 9900 - 1) * 100, abs=0.01)
    assert m["close_pos"] == pytest.approx(0.8) and m["observe_only"] is True
    assert m["absorb_date"] == r.start_date == df.index[-20].strftime("%Y-%m-%d")
    assert r.end_date == df.index[-1].strftime("%Y-%m-%d") and r.score == 0
    assert all(s.startswith("✔ ") for s in r.reasons) and len(r.reasons) == 4
    assert any("관찰용" in w for w in r.warnings)
    kinds = [a["kind"] for a in r.annotations]
    assert kinds == ["hline", "marker"]
    assert r.annotations[0]["price"] == 9900 and r.annotations[1]["date"] == r.start_date


def test_absorb_forming_when_far_above_tail():
    r = run_absorb(absorb_df(after=11000))             # +11.1% 위
    assert r.detected and r.stage == FORMING
    assert r.metrics["gap_pct"] == pytest.approx((11000 / 9900 - 1) * 100, abs=0.01)
    assert any("멀다" in w for w in r.warnings)


def test_absorb_gap_boundary_5pct():
    near = run_absorb(absorb_df(after=9900 * 1.05 - 1))
    far = run_absorb(absorb_df(after=9900 * 1.05 + 1))
    assert near.stage == NEAR_PIVOT and far.stage == FORMING


def test_absorb_rejected_when_tail_low_broken():
    df = absorb_df()
    df = put(df, len(df) - 3, low=9890)                # 꼬리 저가 9,900 을 깸
    r = run_absorb(df)
    assert not r.detected and r.stage is None
    assert any("흡수봉 없음" in w for w in r.warnings)


def test_absorb_tail_low_touch_is_kept():
    df = put(absorb_df(), -3, low=9900)                # 같은 값 = 깨지 않음 (min ≥ low[k])
    assert run_absorb(df).detected


@pytest.mark.parametrize("mult, ok", [(3.0, True), (2.99, False)])
def test_absorb_volume_boundary(mult, ok):
    assert run_absorb(absorb_df(k_vol=mult)).detected is ok


@pytest.mark.parametrize("close, ok", [(10200, True), (10190, False)])   # (c−l)/(h−l) = 0.6 / 0.58
def test_absorb_close_position_boundary(close, ok):
    r = run_absorb(absorb_df(tail=dict(open=close, close=close)))
    assert r.detected is ok


@pytest.mark.parametrize("low, ok", [(9974, True), (9976, False)])      # 52주 저점 9,500 × 1.05 = 9,975
def test_absorb_near_52w_low_boundary(low, ok):
    df = absorb_df(after=10400, tail=dict(low=low, open=10350, high=10450, close=10350))
    df = put(df, 200, low=9500)                        # 흡수봉(280) 의 250봉 창 안, 탐색 60봉 밖
    ev = find_absorb(make_context(df))
    assert (ev is not None) is ok
    if ok:
        assert ev["low_52w"] == 9500 and ev["k"] == 280


def test_absorb_lookback_window_60():
    assert run_absorb(absorb_df(ago=59)).detected
    assert not run_absorb(absorb_df(ago=60)).detected


def test_absorb_picks_most_recent_event():
    df = absorb_df(ago=30, after=10300)
    df = put(df, len(df) - 6, open=10250, high=10350, low=9950, close=10300, volume=V0 * 5)  # 두 번째 흡수봉
    r = run_absorb(df)
    assert r.detected and r.metrics["days_since"] == 5 and r.pivot == 9950


def test_absorb_needs_261_bars():
    short = run_absorb(absorb_df(n=260))
    assert not short.detected and any("이력 부족" in w for w in short.warnings)
    assert run_absorb(absorb_df(n=261)).detected


def test_absorb_config_override():
    from chart_screener.config import Config
    cfg = Config()
    cfg.patterns["absorb"] = AbsorbConfig(vol_mult=5.0)
    assert not run_absorb(absorb_df(k_vol=4.0), cfg=cfg).detected


# ================================================================ stage2
def stage2_df(n=340, ago=5, cross_vol=3.0, after=10700, start=12000, end=10000, base=9600, amp=300) -> pd.DataFrame:
    """start → end 하락(앞 n−240 봉) 뒤 base ± amp 사인 옆걸음, 돌파 앞 3봉 9,500, k = 마지막 −ago 봉에
    종가 after−100 · 거래량 cross_vol 배로 150일선 돌파, 이후 종가 after."""
    i = n - 1
    k = i - ago
    t = np.arange(n)
    c = np.empty(n)
    d = n - 240
    c[:d] = np.linspace(start, end, d)
    c[d:k] = base + amp * np.sin((t[d:k] - d) / 9.0)
    c[k - 3:k] = 9500
    c[k] = after - 100
    c[k + 1:] = after
    v = np.full(n, float(V0))
    v[k] = V0 * cross_vol
    return frame(c, v)


def run_stage2(df, cfg=None):
    return detect_stage2(make_context(df, cfg=cfg))


def test_stage2_breakout_detected():
    df = stage2_df()
    r = run_stage2(df)
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT                         # 돌파 5봉 전 ≤ 5
    m = r.metrics
    assert m["days_since_cross"] == 5 and m["vol_mult"] == pytest.approx(3.0)
    assert m["ma150_pct"] > 0 and m["ma150_slope_20"] >= -1
    assert m["base_below_pct"] >= 50 and m["base_range_pct"] <= 60
    assert m["observe_only"] is True and r.score == 0
    ma = make_context(df).sma(150)
    assert r.pivot == r.stop == pytest.approx(ma.iloc[-6])     # 피벗 = 손절 = 돌파일 150일선 (고정)
    assert m["ma150"] == pytest.approx(ma.iloc[-1])             # 지금 150일선은 수치로
    assert r.breakout_date == m["cross_date"] == df.index[-6].strftime("%Y-%m-%d")
    assert r.start_date == df.index[-6 - 130].strftime("%Y-%m-%d")
    # 하루 앞(같은 돌파)에서도 피벗 · 시작일이 같아야 백테스트가 한 사건으로 묶는다
    r1 = run_stage2(df.iloc[:-1])
    assert r1.detected and r1.pivot == pytest.approx(r.pivot) and r1.start_date == r.start_date
    assert all(s.startswith("✔ ") for s in r.reasons) and len(r.reasons) == 5
    kinds = [a["kind"] for a in r.annotations]
    assert kinds == ["box", "marker"]
    bx = r.annotations[0]
    assert bx["start"] == df.index[-131].strftime("%Y-%m-%d") and bx["end"] == df.index[-12].strftime("%Y-%m-%d")


@pytest.mark.parametrize("ago, stage", [(0, BREAKOUT), (5, BREAKOUT), (6, FORMING), (9, FORMING)])
def test_stage2_stage_by_cross_age(ago, stage):
    r = run_stage2(stage2_df(ago=ago))
    assert r.detected and r.stage == stage and r.metrics["days_since_cross"] == ago


def test_stage2_cross_outside_10_bars():
    r = run_stage2(stage2_df(ago=10))
    assert not r.detected and any("상향 돌파 없음" in w for w in r.warnings)


@pytest.mark.parametrize("mult, ok", [(2.0, True), (1.99, False)])
def test_stage2_volume_boundary(mult, ok):
    r = run_stage2(stage2_df(cross_vol=mult))
    assert r.detected is ok
    if not ok:
        assert any("거래량" in w for w in r.warnings)


def test_stage2_volume_can_come_after_cross():
    df = stage2_df(ago=5, cross_vol=1.0)
    df = put(df, -2, volume=V0 * 2.5)                  # 돌파 뒤 하루 거래량 2.5배
    r = run_stage2(df)
    assert r.detected and r.metrics["vol_mult"] == pytest.approx(2.5)


@pytest.mark.parametrize("mult, ok", [(1.59, True), (1.61, False)])
def test_stage2_base_range_boundary(mult, ok):
    df = stage2_df()
    ev = evaluate(make_context(df))
    j = len(df) - 60                                   # 바닥 구간(i−130 ~ i−11) 안 한 봉의 고가만 튀게
    df = put(df, j, high=ev["base_bottom"] * mult)
    r = run_stage2(df)
    assert r.detected is ok
    if not ok:
        assert any("옆걸음 아님" in w for w in r.warnings)


def test_stage2_rejects_uptrend_base():
    # 계속 오르는 종목: 바닥 구간 종가가 150일선 위 → 1단계 바닥 아님
    n = 340
    c = np.linspace(8000, 11000, n)
    r = run_stage2(frame(c, np.full(n, float(V0))))
    assert not r.detected
    assert any("아래인 비율" in w for w in r.warnings)


def test_stage2_rejects_falling_ma():
    # 끝까지 이어지는 하락(16,000 → 9,500) 뒤 하루 급등 — 150일선은 20봉 전보다 1% 넘게 낮다
    n = 340
    c = np.concatenate([np.linspace(16000, 9500, n - 3), [11500, 11600, 11600]])
    v = np.full(n, float(V0))
    v[n - 3] = V0 * 3
    df = frame(c, v)
    ev = evaluate(make_context(df))
    assert ev["slope_pct"] < -1
    r = run_stage2(df)
    assert not r.detected and any("하락 중" in w for w in r.warnings)


def test_stage2_rejects_close_below_prior_high():
    df = stage2_df(after=9850)                         # 150일선 위지만 석 달 종가 고점(≈9,900) 아래
    ev = evaluate(make_context(df))
    assert ev["ma150_pct"] > 0
    r = run_stage2(df)
    assert not r.detected and any("석 달" in w for w in r.warnings)


def test_stage2_rejects_close_back_below_ma():
    df = put(stage2_df(ago=5), -1, close=9300, open=9300, low=9250)
    r = run_stage2(df)
    assert not r.detected and any("150일선 아래" in w for w in r.warnings)


def test_stage2_needs_321_bars():
    short = run_stage2(stage2_df(n=320))
    assert not short.detected and any("이력 부족" in w for w in short.warnings)
    assert run_stage2(stage2_df(n=321)).detected


def test_stage2_config_override():
    from chart_screener.config import Config
    cfg = Config()
    cfg.patterns["stage2"] = Stage2Config(breakout_bars=3)
    assert run_stage2(stage2_df(ago=4), cfg=cfg).stage == FORMING


# ================================================================ 공통
def test_registered_and_observe_only():
    assert REGISTRY["absorb"][0] == "바닥 투매 흡수" and REGISTRY["stage2"][0] == "바닥 탈출"
    assert "absorb" not in scoring.BASE_PATTERNS and "stage2" not in scoring.BASE_PATTERNS


def test_to_dict_jsonable():
    import json
    for r in (run_absorb(absorb_df()), run_stage2(stage2_df())):
        d = r.to_dict()
        json.dumps(d, ensure_ascii=False)
        assert d["stage_label"] in ("형성 중", "피벗 근접", "돌파")
