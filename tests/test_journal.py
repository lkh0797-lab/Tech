import numpy as np
import pandas as pd
import pytest

from chart_screener import journal, scoring
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult
from chart_screener.scanner import ScanResult, StockScan


def _ss(code, stage, pattern="vcp", composite=50.0, close=10000.0, name=None, leader=False):
    res = {}
    if pattern:
        res[pattern] = PatternResult(name=pattern, label=pattern, detected=True, score=composite, stage=stage,
                                     pivot=10000.0, stop=9300.0)
    sb = scoring.compute(res, 80)
    sb.composite, sb.leader = composite, leader
    return StockScan(code=code, name=name or f"종목{code}", market="KOSPI", close=close, change_pct=0.0,
                     market_cap=1e12, rs=80.0, value_today=1e10, avg_value_20=1e10, max_value_5=1e10,
                     partial=False, results=res, score=sb, leader=leader)


def _scan(asof, stocks):
    return ScanResult(asof=pd.Timestamp(asof), generated_at=pd.Timestamp(asof) + pd.Timedelta(hours=16),
                      market={}, stocks=stocks, scanned=len(stocks), elapsed=0.0, patterns=[])


def test_badge_rules():
    assert journal.badge_for(None, NEAR_PIVOT, in_prev=False) == "신규"
    assert journal.badge_for(FORMING, NEAR_PIVOT, True) == "단계상승"
    assert journal.badge_for(FORMING, BREAKOUT, True) == "돌파"
    assert journal.badge_for(NEAR_PIVOT, BREAKOUT, True) == "돌파"
    assert journal.badge_for(BREAKOUT, FAILED, True) == "실패"
    assert journal.badge_for(NEAR_PIVOT, NEAR_PIVOT, True) is None
    assert journal.badge_for(BREAKOUT, NEAR_PIVOT, True) is None
    assert journal.badge_for(BREAKOUT, EXTENDED, True) is None


def test_first_scan_has_no_badges_and_is_written(tmp_path):
    path = tmp_path / "journal.csv"
    scan = _scan("2026-10-06", [_ss("005930", FORMING), _ss("000660", NEAR_PIVOT),
                                _ss("010950", None, pattern=None, leader=True)])
    summary = journal.annotate(scan, path)
    assert scan.prev_asof is None and all(s.badge is None for s in scan.stocks)
    assert summary["탈락"] == []
    journal.append(scan, path)
    j = journal.load_journal(path)
    assert list(j.columns) == journal.COLUMNS and len(j) == 3
    assert set(j["code"]) == {"005930", "000660", "010950"}           # 앞자리 0 보존
    assert j.set_index("code").loc["010950", "pattern"] == "leader"
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")               # UTF-8-SIG


def test_annotate_against_previous_asof(tmp_path):
    path = tmp_path / "journal.csv"
    prev = _scan("2026-10-05", [_ss("000001", FORMING), _ss("000002", NEAR_PIVOT), _ss("000003", NEAR_PIVOT),
                                _ss("000004", BREAKOUT), _ss("000005", NEAR_PIVOT, composite=70)])
    journal.append(prev, path)
    # 같은 날 다시 기록하면 통째로 교체 (중복 없음)
    journal.append(prev, path)
    assert len(journal.load_journal(path)) == 5

    now = _scan("2026-10-06", [_ss("000001", NEAR_PIVOT), _ss("000002", BREAKOUT), _ss("000003", NEAR_PIVOT),
                               _ss("000004", FAILED), _ss("000006", FORMING)])
    summary = journal.annotate(now, path)
    badges = {s.code: s.badge for s in now.stocks}
    assert badges == {"000001": "단계상승", "000002": "돌파", "000003": None, "000004": "실패", "000006": "신규"}
    assert {s.code: s.prev_stage for s in now.stocks}["000001"] == FORMING
    assert now.prev_asof == "2026-10-05"
    assert [d["code"] for d in now.dropped] == ["000005"] and now.dropped[0]["stage"] == NEAR_PIVOT
    assert [s.code for s in summary["돌파"]] == ["000002"] and len(summary["탈락"]) == 1

    journal.append(now, path)
    j = journal.load_journal(path)
    assert sorted(j["asof"].unique()) == ["2026-10-05", "2026-10-06"]
    assert not j.duplicated(["asof", "code"]).any()
    # 재실행(같은 기준일): 비교 대상은 여전히 그 이전 기준일
    again = _scan("2026-10-06", [_ss("000001", NEAR_PIVOT)])
    journal.annotate(again, path)
    assert again.prev_asof == "2026-10-05" and again.stocks[0].badge == "단계상승"
    journal.append(again, path)
    assert (journal.load_journal(path)["asof"] == "2026-10-06").sum() == 1


class _FakeCache:
    def __init__(self, frames):
        self.frames = frames

    def load(self, code):
        return self.frames.get(code)


def _path_df(closes, start="2026-01-02"):
    idx = pd.bdate_range(start, periods=len(closes))
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6}, index=idx)


def test_forward_outcome_and_track(tmp_path):
    up = _path_df(np.linspace(100, 160, 90))         # 꾸준히 상승 → +20% 먼저
    down = _path_df(np.linspace(100, 70, 90))        # 하락 → 손절 먼저
    asof = f"{up.index[9]:%Y-%m-%d}"
    o = journal.forward_outcome(up, asof, stop=93)
    entry = float(up["open"].iloc[10])
    assert o["entry"] == pytest.approx(entry)
    assert o["ret_5"] == pytest.approx(up["close"].iloc[14] / entry - 1)
    assert o["ret_60"] == pytest.approx(up["close"].iloc[69] / entry - 1)
    assert o["outcome"] == "target" and o["target_hit"] and not o["stop_hit"]
    d = journal.forward_outcome(down, asof, stop=93)
    assert d["outcome"] == "stop" and d["stop_hit"]
    late = journal.forward_outcome(up, f"{up.index[-1]:%Y-%m-%d}", stop=93)
    assert np.isnan(late["entry"]) and late["outcome"] is None       # 아직 진입 전

    path = tmp_path / "journal.csv"
    rows = []
    for k, (code, stage, comp) in enumerate([("000001", BREAKOUT, 80), ("000002", NEAR_PIVOT, 60),
                                             ("000003", FORMING, 40), ("000004", BREAKOUT, 70),
                                             ("000005", NEAR_PIVOT, 50)]):
        rows.append(_ss(code, stage, composite=comp, close=100.0))
    scan = _scan(asof, rows)
    for s in scan.stocks:
        s.results["vcp"].stop = 93.0
    journal.append(scan, path)
    frames = {"000001": up, "000002": down, "000003": up, "000004": down, "000005": up}
    j = journal.track(path, cache=_FakeCache(frames))
    assert j["entry"].notna().all() and j["first"].all()
    assert set(j.loc[j["code"].isin(["000002", "000004"]), "outcome"]) == {"stop"}
    saved = journal.load_journal(path)
    assert {"ret_5", "ret_20", "ret_60", "outcome", "stop_hit", "target_hit"} <= set(saved.columns)
    summ = journal.summarize(j)
    assert set(summ) == {"전체", "대표 패턴", "단계", "종합점수 5분위"}
    assert summ["전체"].iloc[0]["진입"] == 5 and summ["전체"].iloc[0]["손절먼저%"] == 40.0
    assert len(summ["종합점수 5분위"]) == 5
    # 추적 열이 있는 일지에 새 스캔을 이어 붙여도 깨지지 않음
    journal.append(_scan("2026-10-07", [_ss("000009", NEAR_PIVOT)]), path)
    assert len(journal.load_journal(path)) == 6


def test_track_missing_cache_rows(tmp_path):
    path = tmp_path / "journal.csv"
    journal.append(_scan("2026-03-02", [_ss("000001", NEAR_PIVOT)]), path)
    j = journal.track(path, cache=_FakeCache({}), save=False)
    assert j["entry"].isna().all()
    summ = journal.summarize(j)
    assert summ["전체"].iloc[0]["진입"] == 0
