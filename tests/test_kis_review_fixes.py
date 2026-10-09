"""2026-10-09 검토에서 확인된 결함들의 회귀 시험 — 증권사(KIS) 허브 · 스캔 연결 · 저평가 목록 · 리포트.

네트워크 없이 가짜 클라이언트로만 돈다. 비밀값 · 설정 파일은 쓰지 않는다.
"""
import json
import os
import time as _t
from datetime import date, datetime, timedelta

import pytest

from chart_screener import kis_scan, scoring
from chart_screener.backtest import BacktestConfig, run_backtest
from chart_screener.broker.kis import KST, KISConfig, TokenManager
from chart_screener.data import kis_market as km
from chart_screener.scanner import ScanResult, refilter_candidates
from chart_screener.value_list import parse_value

from test_kis_market import DAY, FakeClient, opinion_rows


# ---------------------------------------------------------------- 토큰: 다른 스레드가 받은 새 토큰은 지우지 않는다
def _tm(tmp_path) -> TokenManager:
    cfg = KISConfig(app_key="A" * 36, app_secret="S" * 180, base_url="https://example.invalid", ws_url="ws://example.invalid")
    return TokenManager(cfg, cache_path=tmp_path / "tok.json", wait_on_limit=False, session=object())


def test_invalidate_keeps_newer_token(tmp_path):
    tm = _tm(tmp_path)
    exp = _t.time() + 86400
    tm._token, tm._expires_at = "T2", exp
    tm._save_state({"tokens": {tm.cfg.key_id: {"token": "T2", "expires_at": exp}}})
    tm.invalidate("T1")                          # T1 로 보낸 요청이 늦게 거부됨 — 이미 T2 로 바뀜
    assert tm._token == "T2"
    assert json.loads((tmp_path / "tok.json").read_text(encoding="utf-8"))["tokens"][tm.cfg.key_id]["token"] == "T2"
    tm.invalidate("T2")                          # 지금 토큰이 거부되면 지운다
    assert tm._token is None
    assert tm.cfg.key_id not in json.loads((tmp_path / "tok.json").read_text(encoding="utf-8")).get("tokens", {})
    tm._token = "T3"
    tm.invalidate()                              # 인자 없음 = 예전처럼 무조건 지움
    assert tm._token is None


# ---------------------------------------------------------------- 캐시 쓰기 실패 · 단계 기록
class _BrokenCache(km.KISDayCache):
    def save(self, kind, day, entries):
        raise PermissionError(13, "drive locked")


def test_cache_write_error_keeps_results(tmp_path):
    fc = FakeClient()
    got = km.fetch_status(fc, ["005930", "101000"], _BrokenCache(tmp_path / "kis"), day=DAY)
    assert set(got) == {"005930", "101000"}      # 저장 못 해도 받은 것은 돌려준다


def test_hub_turns_off_on_unexpected_error(tmp_path):
    cfg = km.KISMarketConfig(cache_dir=tmp_path / "kis", snapshot_path=None, workers=1)
    hub = kis_scan.open_hub("on", cfg=cfg, connect=lambda c: (FakeClient(), ""))
    hub.day = hub.res.day = DAY

    def boom(cs, errs, w):
        raise OSError("drive dropped")

    assert hub._run("status", ["005930"], boom) == {}
    assert not hub.on and "OSError" in hub.res.fatal and "상태 단계" in hub.res.fatal
    st = hub.res.steps[-1]
    assert st["ok"] == 0 and st["stop"] is True  # 멈춘 단계를 성공으로 세지 않는다
    assert "중단" in hub.summary_line()


def test_step_ok_not_counted_after_fatal(tmp_path):
    fc = FakeClient(fatal_after=2)
    cfg = km.KISMarketConfig(cache_dir=tmp_path / "kis", snapshot_path=None, workers=1)
    res = km.refresh([f"{i:06d}" for i in range(10)], [], client=fc, cfg=cfg, day=DAY)
    assert res.fatal and res.steps[0]["ok"] == 0 and res.steps[0]["stop"] is True


# ---------------------------------------------------------------- 상태 캐시 신선도
def test_status_cache_reused_only_same_day_within_ttl(tmp_path, monkeypatch):
    cache = km.KISDayCache(tmp_path / "kis")
    fc = FakeClient()
    t0 = datetime(2026, 10, 8, 16, 0, tzinfo=KST)
    monkeypatch.setattr(km, "_now", lambda: t0)
    km.fetch_status(fc, ["005930"], cache, day=DAY)
    n = fc.count("inquire-price")
    for later in (t0 + timedelta(hours=1), datetime(2026, 10, 9, 15, 0, tzinfo=KST),   # 저녁 · 휴장일(한글날)
                  datetime(2026, 10, 12, 7, 30, tzinfo=KST)):                          # 다음 개장일 장 전
        monkeypatch.setattr(km, "_now", lambda later=later: later)
        km.fetch_status(fc, ["005930"], cache, day=DAY)
        assert fc.count("inquire-price") == n, later           # 장 밖 · 그사이 장이 안 열림 — 재사용
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 12, 10, 30, tzinfo=KST))
    km.fetch_status(fc, ["005930"], cache, day=DAY)           # 다음 개장일 장중 — 기준일은 같아도 다시 받는다
    assert fc.count("inquire-price") == n + 1
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 12, 12, 0, tzinfo=KST))
    km.fetch_status(fc, ["005930"], cache, day=DAY)           # 장중 1.5시간 뒤 — 재사용
    assert fc.count("inquire-price") == n + 1
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 12, 16, 0, tzinfo=KST))
    km.fetch_status(fc, ["005930"], cache, day=DAY)           # 장중에 받은 것은 마감(15:45) 뒤 한 번 더
    assert fc.count("inquire-price") == n + 2


# ---------------------------------------------------------------- 거래대금 확정 (시간외까지)
def test_turnover_refetched_after_value_final(tmp_path, monkeypatch):
    cache = km.KISDayCache(tmp_path / "kis")
    fc = FakeClient()
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 8, 16, 0, tzinfo=KST))
    km.fetch_turnover(fc, ["005930"], cache, day=DAY)
    p = cache.turnover_path("005930")
    early = datetime(2026, 10, 8, 16, 0, tzinfo=KST).timestamp()
    os.utime(p, (early, early))                                 # 16:00 에 받은 것으로
    n = fc.count("inquire-daily-itemchartprice")
    km.fetch_turnover(fc, ["005930"], cache, day=DAY)          # 아직 18:10 전 — 다시 묻지 않음
    assert fc.count("inquire-daily-itemchartprice") == n
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 8, 19, 0, tzinfo=KST))
    km.fetch_turnover(fc, ["005930"], cache, day=DAY)          # 확정 뒤 — 한 번 다시 받고 시각을 남긴다
    assert fc.count("inquire-daily-itemchartprice") == n + 1
    km.fetch_turnover(fc, ["005930"], cache, day=DAY)
    assert fc.count("inquire-daily-itemchartprice") == n + 1


class _NoTurnoverWrite(km.KISDayCache):
    def save_turnover(self, code, series):
        raise PermissionError(13, "drive locked")


def test_turnover_save_error_keeps_series(tmp_path, monkeypatch):
    good = km.KISDayCache(tmp_path / "kis")
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 8, 16, 0, tzinfo=KST))
    km.fetch_turnover(FakeClient(), ["005930"], good, day=DAY)          # 16:00 에 받아 둔 이력
    early = datetime(2026, 10, 8, 16, 0, tzinfo=KST).timestamp()
    os.utime(good.turnover_path("005930"), (early, early))
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 8, 19, 0, tzinfo=KST))
    errs = {}
    got = km.fetch_turnover(FakeClient(), ["005930"], _NoTurnoverWrite(tmp_path / "kis"), day=DAY, errors=errs)
    assert len(got["005930"]) >= 100 and errs == {}                     # 저장 못 해도 받은 것 · 쌓인 것은 쓴다
    errs = {}
    got = km.fetch_turnover(FakeClient(fail={"005930"}), ["005930"], good, day=DAY, errors=errs)
    assert "005930" in errs and len(got["005930"]) >= 100               # 받다 실패하면 쌓인 이력으로 (재시도 대상)


def test_status_falls_back_to_stale_entry_when_refetch_fails(tmp_path, monkeypatch):
    cache = km.KISDayCache(tmp_path / "kis")
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 8, 16, 0, tzinfo=KST))
    km.fetch_status(FakeClient(), ["101000"], cache, day=DAY)
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 12, 10, 30, tzinfo=KST))   # 다음 개장일 장중 — 다시 받아야 함
    errs = {}
    got = km.fetch_status(FakeClient(fail={"101000"}), ["101000"], cache, day=DAY, errors=errs)
    assert "101000" in errs and got["101000"].mang                       # 묵은 관리종목 상태라도 남겨 제외가 풀리지 않게


# ---------------------------------------------------------------- 의견 여력: 묵은 리포트 전일 종가를 쓰지 않음
def test_opinion_gap_needs_live_price():
    op = km.parse_opinions(opinion_rows(), DAY, price=None)
    assert op.avg_target_90d is not None and op.gap_pct is None and op.price is None


# ---------------------------------------------------------------- 휴장일: KIS 가 모르면 달력, 장중 봉은 확정으로 치지 않음
class _Unknown:
    def open_day(self, d):
        return None


def test_holiday_skip_falls_back_to_calendar_when_kis_unknown():
    now = datetime(2026, 10, 9, 16, 0, tzinfo=KST)              # 한글날
    assert km.is_open_today(_Unknown(), now) is False
    assert km.market_date(_Unknown(), now) == date(2026, 10, 8)
    skip, why = kis_scan.holiday_skip(_Unknown(), now=now, last_bar=date(2026, 10, 8))
    assert skip and "직전 개장일" in why


def test_cached_index_last_ignores_partial_bar(tmp_path, monkeypatch):
    import pandas as pd

    from chart_screener.data import ohlcv as ohlcv_mod

    idx = pd.DatetimeIndex(pd.to_datetime(["2026-10-07", "2026-10-08"]), name="date")
    df = pd.DataFrame({"open": [1.0, 1.0], "high": [1.0, 1.0], "low": [1.0, 1.0], "close": [1.0, 1.0],
                       "volume": [1.0, 1.0]}, index=idx)
    root = tmp_path / "ohlcv"
    root.mkdir()
    df.to_pickle(root / "KOSPI.pkl")
    orig = ohlcv_mod.OHLCVCache.__init__
    monkeypatch.setattr(ohlcv_mod.OHLCVCache, "__init__", lambda self, root_=None, **kw: orig(self, root, **kw))
    t = datetime(2026, 10, 8, 11, 0, tzinfo=KST).timestamp()   # 10-08 장중에 받은 캐시
    os.utime(root / "KOSPI.pkl", (t, t))
    assert kis_scan._cached_index_last() == date(2026, 10, 7)
    t = datetime(2026, 10, 8, 16, 30, tzinfo=KST).timestamp()  # 종가 확정 뒤
    os.utime(root / "KOSPI.pkl", (t, t))
    assert kis_scan._cached_index_last() == date(2026, 10, 8)


# ---------------------------------------------------------------- 저평가 목록: 그날 증권사 상태로 등급 내림
def test_value_list_apply_status():
    vl = parse_value({"v": 1, "rows": [{"code": "000001", "tier": "저평가"}, {"code": "000002", "tier": "저평가"},
                                       {"code": "000003", "tier": "관찰", "tier_why": ["빨간불"]}]})
    n = vl.apply_status(lambda c: {"000002": "관리종목", "000003": "거래정지"}.get(c))
    assert n == 1 and vl.get("000002")["tier"] == "관찰" and vl.get("000002")["tier_why"] == ["증권사 상태: 관리종목"]
    assert vl.get("000001")["tier"] == "저평가" and vl.get("000003")["tier_why"] == ["빨간불"]   # 이미 관찰은 그대로
    assert vl.counts() == {"저평가": 1, "관찰": 2}


# ---------------------------------------------------------------- 수급 반영 뒤 후보 다시 맞추기
class _S:
    def __init__(self, code, cand, composite=50.0, ctx=True, thin=None):
        self.code, self.name, self.market, self.close, self.rs = code, code, "KOSPI", 1000.0, 80.0
        self.results = {"cand": cand}
        self.score = type("Sc", (), {"composite": composite})()
        self.ctx = object() if ctx else None
        self.thin = thin

    def display_lead(self):
        return None


def test_refilter_candidates(monkeypatch):
    monkeypatch.setattr(scoring, "is_candidate", lambda results, rs=None: results["cand"])
    a, b, c, d, e = _S("A", True, 60), _S("B", False, 70), _S("C", True, 80), _S("D", True, thin="주가"), _S("E", True)
    f = _S("F", True)
    f.kst = ["관리종목"]                                          # 스캔 때 비후보라 excluded 에 없던 관리종목
    scan = ScanResult(asof=None, generated_at=None, market={}, stocks=[a, b], scanned=2, elapsed=0.0, patterns=[],
                      value_scans={"C": c, "D": d, "E": e, "F": f}, excluded=[{"code": "E"}])
    assert refilter_candidates(scan) == (1, 1)
    assert [s.code for s in scan.stocks] == ["C", "A"]           # B 빠짐 · C 들어옴 (D 문턱 밑 · E · F 상태 제외는 안 들어옴)
    assert scan.dropped[-1]["code"] == "B" and "CAN SLIM" in scan.dropped[-1]["reason"] and b.ctx is None
    assert scan.excluded[-1]["code"] == "B"                      # 일지 비교 뒤에도 사유가 남게
    scan.include_all = True
    assert refilter_candidates(scan) == (0, 0)


# ---------------------------------------------------------------- 백테스트: 잴 수 없는 관찰 패턴은 이유와 함께 거절
def test_backtest_rejects_unmeasurable_patterns():
    with pytest.raises(ValueError, match="외부 파일"):
        run_backtest(BacktestConfig(pattern="undervalued"))
    with pytest.raises(ValueError, match="--mode stage"):
        run_backtest(BacktestConfig(pattern="absorb"))
    with pytest.raises(ValueError, match="near_pivot"):
        run_backtest(BacktestConfig(pattern="absorb", mode="stage"))          # 기본 단계 breakout 은 absorb 에 없다
