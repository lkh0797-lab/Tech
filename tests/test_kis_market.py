"""KIS 일일 데이터 허브 (chart_screener.data.kis_market) — 네트워크 없이 가짜 클라이언트로 검증.

응답 모양은 2026-10 실전 응답(005930·000660·101000 등)을 줄여 옮긴 것이다. 비밀값·설정 파일은 쓰지 않는다.
"""
import json
import threading
from datetime import date, datetime

import pandas as pd
import pytest

from chart_screener.broker.kis import KST, PATH_DAILY, PATH_PRICE, KISAuthError, KISError
from chart_screener.data import kis_market as km
from chart_screener.data.investor import COLUMNS

DAY = date(2026, 10, 8)   # 2026-10-09(한글날) 휴장 전 마지막 개장일


def price_out(stat="55", **kw):
    out = {"iscd_stat_cls_code": stat, "mang_issu_cls_code": "N", "mrkt_warn_cls_code": "00", "temp_stop_yn": "N",
           "sltr_yn": "N", "short_over_yn": "N", "invt_caful_yn": "N", "marg_rate": "40.00", "crdt_able_yn": "Y",
           "hts_avls": "15375713", "per": "40.07", "pbr": "4.11", "eps": "6564.00", "bps": "63997.00",
           "hts_frgn_ehrt": "46.35", "whol_loan_rmnd_rate": "0.36", "bstp_kor_isnm": "전기·전자",
           "stck_prpr": "263000", "acml_tr_pbmn": "5617134619618", "hts_kor_isnm": None,
           "frgn_hldn_qty": "3000", "lstn_stcn": "10000"}     # 외국인 보유율 30% (소진율 46.35% 와 다름 — 한도 있는 종목)
    out.update(kw)
    return out


PRICES = {
    "005930": price_out(),
    "101000": price_out("51", mang_issu_cls_code="Y", marg_rate="100.00", crdt_able_yn="N", hts_avls="141",
                        stck_prpr="1427", bstp_kor_isnm="기계·장비"),
    "031860": price_out("58", acml_tr_pbmn="0", stck_prpr="512"),
    "027040": price_out("57", marg_rate="100.00"),
    "222222": price_out("55", mrkt_warn_cls_code="03"),
}

ESTIMATE_005930 = {
    "output1": {"sht_cd": "A005930", "estdate": "20260730"},
    "output4": [{"dt": "2023.12"}, {"dt": "2024.12"}, {"dt": "2025.12"}, {"dt": "2026.12E"}, {"dt": "2027.12E"}],
    "output2": [
        {"data1": "2589355.0", "data2": "3008709.0", "data3": "3336059.0", "data4": "7109715.0", "data5": "9666551.0"},
        {"data1": "-143.0", "data2": "162.0", "data3": "109.0", "data4": "1131.0", "data5": "360.0"},
        {"data1": "65670.0", "data2": "327260.0", "data3": "436011.0", "data4": "3730180.0", "data5": "5885206.0"},
        {"data1": "-849.0", "data2": "3983.0", "data3": "332.0", "data4": "7555.0", "data5": "578.0"},
        {"data1": "144734.0", "data2": "336214.0", "data3": "442610.0", "data4": "3061247.0", "data5": "4470057.0"},
        {"data1": "-736.0", "data2": "1323.0", "data3": "316.0", "data4": "5916.0", "data5": "460.0"},
    ],
    "output3": [
        {"data1": "452335.0", "data2": "753568.0", "data3": "905276.0", "data4": "4269289.0", "data5": "6449280.0"},
        {"data1": "21310.0", "data2": "49500.0", "data3": "66050.0", "data4": "462090.0", "data5": "672398.0"},
        {"data1": "-736.0", "data2": "1323.0", "data3": "334.0", "data4": "5996.0", "data5": "455.0"},
        {"data1": "368.0", "data2": "107.0", "data3": "182.0", "data4": "45.0", "data5": "31.0"},
        {"data1": "100.0", "data2": "36.0", "data3": "76.0", "data4": "27.0", "data5": "16.0"},
        {"data1": "41.0", "data2": "90.0", "data3": "108.0", "data4": "596.0", "data5": "546.0"},
        {"data1": "254.0", "data2": "279.0", "data3": "299.0", "data4": "285.0", "data5": "190.0"},
        {"data1": "71.0", "data2": "362.0", "data3": "720.0", "data4": "6076.0", "data5": "12324.0"},
    ],
}
ESTIMATE_NONE = {"output1": {"sht_cd": "", "estdate": ""}, "output4": [], "output2": [], "output3": []}


def investor_rows(n=30, today_blank=False):
    rows = []
    for i, d in enumerate(pd.bdate_range(end="2026-10-08", periods=n)[::-1]):   # 최신순
        rows.append({"stck_bsop_date": f"{d:%Y%m%d}", "stck_clpr": "263000", "prsn_ntby_qty": "1000",
                     "frgn_ntby_qty": "-500", "orgn_ntby_qty": "200", "prsn_ntby_tr_pbmn": "300",
                     "frgn_ntby_tr_pbmn": "-26614" if i == 0 else "-100", "orgn_ntby_tr_pbmn": "200"})
    if today_blank:
        rows.insert(0, {"stck_bsop_date": "20261009", "stck_clpr": "263000", "prsn_ntby_qty": "",
                        "frgn_ntby_qty": "", "orgn_ntby_qty": "", "prsn_ntby_tr_pbmn": "",
                        "frgn_ntby_tr_pbmn": "", "orgn_ntby_tr_pbmn": ""})
    return rows


def opinion_rows():
    """최신순. 유안타: 500k → 630k (상향, 30일 안), 키움: 400k → 350k (하향, 30일 안), 삼성: 창 밖 이전 → 상향은 60일 전."""
    return [
        {"stck_bsop_date": "20260923", "invt_opnn": "BUY", "rgbf_invt_opnn": "BUY", "mbcr_name": "유안타",
         "hts_goal_prc": "630000", "stck_prdy_clpr": "276500"},
        {"stck_bsop_date": "20260920", "invt_opnn": "BUY", "rgbf_invt_opnn": "BUY", "mbcr_name": "키움",
         "hts_goal_prc": "350000", "stck_prdy_clpr": "270000"},
        {"stck_bsop_date": "20260910", "invt_opnn": "매수", "rgbf_invt_opnn": "매수", "mbcr_name": "미래에셋",
         "hts_goal_prc": "400000", "stck_prdy_clpr": "255500"},
        {"stck_bsop_date": "20260810", "invt_opnn": "BUY", "rgbf_invt_opnn": "BUY", "mbcr_name": "키움",
         "hts_goal_prc": "400000", "stck_prdy_clpr": "231000"},
        {"stck_bsop_date": "20260805", "invt_opnn": "BUY", "rgbf_invt_opnn": "BUY", "mbcr_name": "삼성",
         "hts_goal_prc": "380000", "stck_prdy_clpr": "220000"},
        {"stck_bsop_date": "20260601", "invt_opnn": "BUY", "rgbf_invt_opnn": "HOLD", "mbcr_name": "유안타",
         "hts_goal_prc": "500000", "stck_prdy_clpr": "180000"},
        {"stck_bsop_date": "20260501", "invt_opnn": "BUY", "rgbf_invt_opnn": "BUY", "mbcr_name": "삼성",
         "hts_goal_prc": "300000", "stck_prdy_clpr": "170000"},
    ]


def daily_rows(start, end):
    days = pd.bdate_range(start=pd.Timestamp(start), end=pd.Timestamp(end))[::-1][:100]
    return [{"stck_bsop_date": f"{d:%Y%m%d}", "stck_clpr": "1000", "acml_vol": "10",
             "acml_tr_pbmn": str(1_000_000 + int(f"{d:%m%d}")), "mod_yn": "N"} for d in days]


class FakeClient:
    """KISRestClient 대역: get(path, tr_id, params) 와 open_day(day) 만 흉내. 호출을 기록한다."""

    def __init__(self, fail=(), fatal_after=None, holidays=(date(2026, 10, 9),)):
        self.calls = []
        self.fail = set(fail)
        self.fatal_after = fatal_after
        self.holidays = set(holidays)
        self._lock = threading.Lock()

    def open_day(self, d):
        return d not in self.holidays and d.weekday() < 5

    def get(self, path, tr_id, params):
        code = params.get("FID_INPUT_ISCD") or params.get("SHT_CD")
        with self._lock:
            self.calls.append((path.rsplit("/", 1)[-1], code, dict(params)))
            n = len(self.calls)
        if self.fatal_after is not None and n > self.fatal_after:
            raise KISAuthError("유효하지 않은 AppKey 입니다", "EGW00103")
        if code in self.fail:
            raise KISError("KIS 응답: 조회할 자료가 없습니다 (HTTP 500)", "EMPTY")
        if path == PATH_PRICE:
            return {"rt_cd": "0", "output": PRICES.get(code, price_out())}
        if path == PATH_DAILY:
            return {"rt_cd": "0", "output2": daily_rows(params["FID_INPUT_DATE_1"], params["FID_INPUT_DATE_2"])}
        if path == km.PATH_INVESTOR:
            return {"rt_cd": "0", "output": investor_rows()}
        if path == km.PATH_OPINION:
            return {"rt_cd": "0", "output": opinion_rows() if code == "005930" else []}
        if path == km.PATH_ESTIMATE:
            return {"rt_cd": "0", **(ESTIMATE_005930 if code == "005930" else ESTIMATE_NONE)}
        raise AssertionError(path)

    def count(self, name):
        return sum(1 for c in self.calls if c[0] == name)


@pytest.fixture
def cache(tmp_path):
    return km.KISDayCache(tmp_path / "kis")


# ---------------------------------------------------------------- 상태
def test_status_parse_and_tags():
    s = km.parse_status(PRICES["005930"])
    assert s.stat == "55" and not s.mang and not s.halt and s.credit
    assert s.cap_eok == 15375713 and s.marg == 40 and s.per == pytest.approx(40.07)
    assert s.frgn == pytest.approx(46.35) and s.loan == pytest.approx(0.36) and s.sector == "전기·전자"
    assert s.hold == pytest.approx(30.0)                    # 보유율 = 보유 ÷ 상장주식 (소진율 아님)
    assert km.status_tags(s) == [] and km.status_exclude(s) is None

    mang = km.parse_status(PRICES["101000"])
    assert mang.mang and not mang.credit and mang.cap_eok == 141
    assert km.status_tags(mang) == ["관리종목"] and km.status_exclude(mang) == "관리종목"

    halt = km.parse_status(PRICES["031860"])
    assert halt.halt and km.status_tags(halt) == ["거래정지"] and km.status_exclude(halt) == "거래정지"

    m100 = km.parse_status(PRICES["027040"])
    assert km.status_tags(m100) == [] and km.status_exclude(m100) is None and m100.marg == 100.0   # 흔해서 태그로 안 낸다

    risk = km.parse_status(PRICES["222222"])
    assert km.status_tags(risk) == ["투자위험"] and km.status_exclude(risk) == "투자위험"
    warn = km.parse_status(price_out("53"))
    assert km.status_tags(warn) == ["투자경고"] and km.status_exclude(warn) is None
    hot = km.parse_status(price_out("59", short_over_yn="Y"))
    assert km.status_tags(hot) == ["단기과열"]
    sltr = km.parse_status(price_out(sltr_yn="Y"))
    assert km.status_exclude(sltr) == "정리매매"


def test_status_empty_raises():
    with pytest.raises(KISError):
        km.parse_status({})


def test_fetch_status_cache_reuse_and_errors(cache, monkeypatch):
    monkeypatch.setattr(km, "_now", lambda: datetime(2026, 10, 8, 20, 0, tzinfo=KST))   # 자정을 걸치지 않게 시계 고정
    fc = FakeClient(fail={"999999"})
    errs = {}
    codes = ["005930", "101000", "031860", "027040", "999999"]
    got = km.fetch_status(fc, codes, cache, day=DAY, workers=4, errors=errs)
    assert set(got) == set(codes) - {"999999"} and "999999" in errs and "자료가 없습니다" in errs["999999"]
    assert cache.path("status", DAY).exists()
    n = fc.count("inquire-price")
    again = km.fetch_status(fc, codes[:4], cache, day=DAY)
    assert fc.count("inquire-price") == n                       # 전부 캐시
    assert again["101000"] == got["101000"] and again["101000"].mang
    km.fetch_status(fc, codes[:2], cache, day=DAY, refresh=True)
    assert fc.count("inquire-price") == n + 2


# ---------------------------------------------------------------- 거래대금
def test_turnover_merge_and_skip(cache):
    fc = FakeClient()
    cache.save_turnover("005930", {"20250101": 123.0, "20261001": 5.0})     # 오래된 날짜는 보존돼야 한다
    out = km.fetch_turnover(fc, ["005930", "000660"], cache, days=100, day=DAY)
    s = out["005930"]
    assert s["20250101"] == 123.0 and s["20261008"] == 1_001_008 and s["20261001"] == 1_001_001
    assert "20261009" not in s
    # 캐시가 있는 종목은 마지막 저장일부터만 요청
    p = [c[2] for c in fc.calls if c[1] == "005930"][0]
    assert p["FID_INPUT_DATE_1"] == "20261001" and p["FID_INPUT_DATE_2"] == "20261008"
    assert len(out["000660"]) == 100
    disk = json.loads(cache.turnover_path("000660").read_text(encoding="utf-8"))
    assert list(disk) == sorted(disk)
    n = len(fc.calls)
    km.fetch_turnover(fc, ["005930", "000660"], cache, day=DAY)
    assert len(fc.calls) == n                                   # 기준일이 이미 있으면 요청 안 함


def test_parse_turnover_drops_zero_and_future():
    rows = [{"stck_bsop_date": "20261009", "acml_tr_pbmn": "100"},
            {"stck_bsop_date": "20261008", "acml_tr_pbmn": "0"},
            {"stck_bsop_date": "20261007", "acml_tr_pbmn": "4471785088086"}]
    assert km.parse_turnover(rows, "20261008") == {"20261007": 4471785088086.0}


def test_apply_turnover():
    idx = pd.DatetimeIndex(pd.to_datetime(["2026-10-06", "2026-10-07", "2026-10-08"]), name="date")
    df = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 1.0, "close": 1.5, "volume": 10.0}, index=idx)
    df["value"] = (df["high"] + df["low"] + df["close"]) / 3 * df["volume"]
    df.attrs["halt_dates"] = []
    out = km.apply_turnover(df, {"20261007": 999.0, "20261008": 777.0, "20200101": 1.0})
    assert list(out["value"]) == [pytest.approx(15.0), 999.0, 777.0]
    assert list(out.columns) == list(df.columns) and df.loc["2026-10-07", "value"] == pytest.approx(15.0)
    assert out.attrs["value_real_n"] == 2 and out.attrs["value_real_from"] == "2026-10-07"
    assert out.attrs["halt_dates"] == []
    ser = pd.Series({pd.Timestamp("2026-10-06"): 5.0})
    assert km.apply_turnover(df, ser)["value"].iloc[0] == 5.0
    assert km.apply_turnover(df, {}) is df


# ---------------------------------------------------------------- 수급
def test_flows_parse_sums_and_units():
    fl = km.parse_flows(investor_rows(30, today_blank=True))
    assert len(fl.dates) == 30 and fl.dates == sorted(fl.dates) and fl.dates[-1] == "20261008"
    assert fl.frgn[-1] == pytest.approx(-266.14)                  # 백만원 → 억원
    assert fl.f5 == pytest.approx(-266.14 - 4.0) and fl.f20 == pytest.approx(-266.14 - 19.0)
    assert fl.o20 == pytest.approx(40.0) and fl.p5 == pytest.approx(15.0)
    df = km.flows_frame(fl, foreign_ratio=46.35)
    assert list(df.columns) == COLUMNS and df.index.is_monotonic_increasing and df.index.name == "date"
    assert df["inst_net"].iloc[-1] == 200 and df["foreign_net"].iloc[-1] == -500 and df["indiv_net"].iloc[-1] == 1000
    assert df["close"].iloc[-1] == 263000 and df["foreign_ratio"].iloc[-1] == pytest.approx(46.35)
    assert km.parse_flows([]).dates == []


def test_flows_adapter_feeds_scanner_summary():
    from types import SimpleNamespace

    from chart_screener.scanner import investor_summary
    ctx = SimpleNamespace(info={})
    km.attach_flows(ctx, km.parse_flows(investor_rows(30)), 46.35)
    inv = investor_summary(SimpleNamespace(ctx=ctx, close=263000.0))
    assert inv["days"] == 20 and inv["inst"] == pytest.approx(20 * 200 * 263000)
    assert inv["foreign"] == pytest.approx(20 * -500 * 263000) and inv["foreign_ratio"] == pytest.approx(46.35)
    assert km.attach_flows(SimpleNamespace(info={}), km.Flows()) is None


def test_flows_cache_reused_only_after_final(cache):
    fc = FakeClient()
    km.fetch_flows(fc, ["005930"], cache, day=DAY)
    assert fc.count("inquire-investor") == 1
    data = cache.load("flows", DAY)
    data["005930"]["_at"] = datetime(2026, 10, 8, 16, 0, tzinfo=KST).isoformat()   # 확정 전에 받은 캐시
    cache._write(cache.path("flows", DAY), data)
    km.fetch_flows(fc, ["005930"], cache, day=DAY)
    assert fc.count("inquire-investor") == 2
    got = km.fetch_flows(fc, ["005930"], cache, day=DAY)          # 방금(18:10 이후) 받은 캐시 → 재사용
    assert fc.count("inquire-investor") == 2 and got["005930"].f20 == pytest.approx(-285.14)


# ---------------------------------------------------------------- 투자의견
def test_opinion_raise_detection():
    op = km.parse_opinions(opinion_rows(), DAY, price=263000.0)
    assert op.n30 == 3                       # 09-23 유안타 · 09-20 키움 · 09-10 미래에셋 (기준 09-08 초과)
    assert op.up30 == 1 and op.down30 == 1   # 유안타 500k→630k 상향, 키움 400k→350k 하향
    assert op.rows[0] == ("20260923", "유안타", "BUY", "BUY", 630000.0)
    # 90일(07-10 이후) 증권사별 최신 목표가: 유안타 630k, 키움 350k, 미래에셋 400k, 삼성 380k
    assert op.avg_target_90d == pytest.approx((630000 + 350000 + 400000 + 380000) / 4)
    assert op.gap_pct == pytest.approx(((630000 + 350000 + 400000 + 380000) / 4 / 263000 - 1) * 100, abs=0.01)
    none = km.parse_opinions([], DAY)
    assert none.n30 == 0 and none.avg_target_90d is None and none.gap_pct is None


def test_fetch_opinions_params_and_cache(cache):
    fc = FakeClient()
    got = km.fetch_opinions(fc, ["005930", "101000"], cache, days=180, day=DAY, prices={"005930": 263000.0})
    p = [c[2] for c in fc.calls if c[1] == "005930"][0]
    assert p["FID_INPUT_DATE_1"] == "0020260411" and p["FID_INPUT_DATE_2"] == "0020261008"
    assert p["FID_COND_SCR_DIV_CODE"] == "16633"
    assert got["005930"].up30 == 1 and got["101000"].n30 == 0
    again = km.fetch_opinions(fc, ["005930"], cache, day=DAY)
    assert fc.count("invest-opinion") == 2 and again["005930"].rows[0] == got["005930"].rows[0]


# ---------------------------------------------------------------- 추정실적
def test_estimate_scaling():
    e = km.parse_estimate(ESTIMATE_005930)
    assert e.years[-2:] == ["2026.12E", "2027.12E"] and e.estdate == "20260730"
    assert e.rev[1] == 3008709 and e.rev_g[1] == pytest.approx(16.2) and e.op[1] == 327260
    assert e.eps[1] == pytest.approx(4950) and e.eps[3] == pytest.approx(46209)
    assert e.eps_g[1] == pytest.approx(132.3) and e.per[1] == pytest.approx(10.7)
    assert e.roe[1] == pytest.approx(9.0) and e.debt[1] == pytest.approx(27.9) and e.ev_ebitda[1] == pytest.approx(3.6)
    assert e.fwd_years == ["2026.12E", "2027.12E"]
    assert e.fwd_eps_g == pytest.approx((67239.8 / 46209 - 1) * 100, abs=0.01)
    assert km.parse_estimate(ESTIMATE_NONE) is None


def test_estimate_short_rows_and_single_e():
    js = json.loads(json.dumps(ESTIMATE_005930))
    js["output4"] = js["output4"][:4]
    js["output3"] = js["output3"][:3]                 # 000660 처럼 output3 가 3행뿐인 경우
    e = km.parse_estimate(js)
    assert e.per == [None] * 4 and e.eps[3] == pytest.approx(46209)
    assert e.fwd_years == ["2025.12", "2026.12E"] and e.fwd_eps_g == pytest.approx((46209 / 6605 - 1) * 100, abs=0.01)


def test_fetch_estimates_caches_no_coverage(cache):
    fc = FakeClient()
    got = km.fetch_estimates(fc, ["005930", "101000"], cache, day=DAY)
    assert set(got) == {"005930"}
    km.fetch_estimates(fc, ["005930", "101000"], cache, day=DAY)
    assert fc.count("estimate-perform") == 2


# ---------------------------------------------------------------- 개장일·기준일
def test_market_date_and_open_today():
    fc = FakeClient()
    assert km.market_date(fc, datetime(2026, 10, 9, 17, 0, tzinfo=KST)) == DAY        # 한글날 휴장
    assert km.market_date(fc, datetime(2026, 10, 8, 16, 0, tzinfo=KST)) == DAY
    assert km.market_date(fc, datetime(2026, 10, 8, 10, 0, tzinfo=KST)) == date(2026, 10, 7)
    assert km.market_date(fc, datetime(2026, 10, 12, 9, 0, tzinfo=KST)) == DAY        # 월요일 장 전
    # 클라이언트 없음(또는 KIS 가 모름) → KRX 달력: 10-09 한글날은 휴장이라 직전 개장일은 10-08
    assert km.market_date(None, datetime(2026, 10, 11, 12, 0, tzinfo=KST)) == date(2026, 10, 8)
    assert km.is_open_today(fc, datetime(2026, 10, 9, 9, 0, tzinfo=KST)) is False
    assert km.is_open_today(fc, datetime(2026, 10, 8, 9, 0, tzinfo=KST)) is True


# ---------------------------------------------------------------- 클라이언트 생성
def test_client_or_none_missing_config(tmp_path):
    cfg = km.KISMarketConfig(config_path=str(tmp_path / "nope.yaml"))
    client, why = km.client_or_none(cfg)
    assert client is None and "설정 없음" in why


def test_client_or_none_token_failure():
    class Cfg:
        def diagnose(self):
            return []

    class BadTokens:
        def get(self):
            raise KISAuthError("유효하지 않은 AppSecret 입니다", "EGW00105")

    client, why = km.client_or_none(km.KISMarketConfig(), load=lambda p, env: Cfg(), tokens=lambda c: BadTokens())
    assert client is None and why.startswith("접근토큰 발급 실패") and "AppSecret" in why


# ---------------------------------------------------------------- 일괄 갱신·스냅샷
def test_refresh_end_to_end_and_snapshot(tmp_path):
    fc = FakeClient(fail={"999999"})
    cfg = km.KISMarketConfig(cache_dir=tmp_path / "kis", snapshot_path=tmp_path / "snap.json", workers=4)
    seen = []
    res = km.refresh(["005930", "101000", "031860", "999999"], ["005930", "101000"], client=fc, cfg=cfg, day=DAY,
                     progress=lambda step, i, n: seen.append(step))
    assert res.ok and res.day == DAY
    assert [s["step"] for s in res.steps] == ["status", "turnover", "flows", "opinion", "estimate"]
    st = res.steps[0]
    assert st["n"] == 4 and st["ok"] == 3 and st["fail"] == 1 and "999999" in res.errors["status"]
    assert "031860" not in res.turnover and fc.count("inquire-daily-itemchartprice") == 3   # 거래정지 제외
    assert res.opinions["005930"].price == 263000 and set(res.estimates) == {"005930"}
    assert {"status", "turnover", "flows", "opinion", "estimate"} <= set(seen)
    js = json.loads((tmp_path / "snap.json").read_text(encoding="utf-8"))
    assert js["v"] == 1 and js["date"] == "20261008" and set(js) >= {"at", "env", "status", "flows", "opinion",
                                                                       "estimate"}
    assert js["status"]["101000"]["tags"] == ["관리종목"] and js["status"]["101000"]["ex"] == "관리종목"
    assert js["status"]["031860"]["ex"] == "거래정지" and js["status"]["005930"]["cap"] == 15375713
    assert js["flows"]["005930"]["f20"] == pytest.approx(-285.14)
    assert js["opinion"]["005930"]["up30"] == 1 and js["opinion"]["005930"]["down30"] == 1
    assert js["estimate"]["005930"]["years"] == ["2026.12E", "2027.12E"]
    assert js["estimate"]["005930"]["eps_e"] == pytest.approx(67240)
    assert "NaN" not in (tmp_path / "snap.json").read_text(encoding="utf-8")
    assert "중단" not in res.summary() and "상태: 3/4" in res.summary()


def test_refresh_stops_on_fatal_auth(tmp_path):
    fc = FakeClient(fatal_after=3)
    cfg = km.KISMarketConfig(cache_dir=tmp_path / "kis", snapshot_path=tmp_path / "snap.json", workers=1)
    codes = [f"{i:06d}" for i in range(10)]
    res = km.refresh(codes, codes[:2], client=fc, cfg=cfg, day=DAY)
    assert not res.ok and "AppKey" in res.fatal and "status" in res.fatal
    assert len(fc.calls) <= 5 and not (tmp_path / "snap.json").exists()
    assert [s["step"] for s in res.steps] == ["status"]
    saved = json.loads(km.KISDayCache(tmp_path / "kis").path("status", DAY).read_text(encoding="utf-8"))
    assert len(saved) == 3                                        # 멈추기 전 받은 것은 저장


def test_refresh_without_config_returns_reason(tmp_path):
    cfg = km.KISMarketConfig(config_path=str(tmp_path / "nope.yaml"), cache_dir=tmp_path / "kis",
                             snapshot_path=tmp_path / "snap.json")
    res = km.refresh(["005930"], [], cfg=cfg)
    assert not res.ok and "설정 없음" in res.fatal and res.steps == []


def test_cache_prune(tmp_path):
    c = km.KISDayCache(tmp_path, keep_days=2)
    for d in (1, 2, 5):
        c.save("status", date(2026, 10, d), {"005930": {"stat": "55"}})
    assert sorted(p.name for p in tmp_path.glob("status_*.json")) == ["status_20261002.json", "status_20261005.json"]
