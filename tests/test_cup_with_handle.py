"""컵 앤 핸들 어댑터(patterns/cup_with_handle.py) — 식(cwh_reference)의 결과를 바꾸지 않고 Tech 단계로 옮기는지.

자료는 식 파일의 synthetic_bars() (식 자체 시험과 같은 그림): x−1 = READY, x = 거래량 동반 돌파, 그 뒤 6봉 상승."""
from dataclasses import replace

import pandas as pd
import pytest

from chart_screener import krx
from chart_screener.patterns import REGISTRY, run_all
from chart_screener.patterns import cup_with_handle as cwh
from chart_screener.patterns import cwh_reference as ref
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.scanner import ScanResult, scan_one, to_frame
from synthetic import make_context

BARS = ref.synthetic_bars()
X = len(BARS) - 7                     # 돌파일


def _df(bars) -> pd.DataFrame:
    df = pd.DataFrame({"open": [b.open for b in bars], "high": [b.high for b in bars], "low": [b.low for b in bars],
                       "close": [b.close for b in bars], "volume": [b.volume for b in bars]},
                      index=pd.DatetimeIndex([pd.Timestamp(b.date) for b in bars]))
    df["value"] = df["close"] * df["volume"]
    return df


def _ctx(bars, end, index=False, **kw):
    ctx = make_context(_df(bars[:end + 1]), **kw)
    if not index:
        ctx.index_df = None
    return ctx


def _run(bars, end, **kw):
    return cwh.detect(_ctx(bars, end, **kw))


def _formula(bars, end):
    c = ref.Context(bars[:end + 1], ref.Config())
    return ref.latest_scan(c, "TEST", end, tick_table=krx.TICK_TABLE)


def test_registered_with_new_key_and_label():
    assert REGISTRY["cup_with_handle"][0] == "컵 앤 핸들 (사용자 식)"   # 옛 탐지기 라벨 '컵 앤 핸들'과 구별
    assert "cup_handle" not in REGISTRY                    # 옛 탐지기 키는 쓰지 않는다 (일지 · 기록 채점 분리)
    assert (cwh.NEAR_PCT, cwh.FAIL_PCT, cwh.WINDOW) == (0.05, 0.03, 5)   # base.classify_stage 기본값
    assert ref.Config().buy_zone_max == 0.05                # 매수 범위 · 이격 과다는 식의 값(진입가 기준)
    r = _run(BARS, X - 1)
    assert r.reasons[0].startswith("사용자 식 cwh_reference_v1.0.0") and r.label == "컵 앤 핸들 (사용자 식)"


def test_ready_maps_to_near_pivot_and_keeps_formula_values():
    r = _run(BARS, X - 1)
    p = _formula(BARS, X - 1)[0]
    assert p["state"] == "READY"
    assert r.detected and r.stage == NEAR_PIVOT                  # 종가 95.8 ≥ 피벗 98.25 × 0.95
    assert r.pivot == p["pivot_price"] and r.score == p["quality_score"] and r.stop is None
    assert r.breakout_date is None and r.start_date == p["left_peak_date"] and r.end_date == p["as_of"]
    m = r.metrics
    assert m["state"] == "READY" and m["rule_version"] == "cwh_reference_v1.0.0"
    for k in ("cup_depth", "handle_depth", "base_weeks", "entry_price", "cup_low", "score_coverage"):
        assert m[k] == p[k], k
    assert any(w.startswith("손절 규칙 없음") for w in r.warnings)
    assert cwh.VOL_RAW in r.warnings                             # 미수정 거래량 · 무상증자 미감지 한계 — 결과마다
    assert "volume_unverified" not in m and "attempt_consumed" not in m      # 사건 없는 READY
    kinds = {a["kind"] for a in r.annotations}
    assert kinds == {"segment", "box", "hline"}


def test_far_below_pivot_is_forming():
    bs = list(BARS)
    bs[X - 1] = replace(bs[X - 1], open=93.0, high=93.5, low=92.6, close=93.0)    # 피벗 × 0.95 = 93.34 아래
    r = _run(bs, X - 1)
    assert r.detected and r.metrics["state"] == "READY" and r.stage == FORMING
    bs[X - 1] = replace(bs[X - 1], open=93.4, high=93.7, low=93.2, close=93.4)    # 93.34 위 → 피벗 근접
    assert _run(bs, X - 1).stage == NEAR_PIVOT


def test_breakout_day_and_following_bars():
    r = _run(BARS, X)
    assert r.detected and r.stage == BREAKOUT and r.breakout_date == str(BARS[X].date)
    assert r.metrics["state"] == "BREAKOUT_CONFIRMED" and r.metrics["bars_since_event"] == 0
    assert r.metrics["breakout_rvol"] >= 1.4
    ev = [p for p in _formula(BARS, X) if p.get("event_date")][0]
    assert r.pivot == ev["pivot_price"] and r.metrics["entry_price"] == ev["entry_price"] == 99.0   # 호가 1원
    # 식은 다음 날부터 이 구조를 내지 않는다 — 어댑터는 같은 식 함수로 지난 사건을 다시 잰다
    assert _formula(BARS, X + 1) == [] or all(p["state"] != "READY" for p in _formula(BARS, X + 1))
    assert r.metrics["attempt_consumed"] is False and r.metrics["volume_unverified"] is False
    r1 = _run(BARS, X + 1)
    assert r1.stage == BREAKOUT and r1.metrics["bars_since_event"] == 1 and r1.breakout_date == str(BARS[X].date)
    assert cwh.CARRIED in r1.warnings                            # 식은 이 구조를 더 내지 않음 — Tech 5봉 창
    # 매수 범위는 식처럼 진입가 기준: 종가 103.6 은 피벗 × 1.05 = 103.16 위지만 진입가 × 1.05 = 103.95 안 → 돌파
    r3 = _run(BARS, X + 3)
    assert r3.stage == BREAKOUT and r3.metrics["bars_since_event"] == 3
    r4 = _run(BARS, X + 4)                                       # 종가 105.1 > 진입가 × 1.05
    assert r4.stage == EXTENDED and r4.metrics["bars_since_event"] == 4
    assert not _run(BARS, X + 5).detected                        # 돌파 창(5봉) 밖


def test_after_breakout_fail_and_retest():
    bs = list(BARS)
    bs[X + 2] = replace(bs[X + 2], open=96.0, high=96.5, low=93.5, close=94.0)     # < 피벗 × 0.97 = 95.3
    r = _run(bs, X + 2)
    assert r.detected and r.stage == FAILED and r.metrics["state"] == "BREAKOUT_CONFIRMED"
    bs[X + 2] = replace(bs[X + 2], open=98.5, high=99.0, low=97.5, close=98.0)     # 진입가 아래 · −3% 안 = 재시험
    r = _run(bs, X + 2)
    assert r.stage == NEAR_PIVOT and any("재시험" in x for x in r.reasons)


def test_weak_volume_price_breakout_is_not_a_breakout():
    bs = list(BARS)
    bs[X] = replace(bs[X], volume=100_000)
    r = _run(bs, X)
    assert r.metrics["state"] == "PRICE_BREAKOUT"
    assert r.detected and r.stage == NEAR_PIVOT and r.breakout_date is None
    assert any("돌파 아님" in x and "미달" in x for x in r.reasons)
    assert cwh.CONSUMED_NEXT in r.warnings and r.metrics["attempt_consumed"] is True
    assert {a["text"] for a in r.annotations if a["kind"] == "marker"} == {"돌파 시도"}
    # 다음 날: 식은 이 구조를 내지 않는다 → 식처럼 탐지하지 않고 이유를 남긴다 ('피벗 근접'으로 대기시키지 않음)
    r2 = _run(bs, X + 1)
    assert not r2.detected and r2.breakout_date is None
    assert any("식에서는 이 시도로" in w and "탐지 안 함" in w and "그 뒤" not in w for w in r2.warnings)


def test_unconfirmed_attempt_then_volume_close_is_reported_not_counted():
    """가격만 돌파(거래량 미달) 다음 날 거래량 동반 종가 돌파 — 식은 그 구조를 판정하지 않으므로 '돌파'로 세지 않되 사실은 적는다."""
    bs = list(BARS)
    bs[X] = replace(bs[X], volume=100_000)
    bs[X + 1] = replace(bs[X + 1], open=99.5, high=101.5, low=99.2, close=101.0, volume=3_000_000)
    assert all(p.get("state") != "BREAKOUT_CONFIRMED" for p in _formula(bs, X + 1))
    r = _run(bs, X + 1)
    assert not r.detected and r.stage is None and r.breakout_date is None
    w = [x for x in r.warnings if "식에서는 이 시도로" in x]
    assert len(w) == 1 and f"그 뒤 {BARS[X + 1].date}" in w[0] and "'돌파 확인'으로 세지 않음" in w[0]
    assert "아직 없음" not in w[0]


def test_extended_with_volume_is_reported_as_passed_and_carried_only_while_extended():
    bs = list(BARS)
    bs[X] = replace(bs[X], open=99.0, high=106.0, low=98.9, close=105.5, volume=3_000_000)   # +6.6%, RVOL 3.27
    r = _run(bs, X)
    assert r.metrics["state"] == "EXTENDED" and r.stage == EXTENDED and r.breakout_date is None
    assert any("통과" in x and "매수 범위 밖" in x for x in r.reasons)
    assert {a["text"] for a in r.annotations if a["kind"] == "marker"} == {"진입가 넘음 · 이격"}
    bs[X + 1] = replace(bs[X + 1], open=105.5, high=106.5, low=105.0, close=106.0, volume=1_000_000)
    r1 = _run(bs, X + 1)                                         # 1봉 뒤에도 진입가 +5% 위 → 이격 과다로 이어 보임
    assert r1.detected and r1.stage == EXTENDED and r1.metrics["bars_since_event"] == 1 and cwh.CARRIED in r1.warnings
    assert not any("미달" in x or "아직 없음" in x for x in r1.reasons)
    bs[X + 1] = replace(bs[X + 1], open=101.0, high=101.5, low=99.5, close=100.0, volume=1_000_000)
    r1 = _run(bs, X + 1)                                         # 매수 범위로 돌아옴 — 식은 판정하지 않음 → 탐지 안 함
    assert not r1.detected
    assert any("통과" in w and "매수 범위를 다시 판정하지 않음" in w for w in r1.warnings)


def test_extended_without_volume_is_not_carried():
    bs = list(BARS)
    bs[X] = replace(bs[X], open=99.0, high=106.0, low=98.9, close=105.5, volume=100_000)
    r = _run(bs, X)
    assert r.metrics["state"] == "EXTENDED" and r.stage == EXTENDED and any("미달" in x for x in r.reasons)
    bs[X + 1] = replace(bs[X + 1], open=105.5, high=106.5, low=105.0, close=106.0, volume=100_000)
    assert not _run(bs, X + 1).detected


def test_buy_zone_boundary_uses_entry_price():
    """종가가 (피벗 × 1.05, 진입가 × 1.05] 이면 식은 매수 범위 안 — Tech 도 이격 과다로 부르지 않는다."""
    bs = list(BARS)
    bs[X] = replace(bs[X], open=99.0, high=103.8, low=98.9, close=103.5, volume=100_000)      # 피벗 × 1.05 = 103.16
    p = [q for q in _formula(bs, X) if q.get("event_date")][0]
    assert p["state"] == "PRICE_BREAKOUT" and p["within_buy_zone"]
    assert _run(bs, X).stage == NEAR_PIVOT
    bs[X] = replace(bs[X], open=99.0, high=103.6, low=98.9, close=103.4, volume=3_000_000)
    assert _run(bs, X).stage == BREAKOUT
    bs[X + 1] = replace(bs[X + 1], open=103.4, high=103.6, low=103.0, close=103.4, volume=1_000_000)
    assert _run(bs, X + 1).stage == BREAKOUT                     # 같은 종가 다음 날에도 돌파 (이격 과다로 뒤집히지 않음)
    bs[X + 1] = replace(bs[X + 1], open=103.4, high=104.2, low=103.0, close=104.0, volume=1_000_000)
    assert _run(bs, X + 1).stage == EXTENDED                     # 104.0 > 진입가 99 × 1.05 = 103.95


def test_intraday_cross_close_failed():
    bs = list(BARS)
    bs[X] = replace(bs[X], close=97.5)
    r = _run(bs, X)
    assert r.metrics["state"] == "VOLUME_CONFIRMED_CLOSE_FAILED" and r.stage == NEAR_PIVOT and r.breakout_date is None
    assert any("종가 미달" in x for x in r.reasons)


def test_cup_floor_break_is_not_detected_but_explained():
    bs = list(BARS)
    bs[X] = replace(bs[X], low=70)
    r = _run(bs, X)
    assert not r.detected and any("INVALIDATED" in w and "피벗 98" in w for w in r.warnings)
    assert any("순서 모름" in w for w in r.warnings)             # 같은 봉에서 진입가도 넘음 (식의 same_bar_order_unknown)


def test_benchmark_unknown_is_not_fabricated():
    r = _run(BARS, X - 1)
    assert r.metrics["rs_high_ratio"] is None and r.metrics["score_coverage"] == 0.8 and r.metrics["benchmark"] is None
    assert any("지수 자료 없음" in w for w in r.warnings)
    ri = _run(BARS, X - 1, index=True)                            # 소속 시장 지수가 있으면 RS · 시장 항목을 잰다
    assert ri.metrics["score_coverage"] == 1.0 and ri.metrics["rs_high_ratio"] is not None
    assert ri.metrics["benchmark"] == "KOSPI"


def test_halt_days_are_reinserted_as_zero_volume_bars():
    df = _df(BARS[:X])
    gone = df.index[120:122]
    cut = df.drop(gone)
    cut.attrs["halt_dates"] = [f"{d:%Y-%m-%d}" for d in gone]
    ctx = make_context(cut)
    bars, halts = cwh.to_bars(ctx)
    assert len(bars) == X and [str(bars[i].date) for i in halts] == cut.attrs["halt_dates"]
    prev = float(df["close"].iloc[119])
    assert all(bars[i].volume == 0 and bars[i].open == bars[i].close == bars[i].high == bars[i].low == prev for i in halts)
    ctx.index_df = None
    r = cwh.detect(ctx)
    assert r.detected and r.metrics["zero_volume_fraction50"] == pytest.approx(2 / 50)
    assert any("거래정지" in w and "분할" in w for w in r.warnings)


def _halted_ctx(end, gone=slice(120, 122)):
    df = _df(BARS[:end + 1])
    idx = df.index[gone]
    cut = df.drop(idx)
    cut.attrs["halt_dates"] = [f"{d:%Y-%m-%d}" for d in idx]
    ctx = make_context(cut)
    ctx.index_df = None
    return ctx


def test_halt_inside_breakout_rvol_window_is_not_counted_as_breakout():
    """RVOL 비교 구간(직전 50봉)에 거래정지 — 분할 · 병합이면 미수정 거래량이라 RVOL 이 틀린다. 식 상태는 보이되 '돌파'로 세지 않는다."""
    assert X - 50 <= 120 < X
    r = cwh.detect(_halted_ctx(X))
    assert r.detected and r.metrics["state"] == "BREAKOUT_CONFIRMED" and r.metrics["breakout_rvol"] >= 1.4
    assert r.stage == NEAR_PIVOT and r.breakout_date is None
    assert r.metrics["volume_unverified"] is True and r.metrics["attempt_consumed"] is True
    assert any("거래량 확인으로 세지 않음" in w and "거래정지" in w for w in r.warnings)
    assert {a["text"] for a in r.annotations if a["kind"] == "marker"} == {"돌파 시도"}
    r1 = cwh.detect(_halted_ctx(X + 1))                          # 다음 날: 이어 보이지 않는다(식에서도 구조 끝남)
    assert not r1.detected and any("식에서는 이 시도로" in w and "거래정지" in w for w in r1.warnings)
    ok = cwh.detect(_halted_ctx(X, gone=slice(X - 70, X - 68)))  # 정지일이 RVOL 구간 밖이면 그대로 돌파
    assert ok.stage == BREAKOUT and ok.metrics["volume_unverified"] is False


def test_many_halts_fail_formula_zero_volume_rule():
    df = _df(BARS[:X])
    gone = df.index[120:126]                                     # 최근 50봉 중 6봉 = 12% > 10%
    cut = df.drop(gone)
    cut.attrs["halt_dates"] = [f"{d:%Y-%m-%d}" for d in gone]
    ctx = make_context(cut)
    ctx.index_df = None
    r = cwh.detect(ctx)
    assert not r.detected
    assert any("zero_volume_fraction" in w and "12.0%" in w for w in r.warnings)


def test_partial_bar_is_provisional():
    ctx = _ctx(BARS, X)
    ctx.partial, ctx.session_frac = True, 0.5                    # 오늘(X) 봉은 장중 — 거래량은 하루치로 환산
    r = cwh.detect(ctx)
    assert r.detected and r.stage == BREAKOUT and r.metrics["provisional"] is True
    assert r.metrics["structure_as_of"] == str(BARS[X - 1].date)
    assert any("장중 잠정" in w for w in r.warnings)
    bs = list(BARS)
    bs[X] = replace(bs[X], volume=100_000)
    ctx = _ctx(bs, X)
    ctx.partial, ctx.session_frac = True, 0.5                    # 장중 가격만 돌파 — 아직 끝난 시도가 아니다
    r = cwh.detect(ctx)
    assert r.metrics["state"] == "PRICE_BREAKOUT" and r.metrics["attempt_consumed"] is False
    assert any(w.startswith("장 마감 봉도 진입가를 넘으면") for w in r.warnings)
    ctx = _ctx(BARS, X - 1)
    ctx.partial, ctx.session_frac = True, 0.5                    # 어제까지 완성 봉으로 구조, 오늘 봉은 피벗 아래
    r = cwh.detect(ctx)
    assert r.detected and r.metrics["state"] == "READY" and r.end_date == str(BARS[X - 2].date)
    assert any("장중 스캔" in w for w in r.warnings)


def test_include_rejected_does_not_change_valid_structures():
    """어댑터가 '왜 아닌지' 설명 때문에 include_rejected=True 로 부르지만, 유효 구조 · 사건은 기본 호출과 같아야 한다."""
    for end in range(X - 30, len(BARS)):
        c = ref.Context(BARS[:end + 1], ref.Config())
        a = ref.latest_scan(c, "T", end, tick_table=krx.TICK_TABLE)
        b = ref.latest_scan(c, "T", end, tick_table=krx.TICK_TABLE, include_rejected=True)
        assert ref.clean([p for p in b if p["structure_valid"]]) == ref.clean(a), end


@pytest.mark.parametrize("scale", [None, "weak", "dip"])
def test_cross_gate_is_a_necessary_condition(scale):
    bs = list(BARS)
    if scale == "weak":
        bs[X] = replace(bs[X], volume=100_000)
    elif scale == "dip":
        bs[X + 1] = replace(bs[X + 1], open=99.0, high=99.5, low=97.0, close=97.2)
    c = ref.Context(bs, ref.Config())
    for d in range(30, len(bs)):
        if cwh._events_on(c, "T", d, krx.TICK_TABLE):
            assert cwh._may_cross(c, d), d


def test_bad_ohlc_is_reported_as_detector_error():
    df = _df(BARS[:X])
    df.iloc[100, df.columns.get_loc("high")] = df["low"].iloc[100] - 1      # 고가 < 저가
    ctx = make_context(df)
    with pytest.raises(ValueError, match="식 입력 자료 오류"):
        cwh.detect(ctx)
    res = run_all(make_context(df), ["cup_with_handle"])["cup_with_handle"]
    assert not res.detected and res.warnings[0].startswith("탐지 오류")


def test_scan_one_has_no_buy_plan_and_frame_says_why():
    s = scan_one(_ctx(BARS, X, rs=90))
    assert s.lead().name == "cup_with_handle" and s.score.best_stage == BREAKOUT
    assert s.position is None and s.entry_risk()[1] is None
    scan = ScanResult(asof=s.ctx.df.index[-1], generated_at=pd.Timestamp("2026-10-14 16:00"), market={},
                      stocks=[s], scanned=1, elapsed=0.0, patterns=list(REGISTRY))
    row = to_frame(scan).iloc[0]
    assert row["대표패턴"] == "컵 앤 핸들 (사용자 식)" and row["단계"] == "돌파" and row["진입계획"].startswith("손절 규칙 없는 식")
