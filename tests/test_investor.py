"""투자자별 순매매 수집기 테스트 (오프라인; 실제 요청은 CHART_SCREENER_LIVE=1 일 때만)."""
import json
import os
from datetime import datetime

import pandas as pd
import pytest

from chart_screener.data import investor as inv
from chart_screener.data.ohlcv import KST

# 2026-10 네이버 m.stock trend API 실제 응답 일부 (005930)
SNIPPET = """[
 {"itemCode":"005930","bizdate":"20261006","foreignerPureBuyQuant":"-2,064,174","foreignerHoldRatio":"46.37%",
  "organPureBuyQuant":"-193,422","individualPureBuyQuant":"+1,273,618","closePrice":"273,000",
  "compareToPreviousClosePrice":"-3,000","compareToPreviousPrice":{"code":"5","text":"하락","name":"FALLING"},
  "accumulatedTradingVolume":"12,913,819"},
 {"itemCode":"005930","bizdate":"20261002","foreignerPureBuyQuant":"-350,942","foreignerHoldRatio":"46.41%",
  "organPureBuyQuant":"+614,278","individualPureBuyQuant":"-2,217,946","closePrice":"276,000",
  "compareToPreviousClosePrice":"0","compareToPreviousPrice":{"code":"3","text":"보합","name":"UNCHANGED"},
  "accumulatedTradingVolume":"11,501,250"},
 {"itemCode":"005930","bizdate":"20261001","foreignerPureBuyQuant":"-758,236","foreignerHoldRatio":"46.41%",
  "organPureBuyQuant":"+46,127","individualPureBuyQuant":"-1,292,880","closePrice":"274,500",
  "compareToPreviousClosePrice":"6,000","compareToPreviousPrice":{"code":"2","text":"상승","name":"RISING"},
  "accumulatedTradingVolume":"13,741,073"}
]"""


def test_parse_trend_snippet():
    df = inv.parse_trend(json.loads(SNIPPET))
    assert list(df.columns) == inv.COLUMNS
    assert df.index.is_monotonic_increasing and len(df) == 3
    last = df.iloc[-1]
    assert df.index[-1] == pd.Timestamp("2026-10-06")
    assert last["close"] == 273_000 and last["volume"] == 12_913_819
    assert last["inst_net"] == -193_422 and last["foreign_net"] == -2_064_174
    assert last["indiv_net"] == 1_273_618 and last["foreign_ratio"] == pytest.approx(46.37)
    assert df.loc["2026-10-02", "inst_net"] == 614_278


def test_parse_trend_bad_input():
    assert inv.parse_trend(None).empty
    assert inv.parse_trend([{"foo": 1}, "x", {"bizdate": "2026-13-45"}]).empty
    df = inv.parse_trend([{"bizdate": "20261006", "organPureBuyQuant": "N/A"}])
    assert len(df) == 1 and pd.isna(df["inst_net"].iloc[0])


class _Resp:
    def __init__(self, rows):
        self._rows = rows

    def json(self):
        return self._rows


def _fake_api(n_total: int = 130):
    dates = pd.bdate_range(end="2026-10-06", periods=n_total)[::-1]   # 최신순
    calls = []

    def get(url, **kw):
        calls.append(url)
        size = int(url.split("pageSize=")[1].split("&")[0])
        assert size <= inv.PAGE_MAX
        ds = dates
        if "bizdate=" in url:
            cur = pd.Timestamp(url.split("bizdate=")[1])
            ds = dates[dates < cur]
        return _Resp([{"bizdate": d.strftime("%Y%m%d"), "organPureBuyQuant": "+1,000",
                       "foreignerPureBuyQuant": "-500", "closePrice": "10,000",
                       "accumulatedTradingVolume": "100,000"} for d in ds[:size]])
    return get, calls


def test_fetch_investor_paging(monkeypatch):
    get, calls = _fake_api()
    monkeypatch.setattr(inv.http, "get", get)
    df = inv.fetch_investor("000000", days=100)
    assert len(df) == 100 and not df.index.duplicated().any() and df.index.is_monotonic_increasing
    assert len(calls) == 2 and "bizdate=" in calls[1]
    assert df.index[-1] == pd.Timestamp("2026-10-06")
    assert (df["inst_net"] == 1000).all() and (df["foreign_net"] == -500).all()


def test_fetch_investor_short_history(monkeypatch):
    get, calls = _fake_api(n_total=15)
    monkeypatch.setattr(inv.http, "get", get)
    df = inv.fetch_investor("000000", days=60)
    assert len(df) == 15 and len(calls) == 1


def test_cache_freshness(tmp_path):
    c = inv.InvestorCache(root=tmp_path)
    assert not c.is_fresh("A")
    c.save("A", inv.parse_trend(json.loads(SNIPPET)))
    p = tmp_path / "A.pkl"

    def set_mtime(dt):
        os.utime(p, (dt.timestamp(), dt.timestamp()))

    set_mtime(datetime(2026, 10, 7, 18, 30, tzinfo=KST))               # 수요일 확정 후 수집
    assert c.is_fresh("A", at=datetime(2026, 10, 8, 12, 0, tzinfo=KST))
    assert not c.is_fresh("A", at=datetime(2026, 10, 8, 18, 20, tzinfo=KST))   # 다음 확정 이후
    set_mtime(datetime(2026, 10, 9, 18, 30, tzinfo=KST))               # 금요일 수집 → 주말 내내 신선
    assert c.is_fresh("A", at=datetime(2026, 10, 11, 20, 0, tzinfo=KST))
    set_mtime(datetime(2026, 10, 8, 10, 0, tzinfo=KST))                # 장중 수집: 전일 확정분 포함
    assert c.is_fresh("A", at=datetime(2026, 10, 8, 15, 0, tzinfo=KST))
    assert not c.is_fresh("A", at=datetime(2026, 10, 8, 18, 20, tzinfo=KST))   # 당일 확정 이후 재요청
    set_mtime(datetime(2026, 10, 7, 17, 0, tzinfo=KST))                # 확정 전 수집 → 다음 날엔 낡음
    assert not c.is_fresh("A", at=datetime(2026, 10, 8, 9, 30, tzinfo=KST))


def test_get_investor_offline_and_incremental(tmp_path, monkeypatch):
    c = inv.InvestorCache(root=tmp_path)
    assert inv.get_investor("B", cache=c, offline=True) is None
    get, calls = _fake_api()
    monkeypatch.setattr(inv.http, "get", get)
    df = inv.get_investor("B", days=60, cache=c)
    assert len(df) == 60 and len(calls) == 1
    df2 = inv.get_investor("B", days=60, cache=c)          # 방금 받은 캐시 → 요청 없음
    assert len(df2) == 60 and len(calls) == 1
    df3 = inv.get_investor("B", days=60, cache=c, refresh=True)   # 강제 갱신 → 1회 더
    assert len(df3) == 60 and len(calls) == 2
    assert inv.get_investor("B", days=20, cache=c, offline=True).shape[0] == 20


def test_attach_investor_swallows_errors(monkeypatch, tmp_path):
    class Ctx:
        code, info = "C", {}

    def boom(url, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(inv.http, "get", boom)
    assert inv.attach_investor(Ctx(), cache=inv.InvestorCache(root=tmp_path)) is None
    assert "investor" not in Ctx.info


@pytest.mark.skipif(os.environ.get("CHART_SCREENER_LIVE") != "1", reason="실제 네이버 요청 (CHART_SCREENER_LIVE=1)")
def test_live_fetch(tmp_path):
    df = inv.get_investor("005930", days=20, cache=inv.InvestorCache(root=tmp_path))
    assert df is not None and len(df) == 20
    assert df[["close", "volume", "inst_net", "foreign_net"]].notna().all().all()
