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


def test_no_stop_pattern_has_no_stop_share(ud, monkeypatch):
    """손절 규칙 없는 식(컵 앤 핸들): 'stop' 이 나올 수 없으니 손절 0% 로 찍지 않고 '해당 없음'으로 따로 센다."""
    def nostop(ctx):
        return PatternResult(name="fake", label="가짜", detected=True, score=50.0, stage=NEAR_PIVOT, pivot=12_345.0,
                             stop=None, start_date="2023-11-01", end_date=ctx.date(-1))
    monkeypatch.setitem(REGISTRY, "fake", ("가짜", nostop))
    bt = BacktestConfig(pattern="fake", mode="stage", step=1, stages=(NEAR_PIVOT,), min_bars=260)
    ev = pd.DataFrame(_events_for("AAA", bt, Config(), ud, {}))
    assert len(ev) and (~ev["has_stop"]).all() and "stop" not in set(ev["outcome"])
    s = summarize(ev, (5, 20))
    assert "outcome" not in s.attrs and s.attrs["no_stop"]["n"] == len(ev)
    mixed = pd.concat([ev, ev.assign(has_stop=True, outcome="stop")], ignore_index=True)
    s = summarize(mixed, (5, 20))
    assert s.attrs["outcome"] == {"stop": 100.0} and s.attrs["outcome_n"] == len(ev) and s.attrs["no_stop"]["n"] == len(ev)
    old = ev.drop(columns="has_stop").assign(outcome="open")    # has_stop 칸 없는 옛 이벤트 CSV — 예전처럼 전부 센다
    assert summarize(old, (5,)).attrs["outcome"] == {"open": 100.0}


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


def test_until_drops_later_bars_from_signals_and_returns(ud, monkeypatch):
    """until(포함) 뒤 봉(장중 미완성 봉 등)은 신호 · 진입 · 수익 계산에 안 쓴다."""
    t = 300
    bo = f"{DATES[t]:%Y-%m-%d}"
    monkeypatch.setitem(REGISTRY, "fake", ("가짜", _fake(breakout=lambda ctx: bo if ctx.date(-1) >= bo else None)))
    full = BacktestConfig(pattern="fake", mode="breakout_day", min_bars=260, prefilter=False, horizons=(5, 20))
    e = _events_for("BBB", full, Config(), ud, {})[0]
    assert np.isfinite(e["ret_20"])
    cut = BacktestConfig(**{**full.__dict__, "until": f"{DATES[t + 10]:%Y-%m-%d}"})
    e2 = _events_for("BBB", cut, Config(), ud, {})[0]
    assert e2["date"] == bo and e2["ret_5"] == pytest.approx(e["ret_5"]) and not np.isfinite(e2["ret_20"])
    early = BacktestConfig(**{**full.__dict__, "until": f"{DATES[t]:%Y-%m-%d}"})   # 신호 봉이 마지막 봉 → 다음 봉 없음
    assert _events_for("BBB", early, Config(), ud, {}) == []


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
def test_prefilter_kinds(monkeypatch):
    c = np.array([100, 101, 102, 103, 102.5, 80, 104, 103.9], float)
    h = c * 1.01
    # 필터 종류 자체 (검증된 패턴이 쓰는 도구) — 가짜 패턴 키로 시험
    monkeypatch.setitem(bt_mod.PREFILTER, "t_up", ("near_high_up", 0.84))
    monkeypatch.setitem(bt_mod.PREFILTER, "t_any", ("near_high", 0.85))
    monkeypatch.setitem(bt_mod.PREFILTER, "t_chg", ("chg", 0.069))
    near_up = _maybe_breakout_day("t_up", h, c)
    near_any = _maybe_breakout_day("t_any", h, c)
    assert not near_up[4] and near_any[4]          # 고점 근처 하락 마감: 상승 마감 조건 없는 필터만 후보
    assert not near_any[5]                         # 고점에서 먼 날은 둘 다 제외
    assert near_up[6] and near_any[6]
    chg = _maybe_breakout_day("t_chg", h, np.array([100, 107.5, 108, 120], float))
    assert list(chg) == [False, True, False, True]


def test_prefilter_after_pattern_reset():
    # 2026-10-14: 옛 패턴의 검증된 필터는 패턴과 함께 지웠다. 컵 앤 핸들 · 모르는 패턴은 필터 없이 매일 판정
    c = np.array([100, 101, 102, 103, 102.5, 80, 104, 103.9], float)
    # 《차트의 기술》 기법은 규칙상 꼭 성립하는 조건만 쓴 상위 집합 필터 (놓침 없음 — test_technique_integration 이 실제 탐지기로 확인)
    assert set(bt_mod.PREFILTER) == {"cup_with_handle", "trendline_break", "fib_pullback", "trendline_fib",
                                     "ma60_supply", "red_three_monthly"}
    assert bt_mod.PREFILTER["cup_with_handle"] == ("none", None)
    assert _maybe_breakout_day("cup_with_handle", c * 1.01, c).all()
    assert _maybe_breakout_day("no_such_pattern", c * 1.01, c).all()
    assert _maybe_breakout_day("fib_pullback", c * 1.01, c).all()      # df 가 필요한 필터는 df 없으면 필터 없음
