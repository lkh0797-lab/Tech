"""장기 횡보 후 대량거래 장대양봉 돌파 (long_base_breakout) 테스트."""
import dataclasses

import numpy as np
import pandas as pd
import pytest

from chart_screener.config import Config
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.flat_base import krx_tick
from chart_screener.patterns.long_base_breakout import (LongBaseBreakoutConfig, detect, find_breakouts,
                                                        parse_score_parts)
from synthetic import make_context, make_ohlcv, set_bar

# 0~100: 16000 → 10000 하락, 이후 약 9,100 ~ 10,900 박스 200일 (설계상 박스 상단 ≈ 10,900)
BASE_WP = [(0, 16000), (100, 10000), (130, 10900), (160, 9200), (190, 10800), (220, 9100),
           (250, 10900), (280, 9400), (299, 10700)]
DESIGN_TOP = 10900
BO = dict(open=10750, high=12350, low=10700, close=12300, volume=4_000_000)  # +15%, 거래량 ~13배, ~470억


def base_df(wp=BASE_WP, n=300, seed=1, vol_segments=None, vol_base=300_000) -> pd.DataFrame:
    return make_ohlcv(wp, n=n, seed=seed, vol_base=vol_base, vol_segments=vol_segments)


def extend(df: pd.DataFrame, bars: list[dict]) -> pd.DataFrame:
    """df 뒤에 봉을 이어 붙인다. bars: [{open, high, low, close, volume}, ...]"""
    for b in bars:
        idx = pd.bdate_range(df.index[-1], periods=2)[1:]
        row = pd.DataFrame({k: [df[k].iloc[-1]] for k in df.columns}, index=idx)
        df = pd.concat([df, row])
        df = set_bar(df, len(df) - 1, **b)
    return df


def bar(c, v=400_000, o=None, rng=0.01):
    o = c if o is None else o
    return dict(open=o, high=max(o, c) * (1 + rng / 2), low=min(o, c) * (1 - rng / 2), close=c, volume=v)


def run(df, rs=85, cfg=None, **kw):
    return detect(make_context(df, rs=rs, cfg=cfg, **kw))


def parts(r):
    """metrics.score_parts(표시 문자열) → {항목: 점수} (0 항목은 생략되므로 .get(k, 0) 으로 읽는다)."""
    return parse_score_parts(r.metrics["score_parts"])


def is_tick_ceil(price, raw):
    """price 가 raw 이상인 가장 가까운 KRX 호가인지 (피벗·지지선 반올림 규칙)."""
    t = krx_tick(raw)
    return raw <= price < raw + t + 1e-6 and abs(price / krx_tick(price) - round(price / krx_tick(price))) < 1e-9


def is_tick_floor(price, raw):
    """price 가 raw 이하인 가장 가까운 KRX 호가인지 (손절가 반올림 규칙)."""
    t = krx_tick(raw)
    return raw - t - 1e-6 < price <= raw and abs(price / krx_tick(price) - round(price / krx_tick(price))) < 1e-9


# ---------------------------------------------------------------- (a) 교과서 돌파
def test_textbook_breakout_detected():
    df = extend(base_df(), [BO])
    r = run(df)
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT
    assert abs(r.pivot / DESIGN_TOP - 1) < 0.03
    m = r.metrics
    assert m["base_days"] >= 180 and m["box_height"] < 0.30
    assert m["vol_mult_50d"] >= 5 and m["value_eok"] >= 300
    assert m["days_since_breakout"] == 0 and m["pre_breakout"] is False
    assert r.breakout_date == r.end_date == df.index[-1].strftime("%Y-%m-%d")
    # 손절 = max(몸통 중간값, 박스 상단 -8%) → 몸통 중간값 (10750+12300)/2 = 11,525
    # (재보정: 손절은 호가 단위로 내림 → 11,520, 피벗은 박스 상단을 호가 단위로 올림)
    assert r.stop == 11520 and is_tick_floor(r.stop, (10750 + 12300) / 2)
    assert is_tick_ceil(r.pivot, r.metrics["box_top"])
    # 재보정(2024-26 표본 근거): 예전 점수는 50↑ 였으나, 이 합성 사례는 중간 위치·거래대금 471억(<500억)·
    # 정배열 아님·+15% strong 캔들이라 '평균적인 돌파' 수준(기준 40 근처)이 맞다.
    assert 30 <= r.score <= 60
    assert r.score == pytest.approx(sum(parts(r).values()), abs=0.11)
    kinds = {a["kind"] for a in r.annotations}
    assert {"box", "hline", "marker"} <= kinds
    assert any("억" in a.get("text", "") for a in r.annotations if a["kind"] == "marker")
    assert all(s.startswith("✔ ") for s in r.reasons)


def test_find_breakouts_matches_detect_and_no_lookahead():
    df = extend(base_df(), [BO, bar(12400, 1_000_000), bar(12200, 700_000)])
    ctx = make_context(df, rs=85)
    evs = find_breakouts(ctx)
    assert len(evs) == 1
    ev = evs[0]
    assert ev["i"] == 300 and ev["date"] == df.index[300].strftime("%Y-%m-%d")
    for k in ("base_days", "box_top", "box_bottom", "box_height", "base_drift", "vol_mult_50d", "value_eok",
              "candle_mid", "position", "score"):
        assert k in ev
    # 돌파일까지 자른 데이터로 계산해도 같은 이벤트 (미래 참조 없음)
    ev_cut = find_breakouts(make_context(df.iloc[:301], rs=85))[0]
    assert ev_cut["box_top"] == pytest.approx(ev["box_top"]) and ev_cut["base_days"] == ev["base_days"]
    r = detect(ctx)
    assert r.breakout_date == ev["date"] and is_tick_ceil(r.pivot, ev["box_top"])   # 피벗 = 상단 호가 올림


# ---------------------------------------------------------------- (b) 단계
def test_stage_breakout_holding_few_bars():
    df = extend(base_df(), [BO, bar(12400, 1_200_000), bar(12250, 800_000), bar(12350, 700_000)])
    r = run(df)
    assert r.detected and r.stage == BREAKOUT
    assert r.metrics["days_since_breakout"] == 3 and r.metrics["hold_above_mid"] is True


def test_stage_extended():
    run_up = [bar(c, 1_500_000) for c in (12900, 13500, 14000, 14600, 15100)]
    r = run(extend(base_df(), [BO] + run_up))
    assert r.detected and r.stage == EXTENDED
    assert any("매수 한도" in w for w in r.warnings)


def test_stage_failed_back_into_box():
    r = run(extend(base_df(), [BO, bar(11800, 1_500_000), bar(11000, 1_200_000), bar(10300, 900_000)]))
    assert r.detected and r.stage == FAILED
    assert r.score < 70


def test_stage_failed_by_50pct_rule():
    # 박스 상단 위지만 장대양봉 몸통 중간값(11,525) 아래 마감 → 50% 룰 실패
    r = run(extend(base_df(), [BO, bar(11800, 1_500_000), bar(11400, 1_000_000)]))
    assert r.detected and r.stage == FAILED
    assert any("50%" in w for w in r.warnings)


def test_stage_pullback_retest_on_dry_volume():
    after = [bar(12900, 1_500_000), bar(13500, 1_200_000), bar(13000, 600_000), bar(12500, 500_000),
             bar(12100, 400_000), bar(11850, 350_000)]
    r = run(extend(base_df(), [BO] + after))
    assert r.detected and r.stage == NEAR_PIVOT
    assert r.metrics["pullback"] is True
    assert any("눌림목" in s for s in r.reasons)


def test_stage_near_pivot_holding_after_window():
    # 5봉 이후 지지선(장대양봉 50% 11,525) +5% 이내에서 버팀 → near_pivot (재진입 관점)
    after = [bar(c, 600_000) for c in (12100, 11950, 11900, 12000, 11850, 11950, 11900, 12050)]
    r = run(extend(base_df(), [BO] + after))
    assert r.detected and r.stage == NEAR_PIVOT
    assert r.metrics["pullback"] is False and r.metrics["days_since_breakout"] == 8
    assert r.metrics["post_state"] == "holding"
    assert r.metrics["hold_zone"] == pytest.approx((10750 + 12300) / 2 * 1.05)


def test_holding_far_above_pivot_after_window_is_extended():
    # 회귀: 5봉이 지난 뒤 박스 상단 +25% 에서 버티는 종목을 near_pivot(매수 후보)로 표시하던 문제
    after = [bar(c, 700_000) for c in (13400, 13600, 13500, 13700, 13550, 13650, 13600, 13700)]
    r = run(extend(base_df(), [BO] + after))
    assert r.detected and r.stage == EXTENDED
    assert r.metrics["dist_from_pivot"] > 0.2
    assert any("지지선" in w for w in r.warnings)


def test_close_back_below_pivot_within_window_is_retest_not_breakout():
    # 회귀: 몸통이 박스 안 깊이에서 시작한 장대양봉(50% < 상단) 다음 날 종가가 피벗 아래(실패선 위)로 되밀리면
    # breakout 이 아니라 재시험(near_pivot)
    deep = dict(open=9900, high=11550, low=9850, close=11500, volume=4_000_000)
    df = extend(base_df(), [deep])
    r0 = run(df)
    assert r0.stage == BREAKOUT
    mid, top = r0.metrics["candle_mid"], r0.pivot
    assert mid < top * 0.99
    c = max(mid, top * 0.97) * 1.003
    r = run(extend(df, [bar(c, 900_000)]))
    assert r.detected and r.stage == NEAR_PIVOT and r.metrics["post_state"] == "retest"
    assert c < r.pivot
    assert any("피벗 아래" in w for w in r.warnings)


def test_pre_breakout_watch_near_pivot():
    # 박스 상단 근처로 올라오며 거래량 증가 (아직 장대양봉 없음)
    approach = [bar(c, v, o=c * 0.99) for c, v in
                ((10450, 600_000), (10550, 700_000), (10500, 450_000), (10650, 800_000), (10700, 900_000))]
    r = run(extend(base_df(n=295), approach))
    assert r.detected and r.stage == NEAR_PIVOT
    assert r.metrics["pre_breakout"] is True
    assert abs(r.pivot / DESIGN_TOP - 1) < 0.03
    assert is_tick_floor(r.stop, r.metrics["box_top"] * 0.92)   # 손절 = 상단 -8% 의 호가 내림 (재보정)
    assert is_tick_ceil(r.pivot, r.metrics["box_top"])
    assert r.score <= 60
    assert r.breakout_date is None


def test_pre_breakout_watch_forming():
    approach = [bar(c, v, o=c * 0.99) for c, v in
                ((10000, 600_000), (10100, 700_000), (10050, 450_000), (10150, 800_000), (10200, 900_000))]
    r = run(extend(base_df(n=295), approach))
    assert r.detected and r.stage == FORMING and r.metrics["pre_breakout"] is True


def test_no_watch_without_volume_expansion():
    approach = [bar(c, 280_000, o=c * 0.995) for c in (10450, 10550, 10500, 10650, 10700)]
    r = run(extend(base_df(n=295), approach))
    assert not r.detected
    assert any("거래량" in w for w in r.warnings)


def test_gap_limit_up_candle_accepted():
    # 점상한가에 가까운 갭 상승(+29%): 몸통 조건 면제, 50% 기준은 전일 종가~종가 중간값
    prev = 10700
    gap = dict(open=13700, high=13800, low=13650, close=13800, volume=4_000_000)
    r = run(extend(base_df(), [gap]))
    assert r.detected and r.metrics["limit_up"] is True
    assert r.metrics["candle_mid"] == pytest.approx((min(13700, prev) + 13800) / 2, rel=0.01)


# ---------------------------------------------------------------- (c) 탈락 사례
def _no_breakout(r):
    return not (r.detected and r.breakout_date)


def test_reject_short_base():
    # 급등 후 45일 횡보만 존재 → 60일 이상 구간은 급등 구간을 포함해 박스 높이 초과
    wp = [(0, 7000), (240, 7200), (255, 10500), (270, 9900), (285, 10400), (299, 10300)]
    df = extend(make_ohlcv(wp, n=300, seed=2, vol_base=300_000, smooth=False), [BO])
    r = run(df)
    assert not r.detected
    assert any("유효 베이스 없음" in w for w in r.warnings)


def test_reject_tall_box():
    wp = [(0, 10000), (40, 7000), (80, 11500), (120, 7000), (160, 11500), (200, 7200), (240, 11300),
          (270, 7300), (299, 10700)]
    r = run(extend(make_ohlcv(wp, n=300, seed=3, vol_base=300_000), [dict(BO, open=10900, low=10850)]))
    assert _no_breakout(r)


def test_reject_trending_base():
    wp = [(0, 6000), (299, 10700)]  # 꾸준한 상승 추세 (횡보 아님)
    r = run(extend(make_ohlcv(wp, n=300, seed=4, vol_base=300_000, smooth=False), [BO]))
    assert not r.detected


def test_reject_descending_channel():
    # 진폭 ±2% 로 꾸준히 내려가는 하락 채널: 짧은 구간은 박스처럼 보여도 |추세|/높이 > 60%
    wp = [(0, 13500), (100, 13000)] + [(i, (13000 - 17 * (i - 100)) * (1 + 0.02 * np.sin((i - 100) / 6)))
                                        for i in range(105, 296, 5)] + [(299, 9700)]
    df = extend(make_ohlcv(wp, n=300, seed=5, vol_base=300_000),
                [dict(open=9750, high=11250, low=9700, close=11200, volume=4_000_000)])
    r = run(df)
    assert _no_breakout(r)
    assert any("채널" in w for w in r.warnings)
    # 채널 규칙을 끄면 같은 캔들이 돌파로 잡힌다 (규칙 단독 효과 확인)
    off = Config(patterns={"long_base_breakout": LongBaseBreakoutConfig(max_drift_ratio=10.0)})
    assert run(df, cfg=off).stage == BREAKOUT


def test_reject_weak_candle():
    weak = dict(open=10700, high=11150, low=10650, close=11120, volume=4_000_000)  # +3.9%
    r = run(extend(base_df(), [weak]))
    assert _no_breakout(r)


def test_reject_low_volume():
    r = run(extend(base_df(), [dict(BO, volume=600_000)]))  # 약 2배
    assert not r.detected
    assert any("거래량" in w for w in r.warnings)


def test_reject_low_trading_value():
    # 가격 1/10 → 거래대금 약 47억 (< 300억)
    df = base_df()
    for k in ("open", "high", "low", "close"):
        df[k] = df[k] / 10
    df["value"] = (df["high"] + df["low"] + df["close"]) / 3 * df["volume"]
    big = {k: (v / 10 if k != "volume" else v) for k, v in BO.items()}
    r = run(extend(df, [big]))
    assert not r.detected
    assert any("거래대금" in w for w in r.warnings)


def test_value_threshold_from_global_config():
    cfg = Config(big_value_threshold=1000 * 1e8)  # 1000억으로 상향 → 470억 돌파는 탈락
    r = run(extend(base_df(), [BO]), cfg=cfg)
    assert _no_breakout(r)


def test_reject_long_upper_wick():
    wick = dict(open=10750, high=13500, low=10700, close=11600, volume=4_000_000)
    r = run(extend(base_df(), [wick]))
    assert _no_breakout(r)


def test_reject_old_breakout_outside_recent_window():
    after = [bar(12300 + 20 * k, 500_000) for k in range(30)]
    r = run(extend(base_df(), [BO] + after))
    assert _no_breakout(r)
    # 이력 전체 탐색(백테스트용)에서는 잡힌다
    assert len(find_breakouts(make_context(extend(base_df(), [BO] + after), rs=85))) == 1


def test_reject_when_base_has_bigger_volume_day():
    # 30봉 전 돌파일보다 큰 거래량 → '베이스 최대 거래량 경신' 실패 (60일 이상 베이스 불가)
    r = run(extend(base_df(vol_segments=[(270, 271, 20.0)]), [BO]))
    assert _no_breakout(r)


def test_reject_not_first_breakout_day():
    # 전일 이미 박스 상단 +3% 위에서 마감 → 당일 장대양봉은 '첫 돌파'가 아님
    df = extend(base_df(), [bar(11450, 600_000), dict(open=11450, high=12450, low=11400, close=12400,
                                                       volume=4_000_000)])
    r = run(df)
    assert _no_breakout(r)
    assert any("첫 돌파" in w for w in r.warnings)


def test_config_override_min_base():
    cfg = Config(patterns={"long_base_breakout": LongBaseBreakoutConfig(min_base=260, watch_min_base=260)})
    assert not run(extend(base_df(), [BO]), cfg=cfg).detected


# ---------------------------------------------------------------- 장중 미완성 봉 경고
def test_partial_bar_warning():
    df = extend(base_df(), [BO])
    ctx = make_context(df, rs=85)
    ctx.partial, ctx.session_frac = True, 0.5   # vol/value 는 첫 접근 시 환산되므로 detect 전에 설정
    r = detect(ctx)
    assert r.detected and any("장중" in w for w in r.warnings)


def test_halt_date_warning():
    df = extend(base_df(), [BO])
    df.attrs["halt_dates"] = [df.index[250].strftime("%Y-%m-%d")]
    r = run(df)
    assert r.detected and any("거래정지" in w for w in r.warnings)


def test_halt_warning_has_no_lookahead():
    # 회귀: df.attrs 는 잘라낸 df(iloc)에도 전체 이력의 거래정지일이 남는다 → 마지막 봉 이후 정지일은 무시
    hold = [bar(c, 600_000) for c in (12100, 11950, 11900, 12000, 11850, 11950)]
    full = extend(base_df(), [BO] + hold)
    full.attrs["halt_dates"] = [full.index[305].strftime("%Y-%m-%d")]
    cut = full.iloc[:302]
    assert cut.attrs.get("halt_dates")                 # pandas 가 attrs 를 그대로 넘김
    r = run(cut)
    assert r.detected and not any("거래정지" in w for w in r.warnings)
    assert any("거래정지" in w for w in run(full).warnings)


# ---------------------------------------------------------------- 연속 장대양봉 = 하나의 돌파 (회귀)
def _second_leg_df():
    """박스 상단이 오래된 고점(≈11,800)과 최근 박스(≈10,900) 두 층인 베이스: 첫 장대양봉은 최근 박스를,
    다음 날 장대양봉은 긴 구간의 상단까지 넘는다 (SK 2025-05-28/29 와 같은 구조)."""
    wp = [(0, 16000), (60, 11700), (80, 11000), (100, 11800), (130, 10900), (160, 9200), (190, 10800),
          (220, 9100), (250, 10900), (280, 9400), (299, 10700)]
    df = make_ohlcv(wp, n=300, seed=1, vol_base=300_000)
    c1 = dict(open=10750, high=11600, low=10700, close=11550, volume=3_000_000)
    c2 = dict(open=11600, high=12850, low=11550, close=12800, volume=4_000_000)
    return extend(df, [c1, c2])


def test_second_candle_after_breakout_keeps_first_breakout():
    df = _second_leg_df()
    from chart_screener.patterns import long_base_breakout as lbb
    ctx = make_context(df, rs=85)
    A = lbb._arrays(ctx, LongBaseBreakoutConfig())
    S = lbb._Scan(ctx, A, LongBaseBreakoutConfig(), 300 * 1e8)
    assert S.eval(301)[0] is not None and S.eval(300)[0] is not None   # 두 봉 모두 단독으로는 돌파 조건 충족
    evs = find_breakouts(ctx)
    assert [e["i"] for e in evs] == [300]                              # 백테스트 이벤트는 첫 봉 하나
    first_mid = evs[0]["candle_mid"]
    # 둘째 장대양봉의 50% 아래이지만 첫 돌파의 50%·박스 상단 위 → failed 가 아니어야 한다
    dip = extend(df, [bar(12300, 900_000), bar(12000, 700_000)])
    r = run(dip)
    assert r.breakout_date == df.index[300].strftime("%Y-%m-%d")
    assert is_tick_ceil(r.pivot, evs[0]["box_top"])
    assert r.stage != FAILED and 12000 > first_mid
    assert r.metrics["legs"] == 2 and r.metrics["last_leg_date"] == df.index[301].strftime("%Y-%m-%d")
    assert len(find_breakouts(make_context(dip, rs=85))) == 1


def test_second_candle_after_handle_is_not_new_breakout():
    # 첫 돌파 → 6봉 손잡이(50% 위 유지) → 거래량 더 큰 +10% 장대양봉: 새 장기 베이스 돌파가 아니다
    handle = [bar(c, 500_000) for c in (12400, 12250, 12150, 12300, 12200, 12350)]
    second = dict(open=12400, high=13650, low=12350, close=13600, volume=5_000_000)
    df = extend(base_df(), [BO] + handle + [second, bar(13000, 900_000), bar(12700, 700_000)])
    r = run(df)
    assert r.breakout_date == df.index[300].strftime("%Y-%m-%d")
    assert r.stage != FAILED                       # 12,700 은 둘째 봉 50%(13,000) 아래지만 첫 돌파 기준 유지
    assert r.stop == 11520                         # 첫 돌파 50%선 11,525 의 호가 내림
    assert len(find_breakouts(make_context(df, rs=85))) == 1


def test_rebreakout_after_failed_first_breakout_is_new_event():
    # 첫 돌파가 50% 룰·박스 복귀로 실패한 뒤 다시 나온 장대양봉은 새 돌파(재돌파)
    fail = [bar(11800, 1_500_000), bar(11000, 1_000_000), bar(10400, 600_000)] + \
        [bar(c, 350_000) for c in (10500, 10450, 10600, 10550, 10650, 10600)]
    rebo = dict(open=10650, high=12950, low=10600, close=12900, volume=5_000_000)
    df = extend(base_df(), [BO] + fail + [rebo])
    evs = find_breakouts(make_context(df, rs=85))
    assert [e["i"] for e in evs] == [300, 310]
    r = run(df)
    assert r.detected and r.stage == BREAKOUT and r.breakout_date == df.index[310].strftime("%Y-%m-%d")
    assert r.metrics["legs"] == 1


def test_base_with_held_prior_breakout_is_rejected():
    # 평탄한 박스 → 돌파(유지) → 30봉 깃발 → 장대양봉: 베이스 안에 이미 성공한 돌파가 있으므로 새 이벤트 아님
    wp = [(0, 10000), (30, 10900), (60, 9200), (90, 10800), (120, 9100), (150, 10900), (180, 9400), (210, 10800),
          (240, 9300), (270, 10900), (299, 10700)]
    flag = [bar(12300 + 60 * np.sin(k / 3), 450_000) for k in range(30)]
    df = extend(make_ohlcv(wp, n=300, seed=4, vol_base=300_000),
                [BO] + flag + [dict(open=12400, high=13900, low=12350, close=13850, volume=5_000_000)])
    assert [e["i"] for e in find_breakouts(make_context(df, rs=85))] == [300]
    r = run(df)
    assert _no_breakout(r)
    assert any("유지된 장대양봉" in w for w in r.warnings)


def test_failed_breakout_attempt_inside_base_is_allowed():
    # 40봉 전 박스 상단을 넘었다가 다음 날 박스로 되밀린 장대양봉(실패한 시도)은 베이스를 무효로 만들지 않는다
    wp = [(0, 16000), (100, 10000), (130, 10900), (160, 9200), (190, 10800), (220, 9100), (250, 10500),
          (259, 10600), (262, 10000), (280, 9400), (299, 10700)]
    df = make_ohlcv(wp, n=300, seed=1, vol_base=300_000)
    df = set_bar(df, 259, open=10300, high=11750, low=10250, close=11700, volume=3_500_000)
    df = set_bar(df, 260, open=11500, high=11500, low=10400, close=10450, volume=1_500_000)
    df = extend(df, [dict(BO, high=12550, close=12500)])
    r = run(df)
    assert r.detected and r.stage == BREAKOUT and r.breakout_date == df.index[300].strftime("%Y-%m-%d")
    assert r.start_date <= df.index[259].strftime("%Y-%m-%d")      # 실패한 시도를 품은 베이스


def test_creeping_breakout_without_return_is_not_first():
    # 장대양봉 없이 박스 상단 +3% 위로 올라선 뒤 박스로 돌아오지 않은 상태의 장대양봉 → 첫 돌파 아님
    # (예전 규칙은 직전 1봉만 봤다: 직전 봉 11,050 은 상단 +3% 이내라 통과했었다)
    creep = [bar(c, 500_000) for c in (11450, 11500, 11250, 11100, 11050)]
    big = dict(open=11100, high=12500, low=11050, close=12450, volume=4_500_000)
    r = run(extend(base_df(), creep + [big]))
    assert _no_breakout(r)
    assert any("첫 돌파 아님" in w for w in r.warnings)
    # 같은 이탈이라도 박스(상단 -3% 아래)로 되돌아왔다가 나온 장대양봉은 허용
    back = [bar(c, 500_000) for c in (11450, 11500, 11200, 10700, 10300, 10450, 10600)]
    big2 = dict(open=10650, high=12550, low=10600, close=12500, volume=4_500_000)
    r = run(extend(base_df(), back + [big2]))
    assert r.detected and r.stage == BREAKOUT


# ---------------------------------------------------------------- 직전 추세 꼬리와 박스 경계 (회귀)
def _box_top(df, a, b):
    return float(np.percentile(df["high"].to_numpy()[a:b], 95))


def test_box_after_decline_pivot_not_inflated_by_trend_tail():
    # 15,000 → 10,000 하락 뒤 70일 박스(9,000~10,000) → 장대양봉. 하락 꼬리가 피벗을 끌어올리면 안 된다.
    wp = [(0, 15000), (150, 10000)] + [(150 + k, 10000 if (k // 10) % 2 == 0 else 9000) for k in range(10, 71, 10)] \
        + [(219, 9800)]
    df = make_ohlcv(wp, n=220, seed=3, vol_base=500_000, noise=0.01)
    design_top = _box_top(df, 150, 220)
    r = run(extend(df, [dict(open=9900, high=11300, low=9850, close=11200, volume=5_000_000)]))
    assert r.detected and r.stage == BREAKOUT
    assert abs(r.pivot / design_top - 1) < 0.03
    assert r.metrics["base_days"] <= 100


def test_box_after_uptrend_excludes_trend_tail():
    # 6,000 → 10,000 상승 뒤 120일 박스(9,000~10,000) → 장대양봉. 상승 추세 절반이 베이스로 잡히면 안 된다.
    wp = [(0, 6000), (300, 10000)] + [(300 + k, 10000 if (k // 15) % 2 == 0 else 9000) for k in range(15, 121, 15)] \
        + [(429, 9900)]
    df = make_ohlcv(wp, n=430, seed=8, vol_base=400_000, noise=0.008)
    design_top = _box_top(df, 300, 430)
    r = run(extend(df, [dict(open=9950, high=11000, low=9900, close=10950, volume=4_500_000)]))
    assert r.detected and r.stage == BREAKOUT
    assert abs(r.pivot / design_top - 1) < 0.03
    assert r.metrics["box_height"] < 0.2 and r.metrics["base_days"] < 260
    assert r.metrics["top_confirmed"] and r.metrics["bottom_confirmed"]


# ---------------------------------------------------------------- 상한가권 면제 플래그 (회귀)
def test_limit_up_exemption_flag_is_consistent():
    # +28%, 갭 상승 + 긴 아래꼬리로 몸통비율 < 0.6 → 면제로 통과하면 limit_up=True 이고 사유에 '면제' 명시
    gap = dict(open=12200, high=13750, low=11000, close=13700, volume=4_000_000)
    r = run(extend(base_df(), [gap]))
    assert r.detected and r.metrics["limit_up"] is True and r.metrics["body_ratio"] < 0.6
    assert any("몸통 조건 면제" in s for s in r.reasons)
    prev = float(base_df()["close"].iloc[-1])
    assert r.metrics["candle_mid"] == pytest.approx((min(12200, prev) + 13700) / 2)
    # 몸통 조건을 스스로 충족하는 +29.9% 장대양봉도 같은 플래그(limit_up=True), 단 '면제' 문구는 없음
    full = dict(open=prev, high=prev * 1.3, low=prev * 0.995, close=prev * 1.299, volume=4_000_000)
    r2 = run(extend(base_df(), [full]))
    assert r2.detected and r2.metrics["limit_up"] is True
    assert not any("면제" in s for s in r2.reasons)


# ---------------------------------------------------------------- 공개 함수 일관성 (회귀)
def test_find_breakouts_shares_price_validity_guard():
    df = extend(base_df(), [BO])
    df.iloc[150, df.columns.get_loc("close")] = 0.0
    assert find_breakouts(make_context(df, rs=85)) == []
    r = run(df)
    assert not r.detected and any("판정 불가" in w for w in r.warnings)


def test_watch_stop_label_follows_config():
    approach = [bar(c, v, o=c * 0.99) for c, v in
                ((10450, 600_000), (10550, 700_000), (10500, 450_000), (10650, 800_000), (10700, 900_000))]
    cfg = Config(patterns={"long_base_breakout": LongBaseBreakoutConfig(stop_below_top=0.06)})
    r = run(extend(base_df(n=295), approach), cfg=cfg)
    assert r.detected and r.metrics["pre_breakout"] is True
    assert is_tick_floor(r.stop, r.metrics["box_top"] * 0.94)
    assert "손절(상단 -6%)" in [a["label"] for a in r.annotations if a["kind"] == "hline"]


# ---------------------------------------------------------------- (d) 견고성
@pytest.mark.parametrize("kind", ["short60", "flat", "random", "nan", "zero_vol", "const_vol", "tiny"])
def test_robustness_never_raises(kind):
    rng = np.random.default_rng(0)
    if kind == "short60":
        df = make_ohlcv([(0, 100), (59, 110)], n=60)
    elif kind == "tiny":
        df = make_ohlcv([(0, 100), (4, 101)], n=5)
    elif kind == "flat":
        idx = pd.bdate_range("2023-01-02", periods=400)
        df = pd.DataFrame({"open": 5000.0, "high": 5000.0, "low": 5000.0, "close": 5000.0, "volume": 1e5},
                          index=idx)
        df["value"] = df["close"] * df["volume"]
    else:
        c = 10000 * np.exp(np.cumsum(rng.normal(0, 0.02, 600)))
        idx = pd.bdate_range("2023-01-02", periods=600)
        df = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                           "volume": rng.lognormal(12, 0.5, 600)}, index=idx)
        if kind == "nan":
            df.iloc[100:105, :] = np.nan
        if kind == "zero_vol":
            df["volume"] = 0.0
        if kind == "const_vol":
            df["volume"] = 1e6
        df["value"] = df["close"] * df["volume"]
    r = detect(make_context(df, rs=None))
    assert isinstance(r.detected, bool)
    if kind in ("short60", "tiny", "flat", "zero_vol", "const_vol"):
        assert not r.detected
        assert r.warnings
    assert 0 <= r.score <= 100
    find_breakouts(make_context(df, rs=None))


def test_robustness_breakout_without_index_or_rs():
    df = extend(base_df(), [BO])
    ctx = make_context(df, rs=None)
    ctx.index_df = None
    ctx.rs_rating_hist = None
    ctx.market_state = None
    r = detect(ctx)
    assert r.detected and r.stage == BREAKOUT


def test_config_dataclass_overridable():
    cfg = dataclasses.replace(LongBaseBreakoutConfig(), min_chg=0.20)
    r = run(extend(base_df(), [BO]), cfg=Config(patterns={"long_base_breakout": cfg}))
    assert _no_breakout(r)


# ---------------------------------------------------------------- (e) 재보정: 맥락 지표·점수·경고 (2024-26 표본 근거)
def _uptrend_base_df():
    """완만한 상승(5,000→9,500) 뒤 약 9,300~10,000 박스 → 2년 고점권·이력 최고가·정배열 돌파가 되는 구조."""
    wp = [(0, 5000), (260, 9500)] + [(260 + k, 10000 if (k // 10) % 2 == 0 else 9300) for k in range(10, 81, 10)] \
        + [(349, 9800)]
    return make_ohlcv(wp, n=350, seed=3, vol_base=500_000, noise=0.008)


UP_BO = dict(open=9850, high=10950, low=9800, close=10900, volume=6_000_000)   # +11% normal, ~12배, ~630억


def test_new_context_metrics_present_and_typed():
    r = run(extend(base_df(), [BO]))
    m = r.metrics
    assert m["ath_breakout"] is False                      # 16,000 에서 내려온 박스 → 이력 최고가 아래
    assert m["ma_stacked"] is False
    assert m["weekly_confirm"] == "pending"                # 월요일 돌파, 주 미완성
    assert m["candle_class"] == "strong" and m["vol_class"] == "<=15x"   # +15.2%, 13.7배
    assert m["true_range"] >= m["box_height"] and m["failed_spikes"] == 0
    assert is_tick_ceil(m["support"], max(m["box_top"], m["candle_mid"]))   # 지지선 = max(상단, 50%) 호가 올림
    ev = find_breakouts(make_context(extend(base_df(), [BO]), rs=85))[0]
    for k in ("ath_breakout", "ma_stacked", "weekly_confirm", "candle_class", "vol_class", "true_range",
              "failed_spikes", "failed_spike_dates"):
        assert k in ev


def test_ath_ma_stacked_and_high_position_add_points():
    df = extend(_uptrend_base_df(), [UP_BO])
    r = run(df)
    assert r.detected and r.stage == BREAKOUT
    m, p = r.metrics, parts(r)
    assert m["position"] == "high" and m["ath_breakout"] is True and m["ma_stacked"] is True
    # 정배열 판정은 종가 > 50 > 150 > 200일선 과 정확히 같아야 한다
    c = df["close"]
    sma = [c.rolling(k).mean().iloc[-1] for k in (50, 150, 200)]
    assert m["ma_stacked"] == bool(c.iloc[-1] > sma[0] > sma[1] > sma[2])
    assert p["위치"] == 12 and p["신고가"] == 10 and p["정배열"] == 8 and p.get("캔들", 0) == 0
    assert m["candle_class"] == "normal"
    assert any("신고가 돌파" in s for s in r.reasons) and any("정배열" in s for s in r.reasons)
    base = run(extend(base_df(), [BO]))                 # 중간 위치·정배열 아님·500억 미만
    assert r.score >= base.score + 25
    assert any("정배열 아님" in w for w in base.warnings)


def test_ma_stacked_nan_safe_with_short_history():
    wp = [(0, 10000), (30, 10900), (60, 9200), (90, 10800), (120, 9100), (149, 10700)]
    r = run(extend(make_ohlcv(wp, n=150, seed=2, vol_base=300_000), [BO]))
    assert r.detected and r.metrics["ma_stacked"] is False       # 200일선 결측 → False (예외 없음)
    assert any("판정 불가" in w for w in r.warnings)


def test_weekly_confirm_yes_no_pending():
    base = base_df()                                     # 돌파봉(300)은 월요일
    r0 = run(extend(base, [BO]))
    assert r0.metrics["weekly_confirm"] == "pending" and any("돌파 주 미완성" in w for w in r0.warnings)
    yes = extend(base, [BO] + [bar(c, 900_000) for c in (12400, 12350, 12450, 12420)])   # 금요일 강한 마감
    ry = run(yes)
    assert yes.index[-1].weekday() == 4
    assert ry.metrics["weekly_confirm"] == "yes" and parts(ry)["주간 확인"] == 4
    assert any("주간 확인" in s for s in ry.reasons)
    # 주중 윗꼬리(13,500)로 주간 고저폭이 넓어진 뒤 금요일 종가 12,000 < 주간 중간값 → 확인 실패 (50% 위라 실패 단계는 아님)
    no = extend(base, [BO, dict(open=12350, high=13500, low=12300, close=12500, volume=1_500_000),
                       bar(12300, 900_000), bar(12150, 800_000), bar(12000, 700_000)])
    rn = run(no)
    assert rn.stage != FAILED and rn.metrics["weekly_confirm"] == "no"
    assert parts(rn)["주간 확인"] == -4
    assert any("주간 확인 실패" in w for w in rn.warnings)
    # 장중 미완성 금요일 봉이면 주간 종가 미확정 → pending
    ctx = make_context(yes, rs=85)
    ctx.partial, ctx.session_frac = True, 0.9
    assert detect(ctx).metrics["weekly_confirm"] == "pending"


def test_weekly_confirm_has_no_lookahead_in_find_breakouts():
    # 백테스트 이벤트의 주간 확인은 돌파봉 시점 값(월요일 → pending): 이후 봉을 붙여도 바뀌지 않는다
    full = extend(base_df(), [BO] + [bar(c, 900_000) for c in (12400, 12350, 12450, 12420)])
    ev_full = find_breakouts(make_context(full, rs=85))[0]
    ev_cut = find_breakouts(make_context(full.iloc[:301], rs=85))[0]
    assert ev_full["weekly_confirm"] == ev_cut["weekly_confirm"] == "pending"
    assert ev_full["score"] == pytest.approx(ev_cut["score"])
    # 금요일 돌파는 그 봉에서 주가 끝나므로 돌파 시점에 판정된다
    fri = extend(base_df(n=304), [BO])
    assert fri.index[-1].weekday() == 4
    assert find_breakouts(make_context(fri, rs=85))[0]["weekly_confirm"] in ("yes", "no")


def test_limit_up_and_climax_volume_penalties_with_evidence_warnings():
    prev = float(base_df()["close"].iloc[-1])
    locked = dict(open=prev * 1.02, high=prev * 1.299, low=prev * 1.01, close=prev * 1.299, volume=12_000_000)
    df = extend(base_df(), [locked])
    df.iloc[-1, df.columns.get_loc("value")] = 470e8     # BO 와 같은 거래대금 구간으로 고정 (캔들·거래량 효과만 비교)
    r = run(df)
    assert r.detected and r.metrics["candle_class"] == "limit_up" and r.metrics["vol_class"] == ">30x"
    p = parts(r)
    assert p["캔들"] == -12 and p["상한가 마감"] == -4 and p["거래량"] == -8
    assert any("상한가 마감 장대양봉" in w and "2024-26 표본" in w and "20일 평균 -4%" in w for w in r.warnings)
    assert any("클라이맥스" in w for w in r.warnings)
    assert r.score < run(extend(base_df(), [BO])).score - 15


def test_value_buckets_monotone():
    # 같은 돌파에서 거래대금(value 열)만 바꿔 구간 가감점 확인: <500억 -6 · 500~1000억 0 · 1000~3000억 +5 · 3000억↑ +10
    pts = []
    for eok in (400, 700, 1500, 4000):
        df = extend(base_df(), [BO])
        df.iloc[-1, df.columns.get_loc("value")] = eok * 1e8
        pts.append(parts(run(df)).get("거래대금", 0))
    assert pts == [-6, 0, 5, 10]


def test_true_range_rejects_pump_and_dump_base():
    # 5/95 백분위 박스(≈20%)는 그대로지만 베이스 뒷부분에 2.5만원 급등 꼬리 3봉 → 실제 고저폭 >100% → 베이스 아님
    d = base_df()
    for k in (270, 271, 272):
        d = set_bar(d, k, high=25000)
    df = extend(d, [BO])
    r = run(df)
    assert _no_breakout(r)
    assert any("실제 고저폭" in w and "횡보 아님" in w for w in r.warnings)
    # 규칙을 끄면 같은 돌파가 잡히고, 60% 이상이라 경고·감점
    off = Config(patterns={"long_base_breakout": LongBaseBreakoutConfig(max_true_range=3.0)})
    r2 = run(df, cfg=off)
    assert r2.stage == BREAKOUT and r2.metrics["true_range"] > 1.0
    assert parts(r2)["베이스 건전성"] == -5
    assert any("실제 고저폭" in w for w in r2.warnings)


def test_true_range_warning_between_60_and_100pct():
    d = set_bar(base_df(), 270, high=16000)
    r = run(extend(d, [BO]))
    assert r.detected and r.stage == BREAKOUT
    assert 0.6 <= r.metrics["true_range"] < 1.0 and r.metrics["box_height"] < 0.3
    assert parts(r)["베이스 건전성"] == -5
    assert any("실제 고저폭" in w and "5/95 백분위 박스" in w for w in r.warnings)


def _spiky_base(ks):
    d = base_df()
    for k in ks:
        c0 = float(d["close"].iloc[k - 1])   # 박스 상단까지 치솟았다 박스 안 마감, 거래량 ~6배·약 200억
        d = set_bar(d, k, open=c0, high=10950, low=c0 * 0.99, close=c0 * 1.01, volume=2_000_000)
    return d


def test_failed_spikes_counted_warned_and_penalized():
    r = run(extend(_spiky_base((240, 255, 285)), [BO]))
    assert r.detected and r.stage == BREAKOUT
    m = r.metrics
    assert m["failed_spikes"] == 3 and len(m["failed_spike_dates"].split(", ")) == 3
    assert parts(r)["베이스 건전성"] == -10                 # 두 번째부터 -5, 최대 -10
    assert any("실패한 대량거래 스파이크 3회" in w for w in r.warnings)
    assert sum(1 for a in r.annotations if a["kind"] == "marker" and a["text"] == "실패 스파이크") == 3
    # 한 번은 흔한 흔들기: 집계만, 경고·감점 없음. 연달아 붙은 스파이크 봉은 한 번으로 센다
    r1 = run(extend(_spiky_base((255, 256)), [BO]))
    assert r1.metrics["failed_spikes"] == 1 and parts(r1).get("베이스 건전성", 0) == 0
    assert not any("스파이크" in w for w in r1.warnings)


def test_stop_above_pivot_is_explained():
    prev = 10700
    gap = dict(open=13700, high=13800, low=13650, close=13800, volume=4_000_000)
    r = run(extend(base_df(), [gap]))
    assert r.detected and r.stop > r.pivot
    assert is_tick_floor(r.stop, r.metrics["candle_mid"])
    assert r.metrics["support"] >= r.stop
    assert any("피벗" in s and "위인 이유" in s and "50% 룰" in s for s in r.reasons)
    assert r.metrics["candle_mid"] == pytest.approx((min(13700, prev) + 13800) / 2, rel=0.01)


def test_score_parts_sum_and_post_state_adjustment():
    ok = run(extend(base_df(), [BO, bar(12400, 1_200_000)]))
    failed = run(extend(base_df(), [BO, bar(11800, 1_500_000), bar(11000, 1_200_000), bar(10300, 900_000)]))
    for r in (ok, failed):
        assert r.score == pytest.approx(max(0.0, min(100.0, sum(parts(r).values()))), abs=0.11)
        assert isinstance(r.metrics["score_parts"], str) and r.metrics["score_parts"].startswith("기준 40")
    assert parts(ok).get("돌파 후 상태", 0) == 0
    assert parts(failed)["돌파 후 상태"] <= -20
    assert failed.score < ok.score


def test_watch_metrics_follow_contract_and_tick_rounding():
    approach = [bar(c, v, o=c * 0.99) for c, v in
                ((10450, 600_000), (10550, 700_000), (10500, 450_000), (10650, 800_000), (10700, 900_000))]
    r = run(extend(base_df(n=295), approach))
    m = r.metrics
    assert r.detected and m["pre_breakout"] is True
    assert m["support"] == r.pivot and is_tick_ceil(r.pivot, m["box_top"])
    assert isinstance(m["ma_stacked"], bool) and m["weekly_confirm"] is None and m["failed_spikes"] == 0
    assert m["failed_spike_dates"] is None
