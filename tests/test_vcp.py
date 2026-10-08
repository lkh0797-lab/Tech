"""VCP 탐지기 테스트 (합성 데이터)."""
import numpy as np
import pandas as pd
import pytest

from chart_screener.config import Config
from chart_screener.patterns import REGISTRY
from chart_screener.patterns.base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT
from chart_screener.patterns.vcp import VCPConfig, detect
from synthetic import add_value, make_context, make_ohlcv, set_bar

# 교과서형 VCP: 선행 상승 150% → 베이스 고점 100 (250봉)
#   T1 100→76 (24%), T2 98→87 (11%), T3 97.5→93 (4.6%), 이후 96.5~96.8 타이트
BASE_W = [(0, 40), (150, 60), (250, 100), (275, 76), (300, 98), (315, 87), (330, 97.5), (338, 93),
          (346, 96.5), (352, 96.8)]
BASE_VS = [(150, 250, 1.3), (250, 275, 1.6), (300, 315, 0.75), (330, 353, 0.45)]
PIVOT = 97.5


def _df(extra_w=(), extra_vs=(), end=None, seed=1, w=None, vs=None, noise=0.003, wick=0.004):
    df = make_ohlcv(list(w or BASE_W) + list(extra_w), noise=noise, wick=wick,
                    vol_segments=list(vs if vs is not None else BASE_VS) + list(extra_vs), seed=seed)
    return df.iloc[:end + 1] if end is not None else df


def _run(df, rs=92, cfg=None):
    return detect(make_context(df, rs=rs, cfg=cfg))


def _assert_well_formed(r):
    assert all(s.startswith("✔ ") for s in r.reasons), r.reasons
    assert all(s.startswith("✘ ") for s in r.warnings), r.warnings
    assert not any("분석 오류" in w for w in r.warnings), r.warnings


# ---------------------------------------------------------------- (a) 교과서형
def test_registered():
    assert "vcp" in REGISTRY
    assert REGISTRY["vcp"][0] == "변동성 수축 패턴(VCP)"


def test_textbook_vcp_near_pivot():
    df = _df()
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.stage == NEAR_PIVOT
    assert abs(r.pivot / PIVOT - 1) < 0.03
    assert r.stop < r.pivot and r.stop > 88
    m = r.metrics
    assert 3 <= m["n_contractions"] <= 4
    assert 0.20 < m["first_depth"] < 0.30
    assert m["final_contraction_depth"] < 0.07
    assert m["last_contraction_vol_ratio"] < 0.7
    assert m["prior_advance"] > 0.5
    assert m["depths"].count(">") == m["n_contractions"] - 1
    for k in ("n_contractions", "depths", "base_days", "prior_advance", "final_contraction_depth",
              "last_contraction_vol_ratio", "dryup_days", "tightness", "pivot_distance", "breakout_vol_ratio"):
        assert k in m
    # 베이스 고점 = 평평한 꼭대기(250봉 부근)의 '실제 최고가' 봉 (그 뒤의 낮아진 2차 고점이 아님)
    j = df.index.get_loc(pd.Timestamp(r.start_date))
    assert abs(j - 250) <= 7
    assert df["high"].iloc[j] == df["high"].iloc[225:275].max()
    assert r.end_date == df.index[-1].strftime("%Y-%m-%d")
    assert r.breakout_date is None
    kinds = [a["kind"] for a in r.annotations]
    assert kinds.count("hline") >= 2 and "segment" in kinds and kinds.count("marker") >= 3
    assert 50 <= r.score <= 100
    r.to_dict()  # 직렬화 가능


@pytest.mark.parametrize("seed", [2, 3, 4, 5, 6])
def test_textbook_vcp_other_seeds(seed):
    r = _run(_df(seed=seed))
    assert r.detected, (seed, r.warnings)
    assert r.stage in (NEAR_PIVOT, FORMING)
    assert abs(r.pivot / PIVOT - 1) < 0.03


# ---------------------------------------------------------------- (b) 단계
def test_forming_stage():
    w = [x if x[0] != 315 else (315, 88.5) for x in BASE_W]
    r = _run(_df(w=w, end=320))  # T2 저점 이후 반등 중, 피벗(T2 시작 고점 ≈98) 6% 이상 아래
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.stage == FORMING
    assert abs(r.pivot / 98 - 1) < 0.03
    assert r.metrics["n_contractions"] == 2


def test_breakout_stage_with_volume():
    df = _df(extra_w=[(353, 100.5)], extra_vs=[(353, 354, 3.0)])
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT
    assert r.breakout_date == df.index[353].strftime("%Y-%m-%d")
    assert abs(r.pivot / PIVOT - 1) < 0.03
    assert r.metrics["breakout_vol_ratio"] >= 1.4
    assert any(a["kind"] == "marker" and a["text"].startswith("돌파") for a in r.annotations)


def test_breakout_pivot_matches_pre_breakout_pivot():
    """미래 참조 없음: 돌파 전날 분석한 피벗 = 돌파 후 보고하는 피벗."""
    df = _df(extra_w=[(353, 100.5)], extra_vs=[(353, 354, 3.0)])
    before = _run(df.iloc[:353])
    after = _run(df)
    assert before.detected and after.detected
    assert before.pivot == pytest.approx(after.pivot)
    assert before.stop == pytest.approx(after.stop)


def test_breakout_low_volume_reported_not_required():
    df = _df(extra_w=[(353, 100.0)], extra_vs=[(353, 354, 0.6)])
    r = _run(df)
    assert r.detected and r.stage == BREAKOUT
    assert r.metrics["breakout_vol_ratio"] < 1.4
    assert any("돌파 거래량" in w for w in r.warnings)


def test_extended_stage():
    df = _df(extra_w=[(353, 100.5), (362, 108)], extra_vs=[(353, 354, 3.0), (354, 363, 1.3)])
    r = _run(df)
    assert r.detected, r.warnings
    assert r.stage == EXTENDED
    assert r.breakout_date == df.index[353].strftime("%Y-%m-%d")


def test_failed_stage():
    df = _df(extra_w=[(353, 100.0), (355, 99.0), (359, 92.5)], extra_vs=[(353, 354, 3.0), (354, 360, 1.6)])
    r = _run(df)
    assert r.detected, r.warnings
    assert r.stage == FAILED


def test_breakout_day_after_close_at_pivot():
    """돌파 시도봉이 피벗에 딱 마감(장중 고가는 위)한 다음날 종가 돌파 → 둘째 날을 돌파로 인정."""
    df = _df(extra_w=[(353, 97.5), (354, 100.0)], extra_vs=[(353, 355, 2.5)])
    pv = _run(df.iloc[:353]).pivot
    df = set_bar(df, 353, open=96.8, high=pv * 1.025, low=96.5, close=pv)
    df = set_bar(df, 354, open=pv, high=pv * 1.02, low=pv * 0.995, close=pv * 1.015)
    r = _run(df)
    assert r.detected, r.warnings
    assert r.stage == BREAKOUT
    bo = df.index[354].strftime("%Y-%m-%d")
    assert r.breakout_date == bo
    assert r.pivot == pytest.approx(pv)
    # 트렌드 템플릿 사유는 종료점 다음 봉(353)이 아니라 실제 돌파봉(354) 기준
    tt = [s for s in r.reasons if "트렌드 템플릿" in s]
    assert tt and f"돌파일 {bo}" in tt[0], r.reasons


def test_walk_forward_consistent():
    """과거 시점으로 잘라 매일 실행: 돌파 전에는 피벗 근접, 돌파일 이후에는 같은 피벗·돌파일을 유지."""
    df = _df(extra_w=[(353, 100.5), (358, 101.5)], extra_vs=[(353, 354, 3.0), (354, 359, 1.1)])
    bo_date = df.index[353].strftime("%Y-%m-%d")
    pivots = set()
    for k in range(347, len(df) + 1):
        r = _run(df.iloc[:k])
        _assert_well_formed(r)
        assert r.detected, (k, r.warnings)
        pivots.add(round(r.pivot, 6))
        if k - 1 < 353:
            assert r.stage == NEAR_PIVOT and r.breakout_date is None
        else:
            assert r.stage in (BREAKOUT, NEAR_PIVOT, EXTENDED) and r.breakout_date == bo_date
    assert len(pivots) == 1


def test_stale_breakout_is_ignored():
    """돌파가 추적 기간(15봉)보다 오래되면 그 베이스는 더 이상 보고하지 않는다."""
    df = _df(extra_w=[(353, 100.5), (390, 125)], extra_vs=[(353, 354, 3.0)])
    r = _run(df)
    assert not (r.detected and r.breakout_date == df.index[353].strftime("%Y-%m-%d"))


# ---------------------------------------------------------------- 회귀: 돌파 후 재베이스 금지 (규칙 7)
# 3T 베이스 100 → 78 → 92 → 84 → 91.5 → 88, 피벗 ≈ 92.2
REB_W = [(0, 40), (150, 60), (250, 100), (275, 78), (300, 92), (315, 84), (330, 91.5), (338, 88), (346, 90.5),
         (352, 90.8)]
REB_VS = [(150, 250, 1.3), (250, 275, 1.6), (300, 315, 0.75), (330, 353, 0.45)]


def _rebase_df(seed):
    """돌파(353: 종가 +1.8%, 고가 +2.8%, 거래량 1.2배) → 다음날 피벗까지 눌림 → +0.6% 부근 조용한 횡보."""
    df = make_ohlcv(REB_W + [(353, 94.0), (375, 94.0)], noise=0.002, wick=0.003,
                    vol_segments=REB_VS + [(353, 354, 1.2), (354, 376, 0.5)], seed=seed)
    pv = _run(df.iloc[:353]).pivot
    df = set_bar(df, 353, open=pv * 0.998, high=pv * 1.028, low=pv * 0.995, close=pv * 1.018)
    df = set_bar(df, 354, open=pv * 1.015, high=pv * 1.016, low=pv * 0.996, close=pv * 1.004)
    for k in range(355, 376):
        df = set_bar(df, k, open=pv * 1.003, high=pv * 1.010, low=pv * 0.999, close=pv * 1.006)
    return df, pv


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_breakout_not_rebased_after_one_day_dip(seed):
    """돌파 후 1~2일 눌림을 새 수축(T)으로 보고 돌파일 고가를 새 피벗으로 바꾸면 안 된다.
    돌파 추적 기간 안에서는 같은 피벗·돌파일을 유지하고, 기간이 지나도 '돌파 없는 새 VCP'로 재보고하지 않는다."""
    df, pv = _rebase_df(seed)
    bo = df.index[353].strftime("%Y-%m-%d")
    for k in range(353, 376):
        r = _run(df.iloc[:k + 1])
        _assert_well_formed(r)
        if k <= 367:  # 돌파 후 15봉 이내
            assert r.detected, (k, r.warnings)
        if r.detected:
            assert r.pivot == pytest.approx(pv), (k, r.pivot / pv, r.metrics["depths"])
            assert r.breakout_date == bo, (k, r.breakout_date, r.metrics["depths"])


def _first_breakout_bar(df, lo, hi):
    for k in range(lo, hi):
        r = _run(df.iloc[:k + 1])
        if r.detected and r.breakout_date == df.index[k].strftime("%Y-%m-%d"):
            return k, r
    return None, None


def test_confirmed_inner_breakout_blocks_rebase():
    """깊은 베이스(40%) 오른쪽에서 2T VCP 가 거래량 동반 돌파한 뒤 매수 범위(+5%)·손절가 안에서 맴돌며 생긴
    새 '피벗'은 VCP 로 보지 않는다. 같은 모양이라도 그 돌파가 거래량 없는 찌르기면
    (test_v_shaped_deep_short_base_rejected 의 두 번째 경우) 탐지."""
    w = [(0, 40), (150, 60), (250, 100), (262, 60), (282, 95), (290, 89), (300, 96), (306, 93.5), (314, 96),
         (316, 96.1)]
    df = _df(w=w, vs=[(282, 317, 0.5)])
    b, rb = _first_breakout_bar(df, 292, 305)
    assert b is not None
    assert rb.metrics["breakout_vol_ratio"] < 1.0  # 원래는 거래량 없는 찌르기
    assert _run(df).detected
    df2 = set_bar(df, b, volume=df["volume"].iloc[b - 50:b].mean() * 2.0)
    r = _run(df2)
    _assert_well_formed(r)
    assert not r.detected
    assert any("이미 VCP 돌파" in w for w in r.warnings), r.warnings


# 깊은 베이스 100 → 62, 오른쪽에서 2T VCP(88 → 82, 피벗 ≈ 88.8)가 ~312 에 거래량 2배로 돌파한 뒤의 두 갈래
BOB_VS = [(150, 250, 1.3), (250, 270, 1.6), (290, 310, 0.5), (311, 319, 1.2), (326, 353, 0.45)]
BOB_HEAD = [(0, 40), (150, 60), (250, 100), (270, 62), (290, 88), (298, 82), (306, 87.3), (309, 87.0)]


def _inner_bo_df(tail, seed):
    df = _df(w=BOB_HEAD + tail, vs=BOB_VS, seed=seed)
    b, rb = _first_breakout_bar(df, 300, 318)
    assert b is not None
    return set_bar(df, b, volume=df["volume"].iloc[b - 50:b].mean() * 2.0), rb.pivot


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_base_on_base_after_extended_breakout_allowed(seed):
    """돌파 후 매수 범위를 넘어(+7%) 이격된 뒤 3주 이상 조정받아 만든 새 VCP(같은 큰 베이스 안)는 별개 셋업 → 탐지."""
    df, pv0 = _inner_bo_df([(318, 95), (326, 89), (334, 94.5), (340, 91.5), (346, 93.8), (352, 94.0)], seed)
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.pivot > pv0 * 1.05 and r.breakout_date is None


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_rebase_inside_buy_range_rejected(seed):
    """돌파 후 매수 범위(+5%) 안에서만 맴돌며 생긴 '새 피벗'은 같은 셋업의 재베이스 → 탈락."""
    df, pv0 = _inner_bo_df([(318, 91.5), (326, 88.6), (334, 91.6), (340, 90.0), (346, 91.2), (352, 91.4)], seed)
    r = _run(df)
    _assert_well_formed(r)
    assert not r.detected
    assert any("이미 VCP 돌파" in w for w in r.warnings), r.warnings


# ---------------------------------------------------------------- 회귀: 1봉짜리 수축은 잡음
def test_one_bar_final_dip_does_not_move_pivot():
    """피벗 아래 장중 꼬리 고가 다음날 1봉 급락: 최종 수축(피벗봉→종료점 < 3봉)으로 보지 않고 기존 피벗 유지.
    그 꼬리 고가만 넘고 진짜 피벗은 못 넘은 종가는 돌파가 아니다."""
    base = _df()
    pv = _run(base).pivot
    d = set_bar(base, 351, open=96.7, high=pv * 0.993, low=96.4, close=96.6)
    d = set_bar(d, 352, open=96.0, high=96.2, low=pv * 0.993 * 0.965, close=95.4)
    r = _run(d)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.pivot == pytest.approx(pv)
    assert r.metrics["final_contraction_bars"] >= 3
    d2 = pd.concat([d, d.iloc[[-1]]])
    d2.index = pd.bdate_range(d.index[0], periods=len(d2))
    d2 = set_bar(d2, 353, open=95.5, high=pv * 0.9995, low=95.3, close=pv * 0.997, volume=3e6)
    r2 = _run(d2)
    assert r2.detected and r2.stage == NEAR_PIVOT and r2.breakout_date is None
    assert r2.pivot == pytest.approx(pv)


@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_one_bar_intermediate_contraction_merged(seed):
    """T2→T3 사이 1봉 급락(하락 구간 1봉)은 별도 수축으로 세지 않는다."""
    w = [(0, 40), (150, 60), (250, 100), (275, 76), (300, 98), (315, 87), (328, 97), (334, 97.3), (340, 94.5),
         (346, 96.5), (352, 96.7)]
    vs = [(150, 250, 1.3), (250, 275, 1.6), (300, 315, 0.75), (328, 353, 0.45)]
    df = set_bar(_df(w=w, vs=vs, seed=seed), 329, open=96.8, high=96.9, low=91.8, close=96.4)
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.metrics["n_contractions"] == 3, r.metrics["depths"]
    seg = [a for a in r.annotations if a["kind"] == "segment"][0]["points"]
    assert df.index[329].strftime("%Y-%m-%d") not in [d for d, _ in seg]
    idx = [df.index.get_loc(pd.Timestamp(d)) for d, _ in seg]
    legs = [idx[2 * k + 1] - idx[2 * k] for k in range(1, r.metrics["n_contractions"] - 1)]
    assert all(x >= 2 for x in legs), legs


def test_in_progress_final_contraction_flagged():
    """마지막 봉이 최종 수축 저점을 갱신 중이면 '진행 중' 경고, '매우 타이트' 사유·확정 손절가 표기 금지."""
    r = _run(_df(end=337))
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.metrics["final_in_progress"] == 1
    assert any("진행 중" in w for w in r.warnings), r.warnings
    assert not any("매우 타이트" in s for s in r.reasons)
    assert any(a["kind"] == "hline" and "잠정" in a["label"] for a in r.annotations)
    done = _run(_df())
    assert done.metrics["final_in_progress"] == 0


# ---------------------------------------------------------------- 회귀: 타이트니스·거래량 게이트
def test_loose_last_week_rejected():
    """구조는 같지만 마지막 7봉 종가가 ~10% 범위(최종 수축 저점에서 급반등) → 타이트니스 미달로 탈락."""
    w = [(0, 40), (150, 60), (250, 100), (275, 76), (300, 98), (315, 87), (330, 97.5), (347, 88.6), (352, 96.6)]
    r = _run(_df(w=w))
    _assert_well_formed(r)
    assert not r.detected
    assert any("타이트니스 부족" in w for w in r.warnings), r.warnings


def test_pivot_bar_volume_excluded_from_dryup():
    """최종 수축 거래량 평균은 피벗봉(고점을 만든 상승일) 다음 날부터 — 피벗봉 거래량 폭증이 판정을 흔들지 않음."""
    base = _df()
    r0 = _run(base)
    seg = [a for a in r0.annotations if a["kind"] == "segment"][0]["points"]
    p_i = base.index.get_loc(pd.Timestamp(seg[2 * (r0.metrics["n_contractions"] - 1)][0]))
    df = set_bar(base, p_i, volume=base["volume"].iloc[p_i] * 20)
    r = _run(df)
    assert r.detected, r.warnings
    assert r.metrics["last_contraction_vol_ratio"] == pytest.approx(r0.metrics["last_contraction_vol_ratio"])


def test_final_contraction_volume_gate():
    """최종 수축 거래량이 50일 중앙값의 ~0.89배(> 0.85배)면 탈락, ~0.82배면 통과(감소 폭 경고).
    (기준선이 평균 → 중앙값으로 바뀌며 상한도 0.75 → 0.85 로 재보정 — 워크포워드에서 중앙값 0.75~0.85 구간의
    돌파 성과가 0.75 이하와 차이가 없었다.)"""
    vs = [(150, 250, 1.3), (250, 275, 1.6), (300, 315, 0.75)]
    r = _run(_df(vs=vs + [(330, 353, 0.80)]))
    _assert_well_formed(r)
    assert not r.detected
    assert any("최종 수축 거래량" in w for w in r.warnings), r.warnings
    r2 = _run(_df(vs=vs + [(330, 353, 0.74)]))
    assert r2.detected, r2.warnings
    assert 0.7 < r2.metrics["last_contraction_vol_ratio"] <= 0.85
    assert any("감소 폭이 크지 않음" in w for w in r2.warnings)


def test_nan_volume_in_final_contraction_rejected():
    df = _df()
    df.loc[df.index[-15:], "volume"] = np.nan
    r = _run(add_value(df))
    _assert_well_formed(r)
    assert not r.detected
    assert any("결측" in w for w in r.warnings), r.warnings


def test_zero_volume_days_not_counted_as_dryup():
    base = _df()
    df = base.copy()
    df.loc[df.index[-3:], "volume"] = 0.0
    df = add_value(df)
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert any("결측/0 3봉" in w for w in r.warnings), r.warnings
    # 고갈일은 거래량 > 0 인 봉만: 마지막 10봉 중 0 이 아닌 고갈일 수와 일치 (기준선 = 피벗봉 전날까지 50일 중앙값)
    seg = [a for a in r.annotations if a["kind"] == "segment"][0]["points"]
    p_i = df.index.get_loc(pd.Timestamp(seg[2 * (r.metrics["n_contractions"] - 1)][0]))
    v50 = df["volume"].iloc[p_i - 50:p_i]
    base = float(v50[v50 > 0].median())
    w = df["volume"].iloc[-10:]
    assert r.metrics["dryup_days"] == int(((w > 0) & (w < 0.5 * base)).sum())


# ---------------------------------------------------------------- 회귀: 거래정지일 경고 (미래 정보 유입 방지)
def test_halt_dates_only_within_window():
    full = _df(extra_w=[(420, 120)])
    full.attrs["halt_dates"] = [full.index[400].strftime("%Y-%m-%d")]  # 잘린 시점 이후(미래) 거래정지
    trunc = full.iloc[:353]
    assert trunc.attrs.get("halt_dates")  # iloc 슬라이스에도 attrs 가 따라옴
    r = _run(trunc)
    assert r.detected
    assert not any("거래정지" in w for w in r.warnings), r.warnings
    trunc2 = full.iloc[:353].copy()
    trunc2.attrs["halt_dates"] = [full.index[340].strftime("%Y-%m-%d")]
    r2 = _run(trunc2)
    assert any("거래정지" in w for w in r2.warnings), r2.warnings


# ---------------------------------------------------------------- 회귀: 실전 오탐 (2026-10 검증)
def _cfg(**kw) -> Config:
    return Config(patterns={"vcp": VCPConfig(**kw)})


def _seg_idx(df, r) -> list[int]:
    seg = [a for a in r.annotations if a["kind"] == "segment"][0]["points"]
    return [df.index.get_loc(pd.Timestamp(d)) for d, _ in seg]


def test_near_52w_high_mandatory_at_last_bar():
    """트렌드 템플릿 7/8 이라도 빠진 하나가 7번(52주 고점 -25% 이내)이면 탈락 — 급락 후 반등 구간의 2차 고점
    (SK스퀘어·SK·네이처셀·제주반도체형). 같은 구조라도 규칙을 끄면 탐지되므로 이 기준이 탈락 사유다."""
    w = [(0, 40), (150, 60), (165, 62), (170, 140), (175, 64)] + BASE_W[2:]
    df = _df(w=w)
    r = _run(df)
    _assert_well_formed(r)
    assert not r.detected
    assert any("7번" in x and "52주 고점" in x and "7/8" in x for x in r.warnings), r.warnings
    assert _run(df, cfg=_cfg(require_near_high=False, min_high_vs_prior=0.0)).detected


def test_near_52w_high_mandatory_at_breakout_bar():
    """돌파한 베이스는 돌파봉 시점에도 52주 고점 -25% 이내여야 한다. 마지막 봉에서는 옛 고점(1봉 꼬리 — 대표 고가로
    보는 규칙 1 은 통과)이 52주 창 밖으로 빠졌지만 돌파봉의 52주 창 안에는 있는 경우."""
    df = _df(extra_w=[(353, 100.5), (362, 103)], extra_vs=[(353, 354, 3.0)]).iloc[:363]
    ok = _run(df)
    assert ok.detected and ok.breakout_date == df.index[353].strftime("%Y-%m-%d"), ok.warnings
    k = 362 - 252  # 마지막 봉(362)의 52주 창 밖, 돌파봉(353)의 52주 창 안
    r = _run(set_bar(df, k, high=float(df["close"].iloc[k]) * 2.6))
    _assert_well_formed(r)
    assert not r.detected
    assert any("돌파 시점" in x and "52주 고점" in x for x in r.warnings), r.warnings


def test_base_high_far_below_prior_high_rejected():
    """베이스 고점이 직전 250봉 최고가(대표 고가)의 90% 미만 → 급락 후 반등 구간의 2차 고점(심텍홀딩스형).
    옛 고점이 마지막 봉의 52주 창 밖이라 7번 기준은 통과하는 경우에도 탈락."""
    w = [(0, 40), (60, 80), (95, 130), (130, 70), (150, 60)] + BASE_W[2:]
    df = _df(w=w)
    r = _run(df)
    _assert_well_formed(r)
    assert not r.detected
    assert not any("Stage 2" in x for x in r.warnings), r.warnings
    assert any("급락 후 반등 구간" in x for x in r.warnings), r.warnings
    assert _run(df, cfg=_cfg(min_high_vs_prior=0.0)).detected


def test_secondary_high_after_higher_peak_is_not_base_start():
    """베이스 고점 13봉 전에 더 높은 고점(110)과 그 사이 눌림이 있으면 베이스는 그 고점에서 시작한다(티앤엘형).
    그 기준으로 피벗이 -16% 라 탈락. 예전처럼 왼쪽 5봉만 보면 낮아진 2차 고점(≈100)을 베이스 고점으로 오인해 탐지."""
    w = [(0, 40), (150, 60), (225, 96), (238, 110), (244, 92), (250, 100)] + REB_W[3:]
    df = make_ohlcv(w, noise=0.003, wick=0.004, vol_segments=REB_VS, seed=1)
    r = _run(df)
    _assert_well_formed(r)
    assert not r.detected
    assert r.metrics["base_high"] > 108
    assert any("피벗이 베이스 고점 대비" in x for x in r.warnings), r.warnings
    old = _run(df, cfg=_cfg(peak_left_bars=5))
    assert old.detected and old.metrics["base_high"] < 102


@pytest.mark.parametrize("kind", ["wick", "limit_up"])
def test_spike_base_high_uses_representative_high(kind):
    """베이스 고점 봉이 1봉 스파이크(장중 꼬리 +12% / 하루 만에 되돌린 상한가)면 그 고가가 아니라 3봉 중앙값 대표
    고가로 깊이를 계산하고 경고(컴투스·케이씨형). 상한가 봉은 52주 고점(원래 고가)을 끌어올리므로 7번 기준은 끈다."""
    base = _df()
    r0 = _run(base)
    j = base.index.get_loc(pd.Timestamp(r0.start_date))
    c = float(base["close"].iloc[j])
    if kind == "wick":
        df, kw = set_bar(base, j, high=c * 1.12), {}
    else:
        df, kw = set_bar(base, j, open=c, high=c * 1.295, close=c * 1.295), {"require_near_high": False}
    r = _run(df, cfg=_cfg(**kw))
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.metrics["base_high"] < c * 1.03
    assert r.metrics["first_depth"] == pytest.approx(r0.metrics["first_depth"], abs=0.01)
    assert r.pivot == pytest.approx(r0.pivot)
    assert any("1봉 스파이크" in x and "베이스 고점" in x for x in r.warnings), r.warnings
    # 가드를 끄면 스파이크 고가가 베이스 고점이 되어 1차 수축이 부풀거나(꼬리) 다른 베이스로 바뀐다(상한가)
    raw = _run(df, cfg=_cfg(spike_tol=9.0, require_near_high=False, min_high_vs_prior=0.0))
    assert not raw.detected or abs(raw.metrics["first_depth"] - r.metrics["first_depth"]) > 0.05


def test_spike_pivot_bar_uses_representative_high():
    """최종 수축 시작 고점이 1봉 스파이크(+10%)면 피벗은 대표 고가 — 꼬리 끝을 피벗으로 쓰지 않는다."""
    base = _df()
    r0 = _run(base)
    p_i = _seg_idx(base, r0)[2 * (r0.metrics["n_contractions"] - 1)]
    df = set_bar(base, p_i, high=float(base["close"].iloc[p_i]) * 1.10)
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.pivot == pytest.approx(r0.pivot, rel=0.01)
    assert any("1봉 스파이크" in x and "피벗" in x for x in r.warnings), r.warnings


def test_news_spike_day_cannot_fake_dryup():
    """최종 수축 직전 50일 안의 뉴스 급등일(30배) 하루가 50일 '평균'을 부풀리면 평범한 거래량도 ~0.67배 '고갈'로
    보인다(컴투스·빙그레형). 기준선은 중앙값 → ~1.0배로 판정해 탈락, 평균 기준 비율은 참고로 함께 보고."""
    vs = [(150, 250, 1.3), (250, 275, 1.6), (300, 315, 0.75), (290, 291, 30.0), (330, 353, 0.9)]
    df = _df(vs=vs)
    r = _run(df)
    _assert_well_formed(r)
    assert not r.detected
    m = r.metrics
    assert m["last_contraction_vol_ratio_mean"] < 0.75 and m["last_contraction_vol_ratio"] > 0.85
    assert any("중앙값" in x and "착시" in x for x in r.warnings), r.warnings
    assert _run(df, cfg=_cfg(vol_baseline="mean", max_last_vol_ratio=0.75)).detected  # 예전 방식이면 통과


def test_breakout_reports_robust_volume_ratio():
    df = _df(extra_w=[(353, 100.5)], extra_vs=[(353, 354, 3.0)])
    r = _run(df)
    assert r.stage == BREAKOUT
    m = r.metrics
    assert m["breakout_vol_ratio"] >= 1.4 and m["breakout_vol_ratio_robust"] >= 1.4


def _tail(seed):
    """2차 수축 고점 직후 1봉 급락 꼬리(84.5) → 반등 → 완만한 하락: 병합 규칙이 꼬리를 지워도 깊이는 실제 저점."""
    d = set_bar(_df(seed=seed), 301, open=97.0, high=97.2, low=84.5, close=95.5)
    d = set_bar(d, 302, open=95.5, high=97.3, low=95.2, close=96.6)
    return set_bar(d, 303, open=96.6, high=96.9, low=96.0, close=96.3)


def _final_lower_low():
    """최종 수축 안에서 지그재그 저점 뒤에 반등폭이 작은 더 낮은 저점(삼성전자형: 깊이와 손절가가 다른 저점을 쓰던 경우)."""
    base = _df()
    return set_bar(base, 343, low=float(base["low"].iloc[331:353].min()) * 0.995)


@pytest.mark.parametrize("make", [_df, _final_lower_low, lambda: _tail(1), lambda: _tail(2), lambda: _tail(3)])
def test_contraction_depth_uses_true_lowest_low(make):
    """각 수축의 저점 = 그 수축의 스윙 고점 다음 봉 ~ 다음 스윙 고점 전 봉(최종 수축은 ~종료점)의 실제 최저가.
    최종 수축 깊이와 손절가는 같은 저점에서 나온다(코미팜·삼성전자형)."""
    df = make()
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected and r.breakout_date is None, r.warnings
    idx, e = _seg_idx(df, r), len(df) - 1
    pts = [p for _, p in [a for a in r.annotations if a["kind"] == "segment"][0]["points"]]
    n = r.metrics["n_contractions"]
    for k in range(n):
        h, nxt = idx[2 * k], (idx[2 * k + 2] - 1 if k + 1 < n else e)
        assert idx[2 * k + 1] <= nxt
        assert pts[2 * k + 1] == pytest.approx(float(df["low"].iloc[h + 1:nxt + 1].min())), k
    assert r.stop == pytest.approx(pts[2 * n - 1])
    assert r.metrics["final_contraction_depth"] == pytest.approx(r.metrics["risk_pct"], abs=1e-4)


def test_final_lower_low_reported_in_depth():
    r = _run(_final_lower_low())
    low = float(_final_lower_low()["low"].iloc[343])
    assert r.stop == pytest.approx(low)
    assert r.metrics["final_contraction_depth"] == pytest.approx(1 - low / r.pivot, abs=1e-4)


# 매물대: 베이스 고점(100) 뒤 세 번 되돌아와 99.3·98.6·97.9 를 시험(저점은 계속 낮아져 한 수축으로 병합)한 뒤
# 피벗 ≈ 93.5 — 피벗 +3% 위에 같은 가격대의 별개 고점 3개 (KT&G형: 188~192k 반복 고점 아래 179.7k 피벗)
OV_W = [(0, 40), (130, 60), (225, 100), (233, 90), (241, 99.3), (249, 88.5), (257, 98.6), (265, 87), (273, 97.9),
        (285, 80), (296, 94.5), (311, 86), (326, 93.5), (336, 90), (344, 92.9), (351, 93.1)]
OV_VS = [(130, 225, 1.3), (225, 285, 1.5), (296, 311, 0.75), (326, 352, 0.45)]


@pytest.mark.parametrize("seed", [2, 3, 4])
def test_overhead_supply_penalized(seed):
    """피벗 +3% 위에서 반복 실패한 별개 고점 3개 이상 → 저항대 아래 피벗: 경고 + 감점(KT&G형)."""
    df = make_ohlcv(OV_W, noise=0.003, wick=0.004, vol_segments=OV_VS, seed=seed)
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert r.metrics["overhead_highs"] >= 3
    assert any("피벗 위 매물대" in x for x in r.warnings), r.warnings
    assert r.metrics["sc_매물대"] <= -6
    off = _run(df, cfg=_cfg(overhead_min_count=99))
    assert r.score <= off.score - 6 + 1e-6


@pytest.mark.parametrize("w,vs", [
    (BASE_W, BASE_VS),
    (REB_W, REB_VS),
    # 4T 하강 고점 계단: 2·3차 수축 시작 고점(97, 94.5)이 피벗 +3% 위여도 VCP 자체 구조라 매물로 세지 않음
    ([(0, 40), (150, 60), (250, 100), (275, 75), (295, 97), (308, 85), (320, 94.5), (330, 88), (340, 91.5),
      (346, 89), (352, 91), (356, 91.2)],
     [(150, 250, 1.3), (250, 275, 1.6), (295, 308, 0.8), (320, 357, 0.45)]),
])
def test_descending_highs_not_penalized(w, vs):
    r = _run(make_ohlcv(w, noise=0.003, wick=0.004, vol_segments=vs, seed=1))
    assert r.detected, r.warnings
    assert r.metrics["overhead_highs"] < 2
    assert r.metrics["sc_매물대"] == 0
    assert not any("피벗 위 매물대" in x for x in r.warnings)


def test_entry_risk_over_10pct_penalized():
    """진입 위험(피벗→손절, = 최종 수축 깊이) 11% > 10% → 경고 + 감점 (미너비니 손절 7~8%)."""
    w = [(0, 40), (150, 60), (250, 100), (275, 70), (300, 97), (315, 80), (330, 96), (340, 86.6), (348, 94),
         (352, 94.2)]
    df = make_ohlcv(w, noise=0.003, wick=0.004, seed=1,
                    vol_segments=[(150, 250, 1.3), (250, 275, 1.6), (300, 315, 0.75), (330, 353, 0.45)])
    r = _run(df)
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert 0.10 < r.metrics["risk_pct"] <= 0.12
    assert any("진입 위험" in x for x in r.warnings), r.warnings
    assert r.metrics["sc_손절폭"] <= -5
    assert r.score <= _run(df, cfg=_cfg(warn_risk=0.5)).score - 5 + 1e-6


# ---------------------------------------------------------------- (c) 음성 사례
def test_expanding_contractions_rejected():
    w = [(0, 40), (150, 60), (250, 100), (265, 90), (285, 99), (300, 84), (320, 98), (340, 76), (360, 96),
         (366, 96)]
    r = _run(_df(w=w, vs=[(150, 250, 1.3), (340, 367, 0.5)]))
    _assert_well_formed(r)
    assert not r.detected


def test_no_volume_dryup_rejected():
    vs = [(150, 250, 1.3), (250, 275, 1.0), (300, 315, 1.2), (330, 353, 1.8)]
    r = _run(_df(vs=vs))
    _assert_well_formed(r)
    assert not r.detected
    assert any("거래량" in w for w in r.warnings)


def test_too_deep_first_contraction_rejected():
    w = [(0, 40), (150, 60), (250, 100), (290, 44), (330, 95), (345, 88), (355, 94), (362, 93.5)]
    r = _run(_df(w=w, vs=[(345, 363, 0.5)]))
    _assert_well_formed(r)
    assert not r.detected


def test_downtrend_rejected():
    w = [(0, 220), (250, 110), (275, 84), (300, 108), (315, 96), (330, 107), (338, 102), (346, 106), (352, 106)]
    r = _run(_df(w=w), rs=40)
    _assert_well_formed(r)
    assert not r.detected
    assert any("Stage 2" in w for w in r.warnings)


def test_single_contraction_rejected():
    w = [(0, 40), (150, 60), (250, 100), (275, 76), (305, 98), (330, 98.5)]
    r = _run(_df(w=w, vs=[(305, 331, 0.5)]))
    _assert_well_formed(r)
    assert not r.detected


def test_final_contraction_too_deep_rejected():
    w = [(0, 40), (150, 60), (250, 100), (275, 68), (300, 98), (322, 80), (345, 96), (352, 96)]
    r = _run(_df(w=w, vs=[(322, 353, 0.5)]))
    _assert_well_formed(r)
    assert not r.detected


def test_no_prior_advance_rejected():
    w = [(0, 88), (250, 100), (275, 76), (300, 98), (315, 87), (330, 97.5), (338, 93), (346, 96.5), (352, 96.8)]
    r = _run(_df(w=w))
    _assert_well_formed(r)
    assert not r.detected
    assert any("선행 상승" in w or "Stage 2" in w for w in r.warnings)


def test_v_shaped_deep_short_base_rejected():
    """40% 급락 후 몇 주 만에 V자 회복한 짧은 베이스는 VCP 아님."""
    w = [(0, 40), (150, 60), (250, 100), (253, 60), (259, 95), (262, 89), (266, 96), (268, 93.5), (272, 96),
         (273, 96.1)]
    r = _run(_df(w=w, vs=[(262, 274, 0.5)]))
    _assert_well_formed(r)
    assert not r.detected
    assert any("V자" in w for w in r.warnings), r.warnings
    # 같은 모양이라도 베이스가 충분히 길면(깊은 1차 수축 후 6주 이상) 탐지
    w2 = [(0, 40), (150, 60), (250, 100), (262, 60), (282, 95), (290, 89), (300, 96), (306, 93.5), (314, 96),
          (316, 96.1)]
    r2 = _run(_df(w=w2, vs=[(282, 317, 0.5)]))
    assert r2.detected, r2.warnings


def test_final_contraction_larger_than_previous_rejected():
    """25% → 5% → 6.6%: 저점은 올라가지만 마지막 수축이 직전보다 큼 → 탈락."""
    w = [(0, 40), (150, 60), (250, 100), (275, 75), (300, 96), (312, 91), (325, 98.5), (335, 92), (345, 97),
         (350, 97.2)]
    r = _run(_df(w=w, vs=[(300, 351, 0.5)], noise=0.002, wick=0.003))
    _assert_well_formed(r)
    assert not r.detected
    assert any("직전 수축" in w for w in r.warnings), r.warnings


def test_prior_advance_rule_enforced():
    """교과서형(선행 상승 ~150%)도 선행 상승 기준을 200%로 올리면 탈락 — 규칙이 실제로 적용되는지 확인."""
    cfg = Config(patterns={"vcp": VCPConfig(prior_advance_min=2.0)})
    r = _run(_df(), cfg=cfg)
    _assert_well_formed(r)
    assert not r.detected
    assert any("선행 상승" in w for w in r.warnings), r.warnings


def test_config_override_tightens_rules():
    cfg = Config(patterns={"vcp": VCPConfig(max_final_depth=0.02)})
    r = _run(_df(), cfg=cfg)
    assert not r.detected


# ---------------------------------------------------------------- (d) 견고성
def _flat_df(n, price=100.0, vol=1e6):
    idx = pd.bdate_range("2023-01-02", periods=n)
    return add_value(pd.DataFrame({"open": price, "high": price, "low": price, "close": price,
                                   "volume": vol}, index=idx))


def test_short_history_no_raise():
    r = _run(_df().iloc[-60:])
    _assert_well_formed(r)
    assert not r.detected
    assert any("이력 부족" in w for w in r.warnings)


def test_flat_line_no_raise():
    r = _run(_flat_df(400))
    _assert_well_formed(r)
    assert not r.detected


def test_zero_volume_no_raise():
    r = _run(_flat_df(400, vol=0.0))
    _assert_well_formed(r)
    assert not r.detected


@pytest.mark.parametrize("seed", range(8))
def test_random_walk_no_raise(seed):
    rng = np.random.default_rng(seed)
    n = 750
    c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.025, n)))
    idx = pd.bdate_range("2023-01-02", periods=n)
    o = np.r_[c[0], c[:-1]]
    df = add_value(pd.DataFrame({"open": o, "high": np.maximum(o, c) * 1.01, "low": np.minimum(o, c) * 0.99,
                                 "close": c, "volume": rng.lognormal(13, 0.5, n).round()}, index=idx))
    r = _run(df)
    _assert_well_formed(r)
    if r.detected:
        assert r.pivot and r.stop and r.stop < r.pivot


def test_nan_and_constant_volume_no_raise():
    df = _df()
    df.iloc[-30, df.columns.get_loc("close")] = np.nan
    r = _run(df)
    _assert_well_formed(r)
    assert not r.detected
    df2 = _df()
    df2["volume"] = 1e6
    df2 = add_value(df2)
    r2 = _run(df2)
    _assert_well_formed(r2)  # 일정 거래량 → 고갈 없음 → 미탐지가 정상
    assert not r2.detected


def test_old_price_glitch_outside_window_is_ignored():
    """최근 576봉 밖의 오래된 결측 가격은 무시(그 이후 데이터만 사용) — 선행 상승이 NaN 으로 통과되지 않음."""
    w = [(0, 30), (300, 32)] + [(i + 450, p) for i, p in BASE_W[1:]]
    vs = [(s + 450, e + 450, m) for s, e, m in BASE_VS]
    df = make_ohlcv(w, noise=0.003, wick=0.004, vol_segments=vs, seed=1)
    df.iloc[150, df.columns.get_loc("low")] = np.nan  # 최근 576봉 바깥
    r = _run(add_value(df))
    _assert_well_formed(r)
    assert r.detected, r.warnings
    assert np.isfinite(r.metrics["prior_advance"]) and r.metrics["prior_advance"] > 0.25


def test_rs_missing_no_raise():
    r = _run(_df(), rs=None)
    _assert_well_formed(r)
    assert r.detected  # 7/8 충족 (RS 미상)
