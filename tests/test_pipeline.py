import json
import re

import pandas as pd

from chart_screener import scoring
from chart_screener.patterns.base import BREAKOUT, EXTENDED, PatternResult
from chart_screener.report.html import build_payload, render
from chart_screener.scanner import ScanResult, scan_one
from synthetic import confirmed_market, make_context, make_ohlcv


CWH = "cup_with_handle"


def _pr(name, detected=True, score=80.0, stage=BREAKOUT):
    return PatternResult(name=name, label=name, detected=detected, score=score, stage=stage, pivot=100.0, stop=93.0)


def test_composite_prefers_actionable_stage():
    a = scoring.compute({CWH: _pr(CWH, stage=BREAKOUT)}, rs=90)
    b = scoring.compute({CWH: _pr(CWH, stage=EXTENDED)}, rs=90)
    assert a.composite > b.composite
    assert a.best_pattern == CWH and a.best_stage == BREAKOUT


def test_composite_bonus_and_market_penalty():
    res = {CWH: _pr(CWH)}
    base = scoring.compute(res, rs=90, recent_big_value=True)
    assert "거래대금 300억+ +5" in " ".join(base.notes)
    ms = confirmed_market()
    ms.state = "correction"
    worse = scoring.compute(res, rs=90, market_state=ms, recent_big_value=True)
    assert worse.composite < base.composite


def test_candidate_rule():
    assert scoring.is_candidate({CWH: _pr(CWH)})
    assert not scoring.is_candidate({"vcp": _pr("vcp")})                    # 2026-10-14 제거된 옛 키
    assert not scoring.is_candidate({"trend_template": _pr("trend_template")})


def test_scan_one_and_report_render_roundtrip():
    df = make_ohlcv([(0, 50), (300, 140), (330, 128), (360, 139)], seed=4)
    ctx = make_context(df, rs=93)
    s = scan_one(ctx)
    scan = ScanResult(asof=df.index[-1], generated_at=pd.Timestamp("2026-10-07 16:00"),
                      market={"KOSPI": confirmed_market()}, stocks=[s], scanned=1, elapsed=0.1,
                      patterns=list(s.results))
    payload = build_payload(scan)
    assert payload["stocks"][0]["code"] == "TEST"
    html = render(payload)
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert m, "데이터 블록이 템플릿에 주입되어야 함"
    data = json.loads(m.group(1))
    assert len(data["stocks"][0]["ohlcv"]["t"]) == len(data["stocks"][0]["ohlcv"]["c"])
    assert "NaN" not in m.group(1)
    frag = render(payload, standalone=False)
    assert not frag.lstrip().lower().startswith("<!doctype")


# ---------------------------------------------------------------- 포지션 계획·표·레이더·스캔 배선
import math  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402

from chart_screener import scanner  # noqa: E402
from chart_screener.config import Config  # noqa: E402
from chart_screener.patterns.base import FAILED, FORMING, NEAR_PIVOT  # noqa: E402
from chart_screener.scanner import StockScan, position_plan, radar_entry, to_frame  # noqa: E402
from synthetic import flat_index, set_bar  # noqa: E402


def _stock(results, close=9800.0, avg_value=50e8, market_cap=1e12, rs=90.0, code="000001", name="가나다"):
    sb = scoring.compute(results, rs, close=close)
    s = StockScan(code=code, name=name, market="KOSPI", close=close, change_pct=0.01, market_cap=market_cap, rs=rs,
                  value_today=avg_value, avg_value_20=avg_value, max_value_5=avg_value, partial=False,
                  results=results, score=sb)
    s.position = position_plan(s)
    return s


def _base(stage=NEAR_PIVOT, pivot=10000.0, stop=9300.0, name=CWH, bo=None, metrics=None):
    return PatternResult(name=name, label=name, detected=True, score=80, stage=stage, pivot=pivot, stop=stop,
                         breakout_date=bo, metrics=metrics or {})


def test_position_plan_risk_sizing():
    p = _stock({CWH: _base()}).position
    assert p["entry"] == 10000 and p["stop"] == 9300
    assert p["risk_pct"] == pytest.approx(0.07)
    assert p["shares"] == math.floor(1e8 * 0.01 / 700) and p["cap"] == "위험"
    assert p["amount"] == p["shares"] * 10000 and p["max_loss"] == p["shares"] * 700
    assert p["plan"] == "피벗 10,000 돌파 매수"
    # 비중 한도 20% (손절폭이 좁을 때)
    p = _stock({CWH: _base(stop=9950)}).position
    assert p["cap"] == "비중" and p["shares"] == 2000
    # 유동성 한도: 20일 평균 거래대금 2억 × 2% = 400만 → 400주
    p = _stock({CWH: _base()}, avg_value=2e8).position
    assert p["cap"] == "유동성" and p["shares"] == 400


def test_position_plan_texts():
    # 피벗 기준 손절폭(진입가 바닥)이 10% 를 넘으면 눌림으로 줄지 않는다 → '관망' (예전 '눌림 대기'는 풀릴 수 없는 문구)
    assert _stock({CWH: _base(stop=8800)}).position["plan"] ==         "관망 — 손절폭 12.0% > 10% (피벗 진입 기준 10,000 · 눌림으로 줄지 않음)"
    assert _stock({CWH: _base(stop=8800)}).position["shares"] == 0
    # 피벗 위에서 손절폭만 큰 경우는 피벗 쪽으로 눌리면 풀린다 → '눌림 대기'
    p = _stock({CWH: _base(stage=BREAKOUT, bo="2026-10-06")}, close=10500).position
    assert p["plan"].startswith("눌림 대기 (손절폭 11.4% > 10%") and p["shares"] == 0
    p = _stock({CWH: _base(stage=BREAKOUT, bo="2026-10-06")}, close=10300).position
    assert p["entry"] == 10300 and p["plan"].startswith("돌파 확인")
    assert _stock({CWH: _base(bo="2026-10-01")}, close=9900).position["plan"] == "피벗 10,000 재돌파 매수"
    assert _stock({CWH: _base(stage=FAILED, bo="2026-10-01")}, close=9500).position["plan"] == "돌파 실패 — 관망"
    # 돌파 후 손절가 아래로 밀렸으면 관망
    assert _stock({CWH: _base(bo="2026-10-01")}, close=9200).position["plan"] == "손절가 이탈 — 관망"
    # 돌파 전 형성 중: 지금 가격이 손절가 아래여도 피벗 역지정가 매수 계획은 유효
    p = _stock({CWH: _base(stage=FORMING)}, close=8000).position
    assert p["plan"] == "피벗 10,000 돌파 매수" and p["shares"] > 0
    # 표·리포트의 손절폭(entry_risk)과 점수의 손절폭도 같은 진입가 기준
    s = _stock({CWH: _base(stage=BREAKOUT, bo="2026-10-06")}, close=10300)
    assert s.entry_risk() == (10300, pytest.approx(s.position["risk_pct"], abs=1e-4))
    assert s.score.entry_risk == pytest.approx(s.position["risk_pct"], abs=1e-4)
    # 대표 패턴이 없으면 계획 없음
    assert _stock({}).position is None


def test_no_stop_pattern_gets_no_plan():
    # 컵 앤 핸들 식에는 손절 규칙이 없다 — 수량을 지어내지 않고 표에 이유를 적는다
    s = _stock({CWH: _base(stop=None)})
    assert s.position is None and s.entry_risk() == (10000, None)
    scan = ScanResult(asof=pd.Timestamp("2026-10-07"), generated_at=pd.Timestamp("2026-10-07 16:00"),
                      market={}, stocks=[s], scanned=1, elapsed=0.0, patterns=[CWH])
    row = to_frame(scan).iloc[0]
    assert row["진입계획"] == scanner.NO_STOP_PLAN and pd.isna(row["권장수량"]) and pd.isna(row["손절가"])


def test_to_frame_nan_market_cap_and_new_columns():
    s = _stock({CWH: _base()}, market_cap=float("nan"))
    s.groups = {"sector": "반도체", "themes": [["HBM", 0.9], ["AI", 0.8]], "best_rank_pct": 0.9}
    s.badge = "신규"
    scan = ScanResult(asof=pd.Timestamp("2026-10-07"), generated_at=pd.Timestamp("2026-10-07 16:00"),
                      market={}, stocks=[s], scanned=1, elapsed=0.0, patterns=[CWH])
    df = to_frame(scan)
    row = df.iloc[0]
    assert pd.isna(row["시가총액(억)"])
    for c in ("권장수량", "투입금액(만원)", "최대손실(만원)", "진입계획", "업종", "테마", "배지"):
        assert c in df.columns
    assert row["업종"] == "반도체" and row["테마"] == "HBM, AI" and row["배지"] == "신규"
    assert row["권장수량"] == s.position["shares"]
    empty = to_frame(ScanResult(asof=None, generated_at=pd.Timestamp("2026-10-07"), market={}, stocks=[],
                                scanned=0, elapsed=0.0, patterns=[]))
    assert empty.empty and "진입계획" in empty.columns


def test_scanresult_defaults_for_old_callers():
    scan = ScanResult(asof=None, generated_at=pd.Timestamp("2026-10-07"), market={}, stocks=[], scanned=0,
                      elapsed=0.0, patterns=[])
    assert scan.radar == [] and scan.groups == [] and scan.dropped == []
    assert scan.breadth is None and scan.prev_asof is None
    assert scan.account["size"] == Config().account_size and scan.account["risk_per_trade"] == 0.01


def _big_candle_df(i=-3, chg=0.10, volume=5e6):
    df = make_ohlcv([(0, 10000), (299, 10000)], seed=7, noise=0.002)
    pc = float(df["close"].iloc[i - 1])
    return set_bar(df, i, open=pc, close=pc * (1 + chg), high=pc * (1 + chg) * 1.005, low=pc * 0.995,
                   volume=volume)


def test_radar_entry():
    df = _big_candle_df()
    ctx = make_context(df, rs=80)
    rd = radar_entry(ctx)
    assert rd is not None and rd["date"] == f"{df.index[-3]:%Y-%m-%d}" and rd["days_ago"] == 2
    assert rd["change"] == pytest.approx(0.10, abs=1e-3) and rd["value"] >= Config().big_value_threshold
    pc = float(df["close"].iloc[-4])
    assert rd["support"] == pytest.approx((pc + pc * 1.1) / 2, rel=1e-3)
    assert rd["holding"] == (rd["close"] >= rd["support"])
    assert radar_entry(make_context(_big_candle_df(chg=0.05))) is None        # +7% 미만
    assert radar_entry(make_context(_big_candle_df(volume=1e5))) is None       # 300억 미만
    assert radar_entry(make_context(_big_candle_df(i=-12))) is None            # 10거래일 밖


def _synthetic_ud(n_stocks=2):
    from chart_screener.universe_data import UniverseData
    ohlcv, rows = {}, []
    for k in range(n_stocks):
        code = f"00000{k}"
        df = _big_candle_df() if k == 0 else make_ohlcv([(0, 8000), (200, 12000), (299, 12500)], seed=k)
        ohlcv[code] = df
        rows.append({"code": code, "name": f"종목{k}", "market": "KOSPI", "market_cap": float("nan"),
                     "traded_at": pd.NaT, "market_open": False, "value": 0.0})
    uni = pd.DataFrame(rows).set_index("code", drop=False)
    idx = ohlcv["000000"].index
    rs = pd.DataFrame({c: np.full(len(idx), 85.0 + i) for i, c in enumerate(ohlcv)}, index=idx)
    return UniverseData(uni, ohlcv, {"KOSPI": flat_index(len(idx), start=str(idx[0].date()))},
                        {"KOSPI": confirmed_market()}, rs, idx[-1])


def test_run_scan_wires_radar_groups_account(monkeypatch):
    sector = pytest.importorskip("chart_screener.sector")
    calls = {}

    def fake_strength(ud, sm, *a, **k):
        calls["n"] = calls.get("n", 0) + 1
        return pd.DataFrame([{"group": f"G{i}", "kind": "테마", "members": 3, "score": 50 - i,
                              "rank_pct": 1 - i / 20, "leaders": [["000000", "종목0"]]} for i in range(20)])

    def fake_groups(code, sm, strength):
        return {"sector": "업종A", "sector_rank_pct": 0.9, "themes": [["G0", 1.0]], "best_rank_pct": 1.0}

    monkeypatch.setattr(sector, "group_strength", fake_strength)
    monkeypatch.setattr(sector, "stock_groups", fake_groups)
    smap = pd.DataFrame({"code": ["000000", "000001"], "sector": ["업종A", "업종A"], "themes": [["G0"], []]})
    cfg = Config()
    scan = scanner.run_scan(_synthetic_ud(), cfg, include_all=True, verbose=False, sector_map=smap)
    assert calls["n"] == 1                                  # 그룹 강도는 한 번만 계산
    assert len(scan.stocks) == 2 and all(s.groups and s.groups["sector"] == "업종A" for s in scan.stocks)
    assert all(any("주도 업종" in n for n in s.score.notes) for s in scan.stocks)
    assert len(scan.groups) == 15 and scan.groups[0]["rank_pct"] == 1.0
    assert [r["code"] for r in scan.radar] == ["000000"] and scan.radar[0]["themes"] == ["G0"]
    assert scan.account == scanner._account(cfg) and scan.breadth is None
    assert to_frame(scan)["시가총액(억)"].isna().all()       # NaN 시가총액 표 변환


def test_run_scan_without_sector_map():
    scan = scanner.run_scan(_synthetic_ud(), Config(), include_all=True, verbose=False,
                            sector_map=pd.DataFrame(columns=["code", "sector", "themes"]))
    assert scan.groups == [] and all(s.groups is None for s in scan.stocks)
    assert len(scan.radar) == 1 and scan.radar[0]["themes"] == []


def test_enrich_investor_is_display_only(monkeypatch):
    from chart_screener.data import investor
    df = make_ohlcv([(0, 50), (300, 140), (330, 128), (360, 139)], seed=4)
    got = []
    monkeypatch.setattr(investor, "attach_investor", lambda ctx, offline=False: got.append(ctx.code) or pd.DataFrame({"x": [1]}))
    s1 = scan_one(make_context(df, rs=93))
    s2 = scan_one(make_context(df, rs=93, code="T2"))
    before = (s1.score.composite, s2.score.composite)
    scan = ScanResult(asof=df.index[-1], generated_at=pd.Timestamp("2026-10-07 16:00"), market={},
                      stocks=[s1, s2], scanned=2, elapsed=0.0, patterns=[])
    assert scanner.enrich_investor(scan, top=5, offline=True, verbose=False) == 2
    assert got == ["TEST", "T2"] and (s1.score.composite, s2.score.composite) == before   # 점수는 그대로


# ---------------------------------------------------------------- CLI
def test_cli_rejects_unknown_pattern_and_bad_risk(capsys):
    from chart_screener.__main__ import main
    assert main(["scan", "--patterns", "cup_with_handle,nope"]) == 2
    assert "nope" in capsys.readouterr().err
    assert main(["scan", "--patterns", "vcp"]) == 2                 # 2026-10-14 제거된 옛 패턴
    assert "vcp" in capsys.readouterr().err
    assert main(["scan", "--risk", "50"]) == 2
    assert main(["scan", "--account", "0"]) == 2


def test_cli_zero_candidates_and_missing_asof(monkeypatch, tmp_path, capsys):
    from chart_screener import universe_data
    from chart_screener.__main__ import main
    ud = _synthetic_ud(1)
    monkeypatch.setattr(universe_data, "load_universe_data", lambda *a, **k: ud)
    empty = ScanResult(asof=ud.asof, generated_at=pd.Timestamp("2026-10-07 16:00"), market=ud.market, stocks=[],
                       scanned=1, elapsed=0.0, patterns=[])
    monkeypatch.setattr(scanner, "run_scan", lambda *a, **k: empty)
    args = ["scan", "--offline", "--no-html", "--investor-top", "0", "--out", str(tmp_path),
            "--journal", str(tmp_path / "j.csv")]
    assert main(args) == 0
    assert "후보 없음" in capsys.readouterr().out
    assert (tmp_path / "j.csv").exists()
    ud.asof = None
    assert main(args) == 1
