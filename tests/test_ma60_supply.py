"""60일선 수급 돌파 (chart_screener/patterns/ma60_supply.py) — 합성 봉으로 신호 · 비신호 · 경계(부록 §13) · 앞부분 불변 · '모름'.

기본 봉: 종가 100 이 120봉 → 95 가 20봉(60일선 98.33 아래) → 신호 봉 종가 100 (60일선 98.33 위, 전일 95 ≤ 98.33)."""
import numpy as np
import pandas as pd
import pytest

from chart_screener import techniques as tq
from chart_screener.data.kis_market import Flows
from chart_screener.journal import rule_of
from chart_screener.patterns import REGISTRY, run_all
from chart_screener.patterns import ma60_supply as ma
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, NEAR_PIVOT
from synthetic import add_value, make_context, make_ohlcv

BASE = [100.0] * 120 + [95.0] * 20


# ---------------------------------------------------------------- 도우미
def _df(closes, vol=None, start="2024-01-02") -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    o = np.r_[c[0], c[:-1]]
    v = np.full(len(c), 1e6) if vol is None else np.asarray(vol, dtype=float)
    return add_value(pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.005, "low": np.minimum(o, c) * 0.995,
                                   "close": c, "volume": v}, index=pd.bdate_range(start, periods=len(c))))


def _inv(dates, inst, foreign) -> pd.DataFrame:
    """data.investor 모양 (순매매 수량, 주)."""
    n = len(dates)
    inst, foreign = np.broadcast_to(np.asarray(inst, float), n), np.broadcast_to(np.asarray(foreign, float), n)
    return pd.DataFrame({"close": 100.0, "volume": 1e6, "inst_net": inst, "foreign_net": foreign,
                         "indiv_net": -(inst + foreign), "foreign_ratio": 10.0}, index=pd.DatetimeIndex(dates, name="date"))


def _ctx(df, inv=None, **info):
    if inv is not None:
        info["investor"] = inv
    return make_context(df, info=info or {"market_cap": 1e12})


def _junk_future(b: tq.Bars, t: int, seed: int = 0) -> tq.Bars:
    rng = np.random.default_rng(seed)
    o, h, lo, c, v = (x.copy() for x in (b.open, b.high, b.low, b.close, b.volume))
    k = b.n - t - 1
    if k > 0:
        c[t + 1:] = b.close[t] * rng.uniform(0.3, 3.0, k)
        o[t + 1:] = c[t + 1:] * rng.uniform(0.8, 1.2, k)
        h[t + 1:] = np.maximum(o[t + 1:], c[t + 1:]) * 1.2
        lo[t + 1:] = np.minimum(o[t + 1:], c[t + 1:]) * 0.8
        v[t + 1:] = rng.uniform(0, 1e9, k)
    return tq.Bars(o, h, lo, c, v, b.dates)


def _junk_tables(tabs, after, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for tb in tabs:
        x = tb.copy()
        m = x.index > after
        x.loc[m, ["inst", "foreign"]] = rng.normal(0, 1e9, (int(m.sum()), 2))
        x.attrs.update(tb.attrs)
        out.append(x)
    return out


# ---------------------------------------------------------------- 등록 · 신호
def test_registered_with_exact_label_and_rule_id():
    assert REGISTRY["ma60_supply"][0] == "60일선 수급 돌파"
    assert ma.RULE_ID == "ma60s_v1" == tq.RULE_IDS["ma60_supply"]


def test_signal_breakout_with_flows_dongban_and_ssang():
    df = _df(BASE + [100.0])
    r = ma.detect(_ctx(df, _inv(df.index[-10:], 1000, 2000)))
    m = r.metrics
    assert r.detected and r.stage == BREAKOUT
    assert r.pivot == pytest.approx(5900 / 60) and r.stop is None
    assert r.breakout_date == m["cross_date"] == f"{df.index[-1]:%Y-%m-%d}"
    assert m["flow_label"] == "수급 동반" and m["flow_ssang"] and m["flow_unit"] == "주"
    assert m["flow_f_t"] == 3000 and m["flow_s5"] == 15000 and m["flow_inst5"] == 5000
    assert m["ma20_above"] and m["ma120_above"]
    assert r.score == 100 and m["score_coverage"] == 1.0 and m["score_unknown"] == []
    assert m["rule_version"] == "ma60s_v1" and rule_of(r) == "ma60s_v1"          # 일지 rule 칸
    assert any("수급 동반 · 쌍끌이" in x for x in r.reasons)
    assert any("손절 규칙 없음" in w for w in r.warnings)


def test_origins_recorded_for_every_rule():
    df = _df(BASE + [100.0])
    o = ma.detect(_ctx(df)).metrics["origin"]
    assert set(o) == set(ma.ORIGIN)
    assert "57:00" in o["cross"] and "58:00" in o["flow"] and "kiwoom" in o["cross"]
    for k in ("flow_days", "flow_weak", "score", "stage", "zero_vol", "replay", "display"):
        assert o[k].startswith("구현 선택"), k
    for k, v in o.items():
        assert any(s in v for s in ("영상 [", "http", "구현 선택", "스펙", "부록")), k


def test_prev_close_equal_to_ma60_counts_as_cross_today_equal_does_not():
    # 부록 §13: 전일 종가 = SMA60 (≤) 이면 돌파로 인정
    r = ma.detect(_ctx(_df([100.0] * 121 + [101.0])))
    assert r.detected and r.metrics["prev_close"] == r.metrics["prev_ma60"] == 100.0
    # 당일 종가 = SMA60 은 돌파 아님 (C > SMA60 엄격)
    r2 = ma.detect(_ctx(_df([100.0] * 122)))
    assert not r2.detected and "60일선 이하" in r2.warnings[0]


# ---------------------------------------------------------------- 수급 라벨 · 모름
def test_flow_one_day_missing_is_unknown_and_scores_zero():
    # 부록 §13: 수급 5일 중 하루라도 빠지면 '수급 미확인'
    df = _df(BASE + [100.0])
    gone = df.index[-3]
    inv = _inv([d for d in df.index[-10:] if d != gone], 1000, 2000)
    r = ma.detect(_ctx(df, inv))
    m = r.metrics
    assert r.detected and m["flow_label"] == "수급 미확인" and not m["flow_ssang"]
    assert m["flow_missing"] == [f"{gone:%Y-%m-%d}"] and m["flow_f_t"] is None
    assert r.score == 65 and m["score_unknown"] == ["수급"] and m["score_coverage"] == pytest.approx(0.65)
    assert any("수급 미확인" in w and "지어내지 않음" in w for w in r.warnings)
    # NaN 행도 자료 없음
    inv2 = _inv(df.index[-10:], 1000, 2000)
    inv2.loc[df.index[-1], "inst_net"] = np.nan
    assert ma.detect(_ctx(df, inv2)).metrics["flow_label"] == "수급 미확인"


def test_no_investor_data_is_unknown_not_fabricated():
    r = ma.detect(_ctx(_df(BASE + [100.0])))
    assert r.detected and r.metrics["flow_label"] == "수급 미확인"
    assert "투자자 자료 없음" in r.metrics["flow"]["why"]
    assert r.metrics["score_parts"]["수급"] == 0


@pytest.mark.parametrize("inst,foreign,label,ssang", [
    ([5] * 5, [5] * 5, "수급 동반", True),
    ([-1] * 5, [5] * 5, "수급 동반", False),                     # 외국인만 — 동반이지만 쌍끌이 아님
    ([-5] * 5, [1] * 5, "수급 역행", False),                     # s5 < 0
    ([10, 10, 10, 10, -30], [0] * 5, "수급 약함", False),        # 5일 합 > 0 · 당일 < 0
    ([-1, 0, 0, 0, 1], [0] * 5, "수급 약함", False),             # 당일 > 0 · 5일 합 = 0 (동반 아님)
    ([5, 5, 5, 5, -4], [5, 5, 5, 5, -7], "수급 약함", True),     # 쌍끌이 꼬리표는 주 라벨과 따로
])
def test_flow_labels(inst, foreign, label, ssang):
    dates = pd.bdate_range("2024-01-02", periods=8)
    tabs = ma.flow_tables({"investor": _inv(dates[3:], inst, foreign)})
    f = ma.flow_at(dates, 7, tabs)
    assert (f["label"], f["ssang"]) == (label, ssang)
    assert f["s5"] == sum(inst) + sum(foreign)


def test_flow_score_parts_order():
    df = _df(BASE + [100.0])
    sc = {}
    for lab, (i, f) in {"동반쌍끌이": (5, 5), "동반": (-1, 5), "약함": ([10, 10, 10, 10, -30], 0),
                        "미확인": (None, None), "역행": (-5, 1)}.items():
        inv = None if i is None else _inv(df.index[-5:], i, f)
        sc[lab] = ma.detect(_ctx(df, inv)).score
    assert sc["동반쌍끌이"] > sc["동반"] > sc["약함"] > sc["미확인"] > sc["역행"]


def test_kis_amount_preferred_then_quantity_fallback():
    df = _df(BASE + [100.0])
    d5 = [f"{d:%Y%m%d}" for d in df.index[-5:]]
    neg = _inv(df.index[-10:], -1000, -1000)                    # 수량은 순매도
    fl = Flows(dates=d5, close=[100.0] * 5, frgn=[1.0] * 5, orgn=[0.5] * 5, prsn=[-1.5] * 5)
    m = ma.detect(_ctx(df, neg, kis_flows=fl)).metrics
    assert m["flow_label"] == "수급 동반" and m["flow_unit"] == "원" and "KIS" in m["flow_src"]
    assert m["flow_f_t"] == pytest.approx(1.5e8) and m["flow_foreign5"] == pytest.approx(5e8)   # 억원 → 원
    # 금액 자료가 그 5일을 다 덮지 못하면 수량으로 (한 창 안에서 섞지 않음)
    fl2 = Flows(dates=d5[:-1], close=[100.0] * 4, frgn=[1.0] * 4, orgn=[0.5] * 4, prsn=[0.0] * 4)
    m2 = ma.detect(_ctx(df, neg, kis_flows=fl2)).metrics
    assert m2["flow_label"] == "수급 역행" and m2["flow_unit"] == "주"
    # dict 모양(스냅숏 JSON)도 읽는다
    m3 = ma.detect(_ctx(df, kis_flows={"dates": d5, "frgn": [-1.0] * 5, "orgn": [-1.0] * 5})).metrics
    assert m3["flow_label"] == "수급 역행" and m3["flow_unit"] == "원"


def test_future_investor_rows_are_not_read():
    full = _df(BASE + [100.0] + [100.0] * 10)
    t = 140
    df = full.iloc[:t + 1]
    past = _inv(full.index[t - 9:t + 1], 1000, 2000)
    fut = pd.concat([past, _inv(full.index[t + 1:], -1e9, -1e9)])
    a, b = ma.detect(_ctx(df, past)), ma.detect(_ctx(df, fut))
    assert a.to_dict() == b.to_dict() and a.metrics["flow_label"] == "수급 동반"
    # 판정 봉 행이 없고 그 뒤 행만 있으면 미확인 — 다음 날 자료로 메우지 않는다
    hole = fut.drop(index=full.index[t])
    assert ma.detect(_ctx(df, hole)).metrics["flow_label"] == "수급 미확인"


# ---------------------------------------------------------------- 비신호 · 단계 · 경계
def test_below_ma60_is_not_detected():
    r = ma.detect(_ctx(_df(BASE)))
    assert not r.detected and r.stage is None and "60일선 이하" in r.warnings[0]
    assert r.metrics["rule_version"] == "ma60s_v1" and r.metrics["dist_ma60"] < 0


def test_breakout_window_boundary():
    r = ma.detect(_ctx(_df(BASE + [100.0] * 5)))                # 돌파 4봉 뒤 — 창 안
    assert r.detected and r.metrics["bars_since_cross"] == 4 and r.stage == BREAKOUT
    assert r.metrics["flow_now"] is not None                    # 오늘까지 수급도 따로
    r2 = ma.detect(_ctx(_df(BASE + [100.0] * 6)))               # 5봉 뒤 — 창 밖
    assert not r2.detected and "5봉 전" in r2.warnings[0] and "창 5봉 밖" in r2.warnings[0]


@pytest.mark.parametrize("tail,stage", [
    ([110.0], EXTENDED),                  # 60일선 98.5 대비 +11.7%
    ([100.0, 100.0, 90.0], FAILED),       # 60일선 98.17 × 0.97 아래
    ([100.0, 100.0, 97.0], NEAR_PIVOT),   # 60일선 아래지만 −3% 안 — 재시험
    ([100.0, 101.0], BREAKOUT),
])
def test_stages(tail, stage):
    r = ma.detect(_ctx(_df(BASE + tail)))
    assert r.detected and r.stage == stage
    assert r.breakout_date == r.metrics["cross_date"] and r.pivot == pytest.approx(r.metrics["ma60"])


def test_short_history_and_unknown_ma120():
    r = ma.detect(_ctx(_df([100.0] * 59 + [101.0])))            # 60봉 — 전일 60일선 없음
    assert not r.detected and "이력 부족" in r.warnings[0] and "61봉" in r.warnings[0]
    r2 = ma.detect(_ctx(_df([100.0] * 60 + [101.0])))           # 61봉 — 판정 가능
    m = r2.metrics
    assert r2.detected and m["ma120_above"] is None and m["ma20_above"] is True
    assert m["score_unknown"] == ["수급", "120일선"] and r2.score == 50 and m["score_coverage"] == pytest.approx(0.5)
    assert any("120일선(경기선) 모름" in w for w in r2.warnings)


def test_zero_volume_cross_is_not_counted():
    v = np.full(141, 1e6)
    v[-1] = 0
    r = ma.detect(_ctx(_df(BASE + [100.0], vol=v)))
    assert not r.detected and any("거래량 0" in w for w in r.warnings)


def test_partial_bar_is_not_judged_but_flagged():
    # 어제(EOD) 돌파 · 오늘 장중 엉뚱한 봉 → 어제 판정 그대로
    ctx = _ctx(_df(BASE + [100.0, 50.0]))
    ctx.partial = True
    r = ma.detect(ctx)
    assert r.detected and r.stage == BREAKOUT and r.metrics["cross_date"] == f"{ctx.df.index[-2]:%Y-%m-%d}"
    assert r.metrics["provisional_cross"] is False and any("장중 스캔" in w for w in r.warnings)
    # 오늘 장중에만 넘음 → 탐지 안 함 · '장중 잠정' 표시만
    ctx2 = _ctx(_df(BASE + [100.0]))
    ctx2.partial = True
    r2 = ma.detect(ctx2)
    assert not r2.detected and r2.metrics["provisional_cross"] is True
    assert any(w.startswith("장중 잠정") for w in r2.warnings)


# ---------------------------------------------------------------- 체크리스트 · 청산 · 차트
def test_checklist_exit_plan_and_annotations_attached():
    df = _df(BASE + [100.0, 101.0])
    r = ma.detect(_ctx(df, _inv(df.index[-10:], 1000, 2000)))
    m = r.metrics
    ck = {c["no"]: c for c in m["checklist"]}
    assert len(ck) == 10 and sum(m["checklist_counts"].values()) == 10
    assert ck[8]["status"] == "unknown" and "손절 없음" in ck[8]["note"]
    assert ck[4]["status"] == "unknown" and "0건" in ck[4]["note"]            # 재현 표본 없음
    assert m["exit_plan"]["entry_date"] == m["cross_date"] and m["exit_plan"]["held"] == 1
    labels = [a.get("label") for a in r.annotations if a["kind"] == "segment"]
    assert labels == ["60일선(수급선)", "20일선(생명선)", "120일선(경기선)"]
    mk = [a for a in r.annotations if a["kind"] == "marker"]
    assert len(mk) == 1 and mk[0]["date"] == m["cross_date"] and "수급 동반" in mk[0]["text"]
    seg60 = next(a for a in r.annotations if a.get("label") == "60일선(수급선)")
    assert seg60["points"][-1][1] == pytest.approx(r.pivot, abs=0.01)
    assert run_all(_ctx(df), ["ma60_supply"])["ma60_supply"].detected


def _wave():
    return make_ohlcv([(0, 100), (60, 80), (120, 110), (180, 90), (240, 105), (300, 85), (360, 100)],
                      noise=0.02, seed=7)


def test_replay_uses_past_crosses_with_20_bars_elapsed():
    b = tq.Bars.from_df(_wave())
    C, S = b.close, tq.sma(b.close, 60)
    t = b.n - 1
    rp = ma.replay(b, t)
    want = [j for j in range(60, t - 19) if tq.cross_above(C, S, j)]
    assert len(rp) == len(want) >= 3
    for e, j in zip(rp, want):
        assert e["date"] == b.date(j) and e["ret20"] == pytest.approx(C[j + 20] / C[j] - 1)
    assert ma.replay(_junk_future(b, 250), 250) == ma.replay(b, 250)


# ---------------------------------------------------------------- 앞부분 불변
def test_evaluate_prefix_invariant():
    df = _wave()
    b = tq.Bars.from_df(df)
    rng = np.random.default_rng(1)
    inv = _inv(df.index, rng.normal(0, 1e4, len(df)), rng.normal(0, 1e4, len(df)))
    inv.iloc[rng.choice(len(df), 15, replace=False), 2] = np.nan     # 빠진 날 섞기
    tabs = ma.flow_tables({"investor": inv})
    hits = 0
    for t in range(40, b.n):
        a = ma.evaluate(b, t, tabs)
        assert ma.evaluate(b.cut(t), t, tabs) == a
        assert ma.evaluate(_junk_future(b, t, seed=t), t, _junk_tables(tabs, df.index[t], seed=t)) == a
        hits += a["detected"]
    assert hits >= 10


def test_detect_prefix_invariant_with_full_investor_data():
    df = _wave()
    b = tq.Bars.from_df(df)
    rng = np.random.default_rng(2)
    inv = _inv(df.index, rng.normal(0, 1e4, len(df)), rng.normal(0, 1e4, len(df)))
    tabs = ma.flow_tables({"investor": inv})
    seen = 0
    for t in range(70, b.n, 7):
        cut = df.iloc[:t + 1]
        a = ma.detect(_ctx(cut, inv))                                  # 미래 수급 행이 들어 있어도
        bb = ma.detect(_ctx(cut, inv[inv.index <= df.index[t]]))
        assert a.to_dict() == bb.to_dict()
        ev = ma.evaluate(b, t, tabs)                                   # 전체 봉에서 t 판정과 같다
        assert (a.detected, a.stage, a.score) == (ev["detected"], ev["stage"], ev["score"] if ev["detected"] else 0.0)
        seen += a.detected
    assert seen >= 2
