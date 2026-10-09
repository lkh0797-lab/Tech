"""차트 긴 이력 (chart_screener.chart_history) — 가짜 증권사 일봉으로 이어 받기 · 캐시 · 수정주가 어긋남 · 시간 한도."""
import json
import threading
from datetime import date
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest

from chart_screener import chart_history as H
from chart_screener.broker.kis import KISAuthError

ALL = pd.bdate_range("2000-01-03", "2026-10-08")          # 가짜 종목의 전 이력 (상장 2000-01-03)
PRICE = pd.Series(np.linspace(1000, 50000, len(ALL)), index=ALL)


def bars(dates, scale=1.0):
    s = PRICE.loc[dates] * scale
    return pd.DataFrame({"open": s, "high": s * 1.01, "low": s * 0.99, "close": s, "volume": 1000.0},
                        index=pd.DatetimeIndex(dates, name="date"))


class FakeDaily:
    """client.daily(code, start, end): 기간 안의 가장 최근 100봉 (KIS 와 같게). scale 로 수정주가 조정 전 값 흉내."""

    def __init__(self, scale=1.0, fatal=False):
        self.scale, self.fatal, self.calls = scale, fatal, []
        self._lock = threading.Lock()

    def daily(self, code, start, end):
        with self._lock:
            self.calls.append((code, str(start), str(end)))
        if self.fatal:
            raise KISAuthError("유효하지 않은 AppKey 입니다", "EGW00103")
        s, e = pd.Timestamp(str(start).replace("-", "")), pd.Timestamp(str(end).replace("-", ""))
        return bars(ALL[(ALL >= s) & (ALL <= e)][-100:], self.scale)


def recent_frame(n=760):
    return bars(ALL[-n:])


def _hist(tmp_path, code="000001"):
    return json.loads((tmp_path / "out" / "hist" / f"{code}.json").read_text(encoding="utf-8"))


def test_fill_fetches_once_and_writes_merged_history(tmp_path):
    fc, cache = FakeDaily(), H.HistCache(tmp_path / "cache")
    rec = recent_frame()
    r = H.fill(fc, [("000001", rec)], out_dir=tmp_path / "out", cache=cache, budget=60, today=date(2026, 10, 9))
    assert r.written == 1 and r.fetched == 1 and not r.errors and r.calls == len(fc.calls)
    js = _hist(tmp_path)
    assert js["from"] == "2000-01-03" and len(js["t"]) == len(ALL) and js["t"][-1] == 20261008
    assert js["older"] == len(ALL) - 760 and len(js["c"]) == len(js["t"])
    assert js["t"] == sorted(set(js["t"]))                       # 날짜 중복 · 역순 없음
    _, meta = cache.load("000001")
    assert meta["complete"] is True
    n = len(fc.calls)
    H.fill(fc, [("000001", rec)], out_dir=tmp_path / "out", cache=cache, budget=60, today=date(2026, 10, 9))
    assert len(fc.calls) == n                                    # 받은 앞 구간은 다시 묻지 않는다


def test_window_moves_forward_fetches_only_gap(tmp_path):
    fc, cache = FakeDaily(), H.HistCache(tmp_path / "cache")
    H.fill(fc, [("000001", bars(ALL[-900:-140]))], out_dir=tmp_path / "out", cache=cache, budget=60,
           today=date(2026, 5, 1))                               # 몇 달 전 스캔 일봉 창
    n = len(fc.calls)
    r = H.fill(fc, [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60,
               today=date(2026, 10, 9))
    assert r.written == 1 and 0 < len(fc.calls) - n <= 3         # 비어 있는 최근 쪽만 몇 번
    js = _hist(tmp_path)
    assert len(js["t"]) == len(ALL) and js["t"] == sorted(set(js["t"]))


def test_price_basis_mismatch_scales_cache_once(tmp_path):
    cache = H.HistCache(tmp_path / "cache")
    r = H.fill(FakeDaily(scale=2.0), [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60,
               today=date(2026, 10, 9))                          # 증권사 값이 스캔 일봉의 2배(조정 기준 다름)
    assert r.scaled == 1
    js = _hist(tmp_path)
    i = js["t"].index(int(f"{ALL[-761]:%Y%m%d}"))                # 스캔 창 바로 앞날 — 스캔 일봉과 같은 기준
    assert js["c"][i] == pytest.approx(PRICE.iloc[-761], rel=1e-6)
    assert js["v"][i] == 1000                                    # 거래량은 맞추지 않는다 (원래 주식 수)
    fc = FakeDaily(scale=2.0)
    r = H.fill(fc, [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60,
               today=date(2026, 10, 9))
    assert r.scaled == 0 and len(fc.calls) == 0                  # 맞춘 값으로 저장 — 다음엔 다시 묻지도 맞추지도 않음


class HaltDaily(FakeDaily):
    """2015-06-01 하루는 거래정지 행(가격 0)으로 준다."""

    def daily(self, code, start, end):
        df = super().daily(code, start, end)
        d = pd.Timestamp("2015-06-01")
        if d in df.index:
            df.loc[d, ["open", "high", "low", "close", "volume"]] = 0.0
        return df


def test_halted_row_does_not_end_paging(tmp_path):
    cache = H.HistCache(tmp_path / "cache")
    H.fill(HaltDaily(), [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60,
           today=date(2026, 10, 9))
    js = _hist(tmp_path)
    assert js["from"] == "2000-01-03" and js["complete"] is True
    assert len(js["t"]) == len(ALL) - 1                          # 정지일 한 행만 빠진다


def test_gap_after_split_scales_cache_and_cut_gap_keeps_until(tmp_path):
    cache = H.HistCache(tmp_path / "cache")
    r = H.fill(FakeDaily(scale=2.0), [("000001", bars(ALL[-1400:-640], scale=2.0))], out_dir=tmp_path / "out",
               cache=cache, budget=60, today=date(2024, 6, 1))   # 예전: 분할 전 — 증권사 · 스캔 일봉 모두 2배 기준
    assert r.scaled == 0
    old_until = cache.load("000001")[1]["until"]
    # 지금: 기준이 바뀌어 증권사도 1배. 창이 앞으로 가 빈 구간을 받는데, 시간 한도 0 이면 못 받는다 → until 그대로
    r = H.fill(FakeDaily(), [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=0,
               today=date(2026, 10, 9))
    assert r.pending == 1 and cache.load("000001")[1]["until"] == old_until
    r = H.fill(FakeDaily(), [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60,
               today=date(2026, 10, 9))
    js = _hist(tmp_path)
    assert len(js["t"]) == len(ALL) and js["t"] == sorted(set(js["t"]))
    k = js["t"].index(int(f"{ALL[100]:%Y%m%d}"))
    assert js["c"][k] == pytest.approx(PRICE.iloc[100], rel=1e-3)   # 분할 전 캐시 구간도 새 기준(1배)으로 맞춤
    assert r.scaled == 0                                         # 빈 구간 받을 때 맞췄으니 마지막 비교는 그대로


def test_no_client_uses_cache_only_and_budget_marks_pending(tmp_path):
    cache = H.HistCache(tmp_path / "cache")
    r = H.fill(None, [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60)
    assert r.written == 0 and r.pending == 1 and r.calls == 0
    r = H.fill(FakeDaily(), [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=0)
    assert r.pending == 1 and r.written == 0                     # 시간 한도 0 — 다음 스캔에서


def test_newly_listed_stock_has_no_older_part(tmp_path):
    fc, cache = FakeDaily(), H.HistCache(tmp_path / "cache")
    rec = bars(ALL[:300])                                        # 상장 후 300봉뿐 — 스캔 일봉이 전부
    r = H.fill(fc, [("000001", rec)], out_dir=tmp_path / "out", cache=cache, budget=60, today=date(2001, 3, 1))
    assert r.written == 1 and r.skipped == 1                     # 앞 구간은 없지만 스캔 일봉(상장 이후 전부)으로 파일은 씀
    js = _hist(tmp_path)
    assert js["from"] == "2000-01-03" and js["older"] == 0 and len(js["t"]) == 300 and js["complete"] is True
    n = len(fc.calls)
    H.fill(fc, [("000001", rec)], out_dir=tmp_path / "out", cache=cache, budget=60, today=date(2001, 3, 1))
    assert len(fc.calls) == n                                    # 앞 구간 없음도 기억한다


def test_fatal_error_stops(tmp_path):
    r = H.fill(FakeDaily(fatal=True), [("000001", recent_frame()), ("000002", recent_frame())],
               out_dir=tmp_path / "out", cache=H.HistCache(tmp_path / "cache"), budget=60, workers=1)
    assert r.stopped and "AppKey" in r.stopped and r.written == 0
    assert "중단" in r.summary_line()


def test_report_charts_order(monkeypatch):
    from chart_screener.report import html as rhtml
    scan = NS(stocks=[NS(code="A", ctx=object()), NS(code="B", ctx=None)], value_scans={"V": NS(code="V", ctx=object())})
    monkeypatch.setattr(rhtml, "_value_eligible", lambda s: [{"code": "V"}, {"code": "A"}])
    assert [c for c, _ in rhtml.report_charts(scan, top=150)] == ["A", "V"]


class FlakyDaily(FakeDaily):
    """calls 번째 호출부터 fails 번 연속 일시 오류 (서버 5xx 흉내)."""

    def __init__(self, at, fails):
        super().__init__()
        self.at, self.fails = at, fails

    def daily(self, code, start, end):
        n = len(self.calls) + 1
        if self.at <= n < self.at + self.fails:
            self.calls.append((code, str(start), str(end)))
            from chart_screener.broker.kis import KISError
            raise KISError("KIS 서버 오류 (HTTP 500)", None)
        return super().daily(code, start, end)


def test_transient_error_keeps_partial_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    cache = H.HistCache(tmp_path / "cache")
    fc = FlakyDaily(at=10, fails=3)                              # 10번째 쪽에서 재시도 3번 모두 실패
    r = H.fill(fc, [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60,
               today=date(2026, 10, 9))
    assert "000001" in r.errors and r.fetched == 1
    long, meta = cache.load("000001")
    assert meta["complete"] is False and long is not None and len(long) == 9 * 100   # 받은 9쪽은 남는다
    assert _hist(tmp_path)["older"] > 0                          # 받은 데까지로 파일은 쓴다
    fc2 = FakeDaily()
    r = H.fill(fc2, [("000001", recent_frame())], out_dir=tmp_path / "out", cache=cache, budget=60,
               today=date(2026, 10, 9))
    assert not r.errors and len(_hist(tmp_path)["t"]) == len(ALL)
    assert fc2.calls[0][2] < f"{long.index[0]:%Y-%m-%d}"         # 끊긴 곳 앞부터 이어 받음
    _, meta = cache.load("000001")
    assert meta["complete"] is True


def test_transient_error_retried(tmp_path, monkeypatch):
    monkeypatch.setattr(H.time, "sleep", lambda s: None)
    fc = FlakyDaily(at=5, fails=2)                               # 두 번 실패 뒤 세 번째에 성공
    r = H.fill(fc, [("000001", recent_frame())], out_dir=tmp_path / "out", cache=H.HistCache(tmp_path / "cache"),
               budget=60, today=date(2026, 10, 9))
    assert not r.errors and r.written == 1 and len(_hist(tmp_path)["t"]) == len(ALL)
