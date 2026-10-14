"""2026-10-14 기법 검토 반영 — 장중 저가 확정 · 어제 종가 기준 · 풀릴 수 없는 '눌림 대기' · 피벗 없는 단계 이름 ·
빗각 재현(체크 4) · 탐지패턴 단계 · 빈 이벤트 백테스트 · 출처 표시."""
import importlib.util
import json
import pathlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from chart_screener import backtest, scoring
from chart_screener import techniques as tq
from chart_screener.patterns import fib_pullback as fp
from chart_screener.patterns import trendline_break as tb
from chart_screener.patterns.base import BREAKOUT, FAILED, NEAR_PIVOT, PatternResult
from chart_screener.scanner import StockScan, position_plan, scan_one, to_frame
from synthetic import add_value, make_context

ROOT = pathlib.Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------- 피보 합성 그림 (tests/test_fib_pullback.py 와 같은 봉)
L = 99.5
LV = tq.fib_levels(130.0, L)


def _flat(n=40):
    rows = []
    for k in range(n):
        c = 100.3 if k % 2 == 0 else 99.7
        rows.append([100.0, max(100.0, c) + 0.2, min(100.0, c) - 0.2, c, 1e6])
    return rows


UP = [[100, 112.5, 99.8, 112, 3e6], [112, 119, 111.5, 118, 2e6], [118, 125, 117.5, 124, 2e6],
      [124, 130, 123.5, 129, 2e6]]
CONF = [129, 129.5, 125.5, 126, 1.5e6]
DIP = [126, 126.2, 120.5, 121, 1.2e6]
TOUCH = [121, 121.3, 118.0, 119, 0.8e6]
REB = [119, 122.5, 118.8, 122, 2.5e6]          # 신호: 진입 122 · 손절 50% 라인 114.75
HOLDB = [122.5, 124, 122.2, 123.5, 1.2e6]
SIGNAL_ROWS = _flat() + UP + [CONF, DIP, TOUCH, REB]


def _df(rows, start="2024-01-02"):
    a = np.asarray(rows, dtype=float)
    idx = pd.bdate_range(start, periods=len(a))
    return add_value(pd.DataFrame({"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3],
                                   "volume": a[:, 4]}, index=idx))


def _partial(rows, frac=0.5):
    ctx = make_context(_df(rows))
    ctx.partial, ctx.session_frac = True, frac
    return ctx


# ---------------------------------------------------------------- lookahead-1: 장중 저가로 이미 정해진 손절 · 무효
def test_fib_intraday_low_below_stop_is_final_failure():
    pierce = [123.0, 123.2, 114.0, 118.0, 0.5e6]                       # 장중 저가 114 < 손절 114.75, 종가는 손절 위
    ctx = _partial(SIGNAL_ROWS + [HOLDB, pierce])
    r = fp.detect(ctx)
    assert r.detected and r.stage == FAILED
    fin = r.metrics["intraday_final"]
    assert fin["kind"] == "stop" and fin["low"] == 114.0 and fin["level"] == pytest.approx(LV[0.5])
    assert r.stage_label == "손절 · 장중 확정(저가)" and r.warnings[0].startswith("장중 확정(저가)")
    eod = fp.detect(make_context(_df(SIGNAL_ROWS + [HOLDB, pierce])))      # 같은 봉이 완성되면 — 손절 그대로
    assert eod.stage == FAILED and eod.metrics["phase"] == "STOPPED"
    s = scan_one(ctx, ["fib_pullback"])
    assert s.position is not None and s.position["plan"].startswith("손절가 이탈 — 관망") and s.position["shares"] == 0


def test_fib_intraday_close_rule_stays_provisional():
    dip = [123.0, 123.2, 115.5, 116.0, 0.5e6]                          # 저가는 손절 위 — 종가 규칙(진입가 아래)은 마감 뒤에
    r = fp.detect(_partial(SIGNAL_ROWS + [HOLDB, dip]))
    assert r.stage == BREAKOUT and "intraday_final" not in r.metrics


def test_fib_pre_signal_intraday_low_below_wave_low_is_final():
    crash = [119.0, 119.2, 99.0, 112.0, 0.5e6]                         # 신호 전 장중 저가 < 파동 저점 L 99.5
    r = fp.detect(_partial(_flat() + UP + [CONF, DIP, TOUCH, crash]))
    assert r.stage == FAILED and r.metrics["intraday_final"]["kind"] == "invalid_L"
    assert not fp.detect(make_context(_df(_flat() + UP + [CONF, DIP, TOUCH, crash]))).detected   # 마감 뒤: 설정 무효


def test_low_stop_patterns_match_backtest_stop_rule():
    assert set(scoring.LOW_STOP_PATTERNS) == {p for p, r in backtest.STOP_RULE.items() if r == "low"}
    assert set(scoring.EOD_PATTERNS) == {"trendline_break", "fib_pullback", "trendline_fib", "ma60_supply",
                                         "red_three_monthly", "day_leader"}


# ---------------------------------------------------------------- lookahead-5: 장중엔 '마지막 완성 봉' 이라 적는다
def test_partial_wording_names_last_complete_bar():
    pierce = [121, 121.3, LV[0.618] * 0.995, 119, 0.8e6]               # 완성 봉 저가가 61.8% 아래 (종가는 위)
    black = [119, 119.5, 118.6, 118.7, 0.3e6]
    rows = _flat() + UP + [CONF, DIP, pierce, black]
    r = fp.detect(_partial(rows))
    day = f"{_df(rows).index[-2]:%Y-%m-%d}"
    assert any(w.startswith(f"마지막 완성 봉({day}) 저가") for w in r.warnings)
    assert not any(w.startswith("오늘 저가") for w in r.warnings)
    assert r.metrics["expires_basis"] == day
    touch = fp.detect(_partial(_flat() + UP + [CONF, DIP, TOUCH, black]))
    assert any("완성 봉 기준 남은 봉" in x and "오늘 진행 중인 봉 포함" in x for x in touch.reasons)


# ---------------------------------------------------------------- truth-6: 피벗 없는 결과의 단계 이름
def test_pre_signal_touch_is_not_called_near_pivot():
    r = fp.detect(make_context(_df(_flat() + UP + [CONF, DIP, TOUCH])))
    assert r.stage == NEAR_PIVOT and r.pivot is None
    assert r.stage_label == "라인 접촉 · 신호 전" and r.metrics["stage_short"] == "접촉"
    assert r.to_dict()["stage_label"] == "라인 접촉 · 신호 전"
    sig = fp.detect(make_context(_df(SIGNAL_ROWS)))
    assert sig.stage_label == "돌파" and "stage_label" not in sig.metrics


# ---------------------------------------------------------------- truth-3: 미국 통계는 접히는 참고 줄에만
def test_shallow_line_caution_has_no_us_numbers():
    r = fp.detect(make_context(_df(SIGNAL_ROWS)))                      # 38.2% 라인 신호 = 얕은 라인
    assert any(w.startswith("얕은 라인") for w in r.warnings)
    assert not any("59%" in x or tq.BULKOWSKI_LABEL in x for x in r.reasons + r.warnings)
    assert fp.RISK_SHALLOW in r.metrics["bulkowski"]


# ---------------------------------------------------------------- lookahead-2 · 3: 계획 · W 는 단계와 같은 봉 · 풀리는 문구만
def _fib_lead(pivot=50200.0, stop=43550.0, stage=BREAKOUT, bo="2026-10-13", name="fib_pullback", metrics=None):
    return PatternResult(name=name, label=name, detected=True, score=70, stage=stage, pivot=pivot, stop=stop,
                         breakout_date=bo, metrics=metrics or {})


def _scan(results, close, partial=False, eod_close=None, eod_date=None):
    sb = scoring.compute(results, 80.0, close=close, eod_close=eod_close if partial else None)
    s = StockScan(code="000001", name="가", market="KOSDAQ", close=close, change_pct=0.0, market_cap=1e12, rs=80.0,
                  value_today=5e9, avg_value_20=5e9, max_value_5=5e9, partial=partial, results=results, score=sb,
                  eod_close=eod_close, eod_date=eod_date)
    s.position = position_plan(s)
    return s


def test_wide_stop_after_signal_is_hold_not_pullback_wait():
    """신호 뒤 손절폭 13.2% (진입가 = 신호 종가 바닥) — 가격이 손절 쪽으로 눌려도 풀리지 않으므로 '눌림 대기'가 아니다."""
    for close in (49196.0, 46184.0, 44176.0):
        s = _scan({"fib_pullback": _fib_lead(stage=NEAR_PIVOT)}, close)
        assert s.position["plan"].startswith("관망 — 손절폭 13.2% > 10% (진입가 = 신호 종가 50,200")
        assert s.position["shares"] == 0 and "눌림 대기" not in s.position["plan"]
        assert "관망" in " ".join(s.score.notes) or s.score.stage_weight <= 0.7


def test_retest_rebreak_plan_carries_origin_label():
    s = _scan({"fib_pullback": _fib_lead(pivot=50200.0, stop=47000.0, stage=NEAR_PIVOT)}, 49000.0)
    assert s.position["plan"] == "피벗 50,200 재돌파 매수 (Tech 공통 규칙 · 구현 선택 — 기법 규칙 아님)"


def test_intraday_plan_and_weight_use_last_complete_close_for_eod_patterns():
    lead = _fib_lead(pivot=93600.0, stop=87000.0)
    # 어제 종가 95,000 (돌파 단계 판정 봉) · 오늘 장중 89,000 — 계획 · 손절폭 · W 는 어제 종가 기준
    s = _scan({"fib_pullback": lead}, 89000.0, partial=True, eod_close=95000.0, eod_date="2026-10-13")
    assert s.basis(lead) == (95000.0, True)
    assert s.position["entry"] == 95000.0 and "2026-10-13 종가 95,000 매수" in s.position["plan"]
    assert s.score.stage_weight == 1.0                                 # 어제 종가 > 피벗 — '재시험' 덮어쓰기 아님
    assert any("어제 종가 기준" in n for n in s.score.notes)
    row = to_frame(SimpleNamespace(stocks=[s])).iloc[0]
    assert row["피벗대비"] == pytest.approx(round((95000 / 93600 - 1) * 100, 2))
    assert "2026-10-13 종가 기준" in row["단계"]
    cwh = PatternResult(name="cup_with_handle", label="컵", detected=True, score=70, stage=BREAKOUT, pivot=93600.0,
                        stop=87000.0, breakout_date="2026-10-13")
    s2 = _scan({"cup_with_handle": cwh}, 89000.0, partial=True, eod_close=95000.0, eod_date="2026-10-13")
    assert s2.basis(cwh) == (89000.0, False)                           # 컵 앤 핸들 식은 오늘 봉까지 — 지금가


def test_position_plan_intraday_low_guard_for_low_stop_patterns():
    df = _df(SIGNAL_ROWS + [HOLDB, [123.0, 123.2, 114.0, 118.0, 0.5e6]])
    ctx = make_context(df)
    ctx.partial = True
    lead = _fib_lead(pivot=122.0, stop=114.75, bo="2024-03-07")
    s = _scan({"fib_pullback": lead}, 118.0, partial=True, eod_close=123.5, eod_date="2024-03-08")
    s.ctx = ctx
    s.position = position_plan(s)
    assert s.position["plan"].startswith("손절가 이탈 — 관망 (오늘 장중 저가 114")


# ---------------------------------------------------------------- truth-4: 탐지패턴 칸에 단계
def test_frame_detected_patterns_carry_stage():
    lead = _fib_lead(pivot=122.0, stop=114.75)
    red = PatternResult(name="red_three_monthly", label="월봉 적삼병", detected=True, score=40, stage="forming", pivot=130.0)
    s = _scan({"fib_pullback": lead, "red_three_monthly": red}, 123.0)
    txt = to_frame(SimpleNamespace(stocks=[s])).iloc[0]["탐지패턴"]
    assert "월봉 적삼병(형성)" in txt and "피보나치 눌림 반등(돌파)" in txt


# ---------------------------------------------------------------- fidelity-1: 빗각 체크 4 재현
def test_trendline_replay_uses_confirmed_volume_breaks_twenty_bars_old():
    n = 120
    c = np.linspace(100, 160, n)
    b = tq.Bars.from_df(add_value(pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": np.full(n, 1e6)},
                                               index=pd.bdate_range("2024-01-02", periods=n))))

    def brk(t0, t_conf, vol="ok"):
        return tb.Break(line=None, t0=t0, vr=2.0, vol=vol, halts=[], t_conf=t_conf)
    sim = SimpleNamespace(breaks=[brk(10, 12), brk(30, 30), brk(50, 52, "low"), brk(60, None), brk(90, 95)])
    rp = tb.replay(sim, b, 110, tb.TLBreakConfig())
    assert [x["date"] for x in rp] == [b.date(12), b.date(30)]        # 거래량 미달 · 확인 전 · 20봉 안 지남은 뺌
    assert rp[0]["ret20"] == pytest.approx(c[32] / c[12] - 1) and rp[0]["break_date"] == b.date(10)
    assert tb.replay(sim, b, 115, tb.TLBreakConfig())[-1]["date"] == b.date(95)   # t_conf + 20 ≤ E 경계


def test_trendline_checklist_item4_is_replayed_not_skipped():
    from test_trendline_break import _seq
    df, _ = _seq([1.04])
    r = tb.detect(make_context(df))
    it4 = r.metrics["checklist"][3]
    assert "replay" in r.metrics and it4["note"] != "재현 안 함"
    assert "tl_replay" in r.metrics["origin"] and "구현 선택" in r.metrics["origin"]["tl_replay"]
    assert any(x.startswith("체크리스트 10 (검증 전)") for x in r.reasons)


# ---------------------------------------------------------------- fidelity-2 · 3: 출처 표시
def test_origin_labels_video_only_where_sourced():
    assert "영상 [" not in tb.ORIGIN["tl_near"] and "구현 선택" in tb.ORIGIN["tl_near"]
    for k in range(1, 11):
        assert tq.ORIGIN[f"ck{k}"].startswith("영상 [01:02:00–01:05:00]"), k
    assert "6~12개월 참고 창 = 영상" in tq.ORIGIN["ck9"]


# ---------------------------------------------------------------- breakage-1: 신호 0건 패턴이 있어도 요약
def test_bt_techniques_reads_empty_event_file(tmp_path):
    spec = importlib.util.spec_from_file_location("bt_techniques", ROOT / "scripts" / "bt_techniques.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = tmp_path / "events_x.csv"
    pd.DataFrame().to_csv(p, index=False, encoding="utf-8-sig")      # 신호 0건 — 빈 줄만
    assert mod._read_events(p).empty
    res = {"patterns": {"a": {"n_events": 0}, "b": {"n_events": 0}}}
    assert max((str(v["last"]) for v in res["patterns"].values() if v.get("last")), default=None) is None


# ---------------------------------------------------------------- truth-1: 매수 검토 필터
def test_buy_review_filter_excludes_signal_and_hold_rows():
    html = (ROOT / "chart_screener" / "report" / "template.html").read_text(encoding="utf-8")
    assert "function buyReview(s)" in html and "SIGNALS.has(s.best)" in html and "s.plan_hold" in html
    assert "(!state.act || buyReview(s))" in html
    json.dumps({"ok": True})


# ---------------------------------------------------------------- breakage-3 · 4: 실시간 감시는 컵 앤 핸들만
def test_live_scan_runs_only_live_patterns(monkeypatch):
    from chart_screener import live, scanner, universe_data
    seen = {}

    def fake_scan(ud, cfg, patterns=None, **kw):
        seen["patterns"] = patterns
        return SimpleNamespace(stocks=[], asof=ud.asof)
    monkeypatch.setattr(scanner, "run_scan", fake_scan)
    monkeypatch.setattr(universe_data, "load_universe_data",
                        lambda *a, **k: SimpleNamespace(asof=pd.Timestamp("2026-10-13"), ohlcv={"000001": None}))
    scan, items = live.build_watchlist(offline=True, verbose=False, out=lambda *_: None)
    assert seen["patterns"] == list(scoring.LIVE_PATTERNS) and items == []


def test_live_missing_codes_explain_live_scope():
    from chart_screener import live
    scan = SimpleNamespace(stocks=[SimpleNamespace(code="028670")])
    lines = live.missing_codes_text(["028670", "005930"], [], scan)
    assert len(lines) == 2 and all("컵 앤 핸들" in x and "《차트의 기술》" in x for x in lines)
    assert "028670" in lines[0] and "005930" in lines[1]
    assert live.missing_codes_text(["028670"], [SimpleNamespace(code="028670")], scan) == []


# ---------------------------------------------------------------- truth-6: 10% 주도주 단계 이름 · 빗각+피보 신호 전
def test_day_leader_stage_is_named_observation_day():
    from test_day_leader import _run, _sig_df
    r = _run(_sig_df())
    assert r.stage == NEAR_PIVOT and r.pivot is None
    assert r.stage_label == "관찰일 (다음 거래일)" and r.metrics["stage_short"] == "관찰일"


def test_intraday_final_result_is_judged_on_today_not_yesterday():
    lead = _fib_lead(pivot=93600.0, stop=85300.0, stage=FAILED,
                     metrics={"intraday_final": {"kind": "stop", "text": "장중 확정(저가): 오늘 저가 84,600 < 손절 85,300"}})
    s = _scan({"fib_pullback": lead}, 85400.0, partial=True, eod_close=93600.0, eod_date="2026-10-13")
    assert s.basis(lead) == (85400.0, False)
    assert s.position["plan"].startswith("손절가 이탈 — 관망 (장중 확정(저가)")
    assert not any("어제 종가 기준" in n for n in s.score.notes)
    row = to_frame(SimpleNamespace(stocks=[s])).iloc[0]
    assert "종가 기준" not in row["단계"] and row["피벗대비"] == pytest.approx(round((85400 / 93600 - 1) * 100, 2))


def test_trendline_fib_intraday_low_below_stop_is_final():
    from test_trendline_fib import A, HOLDB, _scen
    from chart_screener.patterns import trendline_fib as tf
    df, _, lv = _scen(A + [HOLDB, HOLDB])
    eod = tf.detect(make_context(df.iloc[:-1]))
    assert eod.stage == BREAKOUT and eod.stop
    st = float(eod.stop)
    for col, x in (("open", st * 1.02), ("high", st * 1.03), ("low", st * 0.99), ("close", st * 1.01)):
        df.iloc[-1, df.columns.get_loc(col)] = x
    ctx = make_context(add_value(df))
    ctx.partial, ctx.session_frac = True, 0.5
    r = tf.detect(ctx)
    assert r.stage == FAILED and r.metrics["intraday_final"]["kind"] == "stop"
    assert "intraday_final" in r.metrics["origin"] and r.warnings[0].endswith("[intraday_final]")
    assert tf.detect(make_context(add_value(df))).stage == FAILED       # 마감 뒤 판정도 손절


def test_signal_day_plan_is_technique_entry_not_rebreak():
    lead = _fib_lead(pivot=30900.0, stop=29000.0, metrics={"phase": "SIGNAL"})
    s = _scan({"fib_pullback": lead}, 30900.0)
    assert s.position["plan"] == "신호 종가 30,900 매수 (기법 진입 — 반등 양봉 종가)" and s.position["shares"] > 0
    hold = _fib_lead(pivot=30900.0, stop=29000.0, metrics={"phase": "HOLD"})
    assert _scan({"fib_pullback": hold}, 30900.0).position["plan"].startswith("돌파 확인 — 현재가 30,900 매수")
