import os
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from chart_screener import indicators as ind
from chart_screener.data import ohlcv as ohlcv_mod
from chart_screener.data import universe as universe_mod
from chart_screener.data.ohlcv import KST, OHLCVCache, session_fraction
from chart_screener.market import CONFIRMED, CORRECTION, analyze_market
from chart_screener.patterns import REGISTRY
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, classify_stage
from chart_screener.universe_data import UniverseData, build_context, partial_bar, snapshot_time
from synthetic import flat_index, make_context, make_ohlcv, set_bar


def test_zigzag_alternates_and_finds_swings():
    df = make_ohlcv([(0, 100), (40, 150), (60, 120), (90, 145), (110, 132), (130, 140)], noise=0.002, seed=3)
    piv = ind.zigzag(df["high"], df["low"], 0.05)
    kinds = [p.kind for p in piv]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    highs = [p for p in piv if p.kind == "H"]
    assert abs(highs[0].i - 40) <= 3 and abs(highs[0].price / 150 - 1) < 0.03
    assert piv[-1].confirmed is False


def test_fractal_pivots_no_unconfirmed_tail():
    df = make_ohlcv([(0, 100), (30, 130), (50, 110), (80, 140)], seed=2)
    piv = ind.fractal_pivots(df["high"], df["low"], 5, 5)
    assert all(p.i <= len(df) - 6 for p in piv)


def test_rs_rating_ranks_strongest_highest():
    idx = pd.bdate_range("2023-01-02", periods=300)
    closes = {f"S{k}": pd.Series(100 * (1 + 0.001 * k) ** np.arange(300), index=idx) for k in range(60)}
    rt = ind.rs_rating_table(closes)
    last = rt.iloc[-1]
    assert last["S59"] == 99 and last["S0"] == 1


def test_classify_stage_paths():
    df = make_ohlcv([(0, 100), (100, 100)], noise=0.0, wick=0.0)
    ctx = make_context(df)
    assert classify_stage(ctx, 120, 90)[0] == FORMING
    assert classify_stage(ctx, 103, 90)[0] == NEAR_PIVOT
    df2 = set_bar(df, -2, open=100, high=106, low=100, close=105)
    df2 = set_bar(df2, -1, open=105, high=106, low=103, close=104)
    st, bo = classify_stage(make_context(df2), 102, 90)
    assert st == BREAKOUT and bo == len(df2) - 2
    df3 = set_bar(df, -1, open=100, high=112, low=100, close=111)
    assert classify_stage(make_context(df3), 102, 90)[0] == EXTENDED
    df4 = set_bar(df, -3, open=100, high=106, low=100, close=105)
    df4 = set_bar(df4, -1, open=100, high=100, low=95, close=96)
    assert classify_stage(make_context(df4), 102, 90)[0] == FAILED


def test_market_correction_then_ftd():
    df = make_ohlcv([(0, 1000), (200, 1300), (230, 1050), (260, 1150)], noise=0.001, seed=5)
    st = analyze_market("KOSPI", df)
    assert st.state in (CONFIRMED, CORRECTION)


def test_trend_template_is_helper_not_pattern_and_passes_uptrend():
    # 2026-10-14 패턴 초기화: 트렌드 템플릿은 칩 · 점수에서 빠지고 업종 강도(sector.tt_pass)의 기준 계산으로만 남았다
    from chart_screener.trend import evaluate
    assert "trend_template" not in REGISTRY
    df = make_ohlcv([(0, 50), (300, 140)], noise=0.004, seed=1)
    assert evaluate(make_context(df, rs=95))["passed"] == 8
    df_down = make_ohlcv([(0, 140), (300, 60)], noise=0.004, seed=1)
    assert evaluate(make_context(df_down, rs=20))["passed"] < 8


def test_registry_after_pattern_reset():
    # 옛 탐지기 13개 제거 — 남은 것: 사용자 식 컵 앤 핸들 · 보컬(관찰) · 저평가 종목(정보 칩)
    # + 2026-10-14 《차트의 기술》 영상 기법 6개 (docs/2026-10-14-chart-techniques-*.md) — 라벨은 스펙 그대로
    from chart_screener import techniques as tq
    assert set(REGISTRY) == {"cup_with_handle", "vocal", "undervalued"} | set(tq.PATTERN_LABELS)
    assert REGISTRY["cup_with_handle"][0] == "컵 앤 핸들 (사용자 식)"      # 지운 옛 '컵 앤 핸들'과 라벨로도 구별
    assert {n: REGISTRY[n][0] for n in tq.PATTERN_LABELS} == {
        "red_three_monthly": "월봉 적삼병", "fib_pullback": "피보나치 눌림 반등", "trendline_break": "빗각 추세선 돌파",
        "trendline_fib": "빗각 돌파 + 피보 눌림", "day_leader": "10% 주도주 (단타 관찰)", "ma60_supply": "60일선 수급 돌파"}
    assert not set(REGISTRY) & {"absorb", "stage2", "canslim", "vcp", "cup_handle", "pocket_pivot"}


def test_help_text_describes_current_patterns_only():
    import chart_screener
    from chart_screener.__main__ import LIVE_DESC, LIVE_HELP
    for gone in ("300억", "돌파 전 관찰", "눌림 구간 진입·손절가 이탈을 알리고"):
        assert gone not in LIVE_DESC and gone not in LIVE_HELP, gone
    assert "손절가 이탈 알림이 없고" in LIVE_DESC
    assert "지금 패턴: 컵 앤 핸들(사용자 식" in chart_screener.__doc__


# ---------------------------------------------------------------- 캐시 신선도 · 장중 미완성 봉
def _kst(*a) -> datetime:
    return datetime(*a, tzinfo=KST)


@pytest.mark.parametrize("fetched, at, fresh", [
    (_kst(2026, 10, 6, 16, 0), _kst(2026, 10, 7, 10, 0), False),   # 어제 마감 후 캐시 → 오늘 장중엔 낡음
    (_kst(2026, 10, 7, 9, 50), _kst(2026, 10, 7, 10, 0), True),    # 장중 20분 이내
    (_kst(2026, 10, 7, 9, 30), _kst(2026, 10, 7, 10, 0), False),   # 장중 TTL 경과
    (_kst(2026, 10, 7, 8, 55), _kst(2026, 10, 7, 9, 5), False),    # 장 시작 전에 받은 캐시
    (_kst(2026, 10, 7, 15, 35), _kst(2026, 10, 7, 15, 40), True),  # 15:30~15:45 도 장중 규칙
    (_kst(2026, 10, 6, 16, 0), _kst(2026, 10, 7, 15, 40), False),
    (_kst(2026, 10, 7, 15, 50), _kst(2026, 10, 7, 18, 0), True),   # 확정 종가 이후
    (_kst(2026, 10, 7, 15, 0), _kst(2026, 10, 7, 18, 0), False),
    (_kst(2026, 10, 6, 16, 0), _kst(2026, 10, 7, 8, 0), True),     # 장 전: 어제 확정 종가 이후면 신선
    (_kst(2026, 10, 6, 15, 0), _kst(2026, 10, 7, 8, 0), False),
    (_kst(2026, 10, 9, 16, 0), _kst(2026, 10, 10, 12, 0), True),   # 토요일: 금요일 마감 후 캐시
])
def test_cache_freshness_is_session_aware(tmp_path, fetched, at, fresh):
    cache = OHLCVCache(root=tmp_path)
    p = cache._path("000001")
    p.write_bytes(b"x")
    os.utime(p, (fetched.timestamp(), fetched.timestamp()))
    assert cache.is_fresh("000001", at=at) is fresh


def test_cache_freshness_missing_file(tmp_path):
    assert OHLCVCache(root=tmp_path).is_fresh("999999", at=_kst(2026, 10, 7, 18, 0)) is False


def test_partial_bar_uses_snapshot_time():
    d = pd.Timestamp("2026-10-07")
    part, frac = partial_bar(d, pd.Timestamp("2026-10-07 11:00", tz=KST))
    assert part and frac == pytest.approx(session_fraction(_kst(2026, 10, 7, 11, 0)))
    assert partial_bar(d, pd.Timestamp("2026-10-07 16:56", tz=KST)) == (False, 1.0)   # 장 마감 후
    assert partial_bar(d, pd.Timestamp("2026-10-07 15:30", tz=KST)) == (False, 1.0)
    assert partial_bar(d, pd.Timestamp("2026-10-08 10:00", tz=KST)) == (False, 1.0)   # 다른 날짜의 봉
    assert partial_bar(d, pd.Timestamp("2026-10-07 08:30", tz=KST)) == (False, 1.0)
    assert partial_bar(d, None) == (False, 1.0)
    assert partial_bar(d, pd.Timestamp("2026-10-07 11:00"))[0]                           # tz 없음 = KST


def _ud_with(universe: pd.DataFrame, df: pd.DataFrame, **kw) -> UniverseData:
    return UniverseData(universe.set_index("code", drop=False), {c: df for c in universe["code"]},
                        {"KOSPI": flat_index(len(df), start=str(df.index[0].date()))}, {}, pd.DataFrame(), **kw)


def _snapshot(fetched: str | None, traded: list[str]) -> pd.DataFrame:
    u = pd.DataFrame({"code": [f"00000{i}" for i in range(len(traded))], "name": "x", "market": "KOSPI",
                      "value": 5e9, "market_open": True,
                      "traded_at": pd.to_datetime(traded).tz_localize(KST)})
    if fetched:
        u["fetched_at"] = pd.Timestamp(fetched, tz=KST)
    return u


def test_illiquid_stock_not_partial_after_close():
    df = make_ohlcv([(0, 100), (200, 120)], start="2025-12-22")
    assert df.index[-1] == pd.Timestamp("2026-09-28")
    day = f"{df.index[-1]:%Y-%m-%d}"
    uni = _snapshot(f"{day} 16:56", [f"{day} 12:02", f"{day} 16:55"])   # 0번: 마지막 체결 12:02
    ud = _ud_with(uni, df)
    ctx = build_context("000000", ud)
    assert ctx.partial is False and ctx.session_frac == 1.0
    assert ctx.df["value"].iloc[-1] == 5e9                             # 당일 실제 거래대금 반영
    # 구버전 캐시(fetched_at 없음): 전 종목 traded_at 최댓값을 스냅샷 시각으로
    old = _snapshot(None, [f"{day} 12:02", f"{day} 16:55"])
    assert snapshot_time(old) == pd.Timestamp(f"{day} 16:55", tz=KST)
    assert build_context("000000", _ud_with(old, df)).partial is False


def test_intraday_snapshot_marks_partial():
    df = make_ohlcv([(0, 100), (200, 120)], start="2025-12-22")
    day = f"{df.index[-1]:%Y-%m-%d}"
    ud = _ud_with(_snapshot(f"{day} 11:00", [f"{day} 10:59"]), df)
    ctx = build_context("000000", ud)
    assert ctx.partial is True
    assert ctx.session_frac == pytest.approx(session_fraction(_kst(2026, 9, 28, 11, 0)))
    # 마지막 봉이 스냅샷 날짜가 아니면(정지·지연) 미완성 아님
    ud2 = _ud_with(_snapshot("2026-09-29 11:00", ["2026-09-29 10:59"]), df)
    assert build_context("000000", ud2).partial is False


def test_fetch_universe_adds_fetched_at(monkeypatch):
    rec = {"itemCode": "005930", "stockName": "삼성전자", "stockEndType": "stock",
           "tradeStopType": {"name": "TRADING"}, "closePriceRaw": "70,000", "fluctuationsRatio": "1.2",
           "accumulatedTradingVolumeRaw": "100", "accumulatedTradingValueRaw": "7000000",
           "marketValueRaw": "1000000000000", "localTradedAt": "2026-10-07T12:02:00+09:00",
           "marketStatus": "OPEN"}

    class Resp:
        def json(self):
            return {"stocks": [rec], "totalCount": 1}

    monkeypatch.setattr(universe_mod.http, "get", lambda url, **kw: Resp())
    monkeypatch.setattr(universe_mod, "now_kst", lambda: _kst(2026, 10, 7, 16, 56))
    u = universe_mod.fetch_universe()
    assert "fetched_at" in u.columns and len(u) == 1
    ts = u["fetched_at"].iloc[0]
    assert ts == pd.Timestamp("2026-10-07 16:56", tz=KST) and ts.utcoffset().total_seconds() == 9 * 3600
    assert ohlcv_mod.now_kst().tzinfo is not None
