"""《차트의 기술》 기법 통합: 패턴 묶음(베이스 · 신호 · 관찰) · 후보 규칙 · 표시 대표 · 일지 rule id ·
기법 공통 칸(체크리스트 10 '검증 전' · 청산 계획 · 배지 · 시장 맥락) · 리포트 자료 · 백테스트 신호일 · 사전 필터 · 손절 판정."""
import json
import math
import re
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from chart_screener import backtest as bt_mod
from chart_screener import journal, scanner, scoring, technique_panel
from chart_screener import techniques as tq
from chart_screener.config import Config
from chart_screener.patterns import REGISTRY
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult
from chart_screener.report.html import build_payload, render
from chart_screener.scanner import ScanResult, StockScan
from chart_screener.universe_data import UniverseData
from synthetic import add_value, confirmed_market, flat_index, make_context, make_ohlcv

CWH, TL, FIB, TLF, MA60, RED3, DL = ("cup_with_handle", "trendline_break", "fib_pullback", "trendline_fib",
                                     "ma60_supply", "red_three_monthly", "day_leader")


def _pr(name, stage=BREAKOUT, pivot=100.0, stop=None, score=70.0, detected=True, **kw):
    return PatternResult(name=name, label=REGISTRY[name][0] if name in REGISTRY else name, detected=detected,
                         score=score, stage=stage, pivot=pivot, stop=stop, **kw)


def _stock(results, close=101.0, code="000010", df=None, info=None):
    sb = scoring.compute(results, 80.0, close=close)
    s = StockScan(code=code, name="시험", market="KOSPI", close=close, change_pct=0.0, market_cap=1e12, rs=80.0,
                  value_today=1e10, avg_value_20=1e10, max_value_5=1e10, partial=False, results=results, score=sb)
    s.ctx = make_context(df if df is not None else make_ohlcv([(0, 100), (299, 101)], seed=3), code=code, info=info)
    s.position = scanner.position_plan(s)
    return s


# ---------------------------------------------------------------- 묶음 · 후보 · 대표
def test_every_registered_pattern_has_one_group_and_rule_id():
    groups = {**{n: "base" for n in scoring.BASE_PATTERNS}, **{n: "signal" for n in scoring.SIGNAL_PATTERNS},
              **{n: "observe" for n in scoring.OBSERVE_PATTERNS}, **{n: "info" for n in scoring.INFO_PATTERNS}}
    assert set(groups) == set(REGISTRY)
    assert set(tq.RULE_IDS) == set(tq.PATTERN_LABELS) and set(scoring.SIGNAL_CANDIDATE_STAGES) == set(scoring.SIGNAL_PATTERNS)
    # 일지 rule 칸: 모듈마다 metrics['rule_version'] = tq.RULE_IDS (탐지 안 돼도)
    ctx = make_context(make_ohlcv([(0, 100), (150, 80), (299, 120)], seed=5), code="000020")
    for name, rid in tq.RULE_IDS.items():
        assert journal.rule_of(REGISTRY[name][1](ctx)) == rid, name


def test_candidate_rules_by_group():
    assert scoring.is_candidate({TL: _pr(TL, pivot=50.0)})
    assert scoring.is_candidate({TL: _pr(TL, stage=FAILED, pivot=50.0)})          # 베이스는 단계와 무관 (컵 앤 핸들과 같게)
    assert not scoring.is_candidate({FIB: _pr(FIB, stage=NEAR_PIVOT, pivot=None)})  # 피보 신호 전 접촉 — 피벗 없음
    assert scoring.is_candidate({FIB: _pr(FIB, stage=BREAKOUT, pivot=93.0, stop=85.0)})
    for st, ok in ((BREAKOUT, True), (NEAR_PIVOT, True), (EXTENDED, True), (FAILED, False)):
        assert scoring.is_candidate({MA60: _pr(MA60, stage=st)}) is ok, st
    for st, ok in ((BREAKOUT, True), (EXTENDED, True), (NEAR_PIVOT, False), (FORMING, False), (FAILED, False)):
        assert scoring.is_candidate({RED3: _pr(RED3, stage=st)}) is ok, st
    assert scoring.is_candidate({DL: _pr(DL, stage=NEAR_PIVOT, pivot=None)})       # 관찰 칩은 혼자 후보
    assert not scoring.is_candidate({MA60: _pr(MA60, detected=False)})


def test_compute_uses_only_pivot_bases_and_merges_trendline_pair():
    fib_touch = _pr(FIB, stage=NEAR_PIVOT, pivot=None, score=99.0)
    cup = _pr(CWH, stage=FORMING, pivot=200.0, score=50.0)
    sb = scoring.compute({FIB: fib_touch, CWH: cup}, 80.0, close=150.0)
    assert sb.best_pattern == CWH and FIB in sb.detected_bases and sb.structures == 1
    # 신호 · 관찰만: 대표 없음, W 0.6, 패턴 몫 0 (종합 점수 밖)
    sb = scoring.compute({MA60: _pr(MA60, score=100.0), RED3: _pr(RED3, score=90.0)}, 90.0, close=101.0)
    assert sb.best_pattern is None and sb.pattern_part == 0 and sb.stage_weight == 0.6
    # 빗각과 빗각+피보는 같은 동결 선 — 중첩 보너스 없음
    tl = _pr(TL, pivot=100.0, stop=95.0, start_date="2026-01-02", end_date="2026-09-01")
    tlf = _pr(TLF, pivot=130.0, stop=120.0, start_date="2026-05-02", end_date="2026-10-13")
    sb = scoring.compute({TL: tl, TLF: tlf}, 80.0, close=131.0)
    assert sb.structures == 1 and not any("중첩" in n for n in sb.notes)


def test_display_lead_plan_text_and_live_lead():
    s = _stock({MA60: _pr(MA60), FIB: _pr(FIB, stage=NEAR_PIVOT, pivot=None)})
    assert s.lead() is None and s.display_lead().name == MA60
    assert scanner.plan_text(s) == f"{REGISTRY[MA60][0]} — {scoring.NO_STOP_REASON[MA60]} 매수 계획(수량) 없음"
    s = _stock({DL: _pr(DL, stage=NEAR_PIVOT, pivot=None), "vocal": _pr("vocal", stage=FORMING, pivot=None)})
    assert s.display_lead().name == DL and scanner.plan_text(s) == scanner.OBSERVE_PLAN[DL]
    s = _stock({FIB: _pr(FIB, stage=NEAR_PIVOT, pivot=None), "vocal": _pr("vocal", stage=FORMING, pivot=None)})
    assert s.display_lead().name == "vocal"                                         # 후보를 만든 관찰 칩 먼저
    s = _stock({CWH: _pr(CWH, pivot=100.0, score=40.0), TL: _pr(TL, pivot=99.0, stop=95.0, score=95.0)})
    assert s.lead().name == TL and s.live_lead().name == CWH                        # 실시간 감시는 컵 앤 핸들만
    assert _stock({TL: _pr(TL, pivot=99.0, stop=95.0)}).live_lead() is None
    from chart_screener.live import select_watchlist
    scan = ScanResult(asof=pd.Timestamp("2026-10-13"), generated_at=pd.Timestamp("2026-10-13 16:00"), market={},
                      stocks=[_stock({TL: _pr(TL, stage=NEAR_PIVOT, pivot=99.0)}, close=98.5)], scanned=1, elapsed=0,
                      patterns=[])
    assert select_watchlist(scan, 40) == []


def test_trendline_low_volume_and_pending_breaks_have_no_buy_quantity():
    for phase, word in (("lowvol", "관찰만"), ("pending", "안착 확인 대기")):
        s = _stock({TL: _pr(TL, stage=FORMING if phase == "lowvol" else NEAR_PIVOT, pivot=100.0, stop=97.0,
                            metrics={"phase": phase})}, close=101.0)
        assert s.position["shares"] == 0 and s.position["cap"] is None and word in s.position["plan"]
    s = _stock({TL: _pr(TL, stage=BREAKOUT, pivot=100.0, stop=97.0, breakout_date="2026-10-10",
                        metrics={"phase": "confirmed"})}, close=101.0)
    assert s.position["shares"] > 0 and s.position["plan"].startswith("돌파 확인")


def test_journal_rows_use_display_lead_rule_ids():
    s1 = _stock({MA60: _pr(MA60, metrics={"rule_version": "ma60s_v1"})}, code="000011")
    s2 = _stock({TL: _pr(TL, pivot=99.0, stop=95.0, metrics={"rule_version": "tlbrk_v1"})}, code="000012")
    scan = ScanResult(asof=pd.Timestamp("2026-10-13"), generated_at=pd.Timestamp("2026-10-13 16:00"), market={},
                      stocks=[s1, s2], scanned=2, elapsed=0, patterns=[])
    rows = journal.scan_rows(scan).set_index("code")
    assert rows.loc["000011", "pattern"] == MA60 and rows.loc["000011", "rule"] == "ma60s_v1"
    assert rows.loc["000012", "pattern"] == TL and rows.loc["000012", "rule"] == "tlbrk_v1"


# ---------------------------------------------------------------- 기법 공통 칸
def _risk_file(tmp_path, codes):
    p = tmp_path / "공시위험.json"
    p.write_text(json.dumps({"기준일": "20261013", "codes": codes}, ensure_ascii=False), encoding="utf-8")
    return str(p)


def _ud(n=300, k=4, seed=0):
    frames = {f"00010{i}": make_ohlcv([(0, 10000), (n // 2, 9000 + 400 * i), (n - 1, 11000 + 300 * i)], seed=seed + i, n=n)
              for i in range(k)}
    rows = [{"code": c, "name": f"종목{c[-1]}", "market": "KOSPI", "market_cap": 1e12, "traded_at": pd.NaT,
             "market_open": False, "value": 0.0} for c in frames]
    idx = next(iter(frames.values())).index
    uni = pd.DataFrame(rows).set_index("code", drop=False)
    rs = pd.DataFrame({c: np.full(len(idx), 85.0) for c in frames}, index=idx)
    return UniverseData(uni, frames, {"KOSPI": flat_index(len(idx), start=str(idx[0].date()))},
                        {"KOSPI": confirmed_market()}, rs, idx[-1])


def test_scan_inputs_fill_info_badges_and_risk(tmp_path, monkeypatch):
    ud = _ud()
    codes = list(ud.ohlcv)
    sm = pd.DataFrame({"code": codes, "sector": ["반도체"] * 3 + ["소규모"], "themes": [[] for _ in codes]})
    monkeypatch.setenv(technique_panel.RISK_ENV, _risk_file(tmp_path, {
        codes[0]: {"level": "작전주 꼴", "ref": [{"cat": "자본잠식"}, {"cat": "불성실_지정"}]}}))
    si = technique_panel.scan_inputs(ud, sm, None, None, Config())
    assert si.risk_date == "20261013" and si.summary()["risk_loaded"] and si.summary()["industry_rs_groups"] == 1
    ctx = make_context(ud.ohlcv[codes[0]], code=codes[0], info={"market_cap": 1e12,
                                                                "undervalued": {"tier": "저평가", "tier_why": ["PER 바닥"], "score": 77.0}})
    technique_panel.fill_info(ctx, si)
    assert ctx.info["industry_rs"]["group"] == "반도체" and ctx.info["industry_rs"]["members"] == 3
    assert ctx.info["sector_pos52"] is not None and ctx.info["risk"]["level"] == "작전주 꼴"
    small = make_context(ud.ohlcv[codes[3]], code=codes[3])
    technique_panel.fill_info(small, si)
    assert small.info["industry_rs"]["rank_pct"] is None and small.info["risk"] is None   # 구성 3종목 미만 → 5번 모름
    b = technique_panel.badges(ctx)
    assert b["tier"] == "저평가" and ["공시 위험: 작전주 꼴", "bad"] in b["risk"] and ["자본잠식", "bad"] in b["risk"]
    assert ["불성실공시", "warn"] in b["risk"]
    # 체크리스트 9 = 같은 공시위험 자료로 경고, 5 = 업종 RS
    s = _stock({CWH: _pr(CWH, stage=NEAR_PIVOT, pivot=12000.0)}, close=11500.0, code=codes[0], df=ud.ohlcv[codes[0]])
    s.ctx = ctx
    p = technique_panel.stock_panel(s)
    it = {x["no"]: x for x in p["checklist"]}
    assert p["source"] == "scan" and p["label"] == "검증 전" and len(p["checklist"]) == 10
    assert it[9]["status"] == tq.WARN and "작전주 꼴" in it[9]["note"]
    assert it[5]["status"] in (tq.PASS, tq.WARN) and it[4]["status"] == tq.UNKNOWN          # 컵 앤 핸들 — 재현 안 함
    assert sum(p["counts"].values()) == 10 and p["exit_plan"]["ma10"] is not None


def test_stock_panel_reuses_pattern_checklist_and_exit_plan():
    df = make_ohlcv([(0, 100), (299, 101)], seed=3)
    own = [{"no": i, "name": f"항목{i}", "status": tq.PASS, "status_label": "통과", "value": None, "note": "", "origin": "x"}
           for i in range(1, 11)]
    r = _pr(FIB, pivot=93.0, stop=85.0, metrics={"checklist": own, "exit_plan": {"ma5": 1.0, "notes": []}})
    s = _stock({FIB: r}, df=df)
    p = technique_panel.stock_panel(s)
    assert p["source"] == FIB and p["checklist"] is own and p["exit_source"] == FIB and p["counts"][tq.PASS] == 10


def test_red3_replay_uses_known_bar_and_only_matured_signals():
    from test_red_three_monthly import _long_df
    df = _long_df()
    rp = technique_panel.red3_replay(df)
    sig = __import__("chart_screener.patterns.red_three_monthly", fromlist=["signals"]).signals(df)
    assert rp and len(rp) <= len(sig)
    C = df["close"].to_numpy()
    for r, x in zip(rp, [x for x in sig if x["known_i"] is not None and x["known_i"] + 20 <= len(df) - 1]):
        k = x["known_i"]
        assert r["date"] == x["known_date"] and r["ret20"] == pytest.approx(C[k + 20] / C[k] - 1)
    # 앞부분 불변: 잘라 낸 자료의 재현은 전체 재현의 앞부분
    cut = df.iloc[:len(df) - 30]
    assert technique_panel.red3_replay(cut) == rp[:len(technique_panel.red3_replay(cut))]


def test_market_panel_drops_unfinished_index_bar():
    n = 400
    idx = flat_index(n, start="2025-03-03")
    ud = UniverseData(pd.DataFrame(), {}, {"KOSPI": idx}, {}, pd.DataFrame(), idx.index[-1])
    full = technique_panel.market_panel(ud)["KOSPI"]
    assert full["date"] == f"{idx.index[-1]:%Y-%m-%d}" and full["partial_dropped"] is False
    assert full["ma120"] is not None and set(full["red3_monthly"]) <= set(technique_panel.RED3_KEEP)
    ud.fetched_at = pd.Timestamp(f"{idx.index[-1]:%Y-%m-%d} 10:30", tz="Asia/Seoul")     # 장중 스냅샷
    part = technique_panel.market_panel(ud)["KOSPI"]
    assert part["partial_dropped"] is True and part["date"] == f"{idx.index[-2]:%Y-%m-%d}"
    assert technique_panel.eod_asof(ud) == idx.index[-2]


def test_checklist_market_item_uses_completed_index_bar(monkeypatch):
    """체크리스트 1 — 장중 스냅샷이면 ctx.market_state(오늘 미완성 지수 봉 포함 잠정)가 아니라 완성 봉 국면."""
    ud = _ud()
    code = next(iter(ud.ohlcv))
    last = ud.index["KOSPI"].index[-1]
    ctx = make_context(ud.ohlcv[code], code=code, market_state=ud.market["KOSPI"])
    technique_panel.fill_info(ctx, technique_panel.scan_inputs(ud, None, None, None, Config()))
    assert ctx.info["market_state_eod"] is ud.market["KOSPI"]                       # 완성 봉뿐 → 그대로
    ud.fetched_at = pd.Timestamp(f"{last:%Y-%m-%d} 10:30", tz="Asia/Seoul")
    si = technique_panel.scan_inputs(ud, None, None, None, Config())
    ctx = make_context(ud.ohlcv[code], code=code, market_state=ud.market["KOSPI"])
    technique_panel.fill_info(ctx, si)
    ms = tq.inputs_from_ctx(ctx).market_state
    assert ms is not ud.market["KOSPI"] and ms.date == f"{ud.index['KOSPI'].index[-2]:%Y-%m-%d}"
    item = tq.run_checklist(tq.Bars.from_df(ctx.df), inputs=tq.inputs_from_ctx(ctx))[0]
    assert item.no == 1 and item.status in (tq.PASS, tq.WARN) and ms.date in item.note
    # 다시 판정하지 못하면 1번 '모름' (잠정 국면을 섞지 않음)
    monkeypatch.setattr("chart_screener.market.analyze_market", lambda *a, **k: 1 / 0)
    ctx = make_context(ud.ohlcv[code], code=code, market_state=ud.market["KOSPI"])
    technique_panel.fill_info(ctx, technique_panel.scan_inputs(ud, None, None, None, Config()))
    assert ctx.info["market_state_eod"] is None
    assert tq.run_checklist(tq.Bars.from_df(ctx.df), inputs=tq.inputs_from_ctx(ctx))[0].status == tq.UNKNOWN


def test_run_scan_attaches_panels_market_ctx_and_report(monkeypatch, tmp_path):
    ud = _ud(k=3)
    codes = list(ud.ohlcv)
    monkeypatch.setenv(technique_panel.RISK_ENV, _risk_file(tmp_path, {codes[1]: {"level": "상폐 절차"}}))
    monkeypatch.setattr(scoring, "is_candidate", lambda results, rs=None: True)
    sm = pd.DataFrame({"code": codes, "sector": ["반도체"] * 3, "themes": [[] for _ in codes]})
    scan = scanner.run_scan(ud, Config(), include_all=True, verbose=False, sector_map=sm)
    assert len(scan.stocks) == 3 and all(s.panel and len(s.panel["checklist"]) == 10 for s in scan.stocks)
    assert all("industry_rs" in s.ctx.info and "risk" in s.ctx.info for s in scan.stocks)
    risky = next(s for s in scan.stocks if s.code == codes[1])
    assert risky.badges["risk"] == [["공시 위험: 상폐 절차", "bad"]]
    assert scan.market_ctx and "KOSPI" in scan.market_ctx and scan.tech_info["risk_loaded"]
    fr = scanner.to_frame(scan).set_index("종목코드")
    assert fr.loc[codes[1], "공시위험"] == "공시 위험: 상폐 절차" and fr["체크리스트(검증 전)"].str.startswith("통과").all()
    # 리포트: 기법 칸 · 시장 맥락 · 출처 표 공유
    d = build_payload(scan)
    st = d["stocks"][0]
    assert st["panel"]["label"] == "검증 전" and d["market_ctx"]["KOSPI"]["name"] == "KOSPI" and d["tech_info"]
    assert d["signal_patterns"] == [MA60, RED3] and d["pattern_kind"][DL] == "observe"
    refs = [p["metrics"]["origin"] for s in d["stocks"] for p in s["patterns"].values()
            if isinstance(p["metrics"].get("origin"), dict) and "$ref" in p["metrics"]["origin"]]
    assert refs and all(r["$ref"] in d["origins"] for r in refs)
    assert len(d["origins"]) < len(refs)                                                   # 같은 표는 한 번만
    html = render(d)
    for needle in ('id="dTech"', 'id="mctx"', 'id="techNote"', "참고 — 불코우스키 미국 통계(우리 데이터 아님)", "검증 전 · 점수에 안 들어감",
                   "영상 시각", "구현 선택", "체크 10 (검증 전)", "renderTech", "trendline_break: {"):
        assert needle in html, needle
    for gone in ("+61%", "+436%"):                                                         # 영상 사례 수익률은 싣지 않는다
        assert gone not in html
    if shutil.which("node"):
        js = tmp_path / "r.js"
        js.write_text(re.findall(r"<script>(.*?)</script>", html, re.S)[0], encoding="utf-8")
        out = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True, encoding="utf-8")
        assert out.returncode == 0, out.stderr


def test_refresh_flow_patterns_reruns_ma60_only_with_flows(monkeypatch):
    calls = []
    fake = lambda ctx: calls.append(ctx.code) or _pr(MA60, metrics={"flow_label": "수급 동반"})
    monkeypatch.setitem(REGISTRY, MA60, (REGISTRY[MA60][0], fake))
    a = _stock({MA60: _pr(MA60, metrics={"flow_label": "수급 미확인"})}, code="000031")
    b = _stock({MA60: _pr(MA60, metrics={"flow_label": "수급 미확인"})}, code="000032")
    a.ctx.info["investor"] = pd.DataFrame({"inst_net": [1.0]})
    scan = ScanResult(asof=pd.Timestamp("2026-10-13"), generated_at=pd.Timestamp("2026-10-13 16:00"), market={},
                      stocks=[a, b], scanned=2, elapsed=0, patterns=[])
    assert scanner.refresh_flow_patterns(scan) == 1 and calls == ["000031"]
    assert a.results[MA60].metrics["flow_label"] == "수급 동반" and b.results[MA60].metrics["flow_label"] == "수급 미확인"
    assert a.panel is not None


# ---------------------------------------------------------------- 백테스트: 신호일 · 손절 판정 · 사전 필터
def test_event_date_and_stop_rule_per_pattern():
    tl = _pr(TL, pivot=100.0, stop=95.0, breakout_date="2026-09-01",
             metrics={"break": {"conf_date": "2026-09-03"}, "line": {"anchor_i": 10, "anchor_price": 120.0, "slope_ln": -0.002}})
    assert bt_mod.event_date(TL, tl) == "2026-09-03" and bt_mod.stop_rule(TL, tl) == "close_line"
    tl.breakout_date = None
    assert bt_mod.event_date(TL, tl) is None                                   # 거래량 미달 · 미확인 돌파는 신호 아님
    r3 = _pr(RED3, breakout_date="2026-09-30", metrics={"known_date": "2026-10-01"})
    assert bt_mod.event_date(RED3, r3) == "2026-10-01" and bt_mod.stop_rule(RED3, r3) is None
    fib = _pr(FIB, pivot=93.0, stop=85.0, breakout_date="2026-10-13")
    assert bt_mod.event_date(FIB, fib) == "2026-10-13" and bt_mod.stop_rule(FIB, fib) == "low"
    assert bt_mod.stop_rule(CWH, _pr(CWH)) is None and bt_mod.stop_rule(MA60, _pr(MA60, stop=None)) is None
    line = tq.TrendLine(anchor_i=10, anchor_price=120.0, ln0=math.log(120.0), slope=-0.002, touches=[10], t=50)
    for i in (10, 30, 77):
        assert bt_mod._line_value({"anchor_i": 10, "anchor_price": 120.0, "slope_ln": -0.002}, i) == pytest.approx(line.value(i))
    with pytest.raises(ValueError, match="stage"):
        bt_mod.run_backtest(bt_mod.BacktestConfig(pattern=DL))


def test_prefilter_kinds_are_supersets():
    rng = np.random.default_rng(1)
    n = 260
    c = 10000 * np.cumprod(1 + rng.normal(0, 0.02, n))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.01, n))
    df = add_value(pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99, "close": c,
                                 "volume": rng.uniform(1e5, 1e6, n)}, index=pd.bdate_range("2024-01-02", periods=n)))
    h = df["high"].to_numpy()
    assert (bt_mod._maybe_breakout_day(FIB, h, c, df) == (c > o)).all()
    m = bt_mod._maybe_breakout_day(MA60, h, c, df)
    sma = tq.sma(c, 60)
    crosses = [t for t in range(61, n) if tq.cross_above(c, sma, t)]
    assert crosses and all(m[t] for t in crosses)
    # 달의 첫 거래 봉 — 앞선 같은 달 봉이 거래량 0 이면 그다음 봉도
    df2 = df.copy()
    first = [i for i in range(1, n) if df.index[i].month != df.index[i - 1].month]
    df2.iloc[first[0], df2.columns.get_loc("volume")] = 0
    mf = bt_mod._maybe_breakout_day(RED3, h, c, df2)
    assert mf[first[0]] and mf[first[0] + 1] and not mf[first[0] + 2] and all(mf[i] for i in first)
    assert mf.sum() == len(first) + 2                                          # 첫 봉(0) + 각 달 첫 봉 + 정지 다음 봉


def test_prefilters_never_miss_real_detector_signals():
    """실제 탐지기로: 날마다 detect(df[:t+1]) 의 신호일 == t 이면 사전 필터도 t 를 남긴다 (놓침 없음)."""
    from test_fib_pullback import _random_df
    from test_trendline_fib import _rand_df
    cases = [(FIB, _random_df(11), 40), (MA60, _random_df(12, n=260), 70), (TL, _rand_df(5), 300), (TLF, _rand_df(5), 300)]
    hits = {}
    for name, df, start in cases:
        fn = REGISTRY[name][1]
        mask = bt_mod._maybe_breakout_day(name, df["high"].to_numpy(float), df["close"].to_numpy(float), df)
        hits[name] = 0
        for t in range(start, len(df)):
            r = fn(make_context(df.iloc[:t + 1], code="000099"))
            if r.detected and bt_mod.event_date(name, r) == f"{df.index[t]:%Y-%m-%d}":
                hits[name] += 1
                assert mask[t], (name, t)
    assert hits[FIB] and hits[MA60] and hits[TL], hits                         # 시험이 빈 손이 아니게
