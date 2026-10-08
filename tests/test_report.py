"""HTML 리포트: 새 필드(포지션·배지·업종/테마·레이더·시장 폭·탈락) 렌더링과 구버전 ScanResult 호환."""
import json
import re
import shutil
import subprocess
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from chart_screener.report.html import _clean, build_payload, render
from chart_screener.scanner import ScanResult, scan_one
from synthetic import confirmed_market, make_context, make_ohlcv

ASOF = pd.Timestamp("2026-10-07")


def _stock(code="TEST", name="테스트", seed=4, rs=93):
    df = make_ohlcv([(0, 50), (300, 140), (330, 128), (360, 139)], seed=seed)
    return scan_one(make_context(df, rs=rs, code=code, name=name))


def _breadth(nh_nl=12, pct50=54.1):
    dates = [f"2026-10-0{i}" for i in range(1, 8)]
    return {"date": "2026-10-07", "universe": 340, "new_highs": 20, "new_lows": 8, "nh_nl": nh_nl,
            "nh_nl_10d": float("nan"), "pct_above_50": pct50, "pct_above_200": 41.0, "big_value_up": 5,
            "series": {"dates": dates, "nh_nl": [1, -3, 4, np.nan, 8, 10, nh_nl], "pct_above_50": [50.0] * 7}}


def new_scan() -> ScanResult:
    a, b = _stock("0015N0", "알파벳코드"), _stock("123456", "둘째", seed=7)
    a.badge, a.prev_stage, a.leader = "단계상승", "forming", True
    a.groups = {"sector": "반도체", "sector_rank_pct": 0.62, "themes": [["HBM", 0.97], ("로봇", np.float64(0.4))],
                "themes_all": ["HBM", "로봇", "소규모테마"], "best_rank_pct": 0.97}
    a.position = {"entry": 10690.0, "stop": 9900.0, "risk_pct": 0.0739, "shares": 1265, "amount": 13522850.0,
                  "max_loss": 999350.0, "plan": "피벗 10,690 돌파 매수", "cap": "위험"}
    b.position = {"entry": 5000.0, "stop": 4300.0, "risk_pct": 0.14, "shares": 0, "amount": 0.0, "max_loss": 0.0,
                  "plan": "눌림 대기 (손절폭 14.0% > 10%)", "cap": None}
    scan = ScanResult(asof=ASOF, generated_at=pd.Timestamp("2026-10-07 16:00"),
                      market={"KOSPI": confirmed_market()}, stocks=[a, b], scanned=2, elapsed=0.1,
                      patterns=list(a.results))
    scan.radar = [
        {"code": "0015N0", "name": "알파벳코드", "market": "KOSDAQ", "date": "2026-10-06", "days_ago": 1,
         "change": 0.112, "value": 51_200_000_000.0, "close": 11_000.0, "support": 10_400.0, "holding": True,
         "themes": ["HBM"]},
        {"code": "999999", "name": "후보밖", "market": "KOSPI", "date": pd.Timestamp("2026-10-02"), "days_ago": 3,
         "change": float("nan"), "value": np.float64(3.1e10), "close": 9_000.0, "support": 9_500.0,
         "holding": np.bool_(False), "themes": np.array(["로봇", "원전"])},
    ]
    scan.groups = [
        {"group": "HBM", "kind": "테마", "members": 12, "median_rs": 88.0, "tt_pass_pct": 0.42, "new_highs_20d": 5,
         "big_value_today": 2, "score": 71.3, "rank_pct": 1.0, "leaders": [["0015N0", "알파벳코드"], ["777777", "밖"]],
         "url": "https://example.invalid", "chg_1d": 0.012},
        {"group": "반도체", "kind": "업종", "members": 80, "median_rs": float("nan"), "tt_pass_pct": 0.18,
         "new_highs_20d": 9, "big_value_today": 4, "score": 60.0, "rank_pct": 0.62, "leaders": []},
    ]
    scan.breadth = {"ALL": _breadth(), "KOSPI": _breadth(-4, 38.0), "KOSDAQ": _breadth(15, 61.0)}
    scan.prev_asof = "2026-10-06"
    scan.account = {"size": 50_000_000.0, "risk_per_trade": 0.01, "max_position_pct": 0.2,
                    "max_entry_risk": 0.1, "max_liquidity_pct": 0.02}
    scan.dropped = [{"code": "005930", "name": "삼성전자", "market": "KOSPI", "pattern": "vcp", "stage": "near_pivot",
                     "composite": 71.2, "close": 70_000.0, "asof": "2026-10-06"}, "000660"]
    return scan


def old_scan():
    """새 필드가 생기기 전 ScanResult/StockScan 모양 (속성 자체가 없음)."""
    s = _stock()
    for f in ("position", "badge", "prev_stage", "groups", "leader"):
        s.__dict__.pop(f, None)
    stock = SimpleNamespace(**{k: v for k, v in s.__dict__.items()})
    for m in ("lead", "best", "entry_risk"):
        setattr(stock, m, getattr(s, m))
    stock.lead_name = s.lead_name
    return SimpleNamespace(asof=ASOF, generated_at=pd.Timestamp("2026-10-07 16:00"),
                           market={"KOSPI": confirmed_market()}, stocks=[stock], scanned=1)


def _data(html: str) -> dict:
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert m, "데이터 블록이 템플릿에 주입되어야 함"
    assert "NaN" not in m.group(1) and "Infinity" not in m.group(1)
    return json.loads(m.group(1))


def test_new_fields_in_payload_and_html():
    html = render(build_payload(new_scan()))
    d = _data(html)
    assert set(d["breadth"]) == {"ALL", "KOSPI", "KOSDAQ"}
    k = d["breadth"]["KOSPI"]
    assert k["nh_nl"] == -4 and k["pct_above_50"] == 38.0 and k["nh_nl_10d"] is None and k["universe"] == 340
    assert k["series"]["nh_nl"][3] is None and len(k["series"]["dates"]) == 7
    assert d["prev_asof"] == "2026-10-06"
    assert d["account"]["size"] == 50_000_000 and d["account"]["max_entry_risk"] == 0.1

    r0, r1 = d["radar"]
    assert r0["in_list"] is True and r1["in_list"] is False
    assert r1["date"] == "2026-10-02" and r1["change"] is None and r1["holding"] is False
    assert r1["themes"] == ["로봇", "원전"] and r1["value"] == 31_000_000_000

    g0, g1 = d["groups"]
    assert g0["leaders"] == [["0015N0", "알파벳코드", True], ["777777", "밖", False]]
    assert g0["tt_pass_pct"] == 0.42 and g1["median_rs"] is None and "url" not in g0

    assert d["dropped"][0]["score"] == 71.2 and d["dropped"][0]["stage"] == "near_pivot"
    assert d["dropped"][1] == {"code": "000660", "name": "000660", "market": None, "stage": None, "pattern": None,
                               "score": None, "close": None, "reason": None}

    a, b = d["stocks"]
    assert a["code"] == "0015N0" and a["badge"] == "단계상승" and a["prev_stage"] == "forming" and a["leader"] is True
    assert a["groups"]["best"] == ["HBM", "테마", 0.97]
    assert a["groups"]["themes"] == [["HBM", 0.97], ["로봇", 0.4]] and a["groups"]["themes_other"] == ["소규모테마"]
    assert a["pos"]["shares"] == 1265 and a["pos"]["plan"].startswith("피벗") and a["pos"]["cap"] == "위험"
    assert b["pos"]["shares"] == 0 and b["pos"]["cap"] is None and "대기" in b["pos"]["plan"]

    for needle in ('id="v-radar"', 'id="v-groups"', 'id="dropBox"', "관심 목록 (매수 신호 아님)", "주도 업종·테마",
                   "거래대금 300억 레이더", 'id="acct"', 'id="riskp"', 'id="dPlan"', 'id="dPos"', "주도주"):
        assert needle in html, needle


def test_old_scan_renders_without_new_fields():
    d = _data(render(build_payload(old_scan())))
    assert d["radar"] is None and d["groups"] is None and d["dropped"] is None
    assert d["breadth"] is None and d["prev_asof"] is None and d["account"] is None
    s = d["stocks"][0]
    assert s["badge"] is None and s["pos"] is None and s["groups"] is None and s["leader"] is False
    assert len(s["ohlcv"]["t"]) == len(s["ohlcv"]["c"])


def test_present_but_empty_lists_are_not_none():
    scan = new_scan()
    scan.radar, scan.groups, scan.dropped = [], pd.DataFrame(columns=["group", "kind"]), []
    d = build_payload(scan)
    assert d["radar"] == [] and d["groups"] == [] and d["dropped"] == []


def test_groups_dataframe_and_breadth_fallback_from_market_state():
    scan = new_scan()
    scan.groups = pd.DataFrame(scan.groups)
    scan.breadth = None
    ms = confirmed_market()
    ms.breadth = _breadth(7, 50.0)
    scan.market = {"KOSPI": ms}
    d = build_payload(scan)
    assert d["groups"][0]["group"] == "HBM" and d["groups"][0]["leaders"][0][2] is True
    assert list(d["breadth"]) == ["KOSPI"] and d["breadth"]["KOSPI"]["nh_nl"] == 7


def test_script_injection_and_clean():
    scan = new_scan()
    scan.stocks[0].name = "</script><b>x"
    html = render(build_payload(scan))
    assert "</script><b>x" not in html
    assert _data(html)["stocks"][0]["name"] == "</script><b>x"
    assert _clean({"a": (1, np.float64("nan")), "b": np.array([1.5, np.inf]), "c": pd.NaT, "d": {2}}) == \
        {"a": [1, None], "b": [1.5, None], "c": None, "d": [2]}


def test_fragment_has_no_document_skeleton():
    frag = render(build_payload(new_scan()), standalone=False)
    assert not frag.lstrip().lower().startswith("<!doctype")
    assert frag.lstrip().startswith("<title>")


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
@pytest.mark.parametrize("make", [new_scan, old_scan])
def test_inline_script_parses_with_node(tmp_path, make):
    html = render(build_payload(make()))
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    assert len(scripts) == 1
    js = tmp_path / "report.js"
    js.write_text(scripts[0], encoding="utf-8")
    out = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
