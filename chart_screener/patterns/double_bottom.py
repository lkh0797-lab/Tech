"""윌리엄 오닐 더블 바텀(W) 패턴.

기준 (O'Neil, *How to Make Money in Stocks* — Double Bottom):
 1. 선행 상승: 왼쪽 고점 이전 약 7개월(150봉) 저점 대비 +25% 이상 상승한 뒤 형성 (30% 이상 바람직).
    왼쪽 고점은 그 기간 최고가(3봉 중앙값 고가 기준)의 -5% 이내여야 함 (폭락 후 반등 고점은 선행 상승이 아님).
    1차 저점 아래 마지막 '종가'에서 왼쪽 고점까지 5봉 이상 — 저점 수준에서 1~4봉 만에 치솟은 스파이크 배제
    (장중 저가 기준이면 상승 추세 중 일시 하회만으로 정상 W(예: 얕은 W)가 탈락하므로 종가 기준)
 2. 모양: 왼쪽 고점(L) → 1차 저점(A) → 중간 고점(M) → 2차 저점(B) → 오른쪽 회복.
    B 가 A 를 소폭(0~5%) 하회하는 '언더컷(셰이크아웃)'이 이상적. B 가 A 보다 위면 약한 형태(감점, +3% 까지),
    A 대비 -6% 를 넘게 깨면 붕괴로 본다.
 3. 기간: 왼쪽 고점부터 돌파(또는 현재)까지 7주(35거래일) 이상, 65주(325거래일) 이내.
    두 저점 간격 3주(15봉) 이상, 각 다리(L→A, A→M, M→B) 5봉 이상.
 4. 깊이: 왼쪽 고점 대비 최저점 12~40% (33% 이내가 바람직, 약세장에서 40% 까지).
    종가 기준(스윙점 ±2봉)으로도 깊이 max(8%, 장중 깊이의 50%) 이상·중간 반등 35% 이상
    — 장중 꼬리(스파이크)만으로 그려진 W 배제
 5. 왼쪽 고점(L) = 1차 저점 이전, A 보다 낮은 저점이 마지막으로 나온 뒤 구간의 '실제' 최고가(베이스 천장).
    단 그 고가가 3봉 중앙값 고가보다 8% 넘게 높은 1봉 스파이크(상한가 후 급락 등)면, 실제 거래된 수준인
    3봉 중앙값 고가의 최고치를 왼쪽 고점으로 쓴다.
    중간 고점: 왼쪽 고점보다 2% 이상 낮고, L→A 하락폭의 50% 이상을 되돌린 반등(피벗이 베이스 상단 절반).
    왼쪽 하락 구간(왼쪽 고점 -3% 이내의 마지막 고점 = 실제 하락 시작점부터, 절반 이상 하락한 뒤)의 반등 종가가
    중간 고점보다 3% 넘게 높으면 복합 베이스로 제외.
 6. 피벗(매수점) = 중간 고점 고가 + 1호가. 오른쪽 상단(피벗 -6% 이내 도달 후, B→피벗 상승폭의 상단 절반)에
    작은 손잡이(2~12% 눌림, 3봉 이상)가 생길 수 있다. 손잡이 고점(handle_pivot)이 피벗보다 낮으면 조기 매수점,
    높으면(장중 피벗 상회 후 눌림) 손잡이 고점 돌파 확인을 권고한다 — 단계 판정은 항상 중간 고점 피벗 기준.
    오른쪽이 피벗권(-6% 이내)에 처음 들어온 뒤 돌파(또는 현재)까지, 그때까지의 최고가 대비 12% 넘게 밀린 적이
    있으면 손잡이 실패(새 베이스)로 제외 — 이후 새 고점·피벗 돌파가 나와도 되살리지 않는다(누적 판정).
 7. 거래량: 언더컷·반등 구간의 대량 거래는 지지 매수로 무방, 피벗 직전 거래량 감소(dry-up) 선호,
    돌파일 거래량 50일 평균 +40% 이상.
 8. 손절 = max(2차 저점, 손잡이 저점, 피벗 -8%) — 오닐의 최대 손실 7~8% 규칙.
    KRX 호가 단위로 맞춤 (저점 기준은 내림, -8% 한도는 올림 — 한도를 넘지 않게).

미래 참조 방지: 2차 저점 B 는 마지막 봉 기준 최근 (max_right_bars + max_bars_since_breakout) 봉 이내의
스윙 저점만 후보로 쓰고, 돌파 후 max_bars_since_breakout 봉이 지난 W 는 '지난 패턴'으로 탈락시킨다.
여러 W 후보가 있으면 가장 최근의 2차 저점을 우선, 같은 B 끼리는 점수가 높은 구조를 고른다.

점수(0~100) = 언더컷 형태 20 + 깊이 15 + 선행 상승 15 + 중간 고점 위치 10
            + 거래량 20 (피벗 직전 dry-up 8, 오른쪽 상승/하락 거래량비 6, 돌파 거래량 6)
            + 추세·RS 20 (RS 10, 200일선 위 5, 200일선 상승 5)
            - 후속 흐름 (failed -20, extended -5 ~ -15: 매수 범위 초과분 20%p 에서 최대)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .. import indicators as ind
from .base import (EXTENDED, FAILED, PatternResult, StockContext, box, classify_stage, hline,
                   marker, register, segment)

NAME, LABEL = "double_bottom", "더블 바텀(W)"


@dataclass
class DoubleBottomConfig:
    zigzag_pct: float = 0.04            # 스윙 포인트 추출용 지그재그 반전폭 (A→M 반등은 최소 ~5.5%)
    # 선행 상승 (오닐: 최소 20~30% 상승 후의 베이스)
    prior_lookback: int = 150           # 왼쪽 고점 이전 저점 탐색 구간 (약 7개월)
    prior_uptrend_min: float = 0.25
    prior_uptrend_good: float = 0.60    # 이 이상이면 선행 상승 만점
    min_prior_bars: int = 40            # 왼쪽 고점 이전 최소 이력
    prior_high_tol: float = 0.05        # 왼쪽 고점 ≥ 직전 150봉 최고가 × (1-5%) — 하락 후 반등 고점이면 제외
    # 기간 (오닐: 최소 7주)
    min_duration: int = 35              # 왼쪽 고점 → 돌파/현재 최소 봉 수
    max_duration: int = 325             # 65주
    min_leg_bars: int = 5               # L→A, A→M, M→B 각 다리 최소 봉 수
    min_low_gap: int = 15               # 두 저점 최소 간격 (3주)
    max_right_bars: int = 60            # 2차 저점 → 돌파(또는 현재) 최대 봉 수 (12주)
    # 깊이 (오닐: 보통 20~30%, 최대 40%)
    min_depth: float = 0.12
    ideal_depth: float = 0.33
    max_depth: float = 0.40
    # 종가 기준 형태 (스윙점 ±2봉 종가): 장중 꼬리(스파이크)만으로 만들어진 W 배제
    min_close_depth: float = 0.08
    min_close_depth_ratio: float = 0.50  # 종가 기준 깊이 ≥ 장중 깊이 × 50% (실데이터 정상 W 는 0.6~0.95)
    min_close_retrace: float = 0.35
    # 두 저점 관계 (오닐: 2차 저점이 1차 저점을 소폭 하회하는 셰이크아웃이 이상적)
    ideal_undercut: float = 0.05        # 언더컷 이상 범위 0~5%
    max_undercut: float = 0.06          # 이보다 깊게 깨면 W 붕괴
    max_second_above: float = 0.03      # 2차 저점이 1차 저점보다 최대 +3% 위 (약한 형태)
    # 중간 고점
    mid_below_left: float = 0.02        # 중간 고점 ≤ 왼쪽 고점 × (1-2%)
    mid_retrace_min: float = 0.50       # (M-A)/(L-A) ≥ 50% — 피벗이 베이스 상단 절반 (하단 절반 매수 금지)
    left_rally_tol: float = 0.03        # 왼쪽 하락 구간(절반 이상 하락 후)의 반등 '종가' ≤ 중간 고점 × (1+3%)
    left_high_tol: float = 0.03         # 하락 시작점 = 왼쪽 고점 -3% 이내 고점 중 가장 최근 것 (복합 베이스 판정용)
    left_spike_tol: float = 0.08        # 왼쪽 최고가 > 3봉 중앙값 고가 × (1+8%) 면 1봉 스파이크 → 중앙값 수준 사용
    min_left_rise_bars: int = 5         # 1차 저점 아래 마지막 종가 → 왼쪽 고점 최소 봉 수 (저점에서 치솟은 스파이크 배제)
    # 오른쪽 회복 (돌파 전): 현재가가 B→피벗 거리의 40% 이상 회복해야 W 로 인정
    right_recovery_min: float = 0.40
    # 손잡이 (선택 사항)
    handle_zone: float = 0.06           # 오른쪽 고점이 피벗 -6% 이내에 도달
    handle_min_depth: float = 0.02
    handle_max_depth: float = 0.12
    handle_min_bars: int = 3
    # 단계 판정
    near_pct: float = 0.05
    buy_range: float = 0.05             # 피벗 +5% 까지 매수 범위
    breakout_window: int = 5
    fail_pct: float = 0.03
    max_bars_since_breakout: int = 20   # 돌파 후 이보다 오래되면 지난 패턴
    stop_max_pct: float = 0.08          # 오닐 손절 7~8%
    failed_penalty: float = 20.0        # 후속 흐름 감점 (돌파 실패)
    extended_penalty: float = 5.0       # 매수 범위 초과 기본 감점
    extended_penalty_max: float = 15.0  # 매수 범위를 20%p 이상 넘으면 최대 감점
    # 거래량
    breakout_vol_mult: float = 1.4      # 돌파일 거래량 ≥ 50일 평균 × 1.4
    dryup_ratio: float = 0.8            # 피벗 직전 5봉 평균 거래량 ≤ 50일 평균 × 0.8 이면 dry-up
    support_vol_mult: float = 1.3       # 2차 저점 부근 대량 거래(지지) 기준
    rs_warn: float = 70.0


# ---------------------------------------------------------------- 유틸
def krx_tick(price: float) -> float:
    """KRX 호가 단위 (2023-01 개편, 코스피·코스닥 공통)."""
    for lim, t in ((2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50), (200_000, 100), (500_000, 500)):
        if price < lim:
            return float(t)
    return 1000.0


def _floor_tick(p: float) -> float:
    """호가 단위로 내림 (구조적 손절가: 저점 아래)."""
    t = krx_tick(p)
    return float(math.floor(p / t + 1e-9) * t)


def _ceil_tick(p: float) -> float:
    """호가 단위로 올림 (최대 손실 한도 손절가: 한도를 넘지 않게)."""
    t = krx_tick(p)
    return float(math.ceil(p / t - 1e-9) * t)


def _median3(x: np.ndarray) -> np.ndarray:
    """중심 3봉 중앙값 (양 끝은 원값). 1봉 스파이크를 걸러낸 '실제 거래 수준'."""
    out = x.copy()
    if len(x) >= 3:
        a, b, c = x[:-2], x[1:-1], x[2:]
        out[1:-1] = np.maximum(np.minimum(a, b), np.minimum(np.maximum(a, b), c))
    return out


def _sma_np(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.concatenate([[0.0], x]))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x))) if x == x else 0.0


def _prep(ctx: StockContext, zz_pct: float):
    """결측·비정상 가격을 보정한 numpy 배열과 지그재그 스윙. 보정 불가면 None."""
    df = ctx.df
    cols = []
    dirty = False
    for k in ("open", "high", "low", "close"):
        a = df[k].to_numpy(dtype=float, copy=True)
        bad = ~np.isfinite(a) | (a <= 0)
        if bad.any():
            dirty = True
            a[bad] = np.nan
        cols.append(a)
    V = ctx.vol.to_numpy(dtype=float, copy=True)
    V[~np.isfinite(V) | (V < 0)] = 0.0
    if dirty:
        import pandas as pd
        fr = pd.DataFrame(np.column_stack(cols)).ffill().bfill()
        if fr.isna().any().any():
            return None
        cols = [fr[i].to_numpy() for i in range(4)]
    O, H, L, C = cols
    H = np.maximum(H, np.maximum(O, C))
    L = np.minimum(L, np.minimum(O, C))
    piv = ind.zigzag(H, L, zz_pct) if dirty else ctx.zigzag(zz_pct)
    return O, H, L, C, V, piv, _median3(H)


# ---------------------------------------------------------------- 구조 탐색
def _eval_pair(cfg: DoubleBottomConfig, H, L, C, Hs, a: int, b: int, last: int):
    """(1차 저점 a, 2차 저점 b) 조합 평가. 반환 (통과 단계 수, 실패 사유, 구조 dict|None)."""
    step = 0
    m = a + 1 + int(np.argmax(H[a + 1:b]))
    if m - a < cfg.min_leg_bars or b - m < cfg.min_leg_bars:   # 잡음 스윙 쌍 — 사유 우선순위 최하
        return step, f"중간 고점 위치 부적절 (A→M {m - a}봉, M→B {b - m}봉 < {cfg.min_leg_bars}봉)", None
    step += 1
    u = L[b] / L[a] - 1
    if u < -cfg.max_undercut or u > cfg.max_second_above:
        return step, (f"2차 저점이 1차 저점 대비 {u:+.1%} (허용 {-cfg.max_undercut:.0%}~"
                      f"+{cfg.max_second_above:.0%})"), None
    step += 1
    if L[a + 1:m + 1].min() < L[a]:
        return step, "1차 저점 이후 중간 고점 전에 더 낮은 저점 존재", None
    step += 1
    if L[m:b].min() < L[b]:
        return step, "중간 고점과 2차 저점 사이에 더 낮은 저점 존재", None
    step += 1
    tick = krx_tick(H[m])
    pivot = float(H[m] + tick)
    above = np.flatnonzero(C[b + 1:last + 1] > pivot)
    bo = int(b + 1 + above[0]) if len(above) else None
    end_right = bo if bo is not None else last
    if end_right > b and L[b + 1:end_right + 1].min() < L[b]:
        return step, "2차 저점 이후 돌파 전에 더 낮은 저점 (W 미완성/붕괴)", None
    step += 1
    if end_right - b > cfg.max_right_bars:
        return step, f"2차 저점 이후 {end_right - b}봉 경과 (최대 {cfg.max_right_bars}봉) — 오래된 W", None
    step += 1
    # 왼쪽 고점: a 이전으로 거슬러 올라가며 A 보다 낮은 저점이 나오기 직전까지 구간(s0~a)의 실제 최고가.
    # 1봉 스파이크(3봉 중앙값 고가보다 8% 넘게 높음)면 실제 거래된 수준(3봉 중앙값 고가의 최고치)을 쓴다.
    lo_lim = max(0, b - cfg.max_duration)
    seg = L[lo_lim:a]
    below = np.flatnonzero(seg < L[a])
    s0 = lo_lim + (int(below[-1]) + 1 if len(below) else 0)
    if a - s0 < cfg.min_leg_bars:
        return step, "왼쪽 고점→1차 저점 하락 구간이 너무 짧음 (선행 상승 없이 바로 저점)", None
    seg_h, seg_s = H[s0:a], Hs[s0:a]
    top = s0 + int(np.flatnonzero(seg_h == seg_h.max())[-1])
    lvl = float(seg_s.max())
    spike = float(H[top] / lvl - 1) if lvl > 0 else 0.0
    if spike > cfg.left_spike_tol:
        h0, lh = s0 + int(np.flatnonzero(seg_s == lvl)[-1]), lvl
    else:
        h0, lh = top, float(H[top])
    # 저점 수준에서 곧바로 치솟은 고점 배제: 마지막으로 1차 저점 아래에서 '마감'한 봉 → 왼쪽 고점까지 봉 수
    cb = np.flatnonzero(C[lo_lim:h0] < L[a])
    launch = h0 - (lo_lim + int(cb[-1])) if len(cb) else h0 - lo_lim + 1
    if launch < cfg.min_left_rise_bars:
        return step, (f"왼쪽 고점이 1차 저점 아래 종가로부터 {launch}봉 만에 형성 — 저점 수준에서 치솟은 스파이크 "
                      f"(선행 상승 아님, ≥{cfg.min_left_rise_bars}봉 필요)"), None
    if a - h0 < cfg.min_leg_bars:
        return step, f"왼쪽 고점→1차 저점 {a - h0}봉 < {cfg.min_leg_bars}봉", None
    step += 1
    # 실제 하락 시작점: 왼쪽 고점 -3% 이내 고점 중 가장 최근 것 (천장권 등락은 복합 베이스 판정에서 제외)
    near_top = np.flatnonzero(H[h0:a] >= lh * (1 - cfg.left_high_tol))
    hd0 = h0 + (int(near_top[-1]) if len(near_top) else 0)
    if H[m] > lh * (1 - cfg.mid_below_left):
        return step, (f"중간 고점이 왼쪽 고점 대비 {H[m] / lh - 1:+.1%} — "
                      f"{cfg.mid_below_left:.0%} 이상 낮아야 함"), None
    step += 1
    retr = (H[m] - L[a]) / (lh - L[a])
    if retr < cfg.mid_retrace_min:
        return step, f"중간 고점 반등이 하락폭의 {retr:.0%} (≥{cfg.mid_retrace_min:.0%} 필요)", None
    step += 1
    # 왼쪽 다리: 하락폭 절반을 지난 뒤의 반등 고점이 중간 고점보다 높으면 W 가 아닌 복합(다중) 베이스
    half = np.flatnonzero(L[hd0 + 1:a + 1] <= lh - 0.5 * (lh - L[a]))
    if len(half):
        j = hd0 + 1 + int(half[0])
        if j < a and C[j:a].max() > H[m] * (1 + cfg.left_rally_tol):
            return step, (f"왼쪽 하락 구간 반등 종가 {C[j:a].max():,.0f} 이 중간 고점보다 "
                          f"{cfg.left_rally_tol:.0%} 넘게 높음 (복합 베이스·상단 매물)"), None
    step += 1
    low = min(L[a], L[b])
    depth = 1 - low / lh
    if depth < cfg.min_depth or depth > cfg.max_depth:
        return step, f"깊이 {depth:.1%} (허용 {cfg.min_depth:.0%}~{cfg.max_depth:.0%})", None
    step += 1
    lc, mc = min(C[max(0, h0 - 2):h0 + 3].max(), lh), C[m - 2:m + 3].max()
    ac, bc = C[a - 2:a + 3].min(), C[b - 2:b + 3].min()
    cdepth = 1 - min(ac, bc) / lc
    cretr = (mc - ac) / (lc - ac) if lc > ac else 0.0
    need_cd = max(cfg.min_close_depth, cfg.min_close_depth_ratio * depth)
    if cdepth < need_cd or cretr < cfg.min_close_retrace:
        return step, (f"종가 기준 깊이 {cdepth:.1%}(장중 {depth:.1%}), 중간 반등 {cretr:.0%} — 장중 꼬리(스파이크)로 "
                      f"만든 형태 (≥{need_cd:.1%}, ≥{cfg.min_close_retrace:.0%} 필요)"), None
    step += 1
    dur = end_right - h0
    if dur < cfg.min_duration or dur > cfg.max_duration:
        return step, (f"기간 {dur}봉 ({dur / 5:.0f}주) — {cfg.min_duration}~{cfg.max_duration}봉 "
                      f"({cfg.min_duration // 5}~{cfg.max_duration // 5}주) 필요"), None
    step += 1
    pstart = max(0, h0 - cfg.prior_lookback)
    if h0 - pstart < cfg.min_prior_bars:
        return step, f"왼쪽 고점 이전 이력 {h0 - pstart}봉 < {cfg.min_prior_bars}봉 (선행 상승 판정 불가)", None
    prior_low_i = pstart + int(np.argmin(L[pstart:h0]))
    prior_gain = lh / L[prior_low_i] - 1
    if prior_gain < cfg.prior_uptrend_min:
        return step, f"선행 상승 {prior_gain:.0%} < {cfg.prior_uptrend_min:.0%}", None
    step += 1
    prior_high = Hs[pstart:h0].max()   # 3봉 중앙값 고가 — 과거 1봉 스파이크 고점은 무시
    if lh < prior_high * (1 - cfg.prior_high_tol):
        return step, (f"왼쪽 고점 {lh:,.0f} 이 직전 고점 {prior_high:,.0f} 보다 {1 - lh / prior_high:.1%} 낮음 "
                      f"— 하락 후 반등 고점(선행 상승 아님)"), None
    step += 1
    recovery = (C[last] - L[b]) / (pivot - L[b]) if pivot > L[b] else 0.0
    if bo is None and recovery < cfg.right_recovery_min:
        return step, (f"오른쪽 회복 미흡: 2차 저점→피벗 거리의 {recovery:.0%} 회복 "
                      f"(≥{cfg.right_recovery_min:.0%} 필요)"), None
    step += 1
    # 손잡이 실패(누적): 오른쪽이 피벗권에 처음 들어온 뒤 돌파 전날(또는 현재)까지, 그때까지의 최고가 대비
    # 손잡이 허용폭보다 깊게 밀린 적이 있으면 새 베이스 — 이후 새 고점·돌파가 나와도 옛 W 로 되살리지 않음
    end_pre = (bo - 1) if bo is not None else last
    if end_pre > b + 1:
        zone = np.flatnonzero(H[b + 1:end_pre + 1] >= pivot * (1 - cfg.handle_zone))
        if len(zone):
            r0 = b + 1 + int(zone[0])
            runmax = np.maximum.accumulate(H[r0:end_pre + 1])
            pulls = 1 - L[r0:end_pre + 1] / runmax
            k = int(np.argmax(pulls))
            if pulls[k] > cfg.handle_max_depth:
                return step, (f"오른쪽 고점 {runmax[k]:,.0f} 이후 {pulls[k]:.1%} 되밀림 — 손잡이 실패"
                              f"(>{cfg.handle_max_depth:.0%}), 새 베이스"), None
    step += 1
    if bo is not None and last - bo > cfg.max_bars_since_breakout:
        return step, f"돌파 후 {last - bo}봉 경과 — 지난 패턴", None
    step += 1
    return step, "", dict(h0=h0, lh=lh, top=top, spike=spike, a=a, m=m, b=b, bo=bo, end_right=end_right,
                          pivot=pivot, tick=tick, undercut=u, retrace=retr, depth=depth, duration=dur,
                          prior_gain=prior_gain, prior_low_i=prior_low_i, recovery=recovery, low=low,
                          close_depth=cdepth, close_retrace=cretr)


def _handle(cfg: DoubleBottomConfig, H, L, V, vavg, g: dict, end_pre: int):
    """오른쪽 상단 손잡이 탐지 (선택 사항). 없으면 None."""
    b, pivot = g["b"], g["pivot"]
    if end_pre - b < cfg.handle_min_bars + 2:
        return None
    r = b + 1 + int(np.argmax(H[b + 1:end_pre + 1]))
    if H[r] < pivot * (1 - cfg.handle_zone) or end_pre - r < cfg.handle_min_bars:
        return None
    hl = r + int(np.argmin(L[r:end_pre + 1]))
    hdepth = 1 - L[hl] / H[r]
    mid_right = (pivot + L[b]) / 2   # 손잡이 저점은 오른쪽 상승폭(B→피벗)의 상단 절반에 있어야 함
    if not (cfg.handle_min_depth <= hdepth <= cfg.handle_max_depth) or L[hl] <= mid_right:
        return None
    hv = float(V[r:end_pre + 1].mean() / vavg[end_pre]) if np.isfinite(vavg[end_pre]) and vavg[end_pre] > 0 \
        else float("nan")
    return dict(r=r, hl=hl, high=float(H[r]), low=float(L[hl]), depth=float(hdepth), bars=end_pre - r + 1,
                vol_ratio=hv, pivot=float(H[r] + krx_tick(H[r])))


def _score(cfg: DoubleBottomConfig, ctx: StockContext, H, L, C, V, vavg, g: dict) -> tuple[float, dict]:
    """품질 점수와 거래량 지표."""
    b, bo, last = g["b"], g["bo"], ctx.n - 1
    end_pre = (bo - 1) if bo is not None else last
    parts = {}
    # 1) 언더컷 형태 (20)
    u = g["undercut"]
    if -cfg.ideal_undercut <= u <= -0.002:
        parts["undercut"] = 20.0
    elif -0.002 < u <= 0.0:
        parts["undercut"] = 15.0
    elif u > 0:
        parts["undercut"] = 15.0 - 10.0 * _clip01(u / cfg.max_second_above)
    else:
        parts["undercut"] = 12.0
    # 2) 깊이 (15)
    d = g["depth"]
    if d < 0.15:
        parts["depth"] = 8 + 7 * _clip01((d - cfg.min_depth) / (0.15 - cfg.min_depth))
    elif d <= cfg.ideal_depth:
        parts["depth"] = 15.0
    else:
        parts["depth"] = 15 - 10 * _clip01((d - cfg.ideal_depth) / (cfg.max_depth - cfg.ideal_depth))
    # 3) 선행 상승 (15)
    parts["prior"] = 7 + 8 * _clip01((g["prior_gain"] - cfg.prior_uptrend_min)
                                     / (cfg.prior_uptrend_good - cfg.prior_uptrend_min))
    # 4) 중간 고점 위치 (10): 하락폭 60~90% 되돌림이 이상적
    r = g["retrace"]
    parts["mid"] = 10.0 if 0.6 <= r <= 0.9 else (7 + 3 * _clip01((r - cfg.mid_retrace_min) / 0.1) if r < 0.6 else 8.0)
    # 5) 거래량 (20)
    va = vavg[end_pre] if np.isfinite(vavg[end_pre]) and vavg[end_pre] > 0 else np.nan
    dry = float(V[max(b + 1, end_pre - 4):end_pre + 1].mean() / va) if va == va and end_pre > b else float("nan")
    parts["dryup"] = 8 * _clip01((1.2 - dry) / (1.2 - 0.6)) if dry == dry else 4.0
    seg_c = C[b:end_pre + 1]
    seg_v = V[b + 1:end_pre + 1]
    chg = np.diff(seg_c)
    upv, dnv = seg_v[chg > 0].sum(), seg_v[chg < 0].sum()
    ud = float(upv / dnv) if dnv > 0 else (3.0 if upv > 0 else float("nan"))
    parts["ud"] = 6 * _clip01((ud - 0.8) / 0.7) if ud == ud else 3.0
    bo_vol = float("nan")
    if bo is not None:
        vb = vavg[bo - 1]
        bo_vol = float(V[bo] / vb) if np.isfinite(vb) and vb > 0 else float("nan")
        parts["bo_vol"] = 6 * _clip01((bo_vol - 1.0) / (cfg.breakout_vol_mult - 1.0)) if bo_vol == bo_vol else 3.0
    else:
        parts["bo_vol"] = 3.0  # 아직 돌파 전: 중립
    vb_b = vavg[b - 1] if b >= 1 else np.nan
    sup = float(V[max(0, b - 2):b + 3].max() / vb_b) if np.isfinite(vb_b) and vb_b > 0 else float("nan")
    # 6) 추세·RS (20)
    rs = ctx.rs_rating
    parts["rs"] = 10 * _clip01((rs - 50) / 49) if rs is not None and rs == rs else 3.0
    s200 = ctx.sma(200).to_numpy()
    if np.isfinite(s200[last]):
        parts["above200"] = 5.0 if C[last] > s200[last] else 0.0
        prev = s200[last - 22] if last >= 22 else np.nan
        parts["rising200"] = 5.0 if np.isfinite(prev) and s200[last] > prev else 0.0
    else:
        parts["above200"] = parts["rising200"] = 0.0
    score = float(min(100.0, max(0.0, sum(parts.values()))))
    vol = dict(dryup_ratio=dry, right_ud_ratio=ud, breakout_vol_ratio=bo_vol, b_vol_ratio=sup)
    return score, {"parts": parts, **vol}


def _search(cfg: DoubleBottomConfig, H, L, C, Hs, piv, last: int):
    lows = np.array([p.i for p in piv if p.kind == "L"], dtype=int)
    best_fail = (-1, -1, "최근 구간에 스윙 저점 없음")
    found = []
    if len(lows) < 2:
        return found, (0, -1, "스윙 저점 부족 (변동 없음 또는 단방향 추세)")
    b_min = last - (cfg.max_right_bars + cfg.max_bars_since_breakout)
    for b in lows[lows >= b_min][::-1]:
        b = int(b)
        a_all = lows[(lows <= b - cfg.min_low_gap) & (lows >= b - cfg.max_duration)][::-1]
        if not len(a_all):
            continue
        u = L[b] / L[a_all] - 1   # 두 저점 관계로 먼저 거른다 (벡터화)
        u_ok = (u >= -cfg.max_undercut) & (u <= cfg.max_second_above)
        if not u_ok.all() and (1, b) > best_fail[:2]:
            bad = np.flatnonzero(~u_ok)
            k = int(bad[np.argmin(np.abs(u[bad]))])   # 허용 범위에 가장 가까웠던 저점으로 사유 기록
            best_fail = (1, b, f"2차 저점이 1차 저점 대비 {u[k]:+.1%} (허용 {-cfg.max_undercut:.0%}~"
                               f"+{cfg.max_second_above:.0%})")
        for a in a_all[u_ok]:
            a = int(a)
            step, why, g = _eval_pair(cfg, H, L, C, Hs, a, b, last)
            if g is not None:
                found.append(g)
            elif (step, b) > best_fail[:2]:
                best_fail = (step, b, why)
        if found:  # 가장 최근 2차 저점에서 유효 구조가 나오면 그 B 로 확정
            break
    return found, best_fail


# ---------------------------------------------------------------- 탐지기
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, DoubleBottomConfig)
    res = PatternResult(name=NAME, label=LABEL)
    need = cfg.min_duration + cfg.min_prior_bars + 10
    if ctx.n < need:
        res.warnings.append(f"✘ 이력 부족 ({ctx.n}봉 < {need}봉) — 더블 바텀 판정 불가")
        return res
    data = _prep(ctx, cfg.zigzag_pct)
    if data is None:
        res.warnings.append("✘ 가격 데이터 결측/비정상 — 판정 불가")
        return res
    O, H, L, C, V, piv, Hs = data
    last = ctx.n - 1
    if not np.isfinite(H).all() or H.max() <= L.min():
        res.warnings.append("✘ 가격 변동 없음 — 판정 불가")
        return res

    found, best_fail = _search(cfg, H, L, C, Hs, piv, last)
    if not found:
        res.warnings.append("✘ 최근 W(더블 바텀) 구조 없음" + (f": {best_fail[2]}" if best_fail[2] else ""))
        return res

    vavg = _sma_np(V, 50)
    scored = []
    for g in found:
        s, extra = _score(cfg, ctx, H, L, C, V, vavg, g)
        scored.append((s, g, extra))
    score, g, extra = max(scored, key=lambda x: (x[0], x[1]["a"]))
    h0, lh, a, m, b, bo, pivot = g["h0"], g["lh"], g["a"], g["m"], g["b"], g["bo"], g["pivot"]
    end_pre = (bo - 1) if bo is not None else last
    hd = _handle(cfg, H, L, V, vavg, g, end_pre)

    stage, bo_i = classify_stage(ctx, pivot, b, near_pct=cfg.near_pct, buy_range=cfg.buy_range,
                                 breakout_window=cfg.breakout_window, fail_pct=cfg.fail_pct)
    c_last = float(C[last])
    # 후속 흐름 감점: 돌파 실패 / 매수 범위 초과(초과폭에 비례)
    if stage == FAILED:
        extra["parts"]["follow"] = -cfg.failed_penalty
    elif stage == EXTENDED:
        over = _clip01((c_last / pivot - 1 - cfg.buy_range) / 0.20)
        extra["parts"]["follow"] = -(cfg.extended_penalty + (cfg.extended_penalty_max - cfg.extended_penalty) * over)
    score = float(min(100.0, max(0.0, sum(extra["parts"].values()))))
    # 손절: 2차 저점 / 손잡이 저점 / 피벗 -8% 중 가장 높은(가까운) 값 — KRX 호가 단위
    stops = {"2차 저점": _floor_tick(L[b] - krx_tick(L[b])), "피벗 -8%": _ceil_tick(pivot * (1 - cfg.stop_max_pct))}
    if hd is not None:
        stops["손잡이 저점"] = _floor_tick(hd["low"] - krx_tick(hd["low"]))
    stop_basis, stop = max(stops.items(), key=lambda kv: kv[1])

    res.detected = True
    res.score = round(score, 1)
    res.stage = stage
    res.pivot = round(pivot, 2)
    res.stop = round(float(stop), 2)
    res.start_date = ctx.date(h0)
    res.end_date = ctx.date(bo_i if bo_i is not None else last)
    res.breakout_date = ctx.date(bo_i) if bo_i is not None else None

    res.metrics = {
        "left_high": float(lh), "first_low": float(L[a]), "mid_high": float(H[m]), "second_low": float(L[b]),
        "left_high_raw": float(H[g["top"]]), "left_spike_pct": round(g["spike"] * 100, 1),
        "undercut_pct": round(g["undercut"] * 100, 2),
        "depth_pct": round(g["depth"] * 100, 1),
        "close_depth_pct": round(g["close_depth"] * 100, 1),
        "close_mid_retrace": round(g["close_retrace"], 2),
        "mid_retrace": round(g["retrace"], 2),
        "mid_below_left_pct": round((1 - H[m] / lh) * 100, 1),
        "duration_bars": g["duration"], "duration_weeks": round(g["duration"] / 5, 1),
        "low_gap_bars": b - a, "right_bars": g["end_right"] - b,
        "prior_uptrend_pct": round(g["prior_gain"] * 100, 1),
        "dist_to_pivot_pct": round((c_last / pivot - 1) * 100, 2),
        "dryup_ratio": round(extra["dryup_ratio"], 2) if extra["dryup_ratio"] == extra["dryup_ratio"] else None,
        "right_ud_ratio": round(extra["right_ud_ratio"], 2) if extra["right_ud_ratio"] == extra["right_ud_ratio"]
        else None,
        "b_vol_ratio": round(extra["b_vol_ratio"], 2) if extra["b_vol_ratio"] == extra["b_vol_ratio"] else None,
        "breakout_vol_ratio": round(extra["breakout_vol_ratio"], 2)
        if extra["breakout_vol_ratio"] == extra["breakout_vol_ratio"] else None,
        "handle": hd is not None,
        "handle_depth_pct": round(hd["depth"] * 100, 1) if hd else None,
        "handle_pivot": round(hd["pivot"], 2) if hd else None,
        "stop_basis": stop_basis,
        "rs": ctx.rs_rating,
    } | {f"score_{k}": round(v, 1) for k, v in extra["parts"].items()}

    # ---- 설명
    R, W = res.reasons, res.warnings
    R.append(f"✔ 선행 상승 +{g['prior_gain']:.0%} 후 W 형성 (왼쪽 고점 {lh:,.0f}, {ctx.date(h0)})")
    if g["spike"] > cfg.left_spike_tol:
        W.append(f"✘ 왼쪽 최고가 {H[g['top']]:,.0f}({ctx.date(g['top'])})는 1봉 스파이크(주변 대비 +{g['spike']:.0%}) "
                 f"— 실제 거래 수준 {lh:,.0f} 을 왼쪽 고점으로 사용")
    u = g["undercut"]
    if u <= -0.002:
        R.append(f"✔ 2차 저점이 1차 저점을 {-u:.1%} 하회 — 셰이크아웃(언더컷)")
    elif u <= 0:
        R.append("✔ 두 저점이 거의 같은 수준 (이중 지지)")
    else:
        W.append(f"✘ 2차 저점이 1차 저점보다 {u:.1%} 높음 — 언더컷 없는 약한 형태")
    if g["depth"] <= cfg.ideal_depth:
        R.append(f"✔ 깊이 {g['depth']:.1%} (≤{cfg.ideal_depth:.0%})")
    else:
        W.append(f"✘ 깊이 {g['depth']:.1%} — 다소 깊음 (≤{cfg.ideal_depth:.0%} 바람직)")
    R.append(f"✔ 기간 {g['duration']}봉 ({g['duration'] / 5:.1f}주), 두 저점 간격 {b - a}봉")
    R.append(f"✔ 중간 고점 {H[m]:,.0f} (왼쪽 고점 대비 -{1 - H[m] / lh:.1%}, 하락폭 {g['retrace']:.0%} 되돌림) "
             f"→ 피벗 {pivot:,.0f}")
    dry = extra["dryup_ratio"]
    if dry == dry:
        if dry <= cfg.dryup_ratio:
            R.append(f"✔ 피벗 직전 거래량 감소 (5봉 평균 = 50일 평균의 {dry:.0%})")
        else:
            W.append(f"✘ 피벗 직전 거래량 감소 미흡 (5봉 평균 = 50일 평균의 {dry:.0%})")
    sup = extra["b_vol_ratio"]
    if sup == sup and sup >= cfg.support_vol_mult:
        R.append(f"✔ 2차 저점 부근 대량 거래 ({sup:.1f}배) — 저점 지지 매수")
    ud = extra["right_ud_ratio"]
    if ud == ud:
        (R.append(f"✔ 오른쪽 상승/하락 거래량비 {ud:.2f}") if ud >= 1.0
         else W.append(f"✘ 오른쪽 상승/하락 거래량비 {ud:.2f} < 1 (매집 약함)"))
    if hd is not None:
        if hd["pivot"] <= pivot:
            R.append(f"✔ 손잡이 {hd['bars']}봉, 깊이 {hd['depth']:.1%} — 조기 매수점(손잡이 고점) {hd['pivot']:,.0f}")
        else:
            R.append(f"✔ 손잡이 {hd['bars']}봉, 깊이 {hd['depth']:.1%}")
            W.append(f"✘ 손잡이 고점 {hd['pivot']:,.0f} 이 중간 고점 피벗보다 높음 — 손잡이 고점 돌파 확인 권장")
    if bo_i is not None:
        bv = extra["breakout_vol_ratio"]
        if bv == bv and bv >= cfg.breakout_vol_mult:
            R.append(f"✔ {ctx.date(bo_i)} 피벗 돌파, 거래량 50일 평균의 {bv:.1f}배")
        elif bv == bv:
            W.append(f"✘ {ctx.date(bo_i)} 돌파 거래량 부족 ({bv:.1f}배 < {cfg.breakout_vol_mult}배)")
        else:
            W.append(f"✘ {ctx.date(bo_i)} 돌파 거래량 비교 불가 (50일 평균 거래량 없음)")
        if bo_i == last and ctx.partial:
            W.append("✘ 돌파봉이 장중 미완성 봉 — 종가·거래량은 추정치 (마감 후 재확인)")
        val = float(ctx.value.iloc[bo_i])
        if val >= ctx.cfg.big_value_threshold:
            R.append(f"✔ 돌파일 거래대금 {val / 1e8:,.0f}억 (≥{ctx.cfg.big_value_threshold / 1e8:,.0f}억)")
    if stage == EXTENDED:
        W.append(f"✘ 피벗 대비 +{c_last / pivot - 1:.1%} — 매수 범위(+{cfg.buy_range:.0%}) 초과")
    elif stage == FAILED:
        W.append(f"✘ 돌파 후 피벗 아래로 {1 - c_last / pivot:.1%} 되밀림 — 돌파 실패")
    rs = ctx.rs_rating
    if rs is None or rs != rs:
        W.append("✘ RS 레이팅 없음")
    elif rs >= cfg.rs_warn:
        R.append(f"✔ RS 레이팅 {rs:.0f}")
    else:
        W.append(f"✘ RS 레이팅 {rs:.0f} < {cfg.rs_warn:.0f} (주도주 아님)")
    ms = ctx.market_state
    if ms is not None and getattr(ms, "state", None) == "correction":
        W.append(f"✘ 시장 조정 국면 ({ms.name}) — 돌파 신뢰도 낮음")
    R.append(f"✔ 손절 {stop:,.0f} ({stop_basis}, 피벗 대비 -{1 - stop / pivot:.1%})")
    # 데이터 주의
    halts = ctx.df.attrs.get("halt_dates") or []
    if halts:
        s_d, e_d = res.start_date, ctx.date(last)
        inside = [d for d in halts if s_d <= str(d)[:10] <= e_d]
        if inside:
            W.append(f"✘ 패턴 구간 내 거래정지 {len(inside)}일 ({inside[0]}~) — 형태 왜곡 가능")
    w = V[h0:last + 1]
    k = max(5, len(w) // 3)
    m1, m3 = np.median(w[:k]), np.median(w[-k:])
    if m1 > 0 and m3 > 0 and (m3 / m1 > 6 or m1 / m3 > 6):
        W.append("✘ 패턴 구간 거래량 수준 급변(액면분할·병합 가능성) — 거래량 비율 신뢰도 낮음")

    # ---- 차트 주석
    d = ctx.df.index
    end_pt = (d[bo_i], float(C[bo_i])) if bo_i is not None else (d[last], c_last)
    res.annotations = [
        hline(pivot, f"피벗 {pivot:,.0f}"),
        hline(stop, f"손절 {stop:,.0f}", "#d50000"),
        segment([(d[h0], lh), (d[a], L[a]), (d[m], H[m]), (d[b], L[b]), end_pt], "W", "#ff6d00"),
        marker(d[b], "언더컷" if u <= -0.002 else "2차 저점", "below", "#00897b", "arrowUp"),
    ]
    if hd is not None:
        res.annotations.append(box(d[hd["r"]], d[end_pre], hd["high"], hd["low"], "손잡이"))
    if bo_i is not None:
        res.annotations.append(marker(d[bo_i], "돌파", "below", "#e91e63", "arrowUp"))
    return res
