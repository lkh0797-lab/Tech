import numpy as np
import pandas as pd
import pytest

from chart_screener import journal, scoring
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult
from chart_screener.scanner import ScanResult, StockScan


CWH = "cup_with_handle"


def _ss(code, stage, pattern=CWH, composite=50.0, close=10000.0, name=None, rule="cwh_reference_v1.0.0"):
    res = {}
    if pattern:
        res[pattern] = PatternResult(name=pattern, label=pattern, detected=True, score=composite, stage=stage,
                                     pivot=10000.0, stop=9300.0, metrics={"rule_version": rule} if rule else {})
    sb = scoring.compute(res, 80)
    sb.composite = composite
    return StockScan(code=code, name=name or f"종목{code}", market="KOSPI", close=close, change_pct=0.0,
                     market_cap=1e12, rs=80.0, value_today=1e10, avg_value_20=1e10, max_value_5=1e10,
                     partial=False, results=res, score=sb)


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
                                _ss("010950", NEAR_PIVOT, pattern="vocal", rule=None)])
    summary = journal.annotate(scan, path)
    assert scan.prev_asof is None and all(s.badge is None for s in scan.stocks)
    assert summary["탈락"] == []
    journal.append(scan, path)
    j = journal.load_journal(path)
    assert list(j.columns) == journal.COLUMNS and len(j) == 3
    assert set(j["code"]) == {"005930", "000660", "010950"}           # 앞자리 0 보존
    by = j.set_index("code")
    assert by.loc["010950", "pattern"] == "vocal" and by.loc["010950", "rule"] == "vocal"   # 보컬만 걸린 후보
    assert by.loc["005930", "pattern"] == CWH and by.loc["005930", "rule"] == "cwh_reference_v1.0.0"
    assert not j["leader"].astype(bool).any()                         # 주도주 판정은 제거 — 옛 칸 호환용
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
        s.results[CWH].stop = 93.0
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


def test_no_stop_rows_are_not_counted_as_zero_stop_rate(tmp_path):
    """손절 규칙 없는 식(컵 앤 핸들) 행: 계속 빠져도 '손절먼저 0%'가 아니라 해당 없음."""
    down = _path_df(np.concatenate([np.full(10, 100.0), np.linspace(100, 60, 80)]))   # −10% 넘게 빠짐
    up = _path_df(np.linspace(100, 160, 90))
    asof = f"{down.index[9]:%Y-%m-%d}"
    o = journal.forward_outcome(down, asof, stop=None)
    assert o["outcome"] == journal.NO_STOP and o["stop_hit"] is None and o["target_hit"] is False
    assert journal.forward_outcome(down, asof, stop=float("nan"))["outcome"] == journal.NO_STOP
    path = tmp_path / "journal.csv"
    scan = _scan(asof, [_ss("000001", BREAKOUT), _ss("000002", NEAR_PIVOT)])
    for s in scan.stocks:
        s.results[CWH].stop = None
    journal.append(scan, path)
    frames = {"000001": down, "000002": up, "000003": _path_df(np.linspace(100, 70, 90))}
    j = journal.track(path, cache=_FakeCache(frames))
    assert set(j["outcome"]) == {journal.NO_STOP}
    summ = journal.summarize(j)
    row = summ["전체"].iloc[0]
    assert row["진입"] == 2 and row["손절가n"] == 0
    assert row["손절먼저%"] is None and row["+20%먼저%"] is None and row["손절비고"].startswith("손절 규칙 없음")
    assert pd.isna(summ["대표 패턴"].iloc[0]["손절먼저%"])
    # 손절가 있는 행과 섞이면 그 행들로만 내고 몇 건인지 적는다
    nxt = _scan(f"{down.index[10]:%Y-%m-%d}", [_ss("000003", BREAKOUT)])
    nxt.stocks[0].results[CWH].stop = 93.0
    journal.append(nxt, path)
    row = journal.summarize(journal.track(path, cache=_FakeCache(frames)))["전체"].iloc[0]
    assert row["진입"] == 3 and row["손절가n"] == 1 and row["손절먼저%"] == 100.0
    assert "손절가 있는 1건만" in row["손절비고"]


def test_track_missing_cache_rows(tmp_path):
    path = tmp_path / "journal.csv"
    journal.append(_scan("2026-03-02", [_ss("000001", NEAR_PIVOT)]), path)
    j = journal.track(path, cache=_FakeCache({}), save=False)
    assert j["entry"].isna().all()
    summ = journal.summarize(j)
    assert summ["전체"].iloc[0]["진입"] == 0


# ---------------------------------------------------------------- 옛 패턴 기록 (2026-10-14 패턴 초기화)
LEGACY_HEADER = "asof,code,name,market,pattern,stage,pivot,stop,composite,rs,close,value,leader\n"


def _legacy(path, rows):
    path.write_text(LEGACY_HEADER + "".join(rows), encoding="utf-8-sig")


def test_legacy_rows_are_kept_and_not_compared(tmp_path):
    path = tmp_path / "journal.csv"
    _legacy(path, ["2026-10-13,000001,옛1,KOSPI,vcp,breakout,100,93,80,90,101,1e10,False\n",
                   "2026-10-13,000002,옛2,KOSPI,cup_handle,forming,100,93,60,90,95,1e10,False\n",
                   "2026-10-13,000003,옛3,KOSPI,,,,,40,90,95,1e10,True\n"])
    old = journal.load_journal(path)
    assert (old["rule"] == "").all() and not journal.is_current(old).any()
    # 같은 기준일(10-13) 새 스캔: 옛 행은 지우지 않고, 직전 비교도 하지 않는다(배지 · 탈락 없음)
    now = _scan("2026-10-13", [_ss("000001", NEAR_PIVOT), _ss("000009", FORMING)])
    summary = journal.annotate(now, path)
    assert now.prev_asof is None and all(s.badge is None for s in now.stocks)
    assert summary["탈락"] == [] and now.dropped == []
    journal.append(now, path)
    j = journal.load_journal(path)
    assert len(j) == 5                                                 # 옛 3 + 새 2 (같은 날 같은 종목도 따로)
    legacy = j[~journal.is_current(j)]
    assert sorted(legacy["pattern"]) == ["", "cup_handle", "vcp"] and set(legacy["asof"]) == {"2026-10-13"}
    assert (j[journal.is_current(j)]["rule"] == "cwh_reference_v1.0.0").all()
    # 다시 같은 날 실행: 새 행만 교체
    journal.append(_scan("2026-10-13", [_ss("000009", NEAR_PIVOT)]), path)
    j = journal.load_journal(path)
    assert len(j) == 4 and (~journal.is_current(j)).sum() == 3
    # 다음 날: 직전 비교는 새 식 행(10-13)끼리
    nxt = _scan("2026-10-14", [_ss("000009", BREAKOUT)])
    journal.annotate(nxt, path)
    assert nxt.prev_asof == "2026-10-13" and nxt.stocks[0].badge == "돌파" and nxt.dropped == []


def test_summarize_separates_legacy(tmp_path):
    path = tmp_path / "journal.csv"
    _legacy(path, ["2026-10-08,000001,옛1,KOSPI,vcp,breakout,100,93,80,90,101,1e10,False\n",
                   "2026-10-08,000002,옛2,KOSPI,leader,,,,60,95,95,1e10,True\n"])
    journal.append(_scan("2026-10-13", [_ss("000003", NEAR_PIVOT)]), path)
    j = journal.track(path, cache=_FakeCache({}), save=False)
    assert list(j["first"]) == [True, True, True]          # 옛 기록과 새 기록은 따로 '처음' 판정
    summ = journal.summarize(j)
    assert summ["전체"].iloc[0]["표본"] == 1                          # 새 식 행만
    legacy = summ[journal.LEGACY_NOTE]
    assert set(legacy["대표 패턴"]) == {"vcp", "leader"}
