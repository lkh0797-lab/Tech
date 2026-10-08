"""실시간 감시 (chart_screener.live) — 감시 목록 선정·알림 규칙·하루 1회 기록·대시보드·출처 선택. 네트워크 없음."""
import asyncio
import base64
import json
from datetime import date, datetime

import numpy as np
import pandas as pd
import pytest

from chart_screener import live, scoring
from chart_screener.broker.kis import KST, KISAuthError, KISError, Quote, Tick
from chart_screener.live import (
    BREAKOUT_HIT, NEAR, PULLBACK, STOP, AlertStore, Dashboard, LiveStatus, Notifier, TriggerEngine, WatchItem,
    avg_volume, parse_naver_polling, projected_volume, render_dashboard, select_watchlist, session_phase,
    toast_command, volume_ratio, write_atomic,
)
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult
from chart_screener.scanner import ScanResult, StockScan, position_plan
from synthetic import add_value, make_context

TODAY = date(2026, 10, 8)
APP_KEY = "PSFAKE" + "k" * 30
APP_SECRET = "FAKESECRET" + "s" * 170


def at(h, m, s=0):
    return datetime(2026, 10, 8, h, m, s, tzinfo=KST)


# ---------------------------------------------------------------- 합성 스캔 결과
def _df(prev_close, today_close=None, n=80, vol=1000.0, today_vol=None):
    """마지막 봉 = 오늘(2026-10-08, 장중) 이면 today_close 를 준다."""
    idx = pd.bdate_range(end="2026-10-08" if today_close is not None else "2026-10-07", periods=n)
    c = np.full(n, float(prev_close))
    df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": vol}, index=idx)
    if today_close is not None:
        df.iloc[-1, df.columns.get_loc("close")] = today_close
        df.iloc[-1, df.columns.get_loc("volume")] = today_vol or vol
    return add_value(df)


def _pr(name, stage, pivot, stop, score=80.0, **kw):
    return PatternResult(name=name, label=kw.pop("label", name), detected=True, score=score, stage=stage,
                         pivot=pivot, stop=stop, start_date="2026-06-01", end_date="2026-10-07", **kw)


def _stock(code, name, results, close, df=None):
    sb = scoring.compute(results, 90.0, close=close)
    s = StockScan(code=code, name=name, market="KOSPI", close=close, change_pct=0.0, market_cap=1e12, rs=90.0,
                  value_today=50e8, avg_value_20=50e8, max_value_5=50e8, partial=False, results=results, score=sb)
    s.ctx = make_context(df if df is not None else _df(close), code=code, name=name)
    s.position = position_plan(s)
    return s


def _scan(stocks):
    return ScanResult(asof=pd.Timestamp("2026-10-07"), generated_at=pd.Timestamp("2026-10-07 16:00"), market={},
                      stocks=sorted(stocks, key=lambda s: -s.score.composite), scanned=len(stocks), elapsed=0.0,
                      patterns=[])


@pytest.fixture
def scan():
    bvp = _pr("big_value_pullback", NEAR_PIVOT, 50000, 48500, score=70,
              metrics={"support": 50000, "buy_zone_top": 51500, "candle_date": "2026-10-01"})
    lb_watch = _pr("long_base_breakout", FORMING, 12000, 11040, score=55, metrics={"pre_breakout": True})
    stocks = [
        _stock("000010", "돌파주", {"vcp": _pr("vcp", BREAKOUT, 100, 93, breakout_date="2026-10-07")}, 102,
               df=_df(102, today_close=103, today_vol=99999)),
        _stock("000020", "근접주", {"cup_handle": _pr("cup_handle", NEAR_PIVOT, 200, 184)}, 196),
        _stock("000030", "눌림주", {"big_value_pullback": bvp}, 52000),
        _stock("000040", "관찰주", {"long_base_breakout": lb_watch}, 11500),
        _stock("000050", "형성주", {"flat_base": _pr("flat_base", FORMING, 300, 276, score=60)}, 280),
        _stock("000060", "실패주", {"vcp": _pr("vcp", FAILED, 100, 93, breakout_date="2026-10-01")}, 95),
        _stock("000070", "이격주", {"vcp": _pr("vcp", EXTENDED, 100, 93, breakout_date="2026-10-01")}, 112),
        _stock("000080", "이탈주", {"vcp": _pr("vcp", BREAKOUT, 100, 93, breakout_date="2026-10-06")}, 92),
        # 대표는 이격 과다 컵(점수 높음), 장기횡보 돌파 전 관찰이 따로 있음 → 관찰 결과로 감시
        _stock("000090", "보조관찰", {"cup_handle": _pr("cup_handle", EXTENDED, 80, 74, score=95,
                                                        breakout_date="2026-10-01"),
                                  "long_base_breakout": _pr("long_base_breakout", FORMING, 90, 82.8, score=10,
                                                            metrics={"pre_breakout": True})}, 88),
    ]
    return _scan(stocks)


# ---------------------------------------------------------------- 감시 목록
def test_select_watchlist_picks_actionable_and_orders_by_priority(scan):
    items = select_watchlist(scan, 40, today=TODAY)
    by = {it.code: it for it in items}
    assert set(by) == {"000010", "000020", "000030", "000040", "000050", "000090"}   # 실패·이격·손절 이탈 제외
    assert by["000010"].reason == "돌파" and by["000020"].reason == "피벗 근접"
    assert by["000030"].reason == "눌림 구간" and by["000040"].reason == "돌파 전 관찰"
    assert by["000050"].reason == "돌파 매수 대기" and by["000050"].plan.startswith("피벗 300 돌파 매수")
    assert by["000090"].reason == "돌파 전 관찰" and by["000090"].pattern == "long_base_breakout"
    assert by["000090"].pivot == 90
    pri = [live._PRIORITY[it.reason] for it in items]
    assert pri == sorted(pri)
    assert items[-1].code == "000050"
    # 눌림목: 50%선·매수 구간 상단 (scoring.pullback_limit / pullback_zone_top 와 같은 값)
    pb = by["000030"]
    assert pb.is_pullback and pb.support == 50000 and pb.zone_top == 51500 and pb.stop == 48500
    assert not by["000010"].is_pullback


def test_watchlist_volume_and_ref_close_exclude_today(scan):
    by = {it.code: it for it in select_watchlist(scan, 40, today=TODAY)}
    it = by["000010"]
    assert it.avg_vol_50 == pytest.approx(1000.0)      # 오늘 99,999주 봉 제외
    assert it.ref_close == pytest.approx(102.0)        # 오늘 장중 103 이 아니라 전일 종가
    assert by["000020"].ref_close == pytest.approx(196.0)


def test_watchlist_top_cap_and_requested_codes(scan):
    items = select_watchlist(scan, 3, today=TODAY, codes=["000050", "000070"])
    assert [it.code for it in items][:2] == ["000070", "000050"] or [it.code for it in items][:2] == ["000050", "000070"]
    by = {it.code: it for it in items}
    assert by["000050"].reason == "돌파 매수 대기"          # 조건에 맞으면 원래 사유 유지
    assert by["000070"].reason == "지정 종목"               # 이격 과다라 원래는 빠지지만 지정했으므로 포함
    assert len(items) == 3
    assert select_watchlist(scan, 0, today=TODAY) == []


def test_avg_volume_needs_history():
    df = _df(100, n=5)
    assert avg_volume(df, TODAY) is None
    assert avg_volume(None, TODAY) is None


# ---------------------------------------------------------------- 거래량 환산
def test_projected_volume_uses_session_profile():
    assert projected_volume(320, at(10, 0)) == pytest.approx(1000)      # 60분 = 32%
    assert projected_volume(1000, at(15, 30)) == pytest.approx(1000)
    assert projected_volume(10, at(9, 2)) is None                        # 장 시작 직후
    assert projected_volume(0, at(11, 0)) is None
    assert volume_ratio(576_000, 1_000_000, at(10, 0)) == pytest.approx(1.8)
    assert volume_ratio(576_000, None, at(10, 0)) is None


# ---------------------------------------------------------------- 알림 규칙
def item(**kw):
    base = dict(code="003490", name="대한항공", market="KOSPI", pattern="vcp", label="VCP", stage=NEAR_PIVOT,
                pivot=30900.0, stop=28700.0, reason="피벗 근접", composite=80.0, ref_close=30500.0,
                avg_vol_50=1_000_000.0)
    base.update(kw)
    return WatchItem(**base)


def tick(code, price, when, vol=float("nan"), pct=0.5, source="kis"):
    """vol: 누적 거래량 (기본 = 모름). 0 이면 '아직 체결 없음'이라 알림 판단에서 빠진다."""
    return Tick(code=code, time=when, price=price, change_pct=pct, cum_volume=vol, cum_value=0.0, high=price,
                low=price, open=price, source=source)


def test_near_then_breakout_with_volume_projection_fire_once(tmp_path):
    store = AlertStore(tmp_path, TODAY)
    eng = TriggerEngine([item()], store, near_pct=0.01, vol_mult=1.4)
    a1 = eng.on_tick(tick("003490", 30700, at(10, 0), vol=400_000))
    assert [a.kind for a in a1] == [NEAR]
    assert "[근접] 대한항공 30,700" in a1[0].text and "잠정" in a1[0].text
    a2 = eng.on_tick(tick("003490", 30950, at(10, 0, 5), vol=576_000))
    assert [a.kind for a in a2] == [BREAKOUT_HIT]
    t = a2[0].text
    assert t.startswith("[돌파] 대한항공 30,950 (피벗 30,900) · 거래량 1.8배 예상 ✓")
    assert "잠정" in t and "종가" in t
    assert a2[0].title == "[돌파] 대한항공" and a2[0].body.startswith("30,950 (피벗 30,900)")
    assert eng.on_tick(tick("003490", 31000, at(10, 1), vol=600_000)) == []
    assert eng.on_tick(tick("003490", 30800, at(10, 2))) == []           # 근접 재알림 없음
    assert eng.on_tick(tick("003490", 31100, at(10, 3))) == []           # 재돌파도 하루 1회
    st = eng.state["003490"]
    assert st.price == 31100 and st.last_alert.startswith("[돌파]")
    # 재실행: 같은 날 기록을 읽어 반복하지 않는다
    store2 = AlertStore(tmp_path, TODAY)
    eng2 = TriggerEngine([item()], store2)
    assert eng2.state["003490"].last_alert.startswith("[돌파]")
    assert eng2.on_tick(tick("003490", 30700, at(11, 0))) == []
    assert eng2.on_tick(tick("003490", 30950, at(11, 1))) == []
    rows = pd.read_csv(store.path, dtype={"code": str}, encoding="utf-8-sig")
    assert rows["code"].tolist() == ["003490", "003490"] and rows["kind"].tolist() == [NEAR, BREAKOUT_HIT]
    assert store.path.name == "live_alerts_20261008.csv"


def test_breakout_with_weak_volume_and_unknown_volume(tmp_path):
    eng = TriggerEngine([item(), item(code="000002", name="무거래량", avg_vol_50=None)], AlertStore(tmp_path, TODAY),
                        vol_mult=1.4)
    weak = eng.on_tick(tick("003490", 31000, at(13, 0), vol=500_000))[0].text   # 13:00 = 0.65 → 0.77배
    assert "거래량 부족(장중 추정) ✘ 0.8배" in weak and "✓" not in weak
    unk = eng.on_tick(tick("000002", 31000, at(13, 0), vol=500_000))[0].text
    assert "거래량 추정 불가" in unk
    early = TriggerEngine([item(code="000003")], AlertStore(tmp_path / "x", TODAY))
    txt = early.on_tick(tick("000003", 31000, at(9, 10), vol=200_000))[0].text
    assert "장 초반 추정" in txt


def test_already_above_pivot_needs_dip_before_breakout_alert(tmp_path):
    eng = TriggerEngine([item(ref_close=31500.0, stage=BREAKOUT, breakout_date="2026-10-07")],
                        AlertStore(tmp_path, TODAY))
    assert eng.on_tick(tick("003490", 31200, at(9, 30))) == []
    assert [a.kind for a in eng.on_tick(tick("003490", 30850, at(10, 0)))] == [NEAR]
    assert [a.kind for a in eng.on_tick(tick("003490", 31000, at(10, 5)))] == [BREAKOUT_HIT]


def test_pullback_zone_and_close_based_stop(tmp_path):
    pb = item(code="000030", name="눌림주", pattern="big_value_pullback", label="300억 눌림목", pivot=50000.0,
              stop=48500.0, support=50000.0, zone_top=51500.0, reason="눌림 구간", ref_close=52000.0)
    eng = TriggerEngine([pb], AlertStore(tmp_path, TODAY))
    assert eng.on_tick(tick("000030", 52000, at(9, 30))) == []
    a = eng.on_tick(tick("000030", 51000, at(10, 0)))
    assert [x.kind for x in a] == [PULLBACK]
    assert "50%선 매수 구간 50,000~51,500 진입" in a[0].text and "손절: 종가 48,500 이탈" in a[0].text
    assert "잠정" in a[0].text
    s = eng.on_tick(tick("000030", 48400, at(11, 0)))
    assert [x.kind for x in s] == [STOP] and "종가 기준" in s[0].text and "잠정" in s[0].text
    assert eng.on_tick(tick("000030", 51000, at(12, 0))) == []


def test_stop_before_entry_says_plan_on_hold(tmp_path):
    eng = TriggerEngine([item(stage=FORMING, reason="돌파 매수 대기")], AlertStore(tmp_path, TODAY))
    a = eng.on_tick(tick("003490", 28600, at(10, 0)))
    assert [x.kind for x in a] == [STOP] and "돌파 전 — 매수 계획 보류" in a[0].text


def test_stop_alert_needs_a_cross_from_above(tmp_path):
    eng = TriggerEngine([item(stage=FORMING, reason="돌파 매수 대기", ref_close=28000.0)], AlertStore(tmp_path, TODAY))
    assert eng.on_tick(tick("003490", 27900, at(9, 30))) == []          # 어제부터 손절가 아래
    assert eng.on_tick(tick("003490", 28800, at(10, 0))) == []          # 위로 올라옴
    assert [a.kind for a in eng.on_tick(tick("003490", 28650, at(10, 30)))] == [STOP]


def test_buy_stop_candidates_below_stop_are_not_watched():
    below = _stock("000100", "손절아래", {"flat_base": _pr("flat_base", FORMING, 300, 276, score=60)}, 250)
    above = _stock("000101", "손절위", {"flat_base": _pr("flat_base", FORMING, 300, 276, score=60)}, 280)
    assert below.position["plan"].startswith("피벗 300 돌파 매수")
    assert [it.code for it in select_watchlist(_scan([below, above]), 40, today=TODAY)] == ["000101"]


def test_ignores_unknown_codes_and_bad_prices(tmp_path):
    eng = TriggerEngine([item()], AlertStore(tmp_path, TODAY))
    assert eng.on_tick(tick("999999", 30950, at(10, 0))) == []
    assert eng.on_tick(tick("003490", float("nan"), at(10, 0))) == []
    assert eng.on_tick(tick("003490", 0, at(10, 0))) == []


def test_alert_store_rolls_over_by_day(tmp_path):
    """자정을 넘겨 실행(--after-hours): 다음 날짜 시세가 오면 기록을 새 날짜로 넘기고 그날 알림은 다시 1회씩."""
    store = AlertStore(tmp_path, TODAY)
    eng = TriggerEngine([item()], store)
    assert [a.kind for a in eng.on_tick(tick("003490", 30950, at(10, 0)))] == [BREAKOUT_HIT]
    nxt = datetime(2026, 10, 9, 10, 0, tzinfo=KST)
    assert [a.kind for a in eng.on_tick(tick("003490", 30800, nxt))] == [NEAR]
    assert store.day == date(2026, 10, 9) and store.path.name == "live_alerts_20261009.csv"
    assert not store.has("003490", BREAKOUT_HIT)
    # 앞 날짜로는 돌아가지 않는다: 늦게 온 전날 시세는 알림도, 기록 파일 변경도 없음
    assert eng.on_tick(tick("003490", 31500, at(15, 20))) == []
    store.roll(TODAY)
    assert store.day == date(2026, 10, 9)
    old = pd.read_csv(tmp_path / "live_alerts_20261008.csv", dtype={"code": str}, encoding="utf-8-sig")
    assert old["kind"].tolist() == [BREAKOUT_HIT]


# ---------------------------------------------------------------- 알림 출력
def test_toast_command_is_encoded_powershell_with_escaping():
    cmd = toast_command("[돌파] A&B's", "30,950 <피벗>")
    assert cmd[0] == "powershell" and "-EncodedCommand" in cmd
    script = base64.b64decode(cmd[-1]).decode("utf-16-le")
    assert "Windows.UI.Notifications" in script and "CreateToastNotifier" in script
    assert "[돌파] A&amp;B&#x27;s" in script or "[돌파] A&amp;B''s" in script
    assert "&lt;피벗&gt;" in script and "<피벗>" not in script


def test_notifier_survives_toast_failures():
    lines = []

    def broken(title, body):
        raise OSError("no powershell")

    n = Notifier(toast=True, out=lines.append, toast_fn=broken)
    al = live.Alert(code="003490", name="대한항공", kind=BREAKOUT_HIT, price=30950, at=at(10, 0),
                    text="[돌파] 대한항공 30,950 (피벗 30,900) · 잠정")
    n.notify(al)
    n.notify(al)
    assert lines[0] == "10:00:00 [돌파] 대한항공 30,950 (피벗 30,900) · 잠정" and n.toast is False
    assert live.show_toast("t", "b", popen=lambda *a, **k: (_ for _ in ()).throw(OSError())) is False
    sent = []
    ok = Notifier(toast=True, out=lambda s: None, toast_fn=lambda t, b: sent.append((t, b)) or True)
    ok.notify(al)
    assert sent == [("[돌파] 대한항공", "30,950 (피벗 30,900) · 잠정")]


# ---------------------------------------------------------------- 대시보드
def test_dashboard_render_escapes_and_has_theme_tokens(tmp_path):
    its = [item(), item(code="000666", name="<script>x</script>", pivot=1000.0, stop=900.0, ref_close=950.0),
           item(code="000030", name="눌림주", support=50000.0, zone_top=51500.0, pivot=50000.0, stop=48500.0)]
    eng = TriggerEngine(its, AlertStore(tmp_path, TODAY))
    eng.on_tick(tick("003490", 30950, at(10, 0), vol=576_000, pct=1.2))
    eng.on_tick(tick("000030", 51000, at(10, 0), pct=-0.8))
    st = LiveStatus(source="한국투자증권 실시간 체결 (KRX, 웹소켓)", message="시세 수신 중", ticks=2,
                    close_at=at(15, 31))
    page = render_dashboard(eng, st, now=at(10, 0, 3), refresh=5)
    assert page.startswith("<!doctype html>") and '<meta http-equiv="refresh" content="5">' in page
    assert "prefers-color-scheme: dark" in page and "--up:" in page and "--down:" in page
    assert "조회 전용" in page and "잠정" in page
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page
    for col in ("종목", "현재가", "등락률", "패턴/단계", "피벗까지 %", "손절가", "거래량 예상배수", "마지막 알림", "갱신 시각"):
        assert f"<th>{col}</th>" in page
    assert "30,950" in page and "+1.20%" in page and "1.8배 ✓" in page and "구간 안" in page
    assert "[돌파] 대한항공" in page and "10:00:00" in page
    assert APP_SECRET not in page
    # 알림 난 종목이 위로
    assert page.index("대한항공") < page.index("&lt;script&gt;")


def test_write_atomic_and_dashboard(tmp_path):
    p = tmp_path / "out" / "live.html"
    assert write_atomic(p, "hello")
    assert p.read_text(encoding="utf-8") == "hello" and not (tmp_path / "out" / "live.html.tmp").exists()
    eng = TriggerEngine([item()], AlertStore(tmp_path, TODAY))
    d = Dashboard(p, eng, LiveStatus(source="네이버"))
    assert d.write() and "대한항공" in p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 시세 출처
NAVER_JS = {"pollingInterval": 7000, "datas": [
    {"itemCode": "005930", "stockName": "삼성전자", "closePrice": "262,500", "closePriceRaw": "262500",
     "compareToPreviousClosePriceRaw": "-6000", "fluctuationsRatioRaw": "-2.23", "openPriceRaw": "269500",
     "highPriceRaw": "270000", "lowPriceRaw": "262000", "accumulatedTradingVolumeRaw": "19844947",
     "accumulatedTradingValueRaw": "5267869000000", "accumulatedTradingValue": "5조 2,679억",
     "localTradedAt": "2026-10-08T10:01:41.891877+09:00"},
    {"itemCode": "000660", "closePrice": "1,686,000", "fluctuationsRatio": "2.15", "localTradedAt": None},
    {"itemCode": "", "closePriceRaw": "1"},
]}


def test_parse_naver_polling():
    ticks = parse_naver_polling(NAVER_JS, now=at(10, 2))
    assert [t.code for t in ticks] == ["005930", "000660"]
    s = ticks[0]
    assert (s.price, s.change, s.change_pct, s.open, s.high, s.low) == (262500, -6000, -2.23, 269500, 270000, 262000)
    assert s.cum_volume == 19844947 and s.cum_value == 5267869000000 and s.source == "naver"
    assert (s.time.hour, s.time.minute, s.time.second) == (10, 1, 41) and s.time.utcoffset().total_seconds() == 32400
    assert ticks[1].price == 1686000 and ticks[1].change_pct == 2.15 and ticks[1].time == at(10, 2)


def test_naver_source_batches_and_falls_back_to_snapshot():
    urls = []

    def fetch(url):
        urls.append(url)
        return NAVER_JS

    async def nosleep(_):
        await asyncio.sleep(0)

    codes = [f"{i:06d}" for i in range(25)]
    src = live.NaverSource(codes, interval=10, fetch_json=fetch, sleep=nosleep, chunk=20)

    async def first(n):
        out = []
        async for t in src.stream():
            out.append(t)
            if len(out) >= n:
                break
        return out

    got = asyncio.run(first(4))
    assert len(got) == 4 and len(urls) == 2
    assert urls[0].endswith("/" + ",".join(codes[:20])) and urls[1].endswith("/" + ",".join(codes[20:]))

    status = []
    snap = [tick("005930", 100, at(10, 0), source="naver")]
    bad = live.NaverSource(["005930"], fetch_json=lambda u: (_ for _ in ()).throw(OSError("down")),
                           snapshot=lambda c: snap, sleep=nosleep, on_status=status.append)

    async def one():
        async for t in bad.stream():
            return t

    assert asyncio.run(one()).price == 100
    assert bad.mode == "snapshot" and any("전 종목 목록" in m for m in status)


def test_kis_source_falls_back_to_rest_when_websocket_fails():
    class FailingWS:
        async def ticks(self):
            raise KISError("웹소켓 연결이 5회 연속 실패했습니다", "WS")
            yield  # pragma: no cover

    class FakeRest:
        label = "한국투자증권 REST 현재가 (15초 간격)"

        async def stream(self, until=None):
            yield tick("005930", 70000, at(10, 0), source="kis-rest")

    status = []
    src = live.KISSource(cfg=None, codes=["005930"], on_status=status.append, ws_factory=FailingWS,
                         rest_factory=FakeRest)

    async def one():
        async for t in src.stream():
            return t

    t = asyncio.run(one())
    assert t.source == "kis-rest" and src.label.startswith("한국투자증권 REST")
    assert any("REST 현재가 조회로" in m for m in status)

    class BadSecretWS:
        async def ticks(self):
            raise KISAuthError("유효하지 않은 AppSecret", "EGW00105")
            yield  # pragma: no cover

    src2 = live.KISSource(cfg=None, codes=["005930"], ws_factory=BadSecretWS, rest_factory=FakeRest)
    with pytest.raises(KISAuthError):
        asyncio.run(_first(src2))


async def _first(src):
    async for t in src.stream():
        return t


def _write_cfg(tmp_path, app=APP_KEY, sec=APP_SECRET):
    p = tmp_path / "kis_devlp.yaml"
    p.write_text(f'my_app: "{app}"\nmy_sec: "{sec}"\nmy_acct_stock: "12345678"\nmy_prod: "01"\n'
                 'prod: "https://openapi.koreainvestment.com:9443"\nops: "ws://ops.koreainvestment.com:21000"\n',
                 encoding="utf-8")
    return p


def test_resolve_source_auto_falls_back_to_naver_with_reason(tmp_path):
    out = []
    kind, cfg, tm = live.resolve_source("auto", config_path=str(tmp_path / "none.yaml"), out=out.append)
    assert kind == "naver" and cfg is None and any("연결 안 함" in m and "설정 파일이 없습니다" in m for m in out)
    out.clear()
    p = _write_cfg(tmp_path, sec="앱키 시크릿")
    kind, _, _ = live.resolve_source("auto", config_path=str(p), out=out.append)
    assert kind == "naver" and any("예시 문구" in m for m in out)
    out.clear()
    assert live.resolve_source("kis", config_path=str(p), out=out.append) == (None, None, None)
    assert any("✘ 한국투자증권 연결 불가" in m for m in out)

    class BadToken:
        def __init__(self, cfg):
            pass

        def get(self):
            raise KISAuthError("유효하지 않은 AppSecret 입니다", "EGW00105")

    class GoodToken(BadToken):
        def get(self):
            return "tok"

    good = _write_cfg(tmp_path)
    out.clear()
    kind, _, _ = live.resolve_source("auto", config_path=str(good), out=out.append, token_factory=BadToken)
    assert kind == "naver" and any("접근토큰 발급 실패" in m for m in out)
    kind, cfg, tm = live.resolve_source("auto", config_path=str(good), out=out.append, token_factory=GoodToken)
    assert kind == "kis" and cfg.app_key == APP_KEY
    assert live.resolve_source("naver") == ("naver", None, None)
    assert all(APP_SECRET not in m for m in out)


class _Resp:
    def __init__(self, status, js):
        self.status_code, self._js = status, js

    def json(self):
        return self._js


class _Session:
    def __init__(self):
        self.headers = {}

    def post(self, url, data=None, headers=None, timeout=None):
        return _Resp(200, {"access_token": "TOKFAKE" + "x" * 40, "access_token_token_expired": "2099-01-01 00:00:00"})

    def get(self, url, headers=None, params=None, timeout=None):
        if "chk-holiday" in url:
            return _Resp(200, {"rt_cd": "0", "output": [{"bass_dt": "20261008", "opnd_yn": "Y"},
                                                        {"bass_dt": "20261009", "opnd_yn": "N"}]})
        return _Resp(200, {"rt_cd": "0", "output": {"stck_prpr": "70000", "prdy_ctrt": "0.5", "acml_vol": "100"}})


def test_check_connection_reports_without_secrets(tmp_path):
    out = []
    bad = _write_cfg(tmp_path, sec="앱키 시크릿")
    assert live.check_connection(str(bad), out=out.append, ws_probe=False) == 1
    assert any("my_sec 이 예시 문구 그대로입니다 (한글 포함, 6자)" in m for m in out)
    out.clear()
    good = _write_cfg(tmp_path)
    assert live.check_connection(str(good), out=out.append, session=_Session(), ws_probe=False, today=TODAY) == 0
    text = "\n".join(out)
    assert "✔ 설정 형식" in text and "✔ 접근토큰 (새로 발급" in text and "✔ 현재가 005930: 70,000원" in text
    assert "✔ 개장일 조회: 10-08 개장" in text
    assert APP_SECRET not in text and APP_KEY not in text and "TOKFAKE" not in text
    assert (tmp_path / "chart_screener_token.json").exists()     # 캐시는 설정 파일 옆
    assert (tmp_path / "chart_screener_holidays.json").exists()  # 개장일 캐시도


def test_probe_websocket_with_fake_connection(tmp_path):
    from test_broker_kis import FakeWS, ccnl_fields, frame
    cfg = live.KISConfig.load(_write_cfg(tmp_path))
    ok, msg = asyncio.run(live.probe_websocket(cfg, "005930", connect=lambda u: FakeWS([frame(ccnl_fields())]),
                                               approval=lambda: "APPROVALFAKE"))
    assert ok and "실시간 체결 수신 005930 70,000원" in msg
    sub = json.dumps({"header": {"tr_id": "H0STCNT0", "tr_key": "005930"},
                      "body": {"rt_cd": "0", "msg1": "SUBSCRIBE SUCCESS"}})

    class Idle(FakeWS):
        async def _gen(self):
            for f in self.frames:
                yield f
            await asyncio.sleep(10)

    ok, msg = asyncio.run(live.probe_websocket(cfg, "005930", timeout=0.2, connect=lambda u: Idle([sub]),
                                               approval=lambda: "APPROVALFAKE"))
    assert ok and "구독 성공" in msg


# ---------------------------------------------------------------- 실행 루프·세션
def test_session_phase():
    assert session_phase(at(8, 59)) == "pre"
    assert session_phase(at(9, 0)) == "open"
    assert session_phase(at(15, 29, 59)) == "open"
    assert session_phase(at(15, 30)) == "closed"
    assert session_phase(datetime(2026, 10, 10, 10, 0, tzinfo=KST)) == "weekend"


class ListSource:
    label = "가짜 시세"

    def __init__(self, ticks, forever=False):
        self.ticks, self.forever = ticks, forever

    async def stream(self):
        for t in self.ticks:
            await asyncio.sleep(0)
            yield t
        while self.forever:
            await asyncio.sleep(0.01)


def test_live_loop_processes_ticks_writes_dashboard_and_ends(tmp_path):
    lines = []
    eng = TriggerEngine([item()], AlertStore(tmp_path, TODAY))
    status = LiveStatus()
    dash = Dashboard(tmp_path / "live.html", eng, status)
    src = ListSource([tick("003490", 30700, at(10, 0)), tick("003490", 30950, at(10, 1), vol=576_000)])
    n = Notifier(toast=False, out=lines.append)
    rc = asyncio.run(live.live_loop(src, eng, n, dash, status, close_at=None, every=0.01, out=lines.append))
    assert rc == 0 and status.ticks == 2 and status.alerts == 2
    assert any("[근접]" in m for m in lines) and any("[돌파]" in m for m in lines)
    page = (tmp_path / "live.html").read_text(encoding="utf-8")
    assert "가짜 시세" in page and "[돌파] 대한항공" in page


def test_live_loop_stops_at_close_time(tmp_path):
    lines = []
    eng = TriggerEngine([item()], AlertStore(tmp_path, TODAY))
    status = LiveStatus()
    dash = Dashboard(tmp_path / "live.html", eng, status)
    rc = asyncio.run(live.live_loop(ListSource([], forever=True), eng, Notifier(toast=False, out=lines.append), dash,
                                    status, close_at=at(15, 31), every=0.01, clock=lambda: at(15, 32),
                                    out=lines.append))
    assert rc == 0 and any("장 마감" in m for m in lines) and status.message == "장 마감 — 종료"


def test_live_loop_reports_source_failure(tmp_path):
    class Boom:
        label = "x"

        async def stream(self):
            raise KISError("웹소켓 실패", "WS")
            yield  # pragma: no cover

    lines = []
    eng = TriggerEngine([item()], AlertStore(tmp_path, TODAY))
    rc = asyncio.run(live.live_loop(Boom(), eng, Notifier(toast=False, out=lines.append),
                                    Dashboard(tmp_path / "d.html", eng, LiveStatus()), LiveStatus(), close_at=None,
                                    every=0.01, out=lines.append))
    assert rc == 1 and any("시세 수신 중단" in m for m in lines)


def test_cli_help_mentions_read_only(capsys):
    from chart_screener.__main__ import main
    with pytest.raises(SystemExit) as ei:
        main(["live", "--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "조회 전용" in out and "--source" in out and "--no-toast" in out and "--after-hours" in out


def test_run_exits_on_weekend_without_network(monkeypatch, capsys):
    from chart_screener.__main__ import main
    monkeypatch.setattr(live, "now_kst", lambda: datetime(2026, 10, 10, 10, 0, tzinfo=KST))

    def boom(*a, **k):
        raise AssertionError("주말에는 출처·스캔을 건드리지 않아야 함")

    monkeypatch.setattr(live, "resolve_source", boom)
    monkeypatch.setattr(live, "build_watchlist", boom)
    assert main(["live", "--no-open", "--no-toast"]) == 0
    assert "주말" in capsys.readouterr().out


# ---------------------------------------------------------------- 리뷰 수정 회귀 테스트
def _d(y, mo, d, h, mi, s=0):
    return datetime(y, mo, d, h, mi, s, tzinfo=KST)


def _pullback_item(**kw):
    base = dict(code="000030", name="눌림주", pattern="big_value_pullback", label="300억 눌림목", pivot=50000.0,
                stop=48500.0, support=50000.0, zone_top=51500.0, reason="눌림 구간", ref_close=51000.0)
    base.update(kw)
    return item(**base)


def test_stale_previous_session_ticks_never_alert_or_touch_old_log(tmp_path):
    """다음 거래일 아침(10-12), 첫 체결 전 네이버 시세는 localTradedAt 이 전 거래일(10-08 15:30)이다."""
    day = date(2026, 10, 12)
    store = AlertStore(tmp_path, day)
    eng = TriggerEngine([item(), _pullback_item()], store)
    js = {"datas": [
        {"itemCode": "003490", "closePriceRaw": "30700", "fluctuationsRatioRaw": "0.66",
         "accumulatedTradingVolumeRaw": "900000", "localTradedAt": "2026-10-08T15:30:00+09:00"},
        {"itemCode": "000030", "closePriceRaw": "51000", "fluctuationsRatioRaw": "-0.5",
         "accumulatedTradingVolumeRaw": "500000", "localTradedAt": "2026-10-08T15:30:00+09:00"}]}
    stale = parse_naver_polling(js, now=_d(2026, 10, 12, 9, 0, 5))
    assert [eng.on_tick(t) for t in stale] == [[], []]          # 근접·눌림 조건이지만 지난 시세라 알림 없음
    assert eng.stale_ticks == 2 and eng.fresh_ticks == 0
    assert store.day == day and list(tmp_path.glob("live_alerts_*.csv")) == []
    st = eng.state["003490"]
    assert st.stale and st.price == 30700 and st.vol_ratio is None
    page = render_dashboard(eng, LiveStatus(), now=_d(2026, 10, 12, 9, 0, 6))
    assert "지난 시세" in page and "알림 제외" in page
    # 오늘 첫 체결부터는 정상 알림, 기록은 오늘 파일에만
    assert [a.kind for a in eng.on_tick(tick("003490", 30700, _d(2026, 10, 12, 9, 2), vol=50_000))] == [NEAR]
    assert [a.kind for a in eng.on_tick(tick("000030", 51000, _d(2026, 10, 12, 9, 2), vol=40_000))] == [PULLBACK]
    assert store.path.name == "live_alerts_20261012.csv" and not (tmp_path / "live_alerts_20261008.csv").exists()
    # 다른 종목 알림이 나도 같은 알림이 되살아나지 않는다
    assert eng.on_tick(tick("000030", 50900, _d(2026, 10, 12, 9, 3), vol=60_000)) == []
    assert not eng.state["003490"].stale


def test_preopen_and_zero_volume_ticks_are_display_only(tmp_path):
    eng = TriggerEngine([item()], AlertStore(tmp_path, TODAY))
    assert eng.on_tick(tick("003490", 30950, at(8, 55), vol=1000)) == []      # 정규장 시작 전 (NXT 프리마켓 등)
    assert eng.on_tick(tick("003490", 30950, at(9, 0, 5), vol=0)) == []        # 아직 체결 없음 (REST = 전일 종가)
    assert eng.stale_ticks == 2 and eng.store.rows == []
    assert [a.kind for a in eng.on_tick(tick("003490", 30950, at(9, 1), vol=5000))] == [BREAKOUT_HIT]
    eng.on_tick(tick("003490", 30000, _d(2026, 10, 7, 15, 30)))               # 오늘 시세를 받은 뒤의 지난 시세
    assert eng.state["003490"].price == 30950 and not eng.state["003490"].stale


def _vitzro(**kw):
    """리뷰 실사례: 장기횡보 돌파 뒤라 손절가(10,140)가 피벗(9,880)보다 위."""
    base = dict(code="042370", name="비츠로테크", pattern="long_base_breakout", label="장기횡보 돌파",
                stage=NEAR_PIVOT, pivot=9880.0, stop=10140.0, ref_close=10510.0, reason="피벗 근접",
                plan="돌파 확인 — 현재가 10,510 매수 (피벗 9,880)")
    base.update(kw)
    return item(**base)


def test_stop_above_pivot_blocks_buy_alerts_after_stop_out(tmp_path):
    eng = TriggerEngine([_vitzro()], AlertStore(tmp_path, TODAY))
    s = eng.on_tick(tick("042370", 10100, at(10, 0), vol=100_000))
    assert [a.kind for a in s] == [STOP]
    assert "손절 검토" in s[0].text and "돌파 전" not in s[0].text and "잠정" in s[0].text
    assert eng.on_tick(tick("042370", 9850, at(11, 0), vol=200_000)) == []    # [근접] 없음
    assert eng.on_tick(tick("042370", 9950, at(13, 0), vol=300_000)) == []    # [돌파] 없음
    assert eng.state["042370"].stopped
    assert "손절 이탈 — 매수 알림 끔" in render_dashboard(eng, LiveStatus(), now=at(13, 0))
    # 재실행해도 기록의 손절 알림으로 같은 상태
    eng2 = TriggerEngine([_vitzro()], AlertStore(tmp_path, TODAY))
    assert eng2.state["042370"].stopped
    assert eng2.on_tick(tick("042370", 9850, at(13, 30), vol=310_000)) == []
    assert eng2.on_tick(tick("042370", 9990, at(13, 31), vol=320_000)) == []


def test_one_tick_through_stop_and_pivot_alerts_only_stop(tmp_path):
    eng = TriggerEngine([_vitzro()], AlertStore(tmp_path, TODAY))
    assert [a.kind for a in eng.on_tick(tick("042370", 9850, at(10, 0), vol=100_000))] == [STOP]
    assert eng.on_tick(tick("042370", 9990, at(10, 1), vol=110_000)) == []


def test_close_below_stop_means_no_buy_alerts_that_day(tmp_path):
    eng = TriggerEngine([item(ref_close=28000.0), _pullback_item(ref_close=48000.0)], AlertStore(tmp_path, TODAY))
    assert eng.state["003490"].stopped and eng.state["000030"].stopped
    assert eng.on_tick(tick("003490", 30800, at(10, 0), vol=100)) == []       # 근접 없음
    assert eng.on_tick(tick("003490", 31000, at(10, 5), vol=100)) == []       # 돌파 없음
    assert eng.on_tick(tick("000030", 51000, at(10, 5), vol=100)) == []       # 눌림 없음
    assert [a.kind for a in eng.on_tick(tick("003490", 28600, at(11, 0), vol=100))] == [STOP]  # 위로 왔다 다시 이탈


def test_stop_wording_follows_entry_plan(tmp_path):
    its = [item(code="000001", plan="피벗 30,900 돌파 매수"),
           item(code="000002", plan="돌파 확인 — 현재가 31,200 매수 (피벗 30,900)", ref_close=31200.0),
           item(code="000003", stage=BREAKOUT, breakout_date="2026-10-06", ref_close=30000.0),
           item(code="000004", plan="피벗 30,900 재돌파 매수", stage=BREAKOUT, breakout_date="2026-10-05",
                ref_close=30000.0)]
    eng = TriggerEngine(its, AlertStore(tmp_path, TODAY))
    txt = {it.code: eng.on_tick(tick(it.code, 28600, at(10, 0), vol=1000))[0].text for it in its}
    assert "돌파 전 — 매수 계획 보류" in txt["000001"]
    assert "손절 검토" in txt["000002"] and "돌파 전" not in txt["000002"]
    assert "손절 검토" in txt["000003"]
    assert "매수 계획 보류" in txt["000004"]                                    # 재돌파 대기 = 아직 매수 전
    assert live.pre_entry(item()) and not live.pre_entry(item(ref_close=31000.0, breakout_date="2026-10-07"))


def test_alert_store_writes_pending_file_when_log_is_locked(tmp_path):
    notes = []
    (tmp_path / "live_alerts_20261008.csv").mkdir()      # 엑셀이 잡고 있는 것처럼 열 수 없게
    store = AlertStore(tmp_path, TODAY, notice=notes.append)
    its = [item(), item(code="000002", name="둘째")]
    eng = TriggerEngine(its, store)
    assert [a.kind for a in eng.on_tick(tick("003490", 30950, at(10, 0)))] == [BREAKOUT_HIT]
    assert [a.kind for a in eng.on_tick(tick("000002", 30950, at(10, 1)))] == [BREAKOUT_HIT]
    assert len(notes) == 1 and "엑셀" in notes[0] and "pending" in notes[0]      # 안내는 한 번
    assert store.pending_path.exists()
    eng2 = TriggerEngine(its, AlertStore(tmp_path, TODAY))                       # 재실행: 대체 파일도 읽는다
    assert eng2.state["000002"].last_alert.startswith("[돌파] 둘째")
    assert eng2.on_tick(tick("003490", 30700, at(11, 0))) == []
    assert eng2.on_tick(tick("003490", 30950, at(11, 1))) == []


def test_naver_source_returns_to_polling_after_outage():
    clock = [0.0]

    async def fake_sleep(s):
        clock[0] += s
        await asyncio.sleep(0)

    calls = {"n": 0}

    def fetch(url):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise OSError("down")
        return NAVER_JS

    status = []
    snap = [tick("005930", 100, at(10, 0), source="naver")]
    src = live.NaverSource(["005930"], interval=10, fetch_json=fetch, snapshot=lambda c: snap, sleep=fake_sleep,
                           on_status=status.append, probe_every=180, clock=lambda: clock[0])

    async def run():
        seen = []
        async for t in src.stream():
            seen.append((src.mode, t.price))
            if [p for _, p in seen].count(262500) == 2:
                return seen

    seen = asyncio.run(run())
    assert [p for m, p in seen if m == "snapshot"] == [100, 100, 100]      # 20초·80초·140초
    assert seen[3] == ("polling", 262500) and src.mode == "polling" and src.label.startswith("네이버 시세 (10초")
    assert calls["n"] == 5                                                 # 3분 뒤 다시 시도해 복구
    assert any("3분마다 다시 시도" in m for m in status) and any("복구" in m for m in status)


def test_kis_source_retries_websocket_after_rest_window():
    clock = [0.0]

    class FailingWS:
        _key = "KEEPKEY"

        async def ticks(self):
            raise KISError("웹소켓 연결이 5회 연속 실패했습니다", "WS")
            yield  # pragma: no cover

    class GoodWS:
        _key = None

        async def ticks(self):
            yield tick("005930", 71000, at(10, 6), source="kis")

    good = GoodWS()
    wss = iter([FailingWS(), good])

    class FakeRest:
        label = "한국투자증권 REST 현재가 (15초 간격)"

        async def stream(self, until=None):
            assert until == pytest.approx(300.0)
            yield tick("005930", 70000, at(10, 0), source="kis-rest")
            clock[0] = until                                               # 5분 지남

    status = []
    src = live.KISSource(cfg=None, codes=["005930"], on_status=status.append, ws_factory=lambda: next(wss),
                         rest_factory=FakeRest, rest_window=300, clock=lambda: clock[0])

    async def two():
        out = []
        async for t in src.stream():
            out.append((t.source, src.mode))
            if len(out) == 2:
                return out

    assert asyncio.run(two()) == [("kis-rest", "rest"), ("kis", "ws")]
    assert src.ws_attempts == 2 and src.label.endswith("웹소켓)") and good._key == "KEEPKEY"
    assert any("5분 뒤 웹소켓을 다시 시도" in m for m in status) and any("재연결" in m for m in status)

    class NoLib:
        async def ticks(self):
            raise KISError("websockets 패키지가 없습니다", "WS_LIB")
            yield  # pragma: no cover

    seen = []

    class Rest2(FakeRest):
        async def stream(self, until=None):
            seen.append(until)
            yield tick("005930", 70000, at(10, 0), source="kis-rest")

    src2 = live.KISSource(cfg=None, codes=["005930"], ws_factory=NoLib, rest_factory=Rest2)
    asyncio.run(_first(src2))
    assert seen == [None] and src2.mode == "rest"                          # 라이브러리가 없으면 REST 만


def test_kis_rest_source_stops_at_deadline():
    clock = [0.0]

    class Client:
        def quote(self, code, market):
            clock[0] += 2.0
            return Quote(code=code, price=1000.0, change=0.0, change_pct=0.0, open=1000.0, high=1000.0,
                         low=1000.0, volume=10.0, value_krw=1e4, time=at(10, 0))

    async def fake_sleep(s):
        clock[0] += s
        await asyncio.sleep(0)

    src = live.KISRestSource(Client(), ["005930", "000660", "035420"], interval=15, sleep=fake_sleep,
                             clock=lambda: clock[0])

    async def collect():
        return [t.code async for t in src.stream(until=3.0)]

    assert asyncio.run(collect()) == ["005930", "000660"]


def test_session_phase_knows_krx_holidays():
    assert live.krx_holiday(date(2026, 10, 9)) and session_phase(_d(2026, 10, 9, 10, 0)) == "holiday"   # 한글날
    assert live.krx_holiday(date(2026, 9, 24))                                                          # 추석
    assert not live.krx_holiday(TODAY) and session_phase(at(10, 0)) == "open"


def _boom(*a, **k):
    raise AssertionError("휴장일에는 스캔·출처를 건드리지 않아야 함")


def test_run_exits_on_krx_holiday_without_network(monkeypatch, capsys):
    from chart_screener.__main__ import main
    monkeypatch.setattr(live, "now_kst", lambda: _d(2026, 10, 9, 8, 50))
    monkeypatch.setattr(live, "resolve_source", _boom)
    monkeypatch.setattr(live, "build_watchlist", _boom)
    assert main(["live", "--no-open", "--no-toast"]) == 0
    assert "휴장일" in capsys.readouterr().out


def test_run_exits_when_kis_holiday_api_says_closed(monkeypatch, tmp_path, capsys):
    from chart_screener.__main__ import main
    cfg = live.KISConfig.load(_write_cfg(tmp_path))
    monkeypatch.setattr(live, "now_kst", lambda: _d(2026, 11, 12, 8, 50))     # 달력에는 없는 날 (가정)
    monkeypatch.setattr(live, "resolve_source", lambda *a, **k: ("kis", cfg, object()))
    asked = []
    monkeypatch.setattr(live.KISRestClient, "open_day", lambda self, day, **k: asked.append(day) or False)
    monkeypatch.setattr(live, "build_watchlist", _boom)
    assert main(["live", "--no-open", "--no-toast", "--out", str(tmp_path)]) == 0
    assert asked == [date(2026, 11, 12)] and "휴장일" in capsys.readouterr().out


def test_run_ctrl_c_during_setup_exits_cleanly(monkeypatch, capsys):
    from chart_screener.__main__ import main
    monkeypatch.setattr(live, "now_kst", lambda: at(9, 30))

    def interrupted(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(live, "resolve_source", interrupted)                  # 토큰 발급 대기 중 Ctrl+C
    assert main(["live", "--no-open", "--no-toast"]) == 0
    assert "Ctrl+C" in capsys.readouterr().out


def test_live_loop_stops_on_unlisted_holiday(tmp_path):
    day = date(2026, 11, 12)
    eng = TriggerEngine([item()], AlertStore(tmp_path, day))
    stale = tick("003490", 30950, _d(2026, 11, 11, 15, 30), vol=900_000)
    lines, status = [], LiveStatus()
    rc = asyncio.run(live.live_loop(ListSource([stale], forever=True), eng, Notifier(toast=False, out=lines.append),
                                    Dashboard(tmp_path / "d.html", eng, status), status, close_at=None, every=0.01,
                                    clock=lambda: _d(2026, 11, 12, 10, 16), out=lines.append, holiday_check=True,
                                    watch_every=0.01))
    assert rc == 0 and status.alerts == 0 and any("휴장일로 보고" in m for m in lines)
    assert status.message.startswith("오늘 체결 없음") and not list(tmp_path.glob("live_alerts_*.csv"))


class _Brief(ListSource):
    async def stream(self):
        for t in self.ticks:
            yield t
        await asyncio.sleep(0.15)


def test_live_loop_warns_without_todays_ticks_but_keeps_running(tmp_path):
    eng = TriggerEngine([item()], AlertStore(tmp_path, TODAY))
    lines, status = [], LiveStatus()
    stale = tick("003490", 30950, _d(2026, 10, 7, 15, 30), vol=900_000)
    rc = asyncio.run(live.live_loop(_Brief([stale]), eng, Notifier(toast=False, out=lines.append),
                                    Dashboard(tmp_path / "d.html", eng, status), status, close_at=None, every=0.01,
                                    clock=lambda: at(9, 6), out=lines.append, holiday_check=True, watch_every=0.01))
    assert rc == 0 and any("아직 오늘 체결이 없습니다" in m for m in lines)
    assert not any("휴장일로 보고" in m for m in lines) and status.message == "시세 수신 종료"
    # 10:15 가 지났어도 오늘 체결을 받았으면 끝내지 않는다
    eng2 = TriggerEngine([item()], AlertStore(tmp_path / "b", TODAY))
    lines2, status2 = [], LiveStatus()
    rc = asyncio.run(live.live_loop(_Brief([tick("003490", 30500, at(10, 0), vol=1000)]), eng2,
                                    Notifier(toast=False, out=lines2.append),
                                    Dashboard(tmp_path / "e.html", eng2, status2), status2, close_at=None,
                                    every=0.01, clock=lambda: at(10, 16), out=lines2.append, holiday_check=True,
                                    watch_every=0.01))
    assert rc == 0 and not any("휴장일" in m or "아직" in m for m in lines2) and status2.message == "시세 수신 종료"


# ---------------------------------------------------------------- 웹소켓 구독 한도 초과 → REST 보충
def test_kis_source_fills_rejected_codes_with_rest():
    """서버가 일부 종목 구독을 거부(MAX SUBSCRIBE OVER)하면 그 종목만 REST 현재가로 보충한다 (실측: 세션당 3건)."""
    now = datetime(2026, 10, 8, 10, 0, tzinfo=KST)

    class FakeWS:
        def __init__(self):
            self.subscribed = {"000001"}
            self.overflow = {"000002", "000003"}
            self.dropped = []
            self._key = None

        async def ticks(self):
            yield Tick(code="000001", time=now, price=1000, change_pct=1.0, cum_volume=10, cum_value=1e4,
                       high=1000, low=990, open=995)
            await asyncio.sleep(3600)   # 실시간은 계속 열려 있음

    class FakeQuotes:
        def __init__(self):
            self.calls = []

        def quote(self, code, market="J"):
            self.calls.append((code, market))
            return Quote(code=code, price=2000, change=10, change_pct=0.5, open=1990, high=2010, low=1980,
                         volume=100, value_krw=2e5, time=now)

    fq = FakeQuotes()
    msgs = []

    async def fast_sleep(_):
        await asyncio.sleep(0)

    src = live.KISSource(cfg=None, codes=["000001", "000002", "000003"], interval=15,
                         on_status=msgs.append, ws_factory=FakeWS, quote_client_factory=lambda: fq,
                         sleep=fast_sleep)

    async def collect():
        got = []
        async for t in src.stream():
            got.append(t)
            if {t.code for t in got} >= {"000001", "000002", "000003"}:
                break
        return got

    got = asyncio.run(asyncio.wait_for(collect(), timeout=5))
    codes = {t.code for t in got}
    assert codes == {"000001", "000002", "000003"}
    calls = [c for c, _ in fq.calls]
    assert calls[:3] == ["000001", "000002", "000003"]                # 시작 시 전 종목 1회 조회
    assert set(calls[3:]) <= {"000002", "000003"}                     # 이후엔 구독 못 한 종목만 REST
    assert any("REST 현재가 조회" in m and "2종목" in m for m in msgs)
    rest_ticks = [t for t in got if t.code != "000001"]
    assert all(t.source == "kis-rest" for t in rest_ticks)


def test_kis_source_overflow_excludes_subscribed_and_includes_capped():
    class W:
        subscribed = {"A"}
        overflow = {"A", "B"}    # 재접속 뒤 A 는 구독 성공 → 제외
        dropped = ["D"]          # 40종목 상한 밖
    src = live.KISSource(cfg=None, codes=["A", "B", "C", "D"], ws_factory=W, quote_client_factory=lambda: None,
                         prime=False)
    assert src._overflow(W()) == ["B", "D"]
