"""CAN SLIM 기술적 스코어카드 테스트 (합성 데이터)."""
import numpy as np
import pandas as pd
import pytest

from chart_screener.market import CORRECTION, MarketState
from chart_screener.patterns import REGISTRY
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, StockContext
from chart_screener.patterns.canslim import CanslimConfig, _consolidated, detect, find_base
from synthetic import add_value, flat_index, make_context, make_ohlcv, set_bar

S = 500.0          # 가격 배율: 100 → 5만원 (거래대금 수백억 수준)
PEAK = 100 * S     # 베이스 왼쪽 고점 (기대 피벗)


def accumulate(df: pd.DataFrame, up: float = 1.6, down: float = 0.75) -> pd.DataFrame:
    """상승일 거래량 ↑, 하락일 거래량 ↓ (매집). up<down 이면 분산."""
    df = df.copy()
    chg = df["close"].diff().to_numpy()
    m = np.where(chg > 0, up, np.where(chg < 0, down, 1.0))
    df["volume"] = (df["volume"].to_numpy() * m).round()
    return add_value(df)


def base_df(tail: list[tuple[int, float]], seed: int = 1, up: float = 1.6, down: float = 0.75) -> pd.DataFrame:
    """300봉 상승(50→100) 후 고점에서 조정하는 베이스. tail = 300봉 이후 웨이포인트(가격 ×1/S)."""
    wp = [(0, 50 * S), (300, PEAK)] + [(i, p * S) for i, p in tail]
    df = make_ohlcv(wp, noise=0.004, wick=0.006, seed=seed, vol_base=1_000_000)
    return accumulate(df, up, down)


def textbook(seed: int = 1) -> pd.DataFrame:
    """고점 100 → 86 (-14%) → 97.5 회복: 피벗 근접."""
    return base_df([(330, 86), (365, 97.5)], seed=seed)


def run(df, **kw):
    return detect(make_context(df, **({"rs": 92} | kw)))


def no_error(r):
    assert not any("계산 오류" in w for w in r.warnings), r.warnings


# ---------------------------------------------------------------- (a) 교과서 사례
def test_registered():
    assert "canslim" in REGISTRY
    assert REGISTRY["canslim"][0] == "CAN SLIM (기술적 요소)"


def test_textbook_near_pivot_detected():
    df = textbook()
    r = run(df)
    no_error(r)
    assert r.detected, (r.metrics, r.warnings)
    assert r.stage == NEAR_PIVOT
    assert abs(r.pivot / PEAK - 1) < 0.03
    assert r.stop == pytest.approx(r.pivot * 0.93)
    assert 0 <= r.score <= 100 and r.score == r.metrics["composite"]
    m = r.metrics
    for k in ("N", "S", "L", "I", "M", "composite", "ud_ratio", "ad_rating", "rs", "rs_line_high_dist",
              "rs_line_leading", "big_up_days", "big_down_days", "value_300_days", "market_state",
              "distribution_days"):
        assert k in m, k
    assert m["C"] == "N/A" and m["A"] == "N/A"
    assert m["ud_ratio"] >= 1.5 and m["ad_rating"] in ("A", "B")
    assert m["big_up_days"] > m["big_down_days"]
    assert m["value_300_days"] > 0
    assert m["market_state"] == "confirmed_uptrend"
    # 피벗 고점(약 300봉)이 베이스 시작(왼쪽 고점), 깊이 ≈ 14%, 길이 ≈ 66봉
    assert abs(pd.Timestamp(r.start_date) - df.index[300]) <= pd.Timedelta(days=7)
    assert m["pivot_date"] == r.start_date and not m["pivot_beyond_window"]
    assert 0.12 < m["base_depth"] < 0.18 and 55 <= m["base_bars"] <= 75
    assert m["quality_mult"] == 1.0 and not m["v_shape"] and m["stop_basis"] == "pivot"
    assert r.end_date == df.index[-1].strftime("%Y-%m-%d")
    assert r.breakout_date is None
    assert all(x.startswith("✔ [") for x in r.reasons)
    assert all(x.startswith("✘ ") for x in r.warnings)
    kinds = [a["kind"] for a in r.annotations]
    assert kinds.count("hline") >= 2 and "box" in kinds
    assert any("[L] RS 92" in x for x in r.reasons)


def test_pivot_definition_highest_consolidated_high():
    df = textbook()
    h, l, c = df["high"].to_numpy(), df["low"].to_numpy(), df["close"].to_numpy()
    g = find_base(h, l, c, CanslimConfig())
    pivot, pj, base_end, kind = g.pivot, g.pj, g.base_end, g.kind
    assert kind == "base" and base_end == pj
    assert abs(pj - 300) <= 5
    assert pivot == pytest.approx(h[pj])
    assert pivot >= h[pj - 20:].max() - 1e-9      # 조정 구간 최고가
    # 피벗 이후 10봉 동안 종가가 피벗을 넘지 않음
    assert c[pj + 1:pj + 11].max() <= pivot


# ---------------------------------------------------------------- (b) 단계
def test_stage_forming():
    df = base_df([(330, 86), (365, 88)])
    r = run(df)
    no_error(r)
    assert r.stage == FORMING
    assert abs(r.pivot / PEAK - 1) < 0.03


def test_stage_breakout_with_volume():
    df = textbook()
    piv = float(df["high"].iloc[290:310].max())
    avg = float(df["volume"].iloc[-51:-1].mean())
    df = set_bar(df, -2, open=piv * 0.99, high=piv * 1.025, low=piv * 0.985, close=piv * 1.02, volume=avg * 3)
    df = set_bar(df, -1, open=piv * 1.02, high=piv * 1.035, low=piv * 1.012, close=piv * 1.03, volume=avg * 2)
    r = run(df)
    no_error(r)
    assert r.detected, (r.metrics, r.warnings)
    assert r.stage == BREAKOUT
    assert r.breakout_date == df.index[-2].strftime("%Y-%m-%d")
    assert abs(r.pivot / piv - 1) < 0.01
    assert r.metrics["new_52w_high"] and r.metrics["breakout_vol_ratio"] >= 1.4
    assert any("돌파 — 거래량" in x for x in r.reasons)
    assert any(a["kind"] == "marker" for a in r.annotations)
    r0 = run(textbook())
    assert r.metrics["N"] > r0.metrics["N"] + 25


def test_stage_breakout_low_volume_warns():
    df = textbook()
    piv = float(df["high"].iloc[290:310].max())
    avg = float(df["volume"].iloc[-51:-1].mean())
    df = set_bar(df, -1, open=piv * 0.995, high=piv * 1.02, low=piv * 0.99, close=piv * 1.015, volume=avg * 0.9)
    r = run(df)
    assert r.stage == BREAKOUT
    assert any("기준 1.4배 미달" in w for w in r.warnings)


def test_stage_extended():
    df = base_df([(330, 86), (355, 99), (358, 103), (366, 113)])
    r = run(df)
    no_error(r)
    assert r.stage == EXTENDED
    assert abs(r.pivot / PEAK - 1) < 0.03
    assert r.breakout_date is not None


def test_stage_failed():
    df = base_df([(330, 86), (355, 99), (358, 104), (366, 95)])
    r = run(df)
    no_error(r)
    assert r.stage == FAILED
    assert abs(r.pivot / PEAK - 1) < 0.03


# ---------------------------------------------------------------- (c) 음성 사례
def test_negative_low_rs():
    r = run(textbook(), rs=60)
    assert not r.detected
    assert any("[필수] RS" in w for w in r.warnings)
    assert any("[L] RS 60" in w for w in r.warnings)


def test_negative_far_from_high():
    # 72 수준 횡보 상승 중 단기 급등(100) 후 원위치: 이평선 조건은 충족, 52주 고점 -25% 초과
    wp = [(0, 55 * S), (300, 70 * S), (305, 100 * S), (312, 71 * S), (366, 74 * S)]
    df = accumulate(make_ohlcv(wp, noise=0.004, seed=2))
    r = run(df)
    no_error(r)
    assert not r.detected
    assert r.metrics["from_52w_high"] < -0.25
    assert any("52주 고점 -25%" in w for w in r.warnings)
    assert not any("50일선 아래" in w for w in r.warnings)


def test_negative_below_50ma():
    df = base_df([(330, 92), (345, 99), (366, 89)])
    r = run(df)
    assert not r.detected
    assert any("50일선 아래" in w for w in r.warnings)


def test_negative_below_200ma():
    wp = [(0, 100 * S), (300, 100 * S), (320, 104 * S), (366, 96 * S)]
    df = accumulate(make_ohlcv(wp, noise=0.003, seed=4))
    r = run(df)
    assert not r.detected
    assert any("200일선 아래" in w for w in r.warnings)


def test_negative_distribution_volume():
    good = run(textbook())
    bad = run(base_df([(330, 86), (365, 97.5)], up=0.7, down=1.6))
    no_error(bad)
    assert not bad.detected
    assert bad.metrics["ud_ratio"] < 1.0 and bad.metrics["ad_rating"] in ("D", "E")
    assert bad.metrics["S"] < good.metrics["S"] - 40
    assert bad.metrics["I"] < good.metrics["I"] - 30
    assert any("[S]" in w for w in bad.warnings)


def test_negative_short_history_not_detected():
    df = textbook().iloc[-100:]
    r = run(df)
    no_error(r)
    assert not r.detected
    assert any("이력" in w for w in r.warnings)


def test_market_correction_cuts_score_and_warns():
    df = textbook()
    corr = MarketState(name="KOSPI", state=CORRECTION, label="조정", date="2024-01-01", close=1.0,
                       above_21ema=False, above_50sma=False, above_200sma=True, sma50_rising=False,
                       sma200_rising=True, distribution_days=7)
    r0 = run(df)
    r = run(df, market_state=corr)
    assert r0.detected and r.detected          # 조정장이어도 탐지는 유지
    assert r.metrics["stock_score"] == r0.metrics["stock_score"]
    assert r.metrics["M"] < 30
    assert r.score == pytest.approx(r.metrics["composite"] * 0.7, abs=0.11)
    assert r.score < r0.score
    assert "조정" in r.warnings[0]
    assert r.metrics["market_state"] == CORRECTION and r.metrics["distribution_days"] == 7


# ---------------------------------------------------------------- RS선 · 플러그인
def test_rs_line_leading():
    df = textbook()
    # 지수가 베이스 구간에서 15% 하락 → RS선은 주가보다 먼저 52주 신고가
    idx = flat_index(len(df), start=str(df.index[0].date()), drift=0.0)
    f = np.ones(len(df))
    f[300:] = np.linspace(1.0, 0.85, len(df) - 300)
    for k in ("open", "high", "low", "close"):
        idx[k] = idx[k] * f
    r = run(df, index_df=idx)
    assert r.metrics["rs_line_leading"] is True
    assert r.metrics["rs_line_high_dist"] >= -0.001
    assert any("RS선 선행 신고가" in x for x in r.reasons)
    assert any(a["kind"] == "marker" and "RS선" in a["text"] for a in r.annotations)
    assert not run(df).metrics["rs_line_leading"]   # 평탄 지수에서는 주가와 동행


def test_fundamentals_plugin():
    df = textbook()
    base = run(df)
    good = run(df, info={"market_cap": 1e12, "fundamentals": {
        "eps_q_yoy": 60.0, "eps_q_yoy_prev": 30.0, "sales_q_yoy": 30.0, "eps_annual_growth_3y": 35.0, "roe": 22.0}})
    assert isinstance(good.metrics["C"], float) and good.metrics["C"] >= 90
    assert good.metrics["A"] == pytest.approx(100.0)
    assert any(x.startswith("✔ [C]") for x in good.reasons) and any(x.startswith("✔ [A]") for x in good.reasons)
    bad = run(df, info={"market_cap": 1e12, "fundamentals": {"eps_q_yoy": 5.0, "roe": 8.0}})
    assert bad.metrics["C"] < 25 and bad.metrics["A"] < 50
    assert bad.metrics["composite"] < base.metrics["composite"] < good.metrics["composite"]
    assert any(w.startswith("✘ [C]") for w in bad.warnings)


def test_investor_plugin_and_no_lookahead():
    df = textbook()
    dates = df.index[-25:]
    inv = pd.DataFrame({"inst_net": 30_000.0, "foreign_net": 40_000.0}, index=dates)
    r = run(df, info={"market_cap": 1e12, "investor": inv})
    assert r.metrics["i_source"] == "proxy+investor"
    assert r.metrics["inv20_ratio"] > 0
    assert any("기관" in x and x.startswith("✔ [I]") for x in r.reasons)
    sell = run(df, info={"market_cap": 1e12, "investor": -inv * 3})
    assert sell.metrics["I"] < r.metrics["I"]
    # 미래 순매매 자료는 무시: 마지막 봉 이후 날짜만 있는 경우 반영하지 않음
    fut = pd.DataFrame({"inst_net": [1e9] * 25, "foreign_net": [1e9] * 25},
                       index=pd.bdate_range(df.index[-1] + pd.Timedelta(days=1), periods=25))
    rf = run(df, info={"market_cap": 1e12, "investor": fut})
    assert rf.metrics["i_source"] == "proxy"


def test_rs_rating_uses_value_at_last_bar():
    """잘린 df + 전체 RS 이력: 마지막 봉 이후의 RS 값은 쓰지 않는다."""
    df = textbook()
    cut = df.iloc[:-30]
    hist = pd.Series(92.0, index=df.index)
    hist.iloc[-30:] = 10.0       # '미래' 값
    ctx = make_context(cut, rs=10)
    ctx.rs_rating_hist = hist
    r = detect(ctx)
    assert r.metrics["rs"] == 92.0


def test_truncated_history_analyzes_latest_bar():
    """walk-forward: 과거 시점으로 자르면 그 시점 기준 단계/종료일."""
    df = base_df([(330, 86), (355, 99), (358, 103), (366, 113)])
    r_past = run(df.iloc[:340])          # 조정 중이던 시점
    assert r_past.end_date == df.index[339].strftime("%Y-%m-%d")
    assert r_past.stage in (FORMING, NEAR_PIVOT) and r_past.breakout_date is None


# ---------------------------------------------------------------- (d) 견고성
def _ctx_raw(df, **kw):
    base = dict(code="X", name="x", market="KOSPI", df=df, index_df=None, rs_rating=None,
                rs_rating_hist=None, market_state=None)
    return StockContext(**(base | kw))


@pytest.mark.parametrize("n", [30, 59, 60, 61, 130])
def test_short_histories(n):
    df = make_ohlcv([(0, 100), (n - 1, 120)], n=n, seed=3)
    r = detect(make_context(df))
    no_error(r)
    if n < CanslimConfig().min_detect_bars:
        assert not r.detected
        assert any("이력" in w for w in r.warnings)
    else:   # 신규 상장주(120~200봉)는 200일선 판정만 생략하고 채점
        assert any("200일선 판정 생략" in w for w in r.warnings)


def test_flat_line_constant_volume():
    idx = pd.bdate_range("2023-01-02", periods=400)
    df = add_value(pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
                                 "volume": 1000.0}, index=idx))
    r = detect(make_context(df))
    no_error(r)
    assert not r.detected
    r2 = detect(_ctx_raw(df))
    no_error(r2)
    assert not r2.detected


def test_random_walk_and_zero_volume():
    rng = np.random.default_rng(7)
    c = 1000 * np.exp(np.cumsum(rng.normal(0, 0.02, 500)))
    idx = pd.bdate_range("2023-01-02", periods=500)
    df = add_value(pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                                 "volume": rng.integers(0, 3, 500).astype(float)}, index=idx))
    r = detect(make_context(df))
    no_error(r)
    df0 = df.copy()
    df0["volume"] = 0.0
    df0 = add_value(df0)
    no_error(detect(make_context(df0)))
    no_error(detect(_ctx_raw(df0)))


def test_nan_values_do_not_raise():
    df = textbook()
    df.iloc[10:15, df.columns.get_loc("close")] = np.nan
    df.iloc[20, df.columns.get_loc("high")] = np.nan
    r = detect(make_context(df))
    no_error(r)
    df2 = textbook()
    df2.iloc[-1, df2.columns.get_loc("close")] = np.nan
    r2 = detect(make_context(df2))
    assert not r2.detected and r2.warnings


def test_partial_bar_and_halt_warnings():
    df = textbook()
    df.attrs["halt_dates"] = [df.index[-20].strftime("%Y-%m-%d")]
    ctx = make_context(df, rs=92)
    ctx.partial, ctx.session_frac = True, 0.5
    r = detect(ctx)
    no_error(r)
    assert any("거래정지" in w for w in r.warnings)
    assert any("장중" in w for w in r.warnings)


def test_to_dict_serializable():
    import json
    r = run(textbook())
    json.dumps(r.to_dict(), ensure_ascii=False)


# ---------------------------------------------------------------- 리뷰 회귀: 긴 베이스의 피벗 (창 밖 왼쪽 고점)
def long_cup(length: int, seed: int = 2, depth: float = 0.32, handle: bool = False) -> pd.DataFrame:
    """250봉 왼쪽 고점(100) → length 봉 컵 → 우측 97 회복 (쉼 없이). handle=True 면 이후 91→97 손잡이."""
    wp = [(0, 40 * S), (250, PEAK), (250 + length // 2, 100 * (1 - depth) * S), (250 + length, 97 * S)]
    if handle:
        wp += [(250 + length + 8, 91 * S), (250 + length + 16, 97 * S)]
    return accumulate(make_ohlcv(wp, noise=0.004, wick=0.006, seed=seed))


@pytest.mark.parametrize("length,seed", [(130, 3), (150, 1), (150, 2), (150, 3), (180, 1), (200, 2)])
def test_long_cup_pivot_is_left_lip(length, seed):
    """왼쪽 고점이 120봉 창 밖이어도 피벗은 왼쪽 고점 — 고점 아래에서 extended/breakout 으로 오판하지 않음."""
    df = long_cup(length, seed)
    lip = float(df["high"].iloc[245:256].max())
    r = run(df, rs=95)
    no_error(r)
    assert abs(r.pivot / lip - 1) < 0.01, (r.pivot, lip)
    assert r.metrics["pivot_beyond_window"]
    assert r.stage in (NEAR_PIVOT, FORMING) and r.breakout_date is None
    assert 0.30 < r.metrics["base_depth"] < 0.38            # 왼쪽 고점 → 컵 바닥
    assert r.metrics["base_bars"] >= length - 10
    assert not any("미만: 짧은 조정" in w for w in r.warnings)


@pytest.mark.parametrize("depth", [0.33, 0.60])
def test_long_cup_with_handle_measures_whole_base(depth):
    df = long_cup(140, seed=3, depth=depth, handle=True)
    lip = float(df["high"].iloc[245:256].max())
    r = run(df, rs=95)
    no_error(r)
    m = r.metrics
    assert abs(r.pivot / lip - 1) < 0.01 and r.stage in (NEAR_PIVOT, FORMING)
    assert m["base_depth"] == pytest.approx(depth, abs=0.04)       # 손잡이가 아니라 컵 전체 깊이
    assert m["base_bars"] >= 150
    assert not any("미만: 짧은 조정" in w for w in r.warnings)
    deep_warn = any("베이스 깊이" in w and "초과" in w for w in r.warnings)
    assert deep_warn == (depth > 0.5)


def test_deep_cup_scores_lower_than_normal_cup():
    shallow = run(long_cup(140, seed=3, depth=0.33, handle=True), rs=95)
    deep = run(long_cup(140, seed=3, depth=0.60, handle=True), rs=95)
    assert deep.metrics["quality_mult"] == pytest.approx(0.85)
    assert shallow.metrics["quality_mult"] == 1.0
    assert deep.metrics["stock_score"] < shallow.metrics["stock_score"] - 8
    assert any("결함 베이스 감점" in w for w in deep.warnings)


def test_pivot_stable_while_lip_leaves_window():
    """walk-forward: 왼쪽 고점(250봉)이 120봉 창을 벗어나는 날(370봉)을 지나도 피벗이 그대로."""
    df = long_cup(150, seed=2)
    lip = float(df["high"].iloc[245:256].max())
    pivots = {round(run(df.iloc[:t + 1], rs=95).pivot, 6) for t in range(355, 400, 3)}
    assert len(pivots) == 1 and abs(pivots.pop() / lip - 1) < 0.01


def test_find_base_left_swing_rejects_window_edge_bar():
    """하락 도중인 창 시작 봉은 '이후 10봉 종가 미돌파'만으로는 후보가 되지만(이전 결함), 왼쪽에 더 높은
    고가가 있어 조정 고점이 아니다 — 창 밖 확장을 막아도 피벗이 창 가장자리로 미끄러지지 않는다."""
    df = long_cup(150, seed=2)
    h, l, c = (df[k].to_numpy() for k in ("high", "low", "close"))
    cfg = CanslimConfig(max_base_lookback=120)          # 확장 금지 → 창 안 후보만
    lo = len(c) - cfg.pivot_lookback                    # 하락 구간 (왼쪽 고점 250봉 이후)
    assert 255 < lo < 300
    assert c[lo + 1:lo + 11].max() <= h[lo]             # 옛 규칙(우측 조건)으로는 후보
    assert not _consolidated(h, c, lo, lo, 10)[0]       # 좌측 스윙 조건으로 탈락
    g = find_base(h, l, c, cfg)
    assert g.pj != lo


def test_right_side_above_lip_base_starts_at_lip():
    """오른쪽이 왼쪽 고점을 넘은 컵: 피벗 = 우측 고점, 베이스 시작 = 왼쪽 고점."""
    wp = [(0, 50 * S), (300, PEAK), (330, 75 * S), (358, 102 * S), (364, 95 * S), (372, 101 * S)]
    df = accumulate(make_ohlcv(wp, noise=0.004, wick=0.006, seed=4))
    r = run(df, rs=95)
    no_error(r)
    lip_i = 280 + int(np.argmax(df["high"].to_numpy()[280:320]))      # 왼쪽 고점 (노이즈 포함 최고가 봉)
    assert r.pivot > float(df["high"].iloc[lip_i])
    assert r.start_date == df.index[lip_i].strftime("%Y-%m-%d")
    assert r.metrics["pivot_date"] > r.start_date
    assert 0.22 < r.metrics["base_depth"] < 0.32


def test_no_extension_after_crash_new_base():
    """65% 넘게 폭락한 옛 고점까지는 확장하지 않는다 (하락 추세 뒤 새 베이스)."""
    wp = [(0, 60 * S), (200, PEAK), (260, 28 * S), (330, 40 * S), (345, 35 * S), (366, 39.5 * S)]
    df = accumulate(make_ohlcv(wp, noise=0.004, wick=0.006, seed=5))
    r = run(df, rs=95)
    no_error(r)
    assert not r.metrics["pivot_beyond_window"]
    assert r.pivot < 45 * S
    assert r.metrics["base_depth"] < 0.3


# ---------------------------------------------------------------- 리뷰 회귀: 단계별 N 채점
def failed_breakout_df() -> tuple[pd.DataFrame, float]:
    df = textbook()
    piv = float(df["high"].iloc[290:310].max())
    avg = float(df["volume"].iloc[-51:-1].mean())
    df = set_bar(df, -4, open=piv * 0.99, high=piv * 1.03, low=piv * 0.985, close=piv * 1.025, volume=avg * 3)
    df = set_bar(df, -3, open=piv * 1.02, high=piv * 1.03, low=piv * 0.98, close=piv * 0.99, volume=avg * 1.5)
    df = set_bar(df, -2, open=piv * 0.99, high=piv * 0.99, low=piv * 0.94, close=piv * 0.95, volume=avg * 2.0)
    df = set_bar(df, -1, open=piv * 0.95, high=piv * 0.955, low=piv * 0.91, close=piv * 0.92, volume=avg * 2.5)
    return df, piv


def test_failed_breakout_gets_no_breakout_bonus():
    df, piv = failed_breakout_df()
    r = run(df)
    no_error(r)
    near = run(textbook())
    assert r.stage == FAILED and near.stage == NEAR_PIVOT
    assert r.metrics["N"] < near.metrics["N"]
    assert not any(x.startswith("✔ [N] 피벗") and "돌파" in x for x in r.reasons)
    assert any("✘ [N] 돌파 실패" in w for w in r.warnings)
    assert r.metrics["quality_mult"] == pytest.approx(0.8)
    assert r.score < near.score
    assert any("손절가" in w and "매도" in w for w in r.warnings)      # 종가 < 피벗 -7%


def test_breakout_closing_back_below_pivot_halves_bonus():
    df = textbook()
    piv = float(df["high"].iloc[290:310].max())
    avg = float(df["volume"].iloc[-51:-1].mean())
    up = set_bar(df, -2, open=piv * 0.99, high=piv * 1.03, low=piv * 0.985, close=piv * 1.02, volume=avg * 3)
    up = set_bar(up, -1, open=piv * 1.02, high=piv * 1.03, low=piv * 1.01, close=piv * 1.025, volume=avg)
    back = set_bar(up, -1, open=piv * 1.0, high=piv * 1.005, low=piv * 0.98, close=piv * 0.985, volume=avg)
    ru, rb = run(up), run(back)
    # 공용 classify_stage: 돌파 후 피벗 아래(실패 기준 -3% 이내)로 되밀리면 '피벗 근접(재시험)'
    assert ru.stage == BREAKOUT and rb.stage == NEAR_PIVOT
    assert rb.breakout_date is not None
    assert ru.metrics["N"] - rb.metrics["N"] >= 9
    assert any("돌파 후 피벗 아래 마감" in w for w in rb.warnings)


def test_intraday_reversal_through_pivot_warns():
    df = textbook()
    piv = float(df["high"].iloc[290:310].max())
    avg = float(df["volume"].iloc[-51:-1].mean())
    rev = set_bar(df, -1, open=piv * 0.985, high=piv * 1.02, low=piv * 0.955, close=piv * 0.96, volume=avg * 2)
    r, base = run(rev), run(df)
    no_error(r)
    assert r.breakout_date is None and r.stage == NEAR_PIVOT
    assert any("장중 피벗" in w and "키 리버설" in w for w in r.warnings)
    assert not any("돌파 대기" in x for x in r.reasons)
    assert r.metrics["N"] <= base.metrics["N"] - 10
    assert any(a["kind"] == "marker" and "되밀림" in a["text"] for a in r.annotations)


def test_short_term_50bar_breakout_credited():
    """스펙: 직전 50봉 고점을 거래량 1.4배↑로 돌파하면 (상위 베이스 피벗 아래여도) N 가산."""
    df = base_df([(330, 80), (345, 90), (358, 85), (366, 88)])
    lvl = float(df["high"].iloc[-51:-1].max())
    avg = float(df["volume"].iloc[-51:-1].mean())
    hot = set_bar(df, -1, open=lvl * 0.99, high=lvl * 1.025, low=lvl * 0.985, close=lvl * 1.02, volume=avg * 2.5)
    cold = set_bar(df, -1, open=lvl * 0.99, high=lvl * 1.025, low=lvl * 0.985, close=lvl * 1.02, volume=avg * 0.9)
    rh, rc = run(hot), run(cold)
    no_error(rh)
    assert rh.stage == FORMING and rh.pivot > lvl * 1.05          # 상위 베이스 피벗(100) 아래
    assert rh.metrics["short_breakout"] == df.index[-1].strftime("%Y-%m-%d")
    assert any("50봉 고점" in x and "아래" in x for x in rh.reasons)
    assert rc.metrics["short_breakout"] == ""
    assert rh.metrics["N"] - rc.metrics["N"] == pytest.approx(10, abs=0.01)


# ---------------------------------------------------------------- 리뷰 회귀: V자, N 필수, 손절 기준, 동률
def test_v_shape_penalized():
    v = accumulate(make_ohlcv([(0, 50 * S), (300, PEAK), (318, 57 * S), (343, 99 * S)], noise=0.003, wick=0.005,
                              seed=6))
    paused = accumulate(make_ohlcv([(0, 50 * S), (300, PEAK), (318, 57 * S), (335, 90 * S), (345, 86 * S),
                                    (360, 98 * S)], noise=0.003, wick=0.005, seed=6))
    rv, rp = run(v, rs=95), run(paused, rs=95)
    no_error(rv)
    assert rv.metrics["v_shape"] and rv.metrics["quality_mult"] == pytest.approx(0.85)
    assert any("V자 급반등" in w for w in rv.warnings)
    assert not rp.metrics["v_shape"] and rp.metrics["quality_mult"] == 1.0


def spike_df() -> pd.DataFrame:
    """단기 급등(100) 후 -16% 수준에서 재상승: 이평선 위지만 신고가권(-15%) 밖."""
    wp = [(0, 50 * S), (300, 70 * S), (305, PEAK), (312, 79 * S), (340, 80 * S), (366, 84 * S)]
    return accumulate(make_ohlcv(wp, noise=0.003, wick=0.005, seed=2))


def test_n_rule_is_a_must():
    r = run(spike_df(), rs=95)
    no_error(r)
    assert -0.25 < r.metrics["from_52w_high"] < -0.15
    assert not r.metrics["n_pass"] and not r.metrics["musts_ok"] and not r.detected
    assert any("[필수] [N]" in w for w in r.warnings)


def test_n_rule_waived_when_rs_line_leads():
    df = spike_df()
    idx = flat_index(len(df), start=str(df.index[0].date()), drift=0.0)
    f = np.ones(len(df))
    f[305:] = np.linspace(1.0, 0.75, len(df) - 305)       # 지수 -25% → RS선은 신고가, 주가는 아님
    for k in ("open", "high", "low", "close"):
        idx[k] = idx[k] * f
    r = run(df, rs=95, index_df=idx)
    assert r.metrics["rs_line_leading"] and not r.metrics["n_pass"]
    assert not any("[필수] [N]" in w for w in r.warnings)
    assert any("N 필수 조건 면제" in x for x in r.reasons)


def test_stop_basis_by_stage():
    df = base_df([(330, 86), (355, 99), (358, 103), (366, 113)])
    ext = run(df)
    close = float(df["close"].iloc[-1])
    assert ext.stage == EXTENDED and ext.metrics["stop_basis"] == "close"
    assert ext.stop == pytest.approx(close * 0.93, rel=1e-6)
    assert any("현재가 기준" in w for w in ext.warnings)
    form = run(base_df([(330, 86), (365, 88)]))
    assert form.stage == FORMING and form.metrics["stop_basis"] == "pivot"
    assert any("돌파 매수 기준" in w for w in form.warnings)


def test_flat_line_ties_are_not_new_highs():
    idx = pd.bdate_range("2023-01-02", periods=400)
    df = add_value(pd.DataFrame({"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
                                 "volume": 1000.0}, index=idx))
    r = detect(make_context(df))
    no_error(r)
    assert not r.metrics["new_52w_high"] and not r.metrics["ath"]
    assert r.metrics["N"] < 70
    assert any("판정 불가" in w for w in r.warnings)
    assert not any("nan" in x for x in r.reasons + r.warnings)
