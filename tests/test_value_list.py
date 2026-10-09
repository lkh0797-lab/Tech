"""기업추적 저평가 목록 ↔ 스캔 · 리포트 (chart_screener.value_list · patterns/undervalued · '저평가 종목' 탭).

목록 파일 읽기(환경변수 · 코드 6자리) → 정보 칩(후보를 만들지 않음) → 목록 종목은 후보가 아니어도 결과 유지 →
분석 대상 밖은 사유 · 미니차트만 → 리포트 탭(범위 토글 · 셋업 카드 · 짧은 차트) · 증권사 자료 함께 받기. 네트워크 없음.
"""
import json
import re
import shutil
import subprocess

import pandas as pd
import pytest

from chart_screener import scanner, scoring, value_list
from chart_screener.config import Config
from chart_screener.patterns import REGISTRY
from chart_screener.patterns.base import FORMING, PatternResult
from chart_screener.report import html as rhtml
from chart_screener.report.html import build_payload, render
from synthetic import make_context, make_ohlcv
from test_kis_scan import EMPTY_SECTORS, FakeKIS, _df, make_hub, make_ud

A, B, C, D, E, F, G = "000001", "000002", "000003", "000004", "000005", "000006", "000007"


def _row(code, tier="저평가", score=70.0, **kw):
    r = {"code": code, "name": f"이름{str(code)[-1:]}", "tier": tier, "score": score, "per": 8.3, "per_then": 16.29,
         "per_pct": 11.4, "dd": -49.26, "roe": 16.8, "debt_eq": 30.3, "ni_yoy": 22.9, "px_yoy": -37.6,
         "industry": "핸드셋", "tier_why": [], "risk": None}
    r.update(kw)
    return r


def _vfile(tmp_path, rows, **meta):
    p = tmp_path / "tech_export.json"
    p.write_text(json.dumps({"v": 1, "at": 1791496816.8, "date": "20261009", "source": "기업추적 저평가",
                             "rows": rows, **meta}, ensure_ascii=False), encoding="utf-8")
    return p


def _data(html: str) -> dict:
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert m and "NaN" not in m.group(1)
    return json.loads(m.group(1))


# ---------------------------------------------------------------- 파일 읽기
def test_load_value_env_and_code_normalisation(tmp_path, monkeypatch):
    monkeypatch.delenv(value_list.ENV, raising=False)
    assert value_list.load_value() is None                                    # 환경변수 없음 → 탭 · 칩 없음
    assert value_list.load_value(tmp_path / "없음.json") is None
    p = _vfile(tmp_path, [_row(5930), _row("660", tier="관찰", tier_why=["빨간불: 잔고"]), _row("0015n0", tier="?"),
                          _row("005930", score=1.0), _row(None), "x",
                          _row("12.0", per=float("nan"), roe="abc", risk="작전주 꼴")])
    monkeypatch.setenv(value_list.ENV, str(p))
    vl = value_list.load_value()
    assert vl.codes() == ["005930", "000660", "0015N0", "000012"]           # 중복은 앞 것만, 코드 없는 행 버림
    assert vl.get(5930)["score"] == 70.0 and vl.get("000660")["tier_why"] == ["빨간불: 잔고"]
    assert vl.get("0015N0")["tier"] == "관찰"                                 # 모르는 등급 → 관찰
    r12 = vl.get("12")
    assert r12["per"] is None and r12["roe"] is None and r12["risk"] == "작전주 꼴"
    assert vl.counts() == {"저평가": 2, "관찰": 2} and vl.date == "20261009" and vl.path == str(p)
    assert "4종목" in vl.summary_line() and "2026-10-09" in vl.summary_line()
    assert value_list.parse_value({"v": 2, "rows": []}) is None and value_list.parse_value({"v": 1}) is None
    bad = tmp_path / "bad.json"
    bad.write_text("{깨짐", encoding="utf-8")
    assert value_list.load_value(bad) is None


# ---------------------------------------------------------------- 정보 칩
def _ctx(info):
    df = make_ohlcv([(0, 100), (200, 120)], seed=3)
    return make_context(df, info=info)


def test_undervalued_pattern_reads_ctx_info_and_never_creates_candidates():
    det = REGISTRY["undervalued"][1]
    assert REGISTRY["undervalued"][0] == "저평가 종목"
    r = det(_ctx({"market_cap": 1e12}))
    assert not r.detected and "CHART_SCREENER_VALUE_JSON" in r.warnings[0]
    r = det(_ctx({"market_cap": 1e12, "undervalued": None}))
    assert not r.detected and r.warnings == ["기업추적 저평가 목록에 없음"]
    row = value_list.norm_row(_row(A, tier="관찰", tier_why=["빨간불: 선수금"], risk="자금조달 잦음"))
    r = det(_ctx({"market_cap": 1e12, "value": 5e9, "undervalued": row}))
    assert r.detected and r.stage is None and r.pivot is None and r.stop is None and r.score == 70.0
    assert r.metrics["tier"] == "관찰" and r.metrics["per_then"] == 16.29 and r.metrics["observe_only"] is True
    assert any("PER 1년 전 16.3 → 지금 8.3" in x for x in r.reasons)
    assert any("52주 고점 대비 -49.3%" in x for x in r.reasons) and any("ROE 16.8%" in x and "부채비율 30%" in x for x in r.reasons)
    assert "관찰 사유: 빨간불: 선수금" in r.warnings and "공시 위험: 자금조달 잦음" in r.warnings
    # 혼자서는 후보가 되지 않고 종합 점수에도 안 들어간다
    assert "undervalued" in scoring.INFO_PATTERNS and "undervalued" not in scoring.BASE_PATTERNS
    assert scoring.is_candidate({"undervalued": r}, 99) is False
    sb = scoring.compute({"undervalued": r}, 95)
    assert sb.best_pattern is None and sb.pattern_part == 0 and sb.detected_bases == []


def test_chip_order_puts_undervalued_after_vocal():
    chips = [n for n in rhtml.CHIP_ORDER if n in REGISTRY]
    assert chips == ["canslim", "pocket_pivot", "vocal", "undervalued", "absorb", "stage2"]
    assert rhtml.DETECTED_ORDER[-3:] == ["vocal", "absorb", "stage2"] and "undervalued" in rhtml.DETECTED_ORDER


# ---------------------------------------------------------------- 스캔
def _universe(tmp_path, monkeypatch, rows=None):
    """A 후보 · B 저평가 비후보 · C 관찰 비후보 · D 일봉 없음(기간 부족) · E 종목 목록 밖 · F 동전주(유동성) · G 목록 밖 비후보."""
    frames = {A: _df(seed=1), B: _df(seed=2), C: _df(seed=3), G: _df(seed=7),
              F: make_ohlcv([(0, 500), (299, 520)], seed=6)}
    ud = make_ud(frames)
    extra = pd.DataFrame([{"code": D, "name": "신규상장", "market": "KOSDAQ", "market_cap": 9e10, "traded_at": pd.NaT,
                           "market_open": False, "value": 0.0}]).set_index("code", drop=False)
    ud.universe = pd.concat([ud.universe, extra])
    vl = value_list.load_value(_vfile(tmp_path, rows or [
        _row(A, score=75.0), _row(B, score=74.5), _row(C, tier="관찰", score=80.9, tier_why=["빨간불"]),
        _row(D, score=60.0), _row(E, tier="관찰", score=50.0), _row(F, score=55.0)]))
    monkeypatch.setattr(scoring, "is_candidate", lambda results, rs=None: A in _seen)
    return ud, vl


_seen = set()      # 지금 분석 중인 종목 코드 (is_candidate 대역이 A 만 후보로)


def _scan(ud, vl, monkeypatch, kis=None):
    """A 만 후보로 (is_candidate 대역이 ctx 코드를 알 수 있게 scan_one 을 감싼다)."""
    orig = scanner.scan_one

    def one(ctx, names=None, keep_ctx=True):
        _seen.clear()
        _seen.add(ctx.code)
        return orig(ctx, names, keep_ctx)

    monkeypatch.setattr(scanner, "scan_one", one)
    return scanner.run_scan(ud, Config(), verbose=False, sector_map=EMPTY_SECTORS, kis=kis, value=vl)


def test_scan_keeps_value_stocks_and_skips_with_reasons(tmp_path, monkeypatch):
    ud, vl = _universe(tmp_path, monkeypatch)
    scan = _scan(ud, vl, monkeypatch)
    assert [s.code for s in scan.stocks] == [A]                               # 저평가 칩은 후보를 만들지 않는다
    assert set(scan.value_scans) == {A, B, C, F} and scan.value is vl
    assert all(scan.value_scans[c].ctx is not None for c in (A, B, C, F))    # 비후보도 ctx 유지 (탭 · 짧은 차트)
    # 동전주 F: 유동성 문턱 밑이어도 목록 종목이라 패턴은 잰다 — 후보 · 레이더에는 넣지 않는다
    assert scan.value_scans[F].thin.startswith("주가") and F not in {s.code for s in scan.stocks}
    assert F not in {r["code"] for r in scan.radar} and scan.scanned == len(ud.ohlcv) - 1
    assert scan.value_scans[B].results["undervalued"].detected
    assert scan.value_scans[C].results["undervalued"].metrics["tier"] == "관찰"
    assert scan.stocks[0].results["undervalued"].detected
    sk = scan.value_skipped
    assert set(sk) == {D, E}
    assert sk[D]["why"].startswith("기간 부족") and sk[D]["spark"] == [] and sk[D]["market"] == "KOSDAQ"
    assert sk[E]["why"].startswith("종목 목록 밖")


def test_scan_without_value_file_is_unchanged(tmp_path, monkeypatch):
    ud, _ = _universe(tmp_path, monkeypatch)
    scan = _scan(ud, None, monkeypatch)
    assert scan.value is None and scan.value_scans == {} and scan.value_skipped == {}
    r = scan.stocks[0].results["undervalued"]
    assert not r.detected and "CHART_SCREENER_VALUE_JSON" in r.warnings[0]
    d = build_payload(scan)
    assert d["value"] is None and d["value_stocks"] == []
    assert "undervalued" not in d["stocks"][0]["detected"]
    html = render(d)
    assert 'id="v-value"' in html and 'id="tab-value"' in html               # 숨김 탭 (자료 없으면 표시 안 함)


# ---------------------------------------------------------------- 리포트
def test_report_value_tab_rows_cards_and_short_charts(tmp_path, monkeypatch):
    ud, vl = _universe(tmp_path, monkeypatch)
    scan = _scan(ud, vl, monkeypatch)
    scan.value_scans[B].results["absorb"] = PatternResult(name="absorb", label="바닥 투매 흡수", detected=True, stage=FORMING)
    html = render(build_payload(scan))
    d = _data(html)
    v = d["value"]
    assert v["date"] == "2026-10-09" and v["n"] == 6 and v["tiers"] == {"저평가": 4, "관찰": 2}
    rows = {r["code"]: r for r in v["rows"]}
    assert [r["code"] for r in v["rows"]] == [A, B, C, D, E, F]              # 파일 순서 (기본 정렬은 화면에서 점수순)
    assert rows[A]["in_list"] and rows[A]["chart"]
    assert not rows[B]["in_list"] and rows[B]["chart"] and ["absorb", "forming"] in rows[B]["pats"]
    assert not rows[C]["chart"] and rows[C]["tier"] == "관찰" and rows[C]["why"] == ["빨간불"]
    assert all(n != "undervalued" for n, _ in rows[B]["pats"])               # 칩 자신은 '걸린 패턴'에서 뺀다
    for c in (D, E):
        assert rows[c]["skip"] and rows[c]["pats"] == [] and not rows[c]["chart"]
        assert rows[c]["nochart"] == "패턴 미판정"
    assert rows[F]["skip"] is None and rows[F]["thin"].startswith("주가") and rows[F]["chart"]   # 문턱 밑도 판정
    assert rows[C]["nochart"] == "관찰 등급" and "nochart" not in rows[B]
    assert rows[A]["skip"] is None and len(rows[A]["spark"]) == rhtml.VALUE_SPARK_BARS
    assert rows[B]["per_then"] == 16.3 and rows[B]["dd"] == -49.3 and rows[B]["debt_eq"] == 30
    # 비후보 저평가 등급(B)만 짧은 차트 — 관찰 등급(C)은 미니차트만
    vs = {s["code"]: s for s in d["value_stocks"]}
    assert set(vs) == {B, F} and vs[B]["vonly"] is True
    assert len(vs[B]["ohlcv"]["t"]) <= rhtml.VALUE_CHART_BARS and len(vs[B]["ma"]["sma50"]) == len(vs[B]["ohlcv"]["t"])
    assert set(vs[B]["patterns"]) <= set(vs[B]["detected"]) | set(rhtml.VALUE_KEEP)
    assert "undervalued" in vs[B]["patterns"] and "absorb" in vs[B]["patterns"]
    assert "undervalued" in d["stocks"][0]["detected"] and "undervalued" in d["chip_patterns"]
    assert d["chip_patterns"].index("undervalued") == d["chip_patterns"].index("vocal") + 1
    assert d["info_patterns"] == ["undervalued"]
    for needle in ('id="v-value"', 'id="tab-value"', 'data-scope="value"', 'data-scope="all"', "저평가 등급", "관찰 포함",
                   'id="vCards"', "priceSpark", "기업추적 저평가 화면의 등급(가치는 지켰는데 주가가 빠진 회사)",
                   "바닥 투매 흡수 6개월 +3.4%p", "패턴 미판정(유동성 · 기간 부족)", "undervalued: {", "저평가 관찰"):
        assert needle in html, needle


def test_value_rows_render_from_list_without_scan_results(tmp_path):
    """예전 ScanResult(value_scans · value_skipped 없음)에 목록만 붙어도 행은 '분석 안 함'으로 그린다."""
    from types import SimpleNamespace
    from test_report import new_scan
    scan = new_scan()
    scan.value = value_list.load_value(_vfile(tmp_path, [_row("0015N0"), _row("999999", tier="관찰")]))
    for f in ("value_scans", "value_skipped"):
        scan.__dict__.pop(f, None)
    d = build_payload(SimpleNamespace(**scan.__dict__))
    rows = d["value"]["rows"]
    assert [r["skip"] for r in rows] == ["분석 안 함", "분석 안 함"] and rows[0]["in_list"] is True
    assert rows[0]["chart"] is True and d["value_stocks"] == []


def test_kis_enrich_includes_value_stocks(tmp_path, monkeypatch):
    ud, vl = _universe(tmp_path, monkeypatch)
    end = ud.ohlcv[A].index[-1]
    hub = make_hub(tmp_path, FakeKIS(flows_end=end))
    ud.ohlcv = hub.load_universe(ud.universe, ud.ohlcv)
    scan = _scan(ud, vl, monkeypatch, kis=hub)
    got = hub.enrich(scan)
    assert got == {"flows": 4, "opinion": 4, "estimate": 4, "value": 3}       # 후보 A + 목록 비후보 B · C · F(문턱 밑)
    b = scan.value_scans[B]
    assert b.kis and b.kis["tp_avg"] > 0 and scanner.investor_summary(b)["src"] == "KIS"
    assert [s.code for s in scan.stocks] == [A]                               # 후보 목록은 그대로
    rows = {r["code"]: r for r in build_payload(scan)["value"]["rows"]}
    assert rows[B]["inv"]["src"] == "KIS" and rows[B]["kis"]["tp_gap"] is not None
    assert rows[C]["kst"] == [] and rows[F]["kst"] == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_value_report_script_parses_with_node(tmp_path, monkeypatch):
    ud, vl = _universe(tmp_path, monkeypatch)
    html = render(build_payload(_scan(ud, vl, monkeypatch)))
    js = tmp_path / "report.js"
    js.write_text(re.findall(r"<script>(.*?)</script>", html, re.S)[0], encoding="utf-8")
    out = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr


def test_frame_lists_undervalued_as_observe(tmp_path, monkeypatch):
    ud, vl = _universe(tmp_path, monkeypatch)
    frame = scanner.to_frame(_scan(ud, vl, monkeypatch))
    assert "저평가 종목" in frame.set_index("종목코드").loc[A, "관찰패턴"]


def test_value_chart_cap_prefers_rows_with_tech_patterns(tmp_path, monkeypatch):
    ud, vl = _universe(tmp_path, monkeypatch, rows=[
        _row(A, score=75.0), _row(B, score=50.0), _row(C, tier="관찰", score=80.9, tier_why=["빨간불"]),
        _row(D, score=60.0), _row(E, tier="관찰", score=50.0), _row(F, score=99.0)])
    scan = _scan(ud, vl, monkeypatch)
    scan.value_scans[B].results["absorb"] = PatternResult(name="absorb", label="바닥 투매 흡수", detected=True, stage=FORMING)
    monkeypatch.setattr(rhtml, "MAX_VALUE_CHARTS", 1)
    d = build_payload(scan)
    rows = {r["code"]: r for r in d["value"]["rows"]}
    # F 는 저평가 점수가 더 높지만 정보 칩만 걸렸다 — 상한 1개면 Tech 패턴(바닥 투매 흡수)이 걸린 B 가 차트를 갖는다
    assert [s["code"] for s in d["value_stocks"]] == [B] and rows[B]["chart"]
    assert not rows[F]["chart"] and rows[F]["nochart"] == "차트 상한 1개 밖"
