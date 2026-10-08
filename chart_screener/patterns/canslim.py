"""CAN SLIM (윌리엄 오닐) — 기술적 요소 스코어카드.

O'Neil, *How to Make Money in Stocks* 의 7개 요소 중 차트로 판정 가능한 N·S·L·I·M 을
각각 0~100 점으로 채점하고 가중 평균(종합점수)한다. 펀더멘털 C·A 는
``ctx.info['fundamentals']`` 가 있을 때만 채점하며, 없으면 'N/A' 로 두고 감점하지 않는다.

베이스 · 피벗 (모든 판정의 기준 구조)
    조정 고점 = 직전 10봉 고가 이상(좌측 스윙 고점)이고, 이후 10봉 동안 종가가 한 번도 넘지 못한 고가.
    피벗(매수 기준가) = 최근 120봉 안 조정 고점 중 최고가.
        단, 120봉 창 밖(최대 325봉 = 65주)에 그보다 높고 이후 종가로 한 번도 돌파되지 않은 조정 고점
        (= 아직 진행 중인 긴 베이스의 왼쪽 고점)이 있으면 그중 최고가가 피벗 — 창이 밀려도 피벗이 미끄러지지
        않는다. 그 고점 이후 최저가까지 65% 넘게 빠졌으면 '하락 추세 뒤 새 베이스'로 보고 확장하지 않는다.
        조정 고점이 없으면(쉼 없는 연속 상승) 마지막 5봉을 뺀 120봉 최고가('run', 상회 시 extended).
    베이스 시작(왼쪽 고점) = 피벗 이전 마지막 '종가 > 피벗' 이후, 피벗 -5%~피벗 범위의 조정 고점 중 그보다
        높은 고가가 나오기 전에 8% 이상 눌림(컵)이 있었던 가장 이른 봉, 없으면 피벗 봉 (오른쪽이 왼쪽 고점을
        살짝 넘은 컵앤핸들도 컵 전체를 베이스로 측정).
    베이스 종료 = 돌파봉 직전(돌파 없으면 마지막 봉). 깊이 = 1 − 베이스 최저가/피벗, 길이 = 시작~종료 봉 수.
    손잡이 = 베이스 저점 이후 최고가에서의 되밀림(깊이·봉수, 보고만).
    돌파봉 = 피벗 봉 이후 처음 종가가 피벗을 넘은 봉 (classify_stage).
    손절가 = 피벗 × (1 − 7%) (오닐 7~8%, 피벗 매수 기준, stop_basis='pivot').
            extended 는 추격 매수 기준으로 현재가 × (1 − 7%) (stop_basis='close').

N  신고가      : 근접도 55 (52주 고점 -25%→0, -15%→30, -5%→50, 0%→55) + 최근 5봉 내 52주 신고가 15
                + 보유 이력 최고가 10 + 돌파 가산 20 중 하나:
                  · 피벗을 최근 10봉 내 거래량 1.4배↑로 돌파 20 (거래량 미달 5, 돌파 후 피벗 아래 마감이면 절반)
                  · 돌파 실패(FAILED: 피벗 -3% 아래) 0 + 경고
                  · 돌파 전 피벗 -5% 이내 대기 10 — 단 최근 5봉에 장중 피벗을 넘고 되밀렸으면 0 + 경고,
                    그 봉 종가 위치 < 0.4(키 리버설)면 -5
                  · (위 피벗 돌파 가산이 없을 때) 스펙의 단기 돌파: 최근 10봉 내 직전 50봉 고점(5봉 이상 묵은)을
                    거래량 1.4배↑로 종가 돌파하고 아직 그 위(-3% 이내)면 10
                베이스 깊이 50% 초과는 돌파 가산 5·대기 5·단기 돌파 5만 인정 (+ 종목 점수 배수 감점).
                신고가는 '초과'만 인정(동률 제외). 돌파 실패, 또는 장중 피벗 돌파 후 하단 절반 마감한 반전 봉의
                신고가는 가산하지 않는다.
S  수급        : 50일 U/D 거래량 비(≥1.0 양호, ≥1.5 우수) 30, IBD식 매집/분산 등급(65봉, A~E) 25,
                대량거래(50일 평균 1.5배↑) 상승일 vs 하락일(50봉) 25, 거래대금 300억↑ 일수(50봉) 20.
                시가총액은 보고만 한다.
L  주도주      : RS 레이팅(≥80 필수, ≥90 이상적) 40, RS선 52주 고점 -2~5% 이내 25,
                RS선 선행 신고가(주가보다 먼저 52주 신고가) 20, RS선 63일 기울기 양(+) 15.
I  기관 수요   : 기술적 대용 = 20일 U/D 거래량 비 30 + 포켓 피벗(10봉) 30 + OBV 50일 신고·기울기 25
                + 최근 20봉 최대 거래량일이 상승·상단 마감 15.
                ``ctx.info['investor']`` (기관·외국인 순매매 DataFrame, data/investor.py) 가 있으면
                20일 누적 순매수 점수와 반반 섞는다. (네트워크 호출 없음)
M  시장 방향   : 시장 상태(상승 확인 100 / 압박 50 / 조정 5) 60% + MarketState.score 40%, 분산일 감점.
C·A 펀더멘털   : fundamentals = {'eps_q_yoy', 'eps_q_yoy_prev', 'sales_q_yoy', 'eps_annual_growth_3y', 'roe'}
                (단위 %, 예: 25.0 = 25%). C: 최근 분기 EPS YoY ≥ 25%. A: 연간 EPS 성장 ≥ 25% & ROE ≥ 17%.

종목 점수 = (N .30, S .20, L .25, I .10 (+ C .15, A .10 있으면) 가중 평균) × 품질 배수 — M 제외.
    품질 배수 (오닐의 '결함 베이스'): 베이스 깊이 >50% ×0.85, >65% ×0.70 / V자 급반등(베이스 우측이 저점 대비
    +60% 이상을 30봉 이내에, 신고 종가 없는 5봉 이상 쉼(손잡이) 없이 — 돌파 전까지만 측정) ×0.85 /
    돌파 실패 ×0.80 — 곱으로 누적.
종합점수(composite) = 종목 점수와 M(.15) 의 가중 평균. score = composite (조정장이면 ×0.7).
탐지(detected) = 종목 점수 ≥ 70 이고 필수 조건 모두 충족:
    RS ≥ 80, 52주 고점 -25% 이내, N 충족(52주 고점 -15% 이내 또는 최근 5봉 신고가 — RS선 선행 신고가면 면제),
    종가 > 50일선·200일선, 이력 ≥ 120봉.
    시장 상태는 탐지 여부를 바꾸지 않는다 — 조정 국면이면 탐지는 유지하되 M 저하 + 점수 ×0.7 + 강한 경고.

경고(점수 무관): 베이스 깊이 50% 초과, 베이스 25봉(5주) 미만, 분석 구간의 거래정지일·거래량 0 봉
(거래정지 추정 — 50일 평균 거래량 왜곡), 장중 미완성 봉(거래량 하루치 추정), 시장 상태 기준일 불일치.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from .. import indicators as ind
from ..market import CONFIRMED, CORRECTION, PRESSURE, STATE_LABELS
from .base import (BREAKOUT, EXTENDED, FAILED, FORMING, PatternResult, StockContext, box, classify_stage, hline,
                   marker, register)

NAME, LABEL = "canslim", "CAN SLIM (기술적 요소)"


@dataclass
class CanslimConfig:
    # ---- 공통
    min_bars: int = 60                 # 이 미만이면 채점 불가 (50일 통계 필요)
    min_detect_bars: int = 120         # 탐지 판정 최소 이력 (상장 약 6개월)
    year: int = 252                    # 52주
    # ---- N: 신고가 (오닐: 신고가 부근의 올바른 베이스에서 돌파할 때 매수)
    n_within_high: float = 0.15        # 52주 고점 -15% 이내 (N 충족 = 탐지 필수)
    n_zero_dist: float = 0.25          # 근접도 점수가 0 이 되는 거리
    n_new_high_bars: int = 5           # 최근 5봉 내 52주 신고가
    ath_min_extra_bars: int = 60       # 이력 최고가 가산은 52주보다 60봉 이상 긴 이력에서만
    breakout_vol_mult: float = 1.4     # 돌파 거래량: 50일 평균 대비 +40% 이상 (오닐)
    breakout_recent_bars: int = 10     # N 가산 대상 '최근 돌파' 범위
    max_base_depth: float = 0.50       # 오닐: 베이스 깊이 최대 33~50% — 초과 시 돌파 가산 축소·경고
    short_bo_lookback: int = 50        # 스펙: 직전 25~50봉 고점 돌파 가산 (피벗 돌파 가산이 없을 때)
    short_bo_min_age: int = 5          # 그 고점이 최소 5봉(1주) 이상 묵어야 '돌파' (연속 상승 제외)
    short_bo_pts: float = 10.0
    key_rev_pos: float = 0.40          # 장중 피벗 돌파 봉의 종가 위치가 이 미만이면 키 리버설
    key_rev_pts: float = 5.0
    # ---- 피벗 / 베이스 / 단계
    pivot_lookback: int = 120          # 피벗 탐색 구간 (약 6개월: 대부분 베이스의 왼쪽 고점 포함)
    max_base_lookback: int = 325       # 오닐 베이스 최대 65주 — 창 밖 '미돌파' 왼쪽 고점 탐색 한계
    ext_max_depth: float = 0.65        # 창 밖 고점 기준 깊이가 이보다 깊으면 '하락 추세 후 새 베이스'로 보고 확장 안 함
    min_cons_bars: int = 10            # 조정 고점: 좌우 10봉(2주) 기준
    lip_tol: float = 0.05              # 베이스 시작: 피벗 -5% 이내의 가장 이른 조정 고점이면서
    lip_min_dip: float = 0.08          # ... 더 높은 고가 이전에 8% 이상 눌림(컵)이 있었던 봉 (단순 상승 구간 제외)
    min_base_bars: int = 25            # 오닐 베이스 최소 5주 — 미만이면 경고만
    breakout_window: int = 5
    near_pct: float = 0.05
    buy_range: float = 0.05            # 피벗 +5% 이내만 매수 (오닐)
    fail_pct: float = 0.03
    stop_pct: float = 0.07             # 오닐 7~8% 손절 원칙
    # ---- 품질 배수 (결함 베이스)
    deep_mult: tuple = ((0.50, 0.85), (0.65, 0.70))   # (깊이 초과 기준, 배수) — 깊은 쪽 우선
    v_rise: float = 0.60               # V자: 베이스 저점 대비 +60% 이상
    v_bars: int = 30                   # ... 30봉 이내 도달
    v_pause: int = 5                   # ... 그동안 5봉 이상 신고 종가 없는 쉼(손잡이)이 없음
    v_mult: float = 0.85
    failed_mult: float = 0.80          # 돌파 실패 (오닐: 매도·회피 신호)
    # ---- S: 수급
    ud_days: int = 50                  # O'Neil U/D ratio 기간
    ud_good: float = 1.0
    ud_great: float = 1.5
    ud_floor: float = 0.8              # 이하이면 0점
    ad_days: int = 65                  # IBD 매집/분산 등급: 13주
    ad_cuts: tuple = (0.20, 0.07, -0.07, -0.20)   # A, B, C, D 하한 (실데이터 분포로 보정)
    big_vol_mult: float = 1.5          # 대량거래일: 50일 평균의 1.5배 이상
    big_days: int = 50
    value_days: int = 50               # 300억 거래대금 일수 집계 기간 (기준값은 Config.big_value_threshold)
    value_full_days: int = 5           # 5일 이상이면 만점
    # ---- L: 주도주
    rs_min: float = 80.0               # 오닐: RS 80 이상
    rs_ideal: float = 90.0
    rs_line_tight: float = 0.02        # RS선 52주 고점 -2% 이내 만점
    rs_line_near: float = 0.05         # -5% 이내 양호
    rs_line_zero: float = 0.15         # -15% 이하 0점
    rs_lead_bars: int = 10             # RS선 선행 신고가 탐색 범위
    rs_slope_days: int = 63            # RS선 기울기 (1분기)
    # ---- I: 기관 수요
    i_ud_days: int = 20
    i_ud_lo: float = 0.8               # 20일 U/D: 0.8 이하 0점
    i_ud_mid: float = 1.2              # 1.2 → 절반
    i_ud_hi: float = 2.5               # 2.5 이상 만점 (단기 비율은 변동이 커 50일보다 높게)
    pp_days: int = 10                  # 포켓 피벗 집계 기간 (2주)
    pp_lookback: int = 10              # 포켓 피벗: 직전 10일 하락일 최대 거래량 초과
    pp_full: int = 2                   # 2회 이상 만점
    obv_days: int = 50
    footprint_days: int = 20           # 최대 거래량일 방향 점검 기간
    inv_days: int = 20                 # 기관+외국인 누적 순매수 기간
    inv_full_ratio: float = 0.05       # 순매수 / 거래량 5% 이상이면 만점
    inv_max_lag: int = 3               # 순매매 자료가 마지막 봉보다 이만큼 이상 늦으면 미사용
    # ---- M: 시장
    m_state_pts: tuple = (100.0, 50.0, 5.0)        # 상승 확인 / 압박 / 조정
    m_dd_free: int = 2
    m_dd_penalty: float = 5.0
    # ---- 종합
    weights: tuple = (0.30, 0.20, 0.25, 0.10, 0.15)  # N, S, L, I, M (I 는 대용지표라 비중 낮춤)
    w_c: float = 0.15
    w_a: float = 0.10
    min_composite: float = 70.0        # 탐지 기준 '종목 점수'(M 제외, 품질 배수 반영)
    correction_cut: float = 0.7        # 조정장 점수 배수
    must_within_high: float = 0.25     # 필수: 52주 고점 -25% 이내
    # ---- C·A (펀더멘털, 단위 %)
    c_eps_min: float = 25.0
    a_growth_min: float = 25.0
    a_roe_min: float = 17.0


# ---------------------------------------------------------------- 유틸
def _lin(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """x0→y0, x1→y1 선형 보간 (범위 밖은 끝값)."""
    if x is None or not np.isfinite(x):
        return y0
    t = (x - x0) / (x1 - x0) if x1 != x0 else 1.0
    return float(y0 + (y1 - y0) * min(1.0, max(0.0, t)))


def _num(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return f if math.isfinite(f) else float("nan")


def _r(x, nd: int = 3):
    return round(float(x), nd) if x is not None and np.isfinite(x) else float("nan")


def _f2(x: float) -> str:
    return f"{x:.2f}" if np.isfinite(x) else "판정 불가(등락 없음)"


@dataclass
class _Arr:
    """numpy 배열 묶음 (핫루프에서 pandas 인덱싱 회피)."""
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    val: np.ndarray
    vavg: np.ndarray      # 전일까지 50일 평균 거래량
    last: int


# ---------------------------------------------------------------- 베이스 · 피벗
@dataclass
class BaseGeom:
    pivot: float
    pj: int               # 피벗 봉
    base_end: int         # classify_stage 기준 봉 (이후 첫 종가 > 피벗 = 돌파봉)
    kind: str             # 'base' | 'run'
    start: int            # 베이스 시작 (왼쪽 고점)
    beyond: bool          # 120봉 창 밖의 미돌파 왼쪽 고점으로 확장했는지


def _consolidated(h: np.ndarray, c: np.ndarray, lo: int, hi: int, m: int) -> np.ndarray:
    """봉 lo..hi 의 '조정 고점' 여부: 직전 m봉 고가 이상(좌측 스윙) & 이후 m봉 종가가 모두 고가 이하."""
    if hi < lo:
        return np.zeros(0, dtype=bool)
    fwd = sliding_window_view(c[lo + 1:hi + m + 1], m).max(axis=1)          # j+1..j+m 종가 최고
    hp = np.concatenate([np.full(m, -np.inf), h])
    back = sliding_window_view(hp[lo:hi + m], m).max(axis=1)                 # j-m..j-1 고가 최고
    hs = h[lo:hi + 1]
    return (fwd <= hs) & (back <= hs)


def find_base(h: np.ndarray, l: np.ndarray, c: np.ndarray, cfg: CanslimConfig) -> BaseGeom:
    """현재 베이스의 피벗·왼쪽 고점 (모듈 docstring '베이스 · 피벗' 정의)."""
    last = len(c) - 1
    m = cfg.min_cons_bars
    lo = max(0, last - cfg.pivot_lookback + 1)
    ext = max(0, min(lo, last - cfg.max_base_lookback + 1))
    ok = _consolidated(h, c, ext, last - m, m)          # ok[t] ↔ 봉 ext + t
    cand = lo + np.flatnonzero(ok[lo - ext:])
    if len(cand):
        top = h[cand].max()
        j = int(cand[h[cand] >= top][-1])               # 동률이면 최근 고점
        kind, end = "base", j
    else:                                               # 쉼 없는 연속 상승
        end = max(lo, last - cfg.breakout_window)
        seg = h[lo:end + 1]
        j = lo + int(len(seg) - 1 - np.argmax(seg[::-1]))
        kind = "run"
    pivot, beyond = float(h[j]), False
    # 창 밖 왼쪽 고점: 피벗보다 높고 j 까지 종가로 한 번도 돌파되지 않은 조정 고점 → 진행 중인 긴 베이스
    n_out = min(lo - ext, len(ok))
    if n_out > 0:
        out = ext + np.flatnonzero(ok[:n_out])
        out = out[h[out] > pivot]
        if len(out):
            rc = np.maximum.accumulate(c[ext + 1:j + 1][::-1])[::-1]     # rc[t] = max(c[ext+1+t .. j])
            out = out[rc[out - ext] <= h[out]]
            sl = np.minimum.accumulate(l[ext:][::-1])[::-1]                # sl[t] = min(l[ext+t ..])
            out = out[1 - sl[out - ext] / h[out] <= cfg.ext_max_depth]
            if len(out):
                top = h[out].max()
                j = int(out[h[out] >= top][-1])
                pivot, kind, end, beyond = float(h[j]), "base", j, True
    return BaseGeom(pivot, j, end, kind, _base_start(h, l, c, ok, ext, pivot, j, cfg), beyond)


def _base_start(h: np.ndarray, l: np.ndarray, c: np.ndarray, ok: np.ndarray, ext: int, pivot: float, pj: int,
                cfg: CanslimConfig) -> int:
    """피벗 이전 마지막 '종가 > 피벗' 이후의 조정 고점 L 중, 피벗 -lip_tol ~ 피벗 범위이고 L 이후 더 높은
    고가가 나오기 전에 lip_min_dip 이상 눌린(컵) 가장 이른 봉. 없으면 피벗 봉 (= 피벗이 왼쪽 고점)."""
    above = np.flatnonzero(c[ext:pj] > pivot)
    s0 = ext + int(above[-1]) + 1 if len(above) else ext
    hi = min(pj - 2, ext + len(ok) - 1)
    if hi < s0:
        return pj
    hs = h[s0:hi + 1]
    idx = s0 + np.flatnonzero(ok[s0 - ext:hi - ext + 1] & (hs >= pivot * (1 - cfg.lip_tol)) & (hs <= pivot))
    for j in idx:
        up = np.flatnonzero(h[j + 1:pj + 1] > h[j])                # 첫 '더 높은 고가' 이전까지가 L 의 조정
        k = j + 1 + (int(up[0]) if len(up) else pj - j)
        if k > j + 1 and l[j + 1:k].min() <= h[j] * (1 - cfg.lip_min_dip):
            return int(j)
    return pj


def _v_shape(h: np.ndarray, l: np.ndarray, c: np.ndarray, low_i: int, end: int,
             cfg: CanslimConfig) -> tuple[bool, float, int, int]:
    """베이스 우측(저점 low_i ~ 베이스 종료 end): (V자 여부, 상승률, 고점까지 봉수,
    최장 쉼 = 신고 종가 없는 연속 봉수). 돌파 이후 상승은 포함하지 않는다(그건 extended 단계)."""
    if low_i >= end or not l[low_i] > 0:
        return False, 0.0, 0, 0
    top = int(np.argmax(h[low_i:end + 1]))
    rise = float(h[low_i + top] / l[low_i] - 1)
    cc = c[low_i:end + 1]
    prev_max = np.maximum.accumulate(np.concatenate([[-np.inf], cc[:-1]]))
    newhi = np.flatnonzero(cc > prev_max)
    pause = int((np.diff(np.concatenate([newhi, [len(cc)]])) - 1).max()) if len(newhi) else len(cc)
    v = rise >= cfg.v_rise and top <= cfg.v_bars and pause < cfg.v_pause
    return bool(v), rise, top, pause


def _short_breakout(a: _Arr, cfg: CanslimConfig) -> tuple[int, float, float] | None:
    """최근 breakout_recent_bars 봉 내, 직전 short_bo_lookback 봉 고점(short_bo_min_age 봉 이상 묵은)을
    거래량 breakout_vol_mult 배 이상으로 종가 돌파한 가장 최근 봉: (봉, 고점, 거래량 배수)."""
    last, L = a.last, cfg.short_bo_lookback
    res = None
    for i in range(max(L, last - cfg.breakout_recent_bars + 1), last + 1):
        w = a.h[i - L:i]
        k = int(np.argmax(w[::-1]))                     # 가장 최근 최고가까지의 거리 - 1
        lvl = float(w[len(w) - 1 - k])
        if k + 1 < cfg.short_bo_min_age or not a.c[i] > lvl:
            continue
        va = a.vavg[i]
        if np.isfinite(va) and va > 0 and a.v[i] >= cfg.breakout_vol_mult * va:
            res = (i, lvl, float(a.v[i] / va))
    return res


# ---------------------------------------------------------------- 문자별 채점
def _letter_n(a: _Arr, cfg: CanslimConfig, geo: dict, out: dict, ok: list, ng: list) -> float:
    h, l, c, last = a.h, a.l, a.c, a.last
    date = geo["date"]
    hi52 = float(h[max(0, last - cfg.year + 1):].max())
    dist = c[last] / hi52 - 1 if hi52 > 0 else float("nan")
    new_high_i = None
    for i in range(max(1, last - cfg.n_new_high_bars + 1), last + 1):
        if h[i] > h[max(0, i - cfg.year + 1):i].max():            # 동률은 신고가 아님
            new_high_i = i
    k = cfg.n_new_high_bars
    ath = (last + 1 > cfg.year + cfg.ath_min_extra_bars) and h[last - k + 1:].max() > h[:last - k + 1].max()

    # 근접도 (55): -25% → 0, -15% → 30, -5% → 50, 0% → 55
    z, w15, w5 = cfg.n_zero_dist, cfg.n_within_high, cfg.near_pct
    pts = (_lin(dist, -z, -w15, 0, 30) if dist < -w15 else
           _lin(dist, -w15, -w5, 30, 50) if dist < -w5 else _lin(dist, -w5, 0.0, 50, 55))
    within = bool(np.isfinite(dist) and dist >= -cfg.n_within_high)
    if within:
        ok.append(f"✔ [N] 52주 고점 대비 {dist:+.1%} (기준 -{cfg.n_within_high:.0%} 이내)")
    elif new_high_i is None:
        ng.append(f"✘ [N] 52주 고점 대비 {dist:+.1%} — 신고가권 이탈 (기준 -{cfg.n_within_high:.0%})")
    hi_pts = 15 * (new_high_i is not None) + 10 * bool(ath)    # 신고가 가산 (아래 단계 판정 후 확정)

    pivot, bo_i, bvr, stage = geo["pivot"], geo["bo_i"], geo["bo_vol_ratio"], geo["stage"]
    depth = geo["base_depth"]
    deep = bool(np.isfinite(depth) and depth > cfg.max_base_depth)
    if deep:
        ng.append(f"✘ [N] 베이스 깊이 {depth:.0%} — 오닐 기준(최대 {cfg.max_base_depth:.0%}) 초과: 결함 베이스 가능")
    if geo["v_shape"]:
        ng.append(f"✘ [N] V자 급반등 — 베이스 저점 대비 +{geo['v_rise']:.0%}를 {geo['v_bars']}봉에, "
                  f"{cfg.v_pause}봉 이상 쉼(손잡이) 없음")
    pv = f"{pivot:,.0f}"
    bonus = False
    void_high = False                                     # 신고가가 실패 돌파·하단 반전 봉의 장중 고가뿐인 경우
    if bo_i is not None and stage == FAILED:
        ng.append(f"✘ [N] 돌파 실패 — 피벗 {pv} 대비 {c[last] / pivot - 1:+.1%} 되밀림 (돌파일 {date(bo_i)})"
                  + (" — 실패한 돌파의 신고가는 가산 제외" if hi_pts else ""))
        bonus = void_high = True                          # 실패한 돌파에는 어떤 돌파·신고가 가산도 없음
    elif bo_i is not None and last - bo_i < cfg.breakout_recent_bars:
        bonus = True
        vol_ok = bool(np.isfinite(bvr) and bvr >= cfg.breakout_vol_mult)
        p = (5.0 if deep else 20.0) if vol_ok else 5.0
        if vol_ok:
            ok.append(f"✔ [N] 피벗 {pv} 돌파 — 거래량 {bvr:.2f}배 ({date(bo_i)}{', 깊은 베이스 후' if deep else ''})")
        else:
            ng.append(f"✘ [N] 피벗 돌파 거래량 {_f2(bvr)}배 — 기준 {cfg.breakout_vol_mult:.1f}배 미달")
        if c[last] < pivot:
            p *= 0.5
            ng.append(f"✘ [N] 돌파 후 피벗 아래 마감 ({c[last] / pivot - 1:+.1%}) — 실패 여부 주시")
        pts += p
    elif bo_i is None:
        k0 = max(geo["base_end"] + 1, last - 4)
        hk = h[k0:last + 1]
        if len(hk) and hk.max() > pivot:                 # 장중 피벗 돌파 후 종가는 아래
            ri = k0 + int(np.argmax(hk))
            rng = h[ri] - l[ri]
            pos = (c[ri] - l[ri]) / rng if rng > 0 else 0.5
            key = pos < cfg.key_rev_pos
            if key:
                pts -= cfg.key_rev_pts
            void_high = pos < 0.5                         # 하단 절반 마감: 그 신고가는 가산 제외
            ng.append(f"✘ [N] 장중 피벗 {pv} 돌파 후 되밀림 ({date(ri)} 고가 {h[ri]:,.0f} · 종가 {c[ri]:,.0f}, "
                      f"종가 위치 {pos:.0%}) — {'키 리버설, ' if key else ''}반전 주의"
                      + (", 신고가 가산 제외" if void_high and hi_pts else ""))
            geo["reversal_i"] = ri
        elif pivot * (1 - cfg.near_pct) <= c[last] <= pivot:
            pts += 5 if deep else 10
            ok.append(f"✔ [N] 피벗 {pv} 대비 {c[last] / pivot - 1:+.1%} — 돌파 대기")
    if hi_pts and not void_high:
        pts += hi_pts
        if new_high_i is not None:
            ok.append(f"✔ [N] 최근 {k}봉 내 52주 신고가 경신 ({date(new_high_i)})")
        if ath:
            ok.append(f"✔ [N] 보유 이력 {(last + 1) / cfg.year:.1f}년 내 최고가 경신")
    if not bonus:
        sb = _short_breakout(a, cfg)
        if sb is not None and c[last] >= sb[1] * (1 - cfg.fail_pct):
            i, lvl, vr = sb
            pts += cfg.short_bo_pts / 2 if deep else cfg.short_bo_pts
            where = "아래" if c[last] < pivot else "위"
            ok.append(f"✔ [N] 최근 {cfg.short_bo_lookback}봉 고점 {lvl:,.0f} 돌파 — 거래량 {vr:.2f}배 ({date(i)}, "
                      f"베이스 피벗 {pv} {where})")
            out["short_breakout"] = date(i)
    out.update(high52=hi52, from_52w_high=_r(dist), new_52w_high=new_high_i is not None, ath=bool(ath),
               n_pass=within or (new_high_i is not None and not void_high))
    return float(min(100.0, max(0.0, pts)))


def _ad_rating(a: _Arr, cfg: CanslimConfig) -> tuple[str, float]:
    """IBD식 매집/분산: 등락 방향과 종가 위치를 거래량 가중 평균 (-1~+1) → A~E."""
    n = min(cfg.ad_days, a.last)
    if n < 10:
        return "N/A", float("nan")
    s = slice(a.last - n + 1, a.last + 1)
    c, h, l, v = a.c[s], a.h[s], a.l[s], a.v[s]
    prev = a.c[a.last - n:a.last]
    d = np.sign(c - prev)
    rng = h - l
    cp = np.where(rng > 0, (c - l) / np.where(rng > 0, rng, 1.0), 0.5)
    f = 0.5 * d + 0.5 * (2 * cp - 1)
    w = np.nan_to_num(v, nan=0.0)
    if w.sum() <= 0:
        return "N/A", float("nan")
    ad = float((f * w).sum() / w.sum())
    for grade, cut in zip("ABCD", cfg.ad_cuts):
        if ad >= cut:
            return grade, ad
    return "E", ad


def _letter_s(ctx: StockContext, a: _Arr, cfg: CanslimConfig, out: dict, ok: list, ng: list) -> float:
    last = a.last
    nud = min(cfg.ud_days, last)
    ud = ind.up_down_volume_ratio(ctx.df, nud, vol=ctx.vol)
    if not np.isfinite(ud):
        chg = np.diff(a.c[last - nud:last + 1])
        ud = 9.99 if (chg > 0).any() else float("nan")   # 하락일 거래량 0
    if np.isfinite(ud):
        pts_ud = _lin(ud, cfg.ud_floor, cfg.ud_good, 0, 15) if ud < cfg.ud_good else _lin(ud, cfg.ud_good, cfg.ud_great, 15, 30)
    else:
        pts_ud = 0.0
    if np.isfinite(ud) and ud >= cfg.ud_great:
        ok.append(f"✔ [S] {nud}일 U/D 거래량 비 {ud:.2f} — 매집 우위 (우수 ≥{cfg.ud_great})")
    elif np.isfinite(ud) and ud >= cfg.ud_good:
        ok.append(f"✔ [S] {nud}일 U/D 거래량 비 {ud:.2f} (양호 ≥{cfg.ud_good})")
    elif np.isfinite(ud):
        ng.append(f"✘ [S] {nud}일 U/D 거래량 비 {ud:.2f} — 하락일 거래량 우위")
    else:
        ng.append(f"✘ [S] {nud}일 등락 없음 — U/D 판정 불가")

    grade, adv = _ad_rating(a, cfg)
    pts_ad = {"A": 25, "B": 20, "C": 12, "D": 5}.get(grade, 0)
    (ok if grade in ("A", "B") else ng).append(
        f"{'✔' if grade in ('A', 'B') else '✘'} [S] 매집/분산 등급 {grade} ({cfg.ad_days}봉, 지수 {adv:+.2f})")

    nb = min(cfg.big_days, last)
    s = slice(last - nb + 1, last + 1)
    big = a.v[s] >= a.vavg[s] * cfg.big_vol_mult
    dc = a.c[s] - a.c[last - nb:last]
    bu, bd = int((big & (dc > 0)).sum()), int((big & (dc < 0)).sum())
    pts_big = float(np.clip(12.5 + 4 * (bu - bd), 0, 25))
    (ok if bu > bd else ng).append(
        f"{'✔' if bu > bd else '✘'} [S] 대량거래({cfg.big_vol_mult}배↑) 상승일 {bu} / 하락일 {bd} (최근 {nb}봉)")

    thr = ctx.cfg.big_value_threshold
    nv = min(cfg.value_days, last + 1)
    vd = int((a.val[last - nv + 1:] >= thr).sum())
    pts_val = 20 * min(1.0, vd / cfg.value_full_days)
    if vd:
        ok.append(f"✔ [S] 거래대금 {thr / 1e8:,.0f}억↑ {vd}일 (최근 {nv}봉)")
    else:
        ng.append(f"✘ [S] 최근 {nv}봉 거래대금 {thr / 1e8:,.0f}억 돌파일 없음")

    mcap = _num(ctx.info.get("market_cap")) if ctx.info else float("nan")
    out.update(ud_ratio=_r(ud, 2), ad_rating=grade, ad_value=_r(adv), big_up_days=bu, big_down_days=bd,
               value_300_days=vd, market_cap_eok=_r(mcap / 1e8, 0) if np.isfinite(mcap) else float("nan"))
    return pts_ud + pts_ad + pts_big + pts_val


def _rs_at_last(ctx: StockContext) -> float | None:
    """마지막 봉 시점 RS 레이팅 (잘린 df 에서도 미래 값을 쓰지 않음)."""
    hist = ctx.rs_rating_hist
    if hist is not None and len(hist):
        s = hist.loc[:ctx.df.index[-1]].dropna()
        return float(s.iloc[-1]) if len(s) else None
    return float(ctx.rs_rating) if ctx.rs_rating is not None and np.isfinite(ctx.rs_rating) else None


def _letter_l(ctx: StockContext, a: _Arr, cfg: CanslimConfig, out: dict, ok: list, ng: list,
              notes: dict) -> float:
    rs = _rs_at_last(ctx)
    pts, avail = 0.0, 0.0
    if rs is not None:
        avail += 40
        pts += 40 if rs >= cfg.rs_ideal else (30 + (rs - cfg.rs_min) if rs >= cfg.rs_min else _lin(rs, 60, cfg.rs_min, 0, 30))
        msg = f"[L] RS {rs:.0f} — 상위 {max(1, 100 - rs):.0f}%"
        if rs >= cfg.rs_min:
            ok.append(f"✔ {msg}" + (" (이상적 ≥90)" if rs >= cfg.rs_ideal else ""))
        else:
            ng.append(f"✘ {msg} (필수 ≥{cfg.rs_min:.0f})")
    else:
        ng.append("✘ [L] RS 레이팅 없음")
    out["rs"] = rs if rs is not None else float("nan")

    rl_s = ctx.rs_line
    dist = float("nan")
    lead_i = None
    slope = float("nan")
    if rl_s is not None:
        rl = rl_s.to_numpy(dtype=float)
        last = a.last
        w = rl[max(0, last - cfg.year + 1):]
        if np.isfinite(rl[last]) and np.isfinite(w).sum() >= 20:
            avail += 60
            dist = rl[last] / np.nanmax(w) - 1
            pts += _lin(dist, -cfg.rs_line_near, -cfg.rs_line_tight, 15, 25) if dist >= -cfg.rs_line_near \
                else _lin(dist, -cfg.rs_line_zero, -cfg.rs_line_near, 0, 15)
            if dist >= -cfg.rs_line_near:
                ok.append(f"✔ [L] RS선 52주 고점 대비 {dist:+.1%} (기준 -{cfg.rs_line_near:.0%} 이내)")
            else:
                ng.append(f"✘ [L] RS선 52주 고점 대비 {dist:+.1%} — 시장 대비 약세")
            # RS선 선행 신고가: RS선은 52주 신고가(초과)인데 주가(종가)는 아직 52주 신고가 아님
            for i in range(max(20, last - cfg.rs_lead_bars + 1), last + 1):
                p0 = max(0, i - cfg.year + 1)
                prior = rl[p0:i]
                if np.isfinite(rl[i]) and np.isfinite(prior).any() and rl[i] > np.nanmax(prior) \
                        and a.c[i] < a.c[p0:i].max():
                    lead_i = i
            if lead_i is not None:
                pts += 20
                ok.append(f"✔ [L] RS선 선행 신고가 — 주가보다 먼저 52주 신고가 ({notes['date'](lead_i)})")
            slope = ind.slope_pct(rl_s.iloc[:last + 1], cfg.rs_slope_days)
            if np.isfinite(slope) and slope > 0:
                pts += 15
                ok.append(f"✔ [L] RS선 {cfg.rs_slope_days}일 기울기 상승 ({slope * 100:+.2f}%/일)")
            else:
                ng.append(f"✘ [L] RS선 {cfg.rs_slope_days}일 기울기 하락")
    if avail < 100:
        ng.append("✘ [L] 지수 데이터 없음 — RS선 항목 제외하고 재정규화" if rl_s is None or avail == 40
                  else "✘ [L] RS 항목 일부 누락 — 재정규화")
    notes["rs_lead_i"] = lead_i
    out.update(rs_line_high_dist=_r(dist), rs_line_leading=lead_i is not None, rs_line_slope=_r(slope * 100, 4)
               if np.isfinite(slope) else float("nan"))
    return pts / avail * 100 if avail else 0.0


def _investor_score(ctx: StockContext, a: _Arr, cfg: CanslimConfig, ok: list, ng: list, out: dict) -> float | None:
    inv = ctx.info.get("investor") if ctx.info else None
    if not isinstance(inv, pd.DataFrame) or inv.empty or not {"inst_net", "foreign_net"} <= set(inv.columns):
        return None
    try:
        inv = inv.sort_index()
        inv = inv[inv.index <= ctx.df.index[-1]]          # 미래 자료 배제
    except TypeError:
        return None
    if len(inv) < cfg.inv_days // 2:
        ng.append(f"✘ [I] 기관·외국인 순매매 자료 부족 ({len(inv)}일)")
        return None
    lag = int((ctx.df.index > inv.index[-1]).sum())
    if lag > cfg.inv_max_lag:
        ng.append(f"✘ [I] 기관·외국인 순매매 자료가 {lag}봉 지연 — 미반영")
        return None
    inv = inv.iloc[-cfg.inv_days:]
    inst = float(np.nansum(inv["inst_net"].to_numpy(dtype=float)))
    frgn = float(np.nansum(inv["foreign_net"].to_numpy(dtype=float)))
    vol_sum = float(np.nansum(a.v[max(0, a.last - len(inv) - lag + 1):a.last - lag + 1]))
    ratio = (inst + frgn) / vol_sum if vol_sum > 0 else float("nan")
    sc = _lin(ratio, -cfg.inv_full_ratio, cfg.inv_full_ratio, 0, 100)
    msg = f"[I] {len(inv)}일 기관 {inst:+,.0f}주 · 외국인 {frgn:+,.0f}주 (거래량 대비 {ratio:+.1%})"
    (ok if inst + frgn > 0 else ng).append(("✔ " if inst + frgn > 0 else "✘ ") + msg)
    out.update(inv_inst_20=inst, inv_foreign_20=frgn, inv20_ratio=_r(ratio, 4))
    return sc


def _letter_i(ctx: StockContext, a: _Arr, cfg: CanslimConfig, out: dict, ok: list, ng: list) -> float:
    last = a.last
    nud = min(cfg.i_ud_days, last)
    chg = np.diff(a.c[last - nud:last + 1])            # indicators.up_down_volume_ratio 와 동일 (numpy)
    vv = a.v[last - nud + 1:last + 1]
    up, dn = vv[chg > 0].sum(), vv[chg < 0].sum()
    ud20 = up / dn if dn > 0 else (9.99 if (chg > 0).any() else float("nan"))
    # 20일 U/D (30): 0.8 → 0, 1.2 → 15, 2.5 → 30
    p_ud = _lin(ud20, cfg.i_ud_lo, cfg.i_ud_mid, 0, 15) if (np.isfinite(ud20) and ud20 < cfg.i_ud_mid) \
        else _lin(ud20, cfg.i_ud_mid, cfg.i_ud_hi, 15, 30)
    # 포켓 피벗 (30): 상승 마감 + 종가가 당일 범위 상단 절반 + 50일선 위
    #                 + 거래량이 직전 10일 하락일 최대 거래량 초과 (Morales & Kacher)
    s50 = ctx.sma(50).to_numpy(dtype=float)
    pp = 0
    for i in range(max(cfg.pp_lookback + 1, last - cfg.pp_days + 1), last + 1):
        rng = a.h[i] - a.l[i]
        if a.c[i] <= a.c[i - 1] or not (a.c[i] > s50[i]) or (rng > 0 and (a.c[i] - a.l[i]) / rng < 0.5):
            continue
        seg = slice(i - cfg.pp_lookback, i)
        down = a.c[seg] < a.c[i - cfg.pp_lookback - 1:i - 1]
        if a.v[i] > (a.v[seg][down].max() if down.any() else 0.0):
            pp += 1
    p_pp = 30 * min(1.0, pp / cfg.pp_full)
    # OBV (25): 최근 5봉 내 50일 최고 15, 50일 기울기 양(+) 10
    no = min(cfg.obv_days, last)
    d = np.sign(np.diff(a.c[last - no:last + 1]))
    obv = np.cumsum(d * np.nan_to_num(a.v[last - no + 1:last + 1]))
    moving = no >= 10 and np.ptp(obv) > 0
    obv_up = bool(moving and np.polyfit(np.arange(no, dtype=float), obv, 1)[0] > 0)
    obv_hi = bool(moving and obv[-5:].max() >= obv.max())
    p_obv = 10 * obv_up + 15 * obv_hi
    # 최대 거래량일 (15): 최근 20봉 중 거래량 최대인 날이 상승·상단 마감이면 매집 흔적
    nf = min(cfg.footprint_days, last)
    fi = last - nf + 1 + int(np.argmax(a.v[last - nf + 1:last + 1]))
    frng = a.h[fi] - a.l[fi]
    f_up = bool(a.c[fi] > a.c[fi - 1] and (frng <= 0 or (a.c[fi] - a.l[fi]) / frng >= 0.5))
    f_down = bool(a.c[fi] < a.c[fi - 1] and frng > 0 and (a.c[fi] - a.l[fi]) / frng < 0.5)
    p_fp = 15 * f_up
    proxy = p_ud + p_pp + p_obv + p_fp
    tag = "✔" if proxy >= 50 else "✘"
    (ok if proxy >= 50 else ng).append(
        f"{tag} [I] 기관 매집 대용지표 {proxy:.0f}점: {nud}일 U/D {_f2(ud20)}, 포켓 피벗 {pp}회, "
        f"OBV {'상승' if obv_up else '정체/하락'}{'·50일 신고' if obv_hi else ''}")
    if f_down:
        ng.append(f"✘ [I] 최근 {nf}봉 최대 거래량일({ctx.date(fi)})이 하락·하단 마감 — 분산 흔적")
    elif f_up:
        ok.append(f"✔ [I] 최근 {nf}봉 최대 거래량일({ctx.date(fi)})이 상승·상단 마감")
    out.update(ud20=_r(ud20, 2), pocket_pivots=pp, obv_rising=bool(obv_up), obv_new_high=obv_hi,
               max_vol_day_up=f_up)
    inv = _investor_score(ctx, a, cfg, ok, ng, out)
    out["i_source"] = "proxy+investor" if inv is not None else "proxy"
    return proxy if inv is None else 0.5 * proxy + 0.5 * inv


def _letter_m(ctx: StockContext, cfg: CanslimConfig, out: dict, ok: list, ng: list) -> float:
    ms = ctx.market_state
    if ms is None:
        ng.append("✘ [M] 시장 상태 정보 없음 — 중립 50점")
        out.update(market_state="N/A", distribution_days=float("nan"))
        return 50.0
    base = dict(zip((CONFIRMED, PRESSURE, CORRECTION), cfg.m_state_pts)).get(ms.state, 50.0)
    dd = int(ms.distribution_days)
    try:
        ms_score = float(ms.score)
    except (KeyError, TypeError, ValueError):            # 알 수 없는 상태값 → 상태 점수만 사용
        ms_score = base
    m = float(np.clip(0.6 * base + 0.4 * ms_score - cfg.m_dd_penalty * max(0, dd - cfg.m_dd_free), 0, 100))
    label = STATE_LABELS.get(ms.state, ms.state)
    msg = f"[M] {ms.name} {label} · 분산일 {dd}개"
    if ms.state == CONFIRMED:
        ok.append(f"✔ {msg}")
    elif ms.state == PRESSURE:
        ng.append(f"✘ {msg} — 상승 압박, 신규 매수 신중")
    else:
        ng.append(f"✘ {msg} — 조정장: 오닐 원칙상 신규 매수 금지 (4종목 중 3종목은 시장을 따른다)")
    if ms.date and ms.date != ctx.date(-1):
        ng.append(f"✘ [M] 시장 상태 기준일 {ms.date} ≠ 마지막 봉 {ctx.date(-1)}")
    out.update(market_state=ms.state, distribution_days=dd)
    return m


def _letters_ca(ctx: StockContext, cfg: CanslimConfig, out: dict, ok: list, ng: list) -> tuple[float | None, float | None]:
    f = ctx.info.get("fundamentals") if ctx.info else None
    if not isinstance(f, dict):
        out.update(C="N/A", A="N/A")
        return None, None
    c_sc = a_sc = None
    g = _num(f.get("eps_q_yoy"))
    if np.isfinite(g):
        if g >= cfg.c_eps_min:
            c_sc = 70 + min(20.0, (g - cfg.c_eps_min) / cfg.c_eps_min * 20)
            prev = _num(f.get("eps_q_yoy_prev"))
            if np.isfinite(prev) and g > prev:
                c_sc += 5
            sales = _num(f.get("sales_q_yoy"))
            if np.isfinite(sales) and sales >= cfg.c_eps_min:
                c_sc += 5
            ok.append(f"✔ [C] 최근 분기 EPS 전년비 {g:+.0f}% (기준 ≥{cfg.c_eps_min:.0f}%)")
        else:
            c_sc = max(0.0, g) / cfg.c_eps_min * 50
            ng.append(f"✘ [C] 최근 분기 EPS 전년비 {g:+.0f}% — 기준 {cfg.c_eps_min:.0f}% 미달")
    g3, roe = _num(f.get("eps_annual_growth_3y")), _num(f.get("roe"))
    parts = []
    if np.isfinite(g3):
        parts.append(50 * min(1.0, max(0.0, g3) / cfg.a_growth_min))
        (ok if g3 >= cfg.a_growth_min else ng).append(
            f"{'✔' if g3 >= cfg.a_growth_min else '✘'} [A] 연간 EPS 성장 {g3:+.0f}% (기준 ≥{cfg.a_growth_min:.0f}%)")
    if np.isfinite(roe):
        parts.append(50 * min(1.0, max(0.0, roe) / cfg.a_roe_min))
        (ok if roe >= cfg.a_roe_min else ng).append(
            f"{'✔' if roe >= cfg.a_roe_min else '✘'} [A] ROE {roe:.1f}% (기준 ≥{cfg.a_roe_min:.0f}%)")
    if parts:
        a_sc = sum(parts) / len(parts) * 2
    out.update(C=_r(min(100.0, c_sc), 1) if c_sc is not None else "N/A",
               A=_r(a_sc, 1) if a_sc is not None else "N/A")
    return (min(100.0, c_sc) if c_sc is not None else None), a_sc


# ---------------------------------------------------------------- 탐지
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, CanslimConfig)
    res = PatternResult(name=NAME, label=LABEL)
    res.metrics = {"C": "N/A", "A": "N/A"}
    n = ctx.n
    if n < cfg.min_bars:
        res.warnings.append(f"✘ 이력 부족 ({n}봉 < {cfg.min_bars}봉) — CAN SLIM 채점 불가")
        return res
    df = ctx.df
    o, h, l, c = (df[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    if not (np.isfinite(c[-cfg.min_bars:]).all() and np.isfinite(h[-cfg.min_bars:]).all()
            and np.isfinite(l[-cfg.min_bars:]).all()) or c[-1] <= 0:
        res.warnings.append("✘ 최근 가격에 결측/비정상 값 — 채점 불가")
        return res
    try:
        return _detect(ctx, cfg, res, o, h, l, c)
    except Exception as e:  # 이상 데이터 안전망: 예외 대신 경고로 반환
        res.detected = False
        res.warnings.append(f"✘ 계산 오류: {type(e).__name__}: {e}")
        return res


def _quality(cfg: CanslimConfig, depth: float, v_shape: bool, stage: str | None) -> tuple[float, list[str]]:
    """결함 베이스 품질 배수와 사유."""
    q, why = 1.0, []
    dm = None
    for thr, k in sorted(cfg.deep_mult):
        if np.isfinite(depth) and depth > thr:
            dm = (thr, k)
    if dm is not None:
        q *= dm[1]
        why.append(f"베이스 깊이 {depth:.0%}>{dm[0]:.0%} ×{dm[1]}")
    if v_shape:
        q *= cfg.v_mult
        why.append(f"V자 급반등 ×{cfg.v_mult}")
    if stage == FAILED:
        q *= cfg.failed_mult
        why.append(f"돌파 실패 ×{cfg.failed_mult}")
    return q, why


def _detect(ctx: StockContext, cfg: CanslimConfig, res: PatternResult,
            o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray) -> PatternResult:
    n, last = ctx.n, ctx.n - 1
    # 결측 구간(오래된 과거)은 앞뒤 값으로 채워 계산을 이어간다
    if not (np.isfinite(h).all() and np.isfinite(l).all() and np.isfinite(c).all()):
        fill = lambda x: pd.Series(x).ffill().bfill().to_numpy()  # noqa: E731
        o, h, l, c = fill(o), fill(h), fill(l), fill(c)
    a = _Arr(o=o, h=h, l=l, c=c, v=np.nan_to_num(ctx.vol.to_numpy(dtype=float)),
             val=np.nan_to_num(ctx.value.to_numpy(dtype=float)),
             vavg=ctx.vol_sma(50).shift(1).to_numpy(dtype=float), last=last)
    date = ctx.date

    # ---- 베이스 · 피벗 · 단계
    g = find_base(h, l, c, cfg)
    pivot = g.pivot
    stage, bo_i = classify_stage(ctx, pivot, g.base_end, near_pct=cfg.near_pct, buy_range=cfg.buy_range,
                                 breakout_window=cfg.breakout_window, fail_pct=cfg.fail_pct)
    if g.kind == "run" and c[last] > pivot and stage == BREAKOUT:
        stage = EXTENDED   # 베이스 없는 연속 상승은 '돌파'가 아니라 추격 구간
    bvr = float("nan")
    if bo_i is not None:
        va = a.v[max(0, bo_i - 50):bo_i]
        va = va[va > 0]                                   # 거래정지(거래량 0) 봉 제외
        bvr = a.v[bo_i] / va.mean() if len(va) else float("nan")
    end = (bo_i - 1) if bo_i is not None else last       # 베이스 종료
    bs = min(g.start, end)
    low_i = bs + int(np.argmin(l[bs:end + 1]))
    base_depth = 1 - l[low_i] / pivot if pivot > 0 else float("nan")
    base_bars = end - bs + 1
    if low_i < end:                                       # 손잡이: 베이스 저점 이후 최고가에서의 되밀림
        rh = low_i + 1 + int(np.argmax(h[low_i + 1:end + 1]))
        handle_depth, handle_bars = 1 - l[rh:end + 1].min() / h[rh], end - rh + 1
    else:
        handle_depth, handle_bars = float("nan"), 0
    v_shape, v_rise, v_bars, v_pause = _v_shape(h, l, c, low_i, end, cfg)
    geo = {"pivot": pivot, "bo_i": bo_i, "bo_vol_ratio": bvr, "date": date, "stage": stage,
           "base_depth": base_depth, "base_end": g.base_end, "v_shape": v_shape, "v_rise": v_rise,
           "v_bars": v_bars}

    out: dict = {}
    okN, ngN, okS, ngS, okL, ngL, okI, ngI, okM, ngM, okF, ngF = ([] for _ in range(12))
    notes = {"date": date}
    sN = _letter_n(a, cfg, geo, out, okN, ngN)
    sS = _letter_s(ctx, a, cfg, out, okS, ngS)
    sL = _letter_l(ctx, a, cfg, out, okL, ngL, notes)
    sI = _letter_i(ctx, a, cfg, out, okI, ngI)
    sM = _letter_m(ctx, cfg, out, okM, ngM)
    sC, sA = _letters_ca(ctx, cfg, out, okF, ngF)

    # ---- 종합점수: 종목 점수(M 제외, 품질 배수)로 탐지, M 은 종합점수·감점에만 반영
    wN, wS, wL, wI, wM = cfg.weights
    parts = [(sN, wN), (sS, wS), (sL, wL), (sI, wI)]
    if sC is not None:
        parts.append((sC, cfg.w_c))
    if sA is not None:
        parts.append((sA, cfg.w_a))
    w_stock = sum(w for _, w in parts)
    raw_stock = sum(s * w for s, w in parts) / w_stock
    quality, q_why = _quality(cfg, base_depth, v_shape, stage)
    stock_score = raw_stock * quality
    composite = (stock_score * w_stock + sM * wM) / (w_stock + wM)

    # ---- 필수 조건
    musts_ok, must_ng = True, []
    rs = out.get("rs")
    if not (rs is not None and np.isfinite(rs) and rs >= cfg.rs_min):
        musts_ok = False
        must_ng.append(f"✘ [필수] RS ≥ {cfg.rs_min:.0f} 미충족")
    if not (out["from_52w_high"] >= -cfg.must_within_high):
        musts_ok = False
        must_ng.append(f"✘ [필수] 52주 고점 -{cfg.must_within_high:.0%} 이내 미충족 ({out['from_52w_high']:+.1%})")
    rs_lead = notes.get("rs_lead_i") is not None
    if not (out["n_pass"] or rs_lead):
        musts_ok = False
        must_ng.append(f"✘ [필수] [N] 52주 고점 -{cfg.n_within_high:.0%} 이내 또는 최근 {cfg.n_new_high_bars}봉 "
                       f"신고가 미충족 ({out['from_52w_high']:+.1%}, RS선 선행 신고가도 없음)")
    elif not out["n_pass"]:
        okN.append(f"✔ [N] 신고가권 밖이지만 RS선 선행 신고가 — N 필수 조건 면제")
    s50 = float(ctx.sma(50).iloc[-1])
    s200 = float(ctx.sma(200).iloc[-1]) if n >= 200 else float("nan")
    if not (c[last] > s50):
        musts_ok = False
        must_ng.append("✘ [필수] 종가가 50일선 아래")
    if n >= 200:
        if not (c[last] > s200):
            musts_ok = False
            must_ng.append("✘ [필수] 종가가 200일선 아래")
    else:
        ngN.append(f"✘ 상장 후 {n}봉 — 200일선 판정 생략 (신규 상장주)")
    if n < cfg.min_detect_bars:
        musts_ok = False
        must_ng.append(f"✘ [필수] 이력 {n}봉 < {cfg.min_detect_bars}봉 — 탐지 보류")

    ms = ctx.market_state
    correction = ms is not None and ms.state == CORRECTION
    score = composite * (cfg.correction_cut if correction else 1.0)
    res.detected = bool(musts_ok and stock_score >= cfg.min_composite)
    if q_why:
        must_ng.insert(0, f"✘ 결함 베이스 감점 ×{quality:.2f} ({', '.join(q_why)}) — 종목 점수 {raw_stock:.0f}→{stock_score:.0f}")
    if not (stock_score >= cfg.min_composite):
        must_ng.append(f"✘ 종목 점수(M 제외) {stock_score:.0f} < {cfg.min_composite:.0f}")
    if correction:
        must_ng.insert(0, f"✘ ⚠ 시장 조정 국면 — 점수 ×{cfg.correction_cut} 감점, 신규 매수 보류 권고")

    # ---- 손절가: 피벗 매수 기준 (extended 는 현재가 기준)
    if stage == EXTENDED:
        stop, stop_basis = c[last] * (1 - cfg.stop_pct), "close"
    else:
        stop, stop_basis = pivot * (1 - cfg.stop_pct), "pivot"

    # ---- 주의 사항
    w0 = max(0, min(bs, last - cfg.ad_days))
    halts = _halts_in(ctx, w0)
    caveats = []
    if halts:
        caveats.append(f"✘ 분석 구간에 거래정지일 {len(halts)}일 ({halts[0]}~) — 액면분할 등으로 거래량 비교 왜곡 가능")
    zero = np.flatnonzero(a.v[w0:] <= 0)
    if len(zero):
        caveats.append(f"✘ 분석 구간에 거래량 0 봉 {len(zero)}개 ({date(w0 + int(zero[0]))}~) — 거래정지 추정, "
                       "50일 평균 거래량·거래량 비율 왜곡 가능")
    if g.kind == "base" and base_bars < cfg.min_base_bars:
        caveats.append(f"✘ 베이스 {base_bars}봉 — 오닐 베이스 최소 {cfg.min_base_bars}봉(5주) 미만: 짧은 조정의 피벗")
    if ctx.partial:
        caveats.append(f"✘ 장중 미완성 봉 — 거래량·거래대금은 하루치 추정(체결 비율 {ctx.session_frac:.0%})")
    if g.kind == "run":
        caveats.append("✘ 최근 2주 이상 조정한 고점 없음(연속 상승) — 피벗 신뢰도 낮음")
    if stage == FORMING:
        caveats.append(f"✘ 손절가 {stop:,.0f}는 피벗 {pivot:,.0f} 돌파 매수 기준 — 돌파 전(현재가 {c[last]:,.0f}) "
                       "매수에는 적용하지 않음")
    elif stage == EXTENDED:
        caveats.append(f"✘ 이격 과다 — 손절가는 현재가 기준 -{cfg.stop_pct:.0%} "
                       f"(피벗 매수분은 {pivot * (1 - cfg.stop_pct):,.0f})")
    elif stage == FAILED and c[last] < pivot * (1 - cfg.stop_pct):
        caveats.append(f"✘ 종가가 피벗 매수 손절가 {stop:,.0f} 아래 — 오닐 원칙상 매도 신호")

    # ---- 결과
    res.score = float(round(max(0.0, min(100.0, score)), 1))
    res.stage = stage
    res.pivot = float(pivot)
    res.stop = round(float(stop), 2)
    res.start_date = date(bs)
    res.end_date = date(last)
    res.breakout_date = date(bo_i) if bo_i is not None else None
    res.reasons = okN + okS + okL + okI + okM + okF
    res.warnings = must_ng + ngN + ngS + ngL + ngI + ngM + ngF + caveats
    res.metrics = {
        "composite": _r(composite, 1), "stock_score": _r(stock_score, 1), "stock_score_raw": _r(raw_stock, 1),
        "quality_mult": _r(quality, 3),
        "N": _r(sN, 1), "S": _r(sS, 1), "L": _r(sL, 1), "I": _r(sI, 1), "M": _r(sM, 1),
        "rs": out["rs"], "ad_rating": out["ad_rating"], "ud_ratio": out["ud_ratio"],
        "C": out.get("C", "N/A"), "A": out.get("A", "N/A"),
        "rs_line_high_dist": out["rs_line_high_dist"], "rs_line_leading": out["rs_line_leading"],
        "rs_line_slope": out["rs_line_slope"],
        "big_up_days": out["big_up_days"], "big_down_days": out["big_down_days"],
        "value_300_days": out["value_300_days"], "market_cap_eok": out["market_cap_eok"],
        "market_state": out["market_state"], "distribution_days": out["distribution_days"],
        "from_52w_high": out["from_52w_high"], "new_52w_high": out["new_52w_high"], "ath": out["ath"],
        "n_pass": bool(out["n_pass"]),
        "ad_value": out["ad_value"], "ud20": out["ud20"], "pocket_pivots": out["pocket_pivots"],
        "obv_rising": out["obv_rising"], "obv_new_high": out["obv_new_high"], "i_source": out["i_source"],
        "pivot_kind": g.kind, "pivot_beyond_window": g.beyond, "pivot_date": date(g.pj),
        "base_bars": int(base_bars), "base_depth": _r(base_depth), "base_low_date": date(low_i),
        "pivot_bars": int(end - g.pj + 1), "handle_depth": _r(handle_depth), "handle_bars": int(handle_bars),
        "v_shape": v_shape, "v_rise": _r(v_rise), "v_pause": int(v_pause),
        "breakout_vol_ratio": _r(bvr, 2), "short_breakout": out.get("short_breakout", ""),
        "stop_basis": stop_basis, "musts_ok": musts_ok,
    }
    for k in ("inv_inst_20", "inv_foreign_20", "inv20_ratio"):
        if k in out:
            res.metrics[k] = out[k]

    # ---- 차트 주석
    ann = [hline(pivot, "피벗(베이스 최고 조정 고점)", "#2962ff"),
           hline(stop, f"손절 -{cfg.stop_pct:.0%} ({'피벗' if stop_basis == 'pivot' else '현재가'} 기준)", "#d50000"),
           box(_ix(ctx, bs), _ix(ctx, max(bs, end)), pivot, float(l[low_i]),
               f"베이스 {base_bars}봉 · 깊이 {base_depth:.0%}")]
    if abs(out["high52"] / pivot - 1) > 0.005:
        ann.append(hline(out["high52"], "52주 고점", "#9e9e9e", "dotted"))
    if bo_i is not None:
        ann.append(marker(_ix(ctx, bo_i), f"돌파 {bvr:.1f}x" if np.isfinite(bvr) else "돌파",
                          position="below", color="#00c853", shape="arrowUp"))
    if geo.get("reversal_i") is not None:
        ann.append(marker(_ix(ctx, geo["reversal_i"]), "장중 돌파 후 되밀림", position="above",
                          color="#d50000", shape="arrowDown"))
    if notes.get("rs_lead_i") is not None:
        ann.append(marker(_ix(ctx, notes["rs_lead_i"]), "RS선 선행 신고가", position="above",
                          color="#2962ff", shape="circle"))
    res.annotations = ann
    return res


def _ix(ctx: StockContext, i: int):
    return ctx.df.index[i]


def _halts_in(ctx: StockContext, start_i: int) -> list[str]:
    """start_i 봉 이후 구간에 포함된 거래정지일."""
    hd = ctx.df.attrs.get("halt_dates") or []
    if not hd:
        return []
    s = ctx.date(start_i)
    e = ctx.date(-1)
    return [d for d in hd if s <= d <= e]
