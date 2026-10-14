"""월봉 적삼병(chart_screener/patterns/red_three_monthly.py) — 합성 월봉으로 신호 · 비신호 · 경계 · 앞부분 불변 · '모름'.

부록 docs/2026-10-14-chart-techniques-addendum.md §13 적삼병 · 공통 항목. 월봉 값을 정확히 맞춘 일봉을 만들어(_daily) 쓴다.
기본 장면: 2022-01~12 하락(바닥권 기준 12개월) → 2023-01 확정 저점(저가 100) → 2023-02~04 병정 3개 → 2023-05 진행 월."""
import json
import warnings

import numpy as np
import pandas as pd
import pytest

from chart_screener import journal
from chart_screener import techniques as tq
from chart_screener.config import Config
from chart_screener.patterns import REGISTRY, run_all
from chart_screener.patterns import red_three_monthly as rtm
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from synthetic import make_context, make_ohlcv

DEC = [(200 - 7 * k, 202 - 7 * k, 192 - 7 * k, 194 - 7 * k) for k in range(12)]   # (O, H, L, C) 2022-01~12
LOW = (117, 119, 100, 108)                                                        # 2023-01 확정 저점
S1, S2, S3 = (108, 115.5, 104, 115), (115, 122.5, 112, 122), (122, 130.5, 119, 130)
NEXT = (130, 133, 128, 132)                                                       # 2023-05 (진행 월)


# ---------------------------------------------------------------- 도우미
def _daily(specs, start="2022-01", vol=1e6) -> pd.DataFrame:
    """달마다 (O, H, L, C) 가 정확히 그 월봉이 되게 영업일 일봉을 만든다 (시가 → 종가 직선, 고 · 저가는 한 날씩)."""
    rows = []
    per = pd.Period(start, "M")
    for o, h, lo_, c in specs:
        days = pd.bdate_range(per.start_time, per.end_time)
        d = len(days)
        closes = o + (c - o) * (np.arange(1, d + 1) / d)
        opens = np.r_[o, closes[:-1]]
        hi, lo = np.maximum(opens, closes), np.minimum(opens, closes)
        lo[d // 3] = lo_
        hi[(2 * d) // 3] = h
        rows += [(days[k], opens[k], hi[k], lo[k], closes[k], vol) for k in range(d)]
        per += 1
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    df.index.name = None
    df["value"] = df["close"] * df["volume"]
    return df


def _base(**swap) -> list:
    m = {"LOW": LOW, "S1": S1, "S2": S2, "S3": S3, "NEXT": NEXT}
    m.update(swap)
    return DEC + [m["LOW"], m["S1"], m["S2"], m["S3"], m["NEXT"]]


def _ctx(df, cfg: rtm.RedThreeConfig | None = None, **kw):
    c = Config()
    if cfg is not None:
        c.patterns[rtm.NAME] = cfg
    return make_context(df, cfg=c, **kw)


def _junk_after(df: pd.DataFrame, t: int, seed: int = 0) -> pd.DataFrame:
    """봉 t 뒤를 엉뚱한 봉으로 바꾼다 (거래량 0 포함) — 앞부분 불변 시험용."""
    rng = np.random.default_rng(seed)
    out = df.copy()
    k = len(df) - t - 1
    if k > 0:
        c = float(df["close"].iloc[t]) * rng.uniform(0.2, 4.0, k)
        o = c * rng.uniform(0.7, 1.3, k)
        out.iloc[t + 1:, out.columns.get_loc("open")] = o
        out.iloc[t + 1:, out.columns.get_loc("close")] = c
        out.iloc[t + 1:, out.columns.get_loc("high")] = np.maximum(o, c) * 1.3
        out.iloc[t + 1:, out.columns.get_loc("low")] = np.minimum(o, c) * 0.6
        out.iloc[t + 1:, out.columns.get_loc("volume")] = rng.choice([0.0, 1e3, 1e9], k)
    return out


# ---------------------------------------------------------------- 신호
def test_signal_basic_fields_and_origins():
    df = _daily(_base()).loc[:"2023-05-03"]
    r = rtm.detect(_ctx(df))
    assert REGISTRY[rtm.NAME][0] == "월봉 적삼병" == r.label
    assert r.detected and r.stage == BREAKOUT and r.pivot == 130.0 and r.stop is None
    m = r.metrics
    assert m["state"] == "signal" and m["rule_version"] == "red3m_v1" == journal.rule_of(r)
    assert (m["signal_month"], m["signal_date"], m["known_date"]) == ("2023-04", "2023-04-28", "2023-05-01")
    assert (m["low_month"], m["low"], m["lag"]) == ("2023-01", 100.0, 3)
    assert r.start_date == "2023-01-02" and r.breakout_date == "2023-04-28"
    assert [s["month"] for s in m["soldiers"]] == ["2023-02", "2023-03", "2023-04"]
    assert m["bottom"]["status"] == "ok" and m["bottom"]["ref_close"] == 194.0
    # 규칙마다 출처
    o = m["origin"]
    assert "영상 [08:00–09:00]" in o["low_confirm"] and "fool.com" in o["bottom"] and "hankyung" in o["n3"]
    assert o["max_lag"].startswith("구현 선택") and o["score"].startswith("구현 선택") and "영상 [11:00]" in o["exclude"]
    assert m["bulkowski_note"].startswith(tq.BULKOWSKI_LABEL)
    assert not any("82%" in x for x in r.reasons + r.warnings)          # 불코우스키 수치는 참고 줄(metrics)에만
    assert any("영상 [04:00–14:00]" in x for x in r.reasons) and any("손절 규칙 없음" in w for w in r.warnings)
    # 점수: 신호 50 + 짧은 위꼬리 · 저가 상승 · 어드밴스 블록 아님 · 키 큰 몸통 (연중 하단 ⅓ 아님)
    assert r.score == 90.0 and m["score_unknown"] == [] and m["flags"]["yearly_low_third"] is False
    kinds = {a["kind"] for a in r.annotations}
    assert {"hline", "box", "marker", "segment"} <= kinds
    assert sum(a["kind"] == "box" for a in r.annotations) == 3
    json.dumps(r.to_dict(), ensure_ascii=False)                          # 리포트 · 일지로 바로 직렬화


def test_month_end_eod_is_still_partial_and_hts_bong():
    """월말 마지막 거래일 EOD 에도 그 달은 미완성 — 다음 달 첫 봉에 신호. 키움 0봉전(진행 달 포함) ≠ 1봉전(우리)."""
    df = _daily(_base())
    j = rtm.evaluate(df.loc[:"2023-04-28"])
    assert j["state"] == "pending" and j["stage"] == NEAR_PIVOT and not j.get("signal_month")
    assert j["hts"]["0봉전"] is True and j["hts"]["1봉전"] is False
    r = rtm.detect(_ctx(df.loc[:"2023-04-28"]))
    assert r.detected and r.stage == NEAR_PIVOT and r.breakout_date is None and r.pivot == 122.0   # max(4월 시가, 3월 종가)
    assert any("0봉전" in x for x in r.reasons)
    j2 = rtm.evaluate(df.loc[:"2023-05-01"])
    assert j2["state"] == "signal" and j2["hts"]["1봉전"] is True
    # 'calendar' 옵션: 4월 마지막 KRX 거래일 봉이 있으면 당일 완성
    jc = rtm.evaluate(df.loc[:"2023-04-28"], cfg=rtm.RedThreeConfig(complete_rule="calendar"))
    assert jc["state"] == "signal" and jc["known_date"] == "2023-04-28"


def test_calendar_rule_matches_core_period_bars():
    """'calendar' 완성 판정은 tq.monthly_bars(complete_rule='calendar') 와 같다 — 코어가 pd.Timedelta(1, 'D') 로 고쳐져
    월말이 주말인 달(2022-12 · 2023-04)에도 DeprecationWarning 이 없다(경고를 오류로 보고 확인)."""
    df = _daily(_base())
    cfg = rtm.RedThreeConfig(complete_rule="calendar")
    for end in ("2023-04-27", "2023-04-28", "2023-03-31", "2023-05-03", "2022-12-30"):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            core = tq.monthly_bars(df.loc[:end], complete_rule="calendar")
        pd.testing.assert_frame_equal(rtm.monthly(df.loc[:end], cfg), core)
    with pytest.raises(ValueError):
        rtm.monthly(df, rtm.RedThreeConfig(complete_rule="eom"))


def test_fourth_consecutive_bull_month_is_not_a_new_signal():
    df = _daily(_base(NEXT=(130, 138.5, 128, 138)) + [(138, 139, 137, 138.5)]).loc[:"2023-06-02"]
    j = rtm.evaluate(df)
    assert j["state"] == "after_signal" and not j["detected"]
    a = j["after_signal"]
    assert a["signal_month"] == "2023-04" and a["run_after"] == 1 and a["total_run"] == 4 and a["intact"]
    r = rtm.detect(_ctx(df))
    assert not r.detected and any("4번째 연속 양봉" in w for w in r.warnings)


def test_low_month_bull_is_not_first_soldier_by_default():
    specs = _base(LOW=(102, 109, 100, 108))                  # 저점 월이 양봉
    df = _daily(specs)
    j = rtm.evaluate(df.loc[:"2023-04-05"])                  # 2023-01(저점 · 양봉) · 02 · 03 = 양봉 3개
    assert j["state"] == "pending" and j["stage"] == NEAR_PIVOT
    cfg = rtm.RedThreeConfig(low_month_as_first=True)
    jf = rtm.evaluate(df.loc[:"2023-04-05"], cfg=cfg)
    assert jf["state"] == "signal" and jf["signal_month"] == "2023-03"
    # 옵션을 켜도 그다음 달(4번째 연속 양봉)은 새 신호가 아니다
    assert rtm.evaluate(df.loc[:"2023-05-03"], cfg=cfg)["state"] == "after_signal"
    assert rtm.evaluate(df.loc[:"2023-05-03"])["signal_month"] == "2023-04"


# ---------------------------------------------------------------- 비신호 · 경계
def test_short_history_before_low_is_bottom_unknown():
    df = _daily(DEC[6:] + [LOW, S1, S2, S3, NEXT], start="2022-07").loc[:"2023-05-03"]
    j = rtm.evaluate(df)
    assert j["state"] == "bottom_unknown" and not j["detected"] and j["bottom"]["status"] == "unknown"
    r = rtm.detect(_ctx(df))
    assert not r.detected and any("바닥권 모름" in w for w in r.warnings) and r.metrics["low_month"] == "2023-01"


@pytest.mark.parametrize("ref_close, ok", [(125.0, True), (124.99, False)])
def test_bottom_zone_boundary_exactly_20pct(ref_close, ok):
    flat = [(ref_close + 1, ref_close + 2, 118, ref_close)] * 12
    df = _daily(flat + [LOW, S1, S2, S3, NEXT]).loc[:"2023-05-03"]
    j = rtm.evaluate(df)
    assert (j["state"] == "signal") is ok
    if not ok:
        assert j["state"] == "not_bottom" and "바닥권 아님" in j["why"][0]


def test_zero_volume_halt_row_changes_month_open_and_low():
    df = _daily(_base()).loc[:"2023-05-03"].copy()
    d0 = df.loc["2023-03"].index[0]
    df.loc[d0, ["open", "high", "low", "close", "volume"]] = [95.0, 95.0, 95.0, 95.0, 0.0]
    assert rtm.evaluate(df)["state"] == "signal"                       # 거래량 0 행 제외 (기본)
    raw = rtm.evaluate(df, cfg=rtm.RedThreeConfig(drop_zero_volume=False))
    assert raw["state"] != "signal" and any("새 저가" in w for w in raw["why"])


def test_gap_down_at_month_boundary_fails_only_higher_close():
    df = _daily(_base(S2=(105, 113.5, 104, 113), S3=(113, 125.5, 110, 125))).loc[:"2023-05-03"]
    j = rtm.evaluate(df)
    assert j["state"] != "signal" and "종가 상승" in j["why"][0]
    assert rtm.evaluate(df, cfg=rtm.RedThreeConfig(require_higher_close=False))["state"] == "signal"


def test_doji_month_breaks_the_run():
    df = _daily(_base(S2=(118, 122, 112, 118), S3=(122, 130.5, 119, 130))).loc[:"2023-05-03"]
    j = rtm.evaluate(df)
    assert j["state"] != "signal" and "보합(도지)" in j["why"][0]


def test_equal_lows_do_not_confirm_and_equal_later_low_is_a_new_low():
    eq = DEC[:11] + [(123, 125, 100, 117)]                    # 2022-12 저가 = 2023-01 저가 = 100
    j = rtm.evaluate(_daily(eq + [LOW, S1, S2, S3, NEXT]).loc[:"2023-05-03"])
    assert j["state"] != "signal" and "확정 저점" in j["why"][0]
    j2 = rtm.evaluate(_daily(_base(S2=(115, 122.5, 100, 122))).loc[:"2023-05-03"])   # 둘째 병정 저가 = 저점
    assert j2["state"] != "signal" and "새 저가" in j2["why"][0]


@pytest.mark.parametrize("n_bear, ok", [(3, True), (4, False)])
def test_max_lag_third_soldier_within_6_months(n_bear, ok):
    bears = [(112, 113, 101 + k, 108) for k in range(n_bear)]        # 저점 뒤 음봉 (저가는 오름 — 다른 저점 없음)
    sold = [(108, 115.5, 105, 115), (115, 122.5, 112, 122), (122, 130.5, 119, 130), (130, 133, 128, 132)]
    df = _daily(DEC + [LOW] + bears + sold)
    t = df.index.searchsorted(df.index[-1].to_period("M").start_time) + 2       # 마지막 달 3번째 봉
    j = rtm.evaluate(df, t)
    assert (j["state"] == "signal") is ok
    if ok:
        assert j["lag"] == 6
    else:
        assert "저점 + 6개월" in j["why"][0]


# ---------------------------------------------------------------- 단계
@pytest.mark.parametrize("nxt, stage, why", [
    ((130, 141, 129, 140), EXTENDED, "기준가 대비"),
    ((130, 131, 119.5, 120), FAILED, "몸통 반납"),
    ((130, 131, 99, 101), FAILED, "구조 무효"),
    ((130, 133, 128, 132), BREAKOUT, "기준가 대비"),
])
def test_signal_stage_from_month_in_progress(nxt, stage, why):
    df = _daily(_base(NEXT=nxt))                                  # 5월 전체 = 진행 월 (6월 봉 없음)
    r = rtm.detect(_ctx(df))
    assert r.detected and r.stage == stage and why in r.metrics["stage_note"]
    assert r.metrics["state"] == "signal" and r.pivot == 130.0


def test_forming_two_soldiers_and_month_in_progress_not_bull():
    df = _daily(_base(S3=(122, 123, 116, 117))).loc[:"2023-04-05"]
    r = rtm.detect(_ctx(df))
    assert r.detected and r.stage == FORMING and r.metrics["state"] == "forming"
    assert r.pivot == 122.0 and r.score == 30.0 + 4 * rtm.SCORE_TAG - rtm.SCORE_TAG * (not r.metrics["flags"]["tall_body"])
    assert any("셋째 대기" in x for x in r.reasons)
    off = rtm.detect(_ctx(df, rtm.RedThreeConfig(detect_forming=False)))
    assert not off.detected and off.metrics["state"] == "forming" and any("detect_forming" in w for w in off.warnings)


def test_advance_block_flag_warns_and_lowers_score():
    df = _daily(_base(S3=(122, 140, 119, 125))).loc[:"2023-05-03"]   # 셋째 위꼬리 15 ≥ 몸통 3
    r = rtm.detect(_ctx(df))
    assert r.detected and r.metrics["flags"]["adv_block"] is True and r.metrics["flags"]["short_upper"] is False
    assert any("어드밴스 블록" in w for w in r.warnings) and r.score < 90


# ---------------------------------------------------------------- 앞부분 불변
def _long_df() -> pd.DataFrame:
    tail = [(130, 138.5, 128, 138), (138, 139, 120, 124), (124, 126, 110, 112), (112, 113, 95, 98),   # 4번째 양봉 → 하락
            (98, 99, 90, 92), (92, 99, 91, 98), (98, 104, 97, 103), (103, 110, 102, 109), (109, 111, 104, 106),
            (106, 107, 96, 99), (99, 106, 97, 105)]
    rng = np.random.default_rng(3)
    df = _daily(_base(NEXT=(130, 138.5, 128, 138)) + tail[1:])
    noise = rng.normal(0, 0.004, len(df))
    for k in ("open", "high", "low", "close"):
        df[k] = df[k] * (1 + noise)
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)
    return df


def test_prefix_invariance_future_bars_never_change_past_judgement():
    df = _long_df()
    seen = set()
    for t in range(0, len(df), 4):
        a = rtm.evaluate(df, t)
        assert rtm.evaluate(_junk_after(df, t, seed=t), t) == a
        assert rtm.evaluate(df.iloc[:t + 1]) == a
        r = rtm.detect(_ctx(df.iloc[:t + 1]))
        assert r.metrics["state"] == a["state"] and r.stage == a["stage"]
        seen.add(a["state"])
    assert {"signal", "pending", "after_signal", "none"} <= seen        # 시험이 비어 있지 않다


def test_signals_replay_is_prefix_stable():
    df = _long_df()
    full = rtm.signals(df)
    assert [s["signal_month"] for s in full][:1] == ["2023-04"]
    for T in range(200, len(df) + 1, 9):
        part = rtm.signals(df.iloc[:T])
        asof = f"{df.index[T - 1]:%Y-%m-%d}"
        assert part == [s for s in full if s["known_date"] is not None and s["known_date"] <= asof]
    s0 = full[0]
    assert s0["known_date"] == "2023-05-01" and df.index[s0["known_i"]] == pd.Timestamp("2023-05-01")
    cal = rtm.signals(df, rtm.RedThreeConfig(complete_rule="calendar"))
    assert cal[0]["known_date"] == cal[0]["signal_date"] == "2023-04-28"


# ---------------------------------------------------------------- 장중 · 모름 · 제외
def test_partial_intraday_bar_is_ignored_for_judgement():
    """장중 미완성 봉의 종가는 판정에 안 쓴다(몸통 반납 = 종가 규칙은 마감 뒤에) — 저가가 확정 저점 위면 단계 그대로."""
    df = _daily(_base()).loc[:"2023-05-04"].copy()
    eod = rtm.evaluate(df.iloc[:-1])
    low_l = eod["low"]
    df.iloc[-1, df.columns.get_indexer(["open", "high", "low", "close"])] = [130.0, 130.0, low_l + 1, low_l + 2]   # 장중 급락
    ctx = _ctx(df)
    ctx.partial = True
    r = rtm.detect(ctx)
    assert r.detected and r.stage == BREAKOUT and r.metrics["state"] == eod["state"]
    assert "intraday_final" not in r.metrics
    assert any(w.startswith("장중") for w in r.warnings)
    mn = r.metrics["month_now"]
    assert mn["live_label"] == "장중 잠정" and mn["live_close"] == low_l + 2 and mn["close"] > 125


def test_partial_low_below_confirmed_low_is_final_failure():
    """저가 규칙(이번 달 저가 ≤ 확정 저점)은 장중 저가로 이미 정해진다 — 저가는 내려가기만 하니 마감 뒤 판정도 돌파 실패."""
    df = _daily(_base()).loc[:"2023-05-04"].copy()
    df.iloc[-1, df.columns.get_indexer(["open", "high", "low", "close"])] = [130.0, 130.0, 50.0, 60.0]   # 장중 폭락
    ctx = _ctx(df)
    ctx.partial = True
    r = rtm.detect(ctx)
    assert r.detected and r.stage == FAILED and r.metrics["state"] == rtm.evaluate(df.iloc[:-1])["state"]
    fin = r.metrics["intraday_final"]
    assert fin["low"] == 50.0 and fin["level"] == rtm.evaluate(df.iloc[:-1])["low"]
    assert r.stage_label.endswith("장중 확정(저가)") and r.warnings[0].startswith("장중 확정(저가)")
    # 마감 뒤(같은 봉을 완성 봉으로) 판정도 돌파 실패 — 장중 판단이 미래를 앞당긴 게 아니라 이미 정해진 사실
    ctx2 = _ctx(df)
    assert rtm.detect(ctx2).stage == FAILED


def test_partial_first_bar_of_new_month_gives_labelled_provisional_signal():
    df = _daily(_base()).loc[:"2023-05-01"]
    ctx = _ctx(df)
    ctx.partial = True
    r = rtm.detect(ctx)
    assert r.metrics["state"] == "pending" and r.stage == NEAR_PIVOT       # EOD 기준: 4월은 아직 미완성
    p = r.metrics["provisional"]
    assert p["label"] == "장중 잠정" and p["state"] == "signal" and p["signal_month"] == "2023-04"
    assert any(x.startswith("장중 잠정") for x in r.reasons)


def test_unknown_data_is_reported_not_fabricated():
    empty = _daily(_base()).iloc[:0]
    r = rtm.detect(_ctx(empty))
    assert not r.detected and r.metrics["state"] == "empty"
    two = _daily(_base()).loc[:"2022-02-10"]
    assert rtm.evaluate(two)["state"] == "too_short"
    # 바닥권 기준 창을 줄여 이력이 짧은 신호 — 직전 10개월 평균이 필요한 꼬리표 · 연중 위치는 '모름'(0점)
    df = _daily(DEC[8:] + [LOW, S1, S2, S3, NEXT], start="2022-09").loc[:"2023-05-03"]
    cfg = rtm.RedThreeConfig(bottom_lookback=3)
    r = rtm.detect(_ctx(df, cfg))
    f = r.metrics["flags"]
    assert r.detected and r.metrics["state"] == "signal"
    assert f["short_upper"] is None and f["tall_body"] is None and f["yearly_pos"] is None
    assert set(r.metrics["score_unknown"]) == {"short_upper", "tall_body", "yearly_low_third"}
    assert r.score == 50 + 2 * rtm.SCORE_TAG                         # 저가 상승 · 어드밴스 블록 아님만
    assert any("모름" in w for w in r.warnings) and any("짧은 위꼬리 모름" in x for x in r.reasons)
    json.dumps(r.to_dict(), ensure_ascii=False)


@pytest.mark.parametrize("name", ["하나금융스팩30호", "KODEX 200", "맥쿼리인프라리츠", "TIGER 미국S&P500"])
def test_spac_etf_reit_excluded(name):
    r = rtm.detect(_ctx(_daily(_base()).loc[:"2023-05-03"], name=name))
    assert not r.detected and r.metrics["state"] == "excluded" and any("[11:00]" in w for w in r.warnings)


def test_index_hook_market_context_and_zero_volume_index():
    df = _daily(_base()).loc[:"2023-05-03"].copy()
    m = tq.market_context(df, "KOSPI", red3=rtm.judge_monthly)
    assert m["red3_monthly"]["state"] == "signal" and m["red3_monthly"]["signal_month"] == "2023-04"
    df["volume"] = 0.0                                             # 지수 거래량이 비어도 (market_context 는 0 행 유지)
    m0 = tq.market_context(df, "KOSPI", red3=rtm.judge_monthly)
    assert m0["red3_monthly"]["state"] == "signal"
    json.dumps(m0["red3_monthly"], ensure_ascii=False)


def test_runs_inside_registry_on_random_daily_bars():
    df = make_ohlcv([(0, 100), (300, 70), (500, 120)], seed=5)
    res = run_all(make_context(df), names=[rtm.NAME])[rtm.NAME]
    assert not any("탐지 오류" in w for w in res.warnings)
    assert res.metrics["rule_version"] == "red3m_v1" and res.metrics["state"] in rtm.STATE_LABELS
    json.dumps(res.to_dict(), ensure_ascii=False)
