"""보컬 눌림목 깔때기 — chart_screener/vocal.py · patterns/vocal.py (합성 자료)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from chart_screener.patterns.base import BREAKOUT, FORMING, NEAR_PIVOT
from chart_screener.patterns.vocal import detect
from chart_screener.vocal import Panel, VocalConfig, funnel, leaders, theme_strength
from synthetic import make_context, make_ohlcv

CFG = VocalConfig()


def _bars(rows: list[tuple[float, float, float, float, float]], start: str = "2025-01-02") -> pd.DataFrame:
    """[(open, high, low, close, volume)] → 일봉 DataFrame (value = close × volume)."""
    idx = pd.bdate_range(start, periods=len(rows))
    df = pd.DataFrame(rows, index=idx, columns=["open", "high", "low", "close", "volume"])
    df["value"] = df["close"] * df["volume"]
    return df


def _arrays(df: pd.DataFrame) -> dict:
    return {"o": df["open"].to_numpy(float), "h": df["high"].to_numpy(float), "l": df["low"].to_numpy(float),
            "c": df["close"].to_numpy(float), "v": df["volume"].to_numpy(float), "tv": df["value"].to_numpy(float),
            "d": df.index}


def _rally_pullback(signal: bool = True) -> pd.DataFrame:
    """바닥 70봉(종가 100, 저가 99) → 10봉 급등(고점 140) → 4봉 눌림(저점 119.5 = 50% 되돌림, 거래량 마름) → 신호봉."""
    rows = [(100, 101, 99, 100, 1e5)] * 70
    for k in range(10):                                   # 104 → 140, 거래량 10배
        c = 104 + (140 - 104) * (k + 1) / 10
        rows.append((c - 3, c + (0 if k < 9 else 0), c - 3 + 0.5, c, 1e6))
    rows[-1] = (136, 140, 135, 139, 1e6)                  # 고점 140
    rows += [(138, 138, 133, 135, 4e5), (134, 134, 125, 128, 3e5), (127, 127, 119.5, 122, 2e5), (122, 123, 120, 121, 2e5)]
    if signal:
        rows.append((121, 128, 120, 127, 6e5))            # 양봉 +5% · 5일선 위 · 거래대금 재유입
    else:
        rows.append((121, 122, 120, 120.5, 2e5))
    return _bars(rows)


def test_funnel_reaches_signal():
    df = _rally_pullback(signal=True)
    f = funnel(_arrays(df), len(df) - 1, lambda d: True, CFG)
    assert f["stage"] == 7, f.get("why")
    assert round(f["gain"]) == 41 and f["rise"] == 10
    assert "50% 되돌림" in f["touched"] and f["dry_prev"]
    assert f["reflow"] and f["bull"] and f["hold"] and f["above5"]
    assert abs(f["stop"] - 119.5) < 1e-9 and f["target"] == 140
    assert f["rr"] > CFG.rr_min


def test_funnel_waits_without_signal():
    df = _rally_pullback(signal=False)
    f = funnel(_arrays(df), len(df) - 1, lambda d: True, CFG)
    assert f["stage"] == 6
    assert "재유입" in f["why"] and "양봉" in f["why"]


def test_funnel_needs_rank_during_rally():
    df = _rally_pullback()
    f = funnel(_arrays(df), len(df) - 1, lambda d: False, CFG)
    assert f["stage"] == 0 and "위 안" in f["why"]


def test_funnel_small_rally_is_not_stage4():
    rows = [(100, 101, 99, 100, 1e5)] * 70 + [(100 + k, 101 + k, 99 + k, 100 + k, 2e5) for k in range(1, 11)]
    df = _bars(rows)
    f = funnel(_arrays(df), len(df) - 1, lambda d: True, CFG)
    assert f["stage"] == 0 and "상승" in f["why"]


def _theme_panel():
    """채움 종목 30곳(거래대금 일정) + 테마 'T' 4곳 — 마지막 10일에 T 거래대금이 몰리고 A 가 가장 많이 오른다."""
    n = 140
    idx = pd.bdate_range("2025-01-02", periods=n)
    ohlcv, themes = {}, {}

    def mk(close, value):
        close = np.asarray(close, float)
        return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                             "volume": np.asarray(value, float) / close, "value": value}, index=idx)
    for k in range(30):
        ohlcv[f"F{k:02d}"] = mk(np.full(n, 50.0), np.full(n, 1e9))
    spec = {"A": (5e9, 0.40), "B": (3e9, 0.25), "C": (2e9, 0.05), "D": (2e9, 0.02)}
    for code, (hot, ret) in spec.items():
        val = np.full(n, 1e8)
        val[-10:] = hot
        close = np.full(n, 100.0)
        close[-10:] = 100 * (1 + ret * np.arange(1, 11) / 10)
        ohlcv[code] = mk(close, val)
        themes[code] = ["T"]
    return Panel(ohlcv, themes, tail=200)


def test_theme_strength_and_leaders():
    P = _theme_panel()
    gi = len(P.dates) - 1
    strong = theme_strength(P, gi, CFG)
    assert [t["theme"] for t in strong] == ["T"]
    t = strong[0]
    assert t["ratio"] >= CFG.theme_ratio and t["n_pool"] == 4
    assert P.dates[t["start"]] == P.dates[-10]            # 거래대금이 몰리기 시작한 날
    lead = leaders(P, "T", t["start"], gi)
    assert [(r["code"], r["role"]) for r in lead] == [("A", "대장"), ("B", "부대장")]


def test_detect_without_cross_section():
    ctx = make_context(make_ohlcv([(0, 100), (200, 120)]))
    r = detect(ctx)
    assert not r.detected and "전 종목 scan" in r.warnings[0]
    ctx.info["vocal"] = None
    r = detect(ctx)
    assert not r.detected and "깔때기 밖" in r.warnings[0]


def _f(stage, lead=True, rr=3.0):
    return {"stage": stage, "H": 140.0, "hk": "2025-04-15", "base_lo": 99.0, "lk": "2025-04-01", "gain": 41.0, "rise": 10,
            "n_rank": 5, "bk": "2025-04-10", "days": 5, "depth": 11.4, "depth_min": 13.6, "pl": 119.5, "pl_d": "2025-04-18",
            "retrace": 50.0, "touched": ["50% 되돌림"], "touched_lv": [("50% 되돌림", 119.5)], "dry_prev": True,
            "v_ratio_peak": 0.2, "reflow_x": 2.5, "entry": 124.0, "stop": 119.5, "target": 140.0, "rr": rr,
            "stop_pct": -3.6, "target_pct": 12.9, "rank": 40, "pool_days": 8, "themes": ["T"],
            "lead": [["T", "대장", "2025-04-08"]] if lead else [], "n_theme_days": 6, "asof": "2025-04-22",
            "why": "신호"}


def test_detect_maps_stages():
    ctx = make_context(make_ohlcv([(0, 100), (200, 120)]))
    for st, want in ((4, FORMING), (5, FORMING), (6, NEAR_PIVOT), (7, BREAKOUT)):
        ctx.info["vocal"] = _f(st)
        r = detect(ctx)
        assert r.detected and r.stage == want, st
        assert r.stop == 119.5
    assert r.pivot == 124.0 and r.breakout_date == "2025-04-22"
    assert any(a["kind"] == "marker" and "⑦" in a["text"] for a in r.annotations)
    assert any("과거 검증" in w for w in r.warnings)


def test_detect_signal_without_leader_or_rr_is_not_breakout():
    ctx = make_context(make_ohlcv([(0, 100), (200, 120)]))
    ctx.info["vocal"] = _f(7, lead=False)
    r = detect(ctx)
    assert r.detected and r.stage == NEAR_PIVOT and r.pivot is None
    assert any("대장" in w for w in r.warnings)
    ctx.info["vocal"] = _f(7, rr=1.0)
    r = detect(ctx)
    assert r.stage == NEAR_PIVOT


def test_vocal_is_candidate_but_not_scored():
    from chart_screener import scoring
    ctx = make_context(make_ohlcv([(0, 100), (200, 120)]))
    ctx.info["vocal"] = _f(7)
    r = detect(ctx)
    assert "vocal" not in scoring.BASE_PATTERNS
    assert scoring.is_candidate({"vocal": r}, rs=10)


def test_detect_drops_junk_and_shows_reason():
    ctx = make_context(make_ohlcv([(0, 100), (200, 120)]))
    f = _f(6)
    f["junk"] = ["공시 위험: 작전주 꼴"]
    ctx.info["vocal"] = f
    r = detect(ctx)
    assert not r.detected and r.warnings[0].startswith("잡주로 제외")


def test_detect_reports_skip_reason():
    ctx = make_context(make_ohlcv([(0, 100), (200, 120)]))
    ctx.info["vocal_skip"] = "보컬 판정 안 함 — 테마 분류표가 없다"
    r = detect(ctx)
    assert not r.detected and r.warnings == ["보컬 판정 안 함 — 테마 분류표가 없다"]


def test_junk_flags_rules():
    from chart_screener.vocal import junk_flags
    junk, warn = junk_flags({"debt": 250.0, "ni4": -100.0, "roe": -20.0}, {"level": "작전주 꼴", "ref": [{"cat": "횡령배임"}]}, CFG)
    assert "공시 위험: 작전주 꼴" in junk and any(j.startswith("부채비율") for j in junk) and any(j.startswith("큰 적자") for j in junk)
    assert "횡령 · 배임 혐의" in warn
    junk, warn = junk_flags({"debt": 80.0, "ni4": 50.0, "roe": 8.0}, None, CFG)
    assert junk == [] and warn == []


def test_backtest_rejects_vocal():
    import pytest
    from chart_screener.backtest import BacktestConfig, run_backtest
    with pytest.raises(ValueError, match="전 시장 단면"):
        run_backtest(BacktestConfig(pattern="vocal"))
