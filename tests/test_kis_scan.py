"""스캔 ↔ 증권사(KIS) 자료 연결 (chart_screener.kis_scan) — 가짜 KIS 클라이언트로 네트워크 없이 검증.

상태 제외 → 탈락 목록, 상태 태그 → 리포트, 실제 거래대금 덮어쓰기 → 300억 레이더, 후보 수급 · 의견 · 추정 → payload,
관찰 전용 패턴(absorb · stage2)은 혼자 후보가 되지 않음, 휴장일 건너뛰기, CLI(--kis · --skip-holiday).
"""
import json
import threading
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from chart_screener import kis_scan, scanner, scoring
from chart_screener.broker.kis import KST, PATH_DAILY, PATH_PRICE, KISAuthError, KISRateLimitError
from chart_screener.config import Config
from chart_screener.data import kis_market as km
from chart_screener.patterns.base import BREAKOUT, FORMING, PatternResult
from chart_screener.report.html import build_payload, render
from synthetic import confirmed_market, flat_index, make_ohlcv, set_bar
from test_kis_market import ESTIMATE_005930, ESTIMATE_NONE, opinion_rows, price_out

DAY = date(2026, 10, 8)
EMPTY_SECTORS = pd.DataFrame(columns=["code", "sector", "themes"])


def _ymd(d) -> str:
    return f"{pd.Timestamp(d):%Y%m%d}"


def flows_rows(end, n=30, frgn_qty="1000", orgn_qty="2000"):
    """inquire-investor output (최신순). 금액 백만원: 외국인 +100(=1억) · 기관 +300(=3억) 매일."""
    return [{"stck_bsop_date": f"{d:%Y%m%d}", "stck_clpr": "10000", "prsn_ntby_qty": "-3000",
             "frgn_ntby_qty": frgn_qty, "orgn_ntby_qty": orgn_qty, "prsn_ntby_tr_pbmn": "-400",
             "frgn_ntby_tr_pbmn": "100", "orgn_ntby_tr_pbmn": "300"}
            for d in pd.bdate_range(end=pd.Timestamp(end), periods=n)[::-1]]


class FakeKIS:
    """KISRestClient 대역 (get · open_day). status: {code: price_out()}, turnover: {code: {YYYYMMDD: 원}}."""

    def __init__(self, status=None, turnover=None, flows_end="2026-10-08", fatal_on=None, holidays=(), flaky=()):
        self.flaky = set(flaky)                  # 첫 요청은 초당 한도 오류, 다음엔 정상
        self.status = status or {}
        self.turnover = turnover or {}
        self.flows_end = flows_end
        self.fatal_on = fatal_on
        self.holidays = set(holidays)
        self.calls = []
        self._lock = threading.Lock()

    def open_day(self, d):
        return d.weekday() < 5 and d not in self.holidays

    def get(self, path, tr_id, params):
        name = path.rsplit("/", 1)[-1]
        code = params.get("FID_INPUT_ISCD") or params.get("SHT_CD")
        with self._lock:
            self.calls.append((name, code))
        if self.fatal_on == name:
            raise KISAuthError("유효하지 않은 AppKey 입니다", "EGW00103")
        if (name, code) in self.flaky:
            self.flaky.discard((name, code))
            raise KISRateLimitError("초당 호출 한도를 넘었습니다", "EGW00201")
        if path == PATH_PRICE:
            return {"output": self.status.get(code) or price_out()}
        if path == PATH_DAILY:
            until = params["FID_INPUT_DATE_2"]
            rows = [{"stck_bsop_date": d, "acml_tr_pbmn": str(v)}
                    for d, v in sorted(self.turnover.get(code, {}).items(), reverse=True) if d <= until]
            return {"output2": rows}
        if path == km.PATH_INVESTOR:
            return {"output": flows_rows(self.flows_end)}
        if path == km.PATH_OPINION:
            return {"output": opinion_rows()}
        if path == km.PATH_ESTIMATE:
            return ESTIMATE_005930 if code != "000009" else ESTIMATE_NONE
        raise AssertionError(path)

    def count(self, name):
        return sum(1 for c in self.calls if c[0] == name)


def make_hub(tmp_path, client, day=DAY) -> kis_scan.KISScan:
    cfg = km.KISMarketConfig(cache_dir=tmp_path / "kis", snapshot_path=None, workers=2)
    hub = kis_scan.open_hub("on", cfg=cfg, connect=lambda c: (client, ""))
    hub.day = hub.res.day = day
    return hub


def _df(volume_at_candle=5e6, seed=7):
    """10,000원 · 하루 100억 정도 거래되는 300봉, 끝에서 3번째 봉이 +10% 장대양봉."""
    df = make_ohlcv([(0, 10000), (299, 10000)], seed=seed, noise=0.002)
    pc = float(df["close"].iloc[-4])
    return set_bar(df, -3, open=pc, close=pc * 1.1, high=pc * 1.1 * 1.005, low=pc * 0.995, volume=volume_at_candle)


def make_ud(frames: dict):
    from chart_screener.universe_data import UniverseData
    rows = [{"code": c, "name": f"종목{c[-1]}", "market": "KOSPI", "market_cap": float("nan"), "traded_at": pd.NaT,
             "market_open": False, "value": 0.0} for c in frames]
    uni = pd.DataFrame(rows).set_index("code", drop=False)
    idx = next(iter(frames.values())).index
    rs = pd.DataFrame({c: np.full(len(idx), 85.0) for c in frames}, index=idx)
    return UniverseData(uni, dict(frames), {"KOSPI": flat_index(len(idx), start=str(idx[0].date()))},
                        {"KOSPI": confirmed_market()}, rs, idx[-1])


def scan_with(hub, ud, monkeypatch, candidate=lambda results, rs=None: True):
    monkeypatch.setattr(scoring, "is_candidate", candidate)
    ud.ohlcv = hub.load_universe(ud.universe, ud.ohlcv)
    return scanner.run_scan(ud, Config(), verbose=False, sector_map=EMPTY_SECTORS, kis=hub)


# ---------------------------------------------------------------- 만들기 · 끄기
def test_open_hub_modes():
    off = kis_scan.open_hub("off", connect=lambda c: pytest.fail("off 는 연결하지 않음"))
    assert not off.on and "off" in off.reason and off.summary_line().startswith("증권사 자료 없음 — 네이버")
    offline = kis_scan.open_hub("auto", offline=True, connect=lambda c: pytest.fail("오프라인 auto 는 연결 안 함"))
    assert not offline.on and offline.reason == "오프라인 실행"
    missing = kis_scan.open_hub("auto", connect=lambda c: (None, "한국투자증권 설정 없음: 파일이 없습니다"))
    assert not missing.on and "설정 없음" in missing.summary_line()
    assert missing.load_universe(pd.DataFrame(index=["000001"]), {"x": 1}) == {"x": 1}   # 꺼져 있으면 그대로
    on = kis_scan.open_hub("on", offline=True, connect=lambda c: (FakeKIS(), ""))
    assert on.on and on.reason == ""


def test_fatal_auth_turns_hub_off(tmp_path):
    fc = FakeKIS(fatal_on="inquire-price")
    hub = make_hub(tmp_path, fc)
    data = {"000001": _df()}
    out = hub.load_universe(pd.DataFrame(index=list(data)), data)
    assert out is data or out["000001"].equals(data["000001"])
    assert not hub.on and "AppKey" in hub.res.fatal and "상태" in hub.res.fatal
    assert fc.count("inquire-daily-itemchartprice") == 0                  # 다음 단계로 가지 않음
    assert "중단" in hub.summary_line() and hub.report_info()["on"] is False
    assert hub.write_snapshots(tmp_path) == []


def test_failed_codes_are_retried_once_with_fewer_workers(tmp_path):
    fc = FakeKIS(flaky={("inquire-price", "000002"), ("inquire-price", "000003")})
    hub = make_hub(tmp_path, fc)
    data = {c: _df(seed=i) for i, c in enumerate(["000001", "000002", "000003"])}
    hub.load_universe(pd.DataFrame(index=list(data)), data)
    assert set(hub.res.status) == {"000001", "000002", "000003"} and hub.retried == {"status": 2}
    st = hub.res.steps[0]
    assert st["step"] == "status" and st["ok"] == 3 and st["fail"] == 0 and fc.count("inquire-price") == 5
    assert "재시도 2" in hub.timing_lines()[1]
    hub2 = make_hub(tmp_path / "b", FakeKIS(flaky={("inquire-price", "000001")}))
    hub2.retry_workers = 0
    hub2.load_universe(pd.DataFrame(index=["000001"]), {"000001": data["000001"]})
    assert hub2.res.steps[0]["fail"] == 1 and "초당 호출 한도" in hub2.timing_lines()[1]
    assert kis_scan.error_reasons({"a": "x", "b": "x", "c": "y"}) == "x 2 · y 1"


# ---------------------------------------------------------------- 상태 · 실제 거래대금
def test_status_exclusion_goes_to_dropped_and_tags_reach_payload(tmp_path, monkeypatch):
    fc = FakeKIS(status={
        "000001": price_out(mrkt_warn_cls_code="02", short_over_yn="Y"),                 # 투자경고 · 단기과열 (남김)
        "000002": price_out("51", mang_issu_cls_code="Y"),                               # 관리종목 → 제외
        "000003": price_out("57", marg_rate="100.00"),                                   # 증거금100% (남김 · 태그 없음)
    })
    hub = make_hub(tmp_path, fc)
    ud = make_ud({c: _df(seed=i) for i, c in enumerate(["000001", "000002", "000003"])})
    scan = scan_with(hub, ud, monkeypatch)
    codes = [s.code for s in scan.stocks]
    assert sorted(codes) == ["000001", "000003"]
    assert [d["code"] for d in scan.excluded] == ["000002"]
    assert scan.dropped[0]["reason"] == "증권사 상태 제외: 관리종목" and scan.dropped[0]["name"] == "종목2"
    by = {s.code: s for s in scan.stocks}
    assert by["000001"].kst == ["투자경고", "단기과열"] and by["000003"].kst == []

    scan.kis = hub.report_info()
    html = render(build_payload(scan))
    d = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    stocks = {s["code"]: s for s in d["stocks"]}
    assert stocks["000001"]["kst"] == ["투자경고", "단기과열"]
    assert d["dropped"][0]["reason"].endswith("관리종목")
    assert d["kis"]["on"] is True and d["kis"]["line"].startswith("증권사 자료: 상태 3")
    for needle in ("tag ks", "증권사 상태(거래정지·정리매매·관리종목·투자위험)로 뺀 후보", 'id="kisLine"'):
        assert needle in html, needle


def test_journal_keeps_status_exclusions(tmp_path, monkeypatch):
    from chart_screener import journal
    hub = make_hub(tmp_path, FakeKIS(status={"000002": price_out("58", temp_stop_yn="Y")}))
    ud = make_ud({c: _df(seed=i) for i, c in enumerate(["000001", "000002"])})
    scan = scan_with(hub, ud, monkeypatch)
    prev = pd.DataFrame([{"asof": "2023-01-01", "code": "000002", "name": "종목2", "market": "KOSPI",
                          "pattern": "vcp", "stage": FORMING, "composite": 50.0, "close": 9000.0}])
    jcols = journal.COLUMNS
    prev = prev.reindex(columns=jcols)
    journal.annotate(scan, journal=prev)
    assert [d["code"] for d in scan.dropped] == ["000002"]
    assert scan.dropped[0]["reason"] == "증권사 상태 제외: 거래정지" and scan.dropped[0]["pattern"] == "vcp"


def test_real_turnover_overwrites_value_and_changes_radar(tmp_path, monkeypatch):
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 8, 20, 0, tzinfo=KST))   # 자정을 걸치지 않게 시계 고정
    # 장대양봉 날 추정 거래대금은 거래량이 작아 ~11억 (레이더 밖) → KIS 실제 거래대금 500억이면 레이더 안
    df = _df(volume_at_candle=1e5)
    candle = _ymd(df.index[-3])
    real = {_ymd(d): 1.2e10 for d in df.index[-100:]}
    real[candle] = 5e10
    real[_ymd(DAY)] = 1e10                       # 기준일 행이 있어야 다음 실행에서 다시 묻지 않는다
    fc = FakeKIS(turnover={"000001": real})
    no_kis = scanner.run_scan(make_ud({"000001": df}), Config(), verbose=False, sector_map=EMPTY_SECTORS)
    assert no_kis.radar == []

    hub = make_hub(tmp_path, fc)
    ud = make_ud({"000001": df})
    scan = scan_with(hub, ud, monkeypatch)
    v = ud.ohlcv["000001"]["value"]
    assert v.loc[df.index[-3]] == 5e10 and v.loc[df.index[-50]] == 1.2e10
    assert v.loc[df.index[0]] == pytest.approx(df["value"].iloc[0])           # 100일보다 앞선 날은 추정치 그대로
    assert ud.ohlcv["000001"].attrs["value_real_n"] == 100
    assert [r["code"] for r in scan.radar] == ["000001"] and scan.radar[0]["value"] == 5e10
    assert fc.count("inquire-daily-itemchartprice") == 1
    # 같은 기준일 재실행은 캐시만 (요청 없음)
    hub2 = make_hub(tmp_path, fc)
    hub2.load_universe(ud.universe, {"000001": df})
    assert fc.count("inquire-daily-itemchartprice") == 1 and fc.count("inquire-price") == 1


# ---------------------------------------------------------------- 후보 수급 · 의견 · 추정
def test_enrich_flows_opinions_estimates_and_report_columns(tmp_path, monkeypatch):
    frames = {"000001": _df(seed=1), "000009": _df(seed=9)}
    end = frames["000001"].index[-1]
    fc = FakeKIS(flows_end=end)
    hub = make_hub(tmp_path, fc)
    scan = scan_with(hub, make_ud(frames), monkeypatch)
    got = hub.enrich(scan)
    assert got == {"flows": 2, "opinion": 2, "estimate": 1}
    s = {x.code: x for x in scan.stocks}["000001"]
    inv = scanner.investor_summary(s)
    assert inv["src"] == "KIS" and inv["days"] == 20
    assert inv["inst"] == pytest.approx(20 * 3e8) and inv["foreign"] == pytest.approx(20 * 1e8)   # 체결 금액 합 (억원 → 원)
    assert inv["foreign_ratio"] == pytest.approx(30.0)          # 외국인 보유율 (소진율 46.35 아님)
    assert any("[I]" in line for line in s.results["canslim"].reasons + s.results["canslim"].warnings)
    assert s.results["canslim"].metrics.get("inv_inst_20") == pytest.approx(20 * 2000)            # CAN SLIM I 재계산
    k = s.kis
    assert k["tp_up30"] >= 1 and k["tp_avg"] > 0 and len(k["opinions"]) == 3
    assert k["tp_gap"] == pytest.approx(round((k["tp_avg"] / s.close - 1) * 100, 2))
    assert k["fwd_eps_g"] == pytest.approx(45.51) and k["eps_e"] == [["2026.12E", 46209.0], ["2027.12E", 67239.8]]
    k9 = {x.code: x for x in scan.stocks}["000009"].kis
    assert k9["fwd_eps_g"] is None and k9["eps_e"] == [] and k9["tp_n30"] is not None   # 추정 커버리지 없음

    scan.kis = hub.report_info()
    html = render(build_payload(scan))
    d = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    p = {x["code"]: x for x in d["stocks"]}["000001"]
    assert set(p["kis"]) == {"tp_n30", "tp_up30", "tp_down30", "tp_avg", "tp_gap", "opinions", "fwd_eps_g", "eps_e"}
    assert p["kis"]["opinions"][0]["date"] == "2026-09-23" and p["inv"]["src"] == "KIS"
    for needle in ("목표가 괴리", "EPS(E) 성장", "수급 20일", 'id="dKisBox"', "renderKis", "한국투자증권 실제 집계치"):
        assert needle in html, needle
    assert [st["step"] for st in d["kis"]["steps"]] == ["status", "turnover", "flows", "opinion", "estimate"]
    assert "의견 2" in d["kis"]["line"] and "실적 2" in d["kis"]["line"]

    frame = scanner.to_frame(scan)
    row = frame.set_index("종목코드").loc["000001"]
    assert row["EPS(E)성장%"] == pytest.approx(45.51) and row["목표가상향30일"] >= 1
    assert row["기관20일순매수(억)"] == pytest.approx(60.0)


def test_snapshots_written_to_out_and_stable_path(tmp_path, monkeypatch):
    frames = {"000001": _df(seed=1)}
    hub = make_hub(tmp_path, FakeKIS(flows_end=frames["000001"].index[-1]))
    scan = scan_with(hub, make_ud(frames), monkeypatch)
    hub.enrich(scan)
    paths = hub.write_snapshots(tmp_path / "out")
    assert paths == [tmp_path / "out" / "kis_snapshot.json", tmp_path / "kis" / "snapshot.json"]
    js = json.loads(paths[1].read_text(encoding="utf-8"))
    assert js["v"] == 1 and js["date"] == "20261008" and set(js["status"]) == {"000001"}
    assert js["flows"]["000001"]["o20"] == pytest.approx(60.0) and js["estimate"]["000001"]["fwd_eps_g"] == 45.51
    assert [s["step"] for s in js["steps"]] == ["status", "turnover", "flows", "opinion", "estimate"]
    assert "NaN" not in paths[0].read_text(encoding="utf-8")


def test_timing_and_summary_lines(tmp_path):
    hub = make_hub(tmp_path, FakeKIS())
    hub.res.steps = [{"step": "status", "n": 2449, "ok": 2447, "fail": 2, "secs": 170.4},
                     {"step": "turnover", "n": 2449, "ok": 2449, "fail": 0, "secs": 81.8}]
    line = hub.summary_line()
    assert line == "증권사 자료: 상태 2,447(실패 2) · 실거래대금 2,449 · 4분 12초"
    lines = hub.timing_lines()
    assert lines[0] == "증권사(KIS) 자료 기준일 2026-10-08" and "합계 4분 12초" in lines[-1]


# ---------------------------------------------------------------- 관찰 전용 패턴
def _pr(name, detected=True, stage=FORMING):
    return PatternResult(name=name, label=name, detected=detected, score=0.0, stage=stage)


def test_observe_only_patterns_never_create_candidates():
    assert scoring.OBSERVE_PATTERNS == ("vocal", "absorb", "stage2")
    assert not set(scoring.OBSERVE_PATTERNS) & set(scoring.BASE_PATTERNS)
    only_obs = {"absorb": _pr("absorb"), "stage2": _pr("stage2", stage=BREAKOUT)}
    assert scoring.is_candidate(only_obs, 99) is False
    assert scoring.is_candidate({**only_obs, "vocal": _pr("vocal")}, 99) is True        # 보컬만 예외 (관찰 칩)
    sb = scoring.compute({**only_obs, "vcp": _pr("vcp", detected=False)}, 95)
    assert sb.best_pattern is None and sb.pattern_part == 0 and sb.detected_bases == []


def test_observe_patterns_in_detected_tabs_and_labels(monkeypatch):
    from chart_screener.patterns import REGISTRY
    from chart_screener.report import html as rhtml
    assert rhtml.DETECTED_ORDER[-3:] == ["vocal", "absorb", "stage2"]
    assert {"absorb", "stage2"} <= set(REGISTRY)
    frames = {"000001": _df(seed=1)}
    monkeypatch.setattr(scoring, "is_candidate", lambda results, rs=None: True)
    scan = scanner.run_scan(make_ud(frames), Config(), verbose=False, sector_map=EMPTY_SECTORS)
    s = scan.stocks[0]
    s.results["absorb"] = _pr("absorb")
    s.results["absorb"].metrics = {"absorb_date": "2024-01-05", "vol_mult": 3.4, "observe_only": True}
    html = render(build_payload(scan))
    d = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert "absorb" in d["stocks"][0]["detected"] and "absorb" in d["chip_patterns"]
    assert d["observe_patterns"] == ["vocal", "absorb", "stage2"]
    assert d["stocks"][0]["best"] != "absorb"                                       # 대표 패턴이 되지 않음
    for needle in ("absorb: {", "stage2: {", "vocal: {", "투매 흡수일", "150일선 돌파일", "깔때기 단계"):
        assert needle in html, needle


# ---------------------------------------------------------------- 휴장일
def test_holiday_skip_with_client_and_calendar():
    fc = FakeKIS(holidays={date(2026, 10, 9)})
    now = datetime(2026, 10, 9, 17, 0, tzinfo=KST)
    assert kis_scan.holiday_skip(fc, now=now, last_bar=date(2026, 10, 8)) == (
        True, "휴장일 — 캐시 최신 봉 2026-10-08 = 직전 개장일")
    skip, why = kis_scan.holiday_skip(fc, now=now, last_bar=date(2026, 10, 7))
    assert not skip and "2026-10-07 < 직전 개장일 2026-10-08" in why
    assert kis_scan.holiday_skip(fc, now=datetime(2026, 10, 8, 17, 0, tzinfo=KST), last_bar=date(2026, 10, 7))[0] is False
    assert kis_scan.holiday_skip(fc, now=now, cached_last_bar=lambda: None)[0] is False
    # 클라이언트 없음: 주말 · KRX 고정 휴장일 달력
    sunday = datetime(2026, 10, 11, 9, 0, tzinfo=KST)
    assert kis_scan.holiday_skip(None, now=sunday, last_bar=date(2026, 10, 8))[0] is True     # 10-09 한글날
    assert kis_scan.holiday_skip(None, now=sunday, last_bar=date(2026, 10, 7))[0] is False


# ---------------------------------------------------------------- CLI
def _cli_args(tmp_path, *extra):
    return ["scan", "--offline", "--investor-top", "0", "--out", str(tmp_path / "out"),
            "--journal", str(tmp_path / "j.csv"), *extra]


def test_cli_kis_on_without_client_fails(monkeypatch, tmp_path, capsys):
    from chart_screener.__main__ import main
    monkeypatch.setattr(km, "client_or_none", lambda cfg=None: (None, "한국투자증권 설정 없음: 시험"))
    assert main(_cli_args(tmp_path, "--kis", "on")) == 1
    assert "설정 없음: 시험" in capsys.readouterr().err


def test_cli_skip_holiday_exits_without_report(monkeypatch, tmp_path, capsys):
    from chart_screener import universe_data
    from chart_screener.__main__ import main
    monkeypatch.setattr(kis_scan, "holiday_skip", lambda client=None, **k: (True, "시험"))
    monkeypatch.setattr(universe_data, "load_universe_data", lambda *a, **k: pytest.fail("적재하면 안 됨"))
    assert main(_cli_args(tmp_path, "--kis", "off", "--skip-holiday")) == 0
    assert "휴장일 — 스캔하지 않음" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_cli_scan_with_fake_kis_end_to_end(monkeypatch, tmp_path, capsys):
    from chart_screener import universe_data
    from chart_screener.__main__ import main
    frames = {"000001": _df(seed=1), "000002": _df(seed=2)}
    ud = make_ud(frames)
    fc = FakeKIS(status={"000002": price_out("51", mang_issu_cls_code="Y")}, flows_end=frames["000001"].index[-1])
    real_open = kis_scan.open_hub

    def fake_open(mode, **k):
        hub = real_open(mode, offline=k.get("offline", False), verbose=False, connect=lambda c: (fc, ""),
                        cfg=km.KISMarketConfig(cache_dir=tmp_path / "kis", snapshot_path=None, workers=2))
        hub.day = hub.res.day = DAY
        return hub

    def fake_load(cfg, *, prepare=None, **k):
        ud.ohlcv = prepare(ud.universe, ud.ohlcv) if prepare else ud.ohlcv
        return ud

    monkeypatch.setattr(kis_scan, "open_hub", fake_open)
    monkeypatch.setattr(universe_data, "load_universe_data", fake_load)
    monkeypatch.setattr(scoring, "is_candidate", lambda results, rs=None: True)
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 9, 17, 0, tzinfo=KST))
    import chart_screener.data.sector as dsector
    monkeypatch.setattr(dsector, "load_sector_map", lambda offline=True: EMPTY_SECTORS)
    assert main(_cli_args(tmp_path, "--kis", "on")) == 0
    out = capsys.readouterr().out
    assert "증권사 상태로 후보 제외 1종목: 종목2(관리종목)" in out
    assert "증권사 자료 반영: 수급 1 · 투자의견 1 · 추정실적 1종목" in out and "합계" in out
    assert (tmp_path / "out" / "kis_snapshot.json").exists() and (tmp_path / "kis" / "snapshot.json").exists()
    html = next((tmp_path / "out").glob("scan_*.html")).read_text(encoding="utf-8")
    assert "증권사 자료: 상태 2" in html and "증권사 상태 제외: 관리종목" in html
    csv = pd.read_csv(next((tmp_path / "out").glob("scan_*.csv")), dtype={"종목코드": str})
    assert list(csv["종목코드"]) == ["000001"] and "EPS(E)성장%" in csv.columns
