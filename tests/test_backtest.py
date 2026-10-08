"""백테스트: _context_at 미래 참조 없음, 신호 중복 제거, 지수 벤치마크 구간, 사전 필터."""
import numpy as np
import pandas as pd
import pytest

from chart_screener import backtest as bt_mod
from chart_screener.backtest import (BacktestConfig, _context_at, _events_for, _maybe_breakout_day, _Static,
                                     first_entries, market_states_by_date, summarize, summarize_first_entries)
from chart_screener.breadth import breadth_history
from chart_screener.config import Config
from chart_screener.patterns import REGISTRY
from chart_screener.patterns.base import NEAR_PIVOT, PatternResult
from chart_screener.universe_data import UniverseData

N = 330
DATES = pd.bdate_range("2023-01-02", periods=N)


def _ohlcv(seed: int, drift: float = 0.001) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 10_000 * np.cumprod(1 + drift + rng.normal(0, 0.01, N))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.003, N))
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99, "close": c,
                       "volume": np.full(N, 1e6)}, index=DATES)
    df["value"] = (df["high"] + df["low"] + df["close"]) / 3 * df["volume"]
    return df


def _index(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    c = 1000 * np.cumprod(1 + 0.0005 + rng.normal(0, 0.008, N))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.004, N))   # 시가 ≠ 전일 종가 (갭)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.004, "low": np.minimum(o, c) * 0.996,
                         "close": c, "volume": 1e6 * (1 + rng.random(N))}, index=DATES)


@pytest.fixture(scope="module")
def ud() -> UniverseData:
    codes = {"AAA": "KOSPI", "BBB": "KOSDAQ", "CCC": "KOSPI"}
    ohlcv = {c: _ohlcv(k) for k, c in enumerate(codes)}
    ohlcv["AAA"].attrs["halt_dates"] = ["2023-03-01", f"{DATES[300]:%Y-%m-%d}"]
    uni = pd.DataFrame({"code": list(codes), "name": ["가", "나", "다"], "market": list(codes.values()),
                        "market_cap": 1e12}).set_index("code", drop=False)
    index = {"KOSPI": _index(10), "KOSDAQ": _index(11)}
    rs = pd.DataFrame({c: np.linspace(10, 90, N) for c in codes}, index=DATES)
    hist = breadth_history(ohlcv, 300e8, codes)
    return UniverseData(uni, ohlcv, index, {}, rs, DATES[-1], breadth_hist=hist)


@pytest.fixture(scope="module")
def mkt(ud):
    return market_states_by_date(ud, DATES[250])


# ---------------------------------------------------------------- 미래 참조 없음
def test_context_at_truncates_everything(ud, mkt):
    t = 280
    date = DATES[t]
    df = ud.ohlcv["AAA"]
    attrs_before = dict(df.attrs)
    ctx = _context_at("AAA", df, t, ud, Config(), mkt)
    assert len(ctx.df) == t + 1 and ctx.df.index[-1] == date
    assert ctx.index_df.index[-1] <= date and len(ctx.index_df) == t + 1
    assert ctx.rs_rating_hist.index[-1] <= date
    assert ctx.rs_rating == pytest.approx(ud.rs["AAA"].iloc[t])
    assert ctx.market_state is not None and ctx.market_state.date <= f"{date:%Y-%m-%d}"
    assert ctx.market_state.breadth is None or ctx.market_state.breadth["date"] <= f"{date:%Y-%m-%d}"
    assert ctx.df.attrs["halt_dates"] == ["2023-03-01"]          # 미래 정지일(300번째 봉) 제거
    assert df.attrs == attrs_before                               # 원본 attrs 는 그대로


def test_context_unaffected_by_future_data(ud, mkt):
    """t 이후 데이터를 바꿔도 t 시점 컨텍스트(가격·지수·RS·시장 상태)는 같아야 한다."""
    t = 290
    a = _context_at("BBB", ud.ohlcv["BBB"], t, ud, Config(), mkt)
    fut = ud.ohlcv["BBB"].copy()
    fut.iloc[t + 1:, :] *= 3.0
    b = _context_at("BBB", fut, t, ud, Config(), mkt)
    pd.testing.assert_frame_equal(a.df, b.df)
    assert a.market_state is b.market_state


def test_market_states_use_breadth_up_to_date(ud, mkt):
    for name, states in mkt.items():
        for d, st in list(states.items())[::20]:
            assert st.date == f"{d:%Y-%m-%d}"
            if st.breadth is not None:
                assert st.breadth["date"] <= st.date


# ---------------------------------------------------------------- 가짜 탐지기
def _fake(stage=NEAR_PIVOT, start="2023-11-01", pivot=lambda ctx: 12_345.0, breakout=lambda ctx: None):
    def fn(ctx):
        return PatternResult(name="fake", label="가짜", detected=True, score=50.0, stage=stage,
                             pivot=pivot(ctx), stop=float(ctx.close.iloc[-1]) * 0.5, start_date=start,
                             end_date=ctx.date(-1), breakout_date=breakout(ctx))
    return fn


def test_stage_mode_dedupes_same_pattern(ud, monkeypatch):
    monkeypatch.setitem(REGISTRY, "fake", ("가짜", _fake()))
    bt = BacktestConfig(pattern="fake", mode="stage", step=1, stages=(NEAR_PIVOT,), min_bars=260,
                        since=str(DATES[0].date()))
    ev = _events_for("AAA", bt, Config(), ud, {})
    assert len(ev) == 1                                           # end_date 가 매일 바뀌어도 1회
    assert ev[0]["date"] == f"{DATES[260]:%Y-%m-%d}" and ev[0]["start_date"] == "2023-11-01"


def test_stage_mode_new_pivot_is_new_signal_and_first_entries_collapses(ud, monkeypatch):
    cut = DATES[300]
    piv = lambda ctx: 10_000.0 if ctx.df.index[-1] < cut else 11_000.0
    monkeypatch.setitem(REGISTRY, "fake", ("가짜", _fake(pivot=piv)))
    bt = BacktestConfig(pattern="fake", mode="stage", step=1, stages=(NEAR_PIVOT,), min_bars=260)
    ev = pd.DataFrame(_events_for("AAA", bt, Config(), ud, {}) + _events_for("BBB", bt, Config(), ud, {}))
    assert len(ev) == 4 and set(ev["date"]) == {f"{DATES[260]:%Y-%m-%d}", f"{cut:%Y-%m-%d}"}
    fe = first_entries(ev)
    assert len(fe) == 2 and set(fe["date"]) == {f"{DATES[260]:%Y-%m-%d}"}
    s = summarize_first_entries(ev, (5, 20))
    assert s.attrs.get("first_entry") and s["신호수"].iloc[0] == 2


def test_stage_filter_respected(ud, monkeypatch):
    monkeypatch.setitem(REGISTRY, "fake", ("가짜", _fake(stage="forming")))
    bt = BacktestConfig(pattern="fake", mode="stage", step=1, stages=(NEAR_PIVOT,), min_bars=260)
    assert _events_for("AAA", bt, Config(), ud, {}) == []


def test_breakout_day_mode_and_index_benchmark(ud, monkeypatch):
    t = 270
    bo = f"{DATES[t]:%Y-%m-%d}"
    monkeypatch.setitem(REGISTRY, "fake", ("가짜", _fake(breakout=lambda ctx: bo if ctx.date(-1) >= bo else None)))
    bt = BacktestConfig(pattern="fake", mode="breakout_day", min_bars=260, prefilter=False, horizons=(5, 20))
    ev = _events_for("BBB", bt, Config(), ud, {})
    assert [e["date"] for e in ev] == [bo]
    e = ev[0]
    df, idx = ud.ohlcv["BBB"], ud.index["KOSDAQ"]
    assert e["entry"] == pytest.approx(df["open"].iloc[t + 1])
    for hz in (5, 20):
        j = t + hz
        assert e[f"ret_{hz}"] == pytest.approx(df["close"].iloc[j] / df["open"].iloc[t + 1] - 1)
        # 지수도 같은 구간: t+1 시가 → t+hz 종가
        assert e[f"idx_{hz}"] == pytest.approx(idx["close"].iloc[j] / idx["open"].iloc[t + 1] - 1)
    out = summarize(pd.DataFrame(ev), (5, 20))
    assert list(out["신호수"]) == [1, 1]


def test_index_benchmark_falls_back_to_close_without_open(ud, monkeypatch):
    t = 270
    bo = f"{DATES[t]:%Y-%m-%d}"
    monkeypatch.setitem(REGISTRY, "fake", ("가짜", _fake(breakout=lambda ctx: bo if ctx.date(-1) >= bo else None)))
    no_open = {m: d.drop(columns="open") for m, d in ud.index.items()}
    ud2 = UniverseData(ud.universe, ud.ohlcv, no_open, {}, ud.rs, ud.asof)
    bt = BacktestConfig(pattern="fake", mode="breakout_day", min_bars=260, prefilter=False, horizons=(5,))
    e = _events_for("BBB", bt, Config(), ud2, {})[0]
    idx = ud.index["KOSDAQ"]
    assert e["idx_5"] == pytest.approx(idx["close"].iloc[t + 5] / idx["close"].iloc[t] - 1)


# ---------------------------------------------------------------- 사전 필터
def test_prefilter_kinds():
    c = np.array([100, 101, 102, 103, 102.5, 80, 104, 103.9], float)
    h = c * 1.01
    near_up = _maybe_breakout_day("vcp", h, c)
    near_any = _maybe_breakout_day("cup_handle", h, c)
    assert not near_up[4] and near_any[4]          # 고점 근처 하락 마감: 거래량 게이트 패턴만 후보
    assert not near_any[5]                         # 고점에서 먼 날은 둘 다 제외
    assert near_up[6] and near_any[6]
    assert _maybe_breakout_day("big_value_pullback", h, c).all()
    unknown = _maybe_breakout_day("no_such_pattern", h, c)
    assert (unknown == near_any).all()             # 모르는 패턴 = 고점 근접(0.85)만
    lbb = _maybe_breakout_day("long_base_breakout", h, np.array([100, 107.5, 108, 120], float))
    assert list(lbb) == [False, True, False, True]
    assert set(bt_mod.PREFILTER) >= {"cup_handle", "canslim", "big_value_pullback", "vcp"}
