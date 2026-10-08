"""컵 앤 핸들 (Cup with Handle) — William O'Neil, *How to Make Money in Stocks* / IBD.

판정 규칙 (임계값은 모두 ``CupHandleConfig``):
 1. 선행 상승 — 왼쪽 립은 '직전 상승의 꼭지'여야 한다.
    - 립 = 직전 20봉 최고가이자 직후 5봉 이상인 스윙 고점. 전후 종가보다 8% 넘게 솟은 윗꼬리 스파이크는 제외.
    - 립 고가 ≥ 직전 120봉 최고 종가의 95% (조정 중 되돌림 고점(lower high) 배제 — 베이스는 더 높은 고점에서
      시작), ≥ 직전 250봉 최고가의 80%.
    - 선행 상승 +30% 이상: 직전 250봉 중 '립 고가보다 높았던 마지막 종가' 이후의 최저가 → 립 고가
      (상승이 실제로 립에서 끝나야 함 — 1년 전 저점으로 채우지 않음). 립 이전 최소 40봉 이력.
 2. 컵 기간: 왼쪽 립 → 오른쪽 립 35~325봉 (7~65주).
 3. 컵 깊이(왼쪽 립 고가 → 컵 최저가): 12~33% 정상. 33~50% 는 컵 기간 중 지수가 10% 이상
    조정받은 경우에만 허용(감점·경고). 50% 초과는 탈락. 종가 기준 깊이도 10% 이상(꼬리 저점 착시 배제).
 4. U자형 (종가 기준, V·L·W 배제):
    - 하단 1/3 체류 비율 ≥ 25%, 바닥 체류 구간 중심 기준 좌·우 측면 각각 컵 길이의 20% 이상,
      2차(포물선) 적합 R² ≥ 0.35 & 아래로 볼록.
    - 오른쪽 급등 배제(일자 바닥 뒤 1~4일 급등으로 립에 붙는 V/L자, 립 위 돌파분은 빼고 립 수준까지만 측정):
      컵 저점 이후 2봉 안에 컵 범위의 55% 초과 상승(스파이크), 또는 w봉(w = max(3, 컵 길이의 5%)) 안에
      75% 초과(60% 초과이면서 주가 +25% 초과) 상승이면 탈락. 각각 30%·40% 초과부터 감점.
      왼쪽 급락(w봉 안 60% 초과 하락)은 경고·감점만 (시장 급락기에 생긴 컵은 흔하므로 탈락 아님).
    - W자 배제: 3봉 평활 종가가 바닥 하단 25% 를 처음~마지막 방문하는 사이 최고점이 컵 범위의 50% 초과면
      탈락(쌍바닥 → double_bottom 트랙), 35% 초과는 감점.
 5. 오른쪽 립: 왼쪽 립 고가의 85% 이상까지 회복, 왼쪽 립을 5% 넘게 웃돌지 않음.
 6. 핸들: 오른쪽 립 이후 5~25봉, 깊이 ≤ 12% (ATR% ≥ 4% 고변동 종목은 15%), 핸들 저점은 컵
    중간값 위(이상적: 상단 1/3). 50일선 위·하락/횡보(쐐기형 상승은 결함)·거래량 고갈
    (핸들 평균 거래량 < 50일 평균, < 오른쪽 상승 구간 평균)은 점수·경고로 반영.
    유효 핸들(5봉 이상, 이미 3% 이상 눌림) 진행 중 장중 고가만 피벗을 max(2%, 1 ATR) 이내로 넘고 종가는
    피벗 이하인 '찌르기'(실패한 돌파 시도)는 핸들을 끊지 않는다 — 피벗 유지, 횟수 기록·경고.
    피벗과 같은 고가(동가 재시험)도 핸들 유지. 눌림 전·횡보 중 신고가는 새 오른쪽 립(핸들 시작)으로 본다.
 7. 피벗 = 핸들 최고가(= 오른쪽 립 고가, 실제 주문가는 +1호가 → metrics['buy_point']).
    손절 = max(핸들 저점, 피벗 −8%) — 둘 다 metrics 에 보고.
    돌파 = 핸들 이후 피벗 위 종가 + 거래량 50일 평균의 1.4배 이상. 거래량 미달이면 '미확인 돌파'로
    피벗 근접(매수 범위를 넘었으면 이격 과다)으로 하향하고 경고.
 변형 (metrics['variant']):
    cup_handle    : 정식 컵 앤 핸들.
    cup_no_handle : 핸들 없이 오른쪽이 왼쪽 립 5% 이내 도달(또는 립 위 종가) → 피벗 = 왼쪽 립 고가, 감점.
                    립 위 종가 직전 15봉 중 3봉 이상 종가가 립의 90~100% 구간이어야 '완성된 컵'
                    (립 부근 체류 없이 수직으로 뚫은 경우는 탈락 — 뚫은 뒤 립 위에서 버틴 봉은 세지 않음).
    cup_forming   : 오른쪽이 컵 절반 이상 회복하며 상승 중 → 단계 forming, 피벗 = 왼쪽 립 고가(예상).

탐색 (미래 참조 없음, 마지막 봉 기준 '최근' 구조만):
    최근 350봉 내 스윙 고점을 왼쪽 립 후보로 두고, 각 후보의 컵 저점 이후를 앞으로 훑으며 핸들 돌파/무핸들
    돌파 사건을 기록한다. 가격이 립 +5% 를 넘으면 그 후보의 구조는 종료. 마지막 봉에서 진행 중인 유효
    핸들이 있으면 그것이 우선(핸들 돌파 뒤라면 돌파 후 10봉 이내 고점에서 시작하고 피벗 −3% 를 지킨
    경우만, 무핸들 돌파 뒤라면 제한 없음), 없으면 최근 15봉 이내 돌파 사건, 없으면 무핸들/형성 중 상태.
    후보 선택(사후 피벗 변경 방지): 같은 컵 저점을 공유하면 가장 높은(이른) 립, 같은 돌파봉을 공유하면
    단계와 무관한 구조 점수가 높은 쪽, 나머지는 최종 점수 최고.

점수 (0~100):
    컵 30      = U자형 15 + 깊이 10 + 오른쪽 립 회복도 5 − 왼쪽 급락 3
                 (u_shape = [0.40·하단 체류(20→45%) + 0.20·측면 균형(15→35%) + 0.20·R²(0.35→0.75)
                             + 0.20·오른쪽 완만함(w봉 급등 75→40%, 2봉 스파이크 55→30% 중 나쁜 쪽)]
                             × W 감점(중간 반등 35→50% 에서 1→0.5))
    핸들 25    = 깊이 8 + 위치 6 + 50일선 위 3 + 하락/횡보 3 + 거래량 고갈 5
                 (cup_no_handle 은 8점 고정, cup_forming 은 0점)
    추세·RS 25 = 선행 상승 8 + 트렌드 템플릿 충족 수 9 + RS 레이팅 8
    거래량 20  = 오른쪽 상승 구간 매집(상승일/하락일 거래량비) 6 + 돌파 거래량 10 (미돌파 5 중립)
                 + 돌파일 거래대금 300억 이상 4
    단계 조정  = failed −25, extended −5
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .base import (EXTENDED, FAILED, FORMING, PatternResult, StockContext, box, classify_stage, hline,
                   marker, register, segment)
from .trend_template import evaluate as tt_evaluate

NAME, LABEL = "cup_handle", "컵 앤 핸들"
V_HANDLE, V_NO_HANDLE, V_FORMING = "cup_handle", "cup_no_handle", "cup_forming"
_VARIANT_LABEL = {V_HANDLE: "컵 앤 핸들", V_NO_HANDLE: "핸들 없는 컵", V_FORMING: "컵 형성 중"}


@dataclass
class CupHandleConfig:
    # ---- 탐색
    search_bars: int = 350              # 왼쪽 립 후보 탐색 범위 (65주 컵 + 핸들)
    lip_left_bars: int = 20             # 왼쪽 립 = 직전 20봉 최고가 (선행 상승의 꼭지)
    lip_right_bars: int = 5             # 왼쪽 립 = 직후 5봉보다 높거나 같음
    lip_max_wick: float = 0.08          # 립 고가가 전후 1봉 최고 종가보다 8% 넘게 높으면 '꼬리 스파이크' → 후보 제외
    min_history: int = 120              # 최소 이력 (선행 상승 40봉 + 컵 35봉 + 여유)
    # ---- 선행 상승 (O'Neil: 베이스 이전 30% 이상 상승, 베이스는 상승의 꼭지에서 시작)
    prior_lookback: int = 250
    prior_min_bars: int = 40
    prior_advance_min: float = 0.30     # 립보다 높았던 마지막 종가 이후 저점 → 립 고가
    lip_max_below_high: float = 0.20    # 왼쪽 립은 직전 250봉 최고가의 80% 이상
    lip_peak_lookback: int = 120        # 왼쪽 립은 직전 120봉 최고 종가의
    lip_peak_tol: float = 0.05          #   95% 이상 (조정 중 되돌림 고점 = lower high 배제)
    # ---- 컵 (O'Neil: 7~65주, 깊이 12~33%, 약세장에서는 40~50%까지)
    min_cup_bars: int = 35
    max_cup_bars: int = 325
    min_depth: float = 0.12
    max_depth: float = 0.33
    hard_max_depth: float = 0.50
    deep_needs_correction: bool = True  # 33% 초과 깊이는 시장 조정기에만 허용
    market_corr_dd: float = 0.10        # 컵 기간 지수 고점 대비 하락폭 ≥ 10% = 시장 조정
    # ---- U자형 (V·L·W 배제: 바닥에서 시간을 보내고 양 벽이 완만해야 함)
    bottom_zone: float = 1 / 3          # 컵 하단 1/3 구간
    min_bottom_frac: float = 0.25       # 하단 1/3 체류 봉 비율 하한
    min_side_frac: float = 0.20         # 좌·우 측면 각각 컵 길이의 20% 이상
    min_quad_r2: float = 0.35           # 컵 구간 종가의 2차(포물선) 적합 R² 하한 — 횡보 박스·지그재그 배제
    min_close_depth: float = 0.10       # 종가 기준 깊이 하한 — 하루짜리 꼬리 저점으로 깊어 보이는 횡보 배제
    thrust_win_frac: float = 0.05       # 급등/급락 측정 창 = 컵 길이의 5% (최소 3봉)
    thrust_min_bars: int = 3
    spike_bars: int = 2                 # 오른쪽 스파이크: 2봉 안에
    max_right_spike: float = 0.55       #   컵 범위의 55% 초과 상승(립 수준까지) → V/L자 탈락
    soft_right_spike: float = 0.30      #   30% 초과부터 감점
    max_right_thrust: float = 0.75      # 오른쪽 급등: w봉 안 상승폭이 컵 범위의 75% 초과 → 탈락
    steep_right_thrust: float = 0.60    #   또는 60% 초과이면서
    steep_right_pct: float = 0.25       #   주가 +25% 초과 (깊은 컵의 수직 상승; 얕은 컵의 빠른 마무리는 허용)
    soft_right_thrust: float = 0.40     #   40% 초과부터 감점
    max_left_drop: float = 0.60         # 왼쪽: 창 안 하락폭이 컵 범위의 60% 초과 → 급락 경고·감점
    w_smooth_bars: int = 3              # W자 판정: 3봉 평활 종가
    w_zone: float = 0.25                #   바닥 하단 25% 첫 방문~마지막 방문 사이
    max_w_rally: float = 0.50           #   중간 반등이 컵 범위의 50% 초과 → W자(쌍바닥) 탈락
    soft_w_rally: float = 0.35          #   35% 초과부터 감점
    # ---- 오른쪽 립 (O'Neil: 고점 10~15% 이내까지 회복)
    right_lip_min: float = 0.85
    right_lip_max_over: float = 0.05    # 왼쪽 립 초과 허용 폭 ("몇 %")
    # ---- 핸들 (O'Neil: 1주 이상, 깊이 8~12%, 컵 상단 절반, 거래량 감소)
    handle_min_bars: int = 5
    handle_max_bars: int = 25
    handle_max_depth: float = 0.12
    handle_max_depth_volatile: float = 0.15
    volatile_atr_pct: float = 0.04      # ATR14/종가 ≥ 4% 면 고변동 종목
    handle_min_position: float = 0.5    # 핸들 저점 ≥ 컵 중간값
    handle_ideal_position: float = 2 / 3
    # 핸들 중 장중 피벗 상회 후 종가는 피벗 이하('찌르기' = 실패한 돌파 시도, IBD: 매수점 불변)
    poke_min_pullback: float = 0.03     #   핸들이 이미 3% 이상 눌렸다면
    poke_max_pct: float = 0.02          #   max(2%, 1 ATR) 이내 찌르기까지 핸들 유지·피벗 불변
    poke_max_atr: float = 1.0           #   (눌림 전 신고가·큰 상회는 새 오른쪽 립 = 핸들 재시작)
    # ---- 무핸들 / 형성 중
    no_handle_near: float = 0.05        # 오른쪽 고점이 왼쪽 립 5% 이내 = 컵 완성
    no_handle_zone: float = 0.90        # 무핸들 립 돌파 전 립 부근(종가 ≥ 립 90%)
    no_handle_min_near_bars: int = 3    #   체류 봉 수 하한 (직전 15봉 중)
    no_handle_near_window: int = 15
    forming_min_recovery: float = 0.5   # 형성 중: 컵 깊이의 50% 이상 회복
    forming_max_pullback: float = 0.08  # 형성 중: 오른쪽 고점 대비 8% 이내 (상승 지속)
    forming_min_right_bars: int = 10
    # ---- 돌파 / 단계
    breakout_vol_mult: float = 1.4      # 돌파 거래량 50일 평균 대비 +40% (미달 = 미확인 돌파)
    max_breakout_age: int = 15          # 이보다 오래된 돌파는 '지난 패턴'
    resume_max_bars: int = 10           # 핸들 돌파 후 이 기간 내 고점에서 시작한 새 핸들은 같은 컵의 핸들로 인정
    near_pct: float = 0.05
    buy_range: float = 0.05
    breakout_window: int = 5
    fail_pct: float = 0.03
    stop_max_pct: float = 0.08          # 손절 상한: 피벗 −8%


# ---------------------------------------------------------------- 보조 함수
def _tick(p: float) -> float:
    """KRX 호가 단위 (2023 개편 기준)."""
    for lim, t in ((2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50), (200_000, 100), (500_000, 500)):
        if p < lim:
            return float(t)
    return 1_000.0


def _clip01(x: float) -> float:
    return 0.0 if not np.isfinite(x) else float(min(1.0, max(0.0, x)))


def _num(x, nd: int = 4):
    """metrics 용: NaN/None → None, 그 외 반올림 float."""
    if x is None:
        return None
    x = float(x)
    return round(x, nd) if np.isfinite(x) else None


def _pct(x) -> str:
    return f"{x:.0%}" if x is not None and np.isfinite(x) else "n/a"


def _prep(ctx: StockContext):
    df = ctx.df
    px = df[["high", "low", "close"]]
    if px.isna().to_numpy().any():
        px = px.ffill().bfill()
    H = px["high"].to_numpy(dtype=float)
    L = px["low"].to_numpy(dtype=float)
    C = px["close"].to_numpy(dtype=float)
    if not (np.isfinite(H).all() and np.isfinite(L).all() and np.isfinite(C).all()) or (C <= 0).any():
        return None
    H = np.maximum(H, C)
    L = np.minimum(L, C)
    V = np.nan_to_num(ctx.vol.to_numpy(dtype=float), nan=0.0)
    return H, L, C, V


def _lip_candidates(H: np.ndarray, lo: int, hi: int, lw: int, rw: int) -> np.ndarray:
    """[lo, hi] 구간의 스윙 고점: 직전 lw 봉보다 높고 직후 rw 봉 이상."""
    if hi < lo:
        return np.empty(0, dtype=int)
    idx = np.arange(lo, hi + 1)
    pad_l = np.concatenate([np.full(lw, -np.inf), H])
    lmax = sliding_window_view(pad_l, lw)[idx].max(axis=1)           # H[a-lw:a]
    pad_r = np.concatenate([H, np.full(rw, -np.inf)])[1:]
    rmax = sliding_window_view(pad_r, rw)[idx].max(axis=1)           # H[a+1:a+1+rw]
    ok = (H[idx] > lmax) & (H[idx] >= rmax)
    return idx[ok]


def _max_move(x: np.ndarray, w: int, up: bool) -> tuple[float, float]:
    """x 안에서 어떤 봉 이후 w봉 이내 최대 상승폭(up) 또는 최대 하락폭 → (폭, 출발 가격)."""
    if len(x) < 2:
        return 0.0, float(x[0]) if len(x) else 0.0
    w = max(1, min(w, len(x) - 1))
    fill = -np.inf if up else np.inf
    win = sliding_window_view(np.concatenate([x[1:], np.full(w - 1, fill)]), w)
    mv = win.max(axis=1) - x[:-1] if up else x[:-1] - win.min(axis=1)
    i = int(np.argmax(mv))
    return float(max(0.0, mv[i])), float(x[i])


def _shape(C: np.ndarray, a: int, b: int, top: float, cfg: CupHandleConfig) -> dict:
    """U자형 지표 (종가): 하단 1/3 체류 비율, 바닥 중심 기준 좌우 측면 비율, 2차 적합 R²,
    오른쪽 급등폭·왼쪽 급락폭(w봉 이내, 컵 범위 대비), W자 중간 반등(컵 범위 대비)."""
    seg = C[a:b + 1]
    n = len(seg)
    low_c = float(seg.min())
    out = {"bottom_frac": 0.0, "left_frac": 0.0, "right_frac": 0.0, "r2": float("nan"), "convex": False,
           "thrust_r": 1.0, "thrust_pct": 1.0, "spike_r": 1.0, "drop_l": 1.0, "w_rally": 1.0, "win": 0}
    if n < 5 or not top > low_c:
        return out
    rng = top - low_c
    zone = low_c + rng * cfg.bottom_zone
    inz = np.flatnonzero(seg <= zone)
    out["bottom_frac"] = len(inz) / n
    center = (inz[0] + inz[-1]) / 2.0
    out["left_frac"] = center / (n - 1)
    out["right_frac"] = 1.0 - out["left_frac"]
    x = np.linspace(-1.0, 1.0, n)
    coef = np.polyfit(x, seg, 2)
    fit = np.polyval(coef, x)
    ss_tot = float(((seg - seg.mean()) ** 2).sum())
    out["r2"] = 1.0 - float(((seg - fit) ** 2).sum()) / ss_tot if ss_tot > 0 else float("nan")
    out["convex"] = bool(coef[0] > 0)
    # 급등/급락: 컵 저점 이후 w봉 이내 최대 상승폭 (립 위 돌파분은 제외하도록 top 에서 자름), 왼쪽은 최대 하락폭
    w = max(cfg.thrust_min_bars, int(round(cfg.thrust_win_frac * (n - 1))))
    mc = int(np.argmin(seg))
    out["win"] = w
    right = np.minimum(seg[mc:], top)
    mv, p0 = _max_move(right, w, True)
    out["thrust_r"], out["thrust_pct"] = mv / rng, (mv / p0 if p0 > 0 else 0.0)
    out["spike_r"] = _max_move(right, cfg.spike_bars, True)[0] / rng
    out["drop_l"] = _max_move(seg[:mc + 1], w, False)[0] / rng
    # W자: 3봉 평활 종가로 바닥 하단 25% 첫 방문~마지막 방문 사이 최고점 (하루짜리 급락·급등 잡음 제거)
    k = np.ones(cfg.w_smooth_bars)
    sm = np.convolve(seg, k, "same") / np.convolve(np.ones(n), k, "same")
    lo_s = float(sm.min())
    rng_s = top - lo_s
    if rng_s > 0:
        dz = np.flatnonzero(sm <= lo_s + rng_s * cfg.w_zone)
        out["w_rally"] = (float(sm[dz[0]:dz[-1] + 1].max()) - lo_s) / rng_s
    return out


def _ud_ratio(C: np.ndarray, V: np.ndarray, s: int, e: int) -> float:
    """[s, e] 구간 상승일 거래량 합 / 하락일 거래량 합."""
    s = max(1, s)
    if e - s < 2:
        return float("nan")
    d = C[s:e + 1] - C[s - 1:e]
    v = V[s:e + 1]
    up, dn = float(v[d > 0].sum()), float(v[d < 0].sum())
    return up / dn if dn > 0 else float("nan")


def _index_drawdown(ctx: StockContext, s: int, e: int) -> float | None:
    """컵 기간 [s, e] 동안 소속 지수의 최대 낙폭 (고점 대비). 지수 없으면 None."""
    idx = ctx.index_df
    if idx is None or "close" not in idx or idx.empty:
        return None
    key = ("cup_handle_idx",)
    if key not in ctx._cache:
        ctx._cache[key] = idx["close"].reindex(ctx.df.index).ffill().to_numpy(dtype=float)
    ic = ctx._cache[key][max(0, s):e + 1]
    ic = ic[np.isfinite(ic)]
    if len(ic) < 5:
        return None
    return float(np.max(1.0 - ic / np.maximum.accumulate(ic)))


# ---------------------------------------------------------------- 후보 하나 평가
def _evaluate_lip(ctx: StockContext, cfg: CupHandleConfig, arr, a: int, allow: np.ndarray, poke_tol: np.ndarray):
    """왼쪽 립 a 에서 시작하는 최근 구조. 성공 시 dict, 실패 시 (진척도, 사유)."""
    H, L, C, V = arr
    T = len(C) - 1
    n = T + 1
    lip = float(H[a])
    if not lip > 0:
        return 0, "립 가격 비정상"
    close_ref = float(C[max(0, a - 1):a + 2].max())
    if lip > close_ref * (1 + cfg.lip_max_wick):
        return 1, f"립이 긴 윗꼬리 스파이크 (고가가 주변 종가보다 {lip / close_ref - 1:.0%} 높음)"
    lim = lip * (1 + cfg.right_lip_max_over)
    over = np.flatnonzero(H[a + 1:] > lim)
    e = a + 1 + int(over[0]) if over.size else n          # 립 +5% 를 처음 넘은 봉 (구조 종료)
    if e < T - cfg.max_breakout_age:
        return 1, f"립 +{cfg.right_lip_max_over:.0%} 상향 이탈({ctx.date(e)}) 후 {T - e}봉 경과 — 지난 구조"
    if e - a < cfg.min_cup_bars:
        return 1, f"립 이후 {e - a}봉 만에 립 상향 이탈 — 컵 기간 부족"
    end = min(e, T)
    m = a + 1 + int(np.argmin(L[a + 1:end + 1]))
    low = float(L[m])
    if m > a + 1 and float(H[a + 1:m].max()) > lip:
        return 1, "컵 좌측에 립보다 높은 고점 존재"
    depth = 1.0 - low / lip
    if depth < cfg.min_depth:
        return 2, f"컵 깊이 {depth:.1%} < {cfg.min_depth:.0%}"
    if depth > cfg.hard_max_depth:
        return 2, f"컵 깊이 {depth:.1%} > {cfg.hard_max_depth:.0%}"
    if m >= end:
        return 2, "컵 저점 형성 중 (오른쪽 미형성)"
    p0 = max(0, a - cfg.prior_lookback)
    if a - p0 < cfg.prior_min_bars:
        return 2, f"왼쪽 립 이전 이력 부족 ({a - p0}봉 < {cfg.prior_min_bars}봉)"
    # 립 = 상승의 꼭지: 직전 120봉 안에 립보다 5% 넘게 높은 종가가 있으면 조정 중 되돌림 고점
    q0 = max(0, a - cfg.lip_peak_lookback)
    peak_c = float(C[q0:a].max())
    if lip < peak_c * (1 - cfg.lip_peak_tol):
        iq = q0 + int(np.argmax(C[q0:a]))
        return 3, (f"왼쪽 립이 {ctx.date(iq)} 고점(종가 {peak_c:,.0f}) 대비 {1 - lip / peak_c:.0%} 아래 — "
                   f"조정 중 되돌림 고점(베이스는 더 높은 고점에서 시작)")
    prior_high = float(H[p0:a].max())
    if lip < prior_high * (1 - cfg.lip_max_below_high):
        return 3, f"왼쪽 립이 직전 {a - p0}봉 고점 대비 {1 - lip / prior_high:.0%} 아래 — 하락 추세 중 반등 고점"
    # 선행 상승: 립보다 높았던 마지막 종가 이후의 저점에서 측정 (상승이 립에서 끝나야 함)
    above = np.flatnonzero(C[p0:a] > lip)
    s0 = p0 + int(above[-1]) + 1 if above.size else p0
    pl_i = s0 + int(np.argmin(L[s0:a]))
    prior_low = float(L[pl_i])
    prior_adv = lip / prior_low - 1.0 if prior_low > 0 else float("nan")
    if not prior_adv >= cfg.prior_advance_min:
        src = f" (립보다 높았던 {ctx.date(s0 - 1)} 이후 저점 기준)" if above.size else ""
        return 3, f"선행 상승 {prior_adv:.0%} < {cfg.prior_advance_min:.0%}{src}"

    # ---- 컵 저점 이후 전진 스캔: 핸들 돌파 / 무핸들 돌파 사건 기록
    mid = low + (lip - low) * cfg.handle_min_position
    rl_min = lip * cfg.right_lip_min
    nh_lvl = lip * cfg.no_handle_zone
    hmin, hmax = cfg.handle_min_bars, cfg.handle_max_bars
    Cl = C[m + 1:end + 1].tolist()
    Hl = H[m + 1:end + 1].tolist()
    Ll = L[m + 1:end + 1].tolist()
    Al = allow[m + 1:end + 1].tolist()
    Pl = poke_tol[m + 1:end + 1].tolist()
    rm, rb, hl, ra = -np.inf, -1, np.inf, cfg.handle_max_depth   # 피벗(오른쪽 립 고가)·시작봉·핸들 저점·허용 깊이
    pk_n, pk_hi = 0, 0.0                                          # 핸들 중 장중 피벗 상회 횟수·최고가
    ev = ev_rej = None
    for k, c in enumerate(Cl):
        j = m + 1 + k
        in_handle = (rb >= 0 and hmin <= j - 1 - rb <= hmax and rm >= rl_min and hl >= mid
                     and hl >= rm * (1 - ra))                 # 이 봉 직전까지 유효 핸들 진행 중
        if in_handle and c > rm:
            ev = (V_HANDLE, j, rb, rm, hl, pk_n, pk_hi)
        if ev is None and c > lip and not (in_handle and c <= rm):   # 핸들 피벗 아래 립 위 종가는 돌파 아님
            zc = C[max(m + 1, j - cfg.no_handle_near_window):j]     # 립 아래 립 부근(90~100%) 종가만 —
            nb = int(((zc >= nh_lvl) & (zc <= lip)).sum())          # 수직 돌파 후 립 위 버티기는 불인정
            if nb >= cfg.no_handle_min_near_bars:
                ev = (V_NO_HANDLE, j, rb, rm, hl, 0, 0.0)
            elif ev_rej is None:
                ev_rej = (j, nb)
        h, lo_k = Hl[k], Ll[k]
        if h > rm:
            # 찌르기(종가 ≤ 피벗, 장중만 상회): 유효 핸들 진행 중이고 핸들이 이미 3% 이상 눌린 뒤
            # max(2%, 1 ATR) 이내 → 핸들·피벗 유지. 그 외(눌림 전 신고가·횡보 중 고점 경신)는 새 오른쪽 립.
            # 동가(= 피벗) 재시험은 h > rm 이 아니므로 애초에 핸들을 끊지 않는다.
            hl2 = min(hl, lo_k)
            if (c <= rm and hmin <= j - rb <= hmax and rm >= rl_min and hl2 >= mid and hl2 >= rm * (1 - ra)
                    and hl <= rm * (1 - cfg.poke_min_pullback) and h <= rm * (1 + Pl[k])):
                hl, pk_n, pk_hi = hl2, pk_n + 1, max(pk_hi, h)
            else:
                rm, rb, hl, ra, pk_n, pk_hi = h, j, np.inf, Al[k], 0, 0.0
        elif lo_k < hl:
            hl = lo_k

    stopped = e <= T
    hlen = T - rb
    pend_ok = (not stopped and rb >= 0 and hmin <= hlen <= hmax and rm >= rl_min and hl >= mid
               and hl >= rm * (1 - ra))
    if pend_ok and ev is not None and ev[0] == V_HANDLE:
        # 핸들 돌파 이후 새 핸들: 돌파 직후(≤10봉) 고점에서 시작하고 피벗을 지켜야 인정
        # (피벗 −3% 아래로 되밀렸으면 '돌파 실패'가 우선). 무핸들 돌파 뒤 핸들은 항상 우선.
        pend_ok = rb - ev[1] <= cfg.resume_max_bars and float(C[ev[1]:T + 1].min()) >= ev[3] * (1 - cfg.fail_pct)
    s: dict
    if pend_ok:
        s = dict(variant=V_HANDLE, b=rb, pivot=rm, right_lip=rm, h_end=T, hl=hl, bo=None, pokes=pk_n, poke_hi=pk_hi)
    elif ev is not None:
        kind, j, rbe, rme, hle, pkn, pkh = ev
        if T - j > cfg.max_breakout_age:
            return 5, f"돌파({ctx.date(j)}) 후 {T - j}봉 경과 — 지난 구조"
        if kind == V_HANDLE:
            s = dict(variant=V_HANDLE, b=rbe, pivot=rme, right_lip=rme, h_end=j - 1, hl=hle, bo=j,
                     pokes=pkn, poke_hi=pkh)
        else:
            s = dict(variant=V_NO_HANDLE, b=j, pivot=lip, right_lip=float(H[m + 1:max(j, m + 2)].max()),
                     h_end=j - 1, hl=None, bo=j, pokes=0, poke_hi=0.0)
    elif ev_rej is not None:
        return 4, (f"립 위 종가({ctx.date(ev_rej[0])}) 직전 {cfg.no_handle_near_window}봉 중 립 "
                   f"{cfg.no_handle_zone:.0%}~100% 구간 체류 {ev_rej[1]}봉 < {cfg.no_handle_min_near_bars}봉 — "
                   f"수직 돌파(컵 미완성)")
    elif stopped:
        return 4, "립 상향 이탈했으나 유효한 핸들/립 돌파 종가 없음"
    elif rb < 0:
        return 4, "오른쪽 미형성"
    elif rm >= lip * (1 - cfg.no_handle_near):
        if hlen < hmin and hl >= mid and hl >= rm * (1 - ra):
            s = dict(variant=V_NO_HANDLE, b=rb, pivot=lip, right_lip=rm, h_end=T, hl=None, bo=None,
                     pokes=0, poke_hi=0.0)
        elif hlen < hmin:
            return 4, f"오른쪽 립 직후 {1 - hl / rm:.1%} 급락 — 핸들 허용폭 초과"
        elif hlen > hmax:
            return 4, f"오른쪽 립 이후 {hlen}봉 — 핸들 기간 과다(>{hmax}봉)"
        else:
            hd = 1 - hl / rm
            return 4, (f"핸들 조건 미달 (깊이 {hd:.1%}, 저점 위치 {(hl - low) / (lip - low):.0%}, "
                       f"오른쪽 립 {rm / lip:.0%})")
    else:
        rec = (C[T] - low) / (lip - low)
        if rec < cfg.forming_min_recovery:
            return 4, f"오른쪽 회복 {rec:.0%} < {cfg.forming_min_recovery:.0%} (컵 형성 초기)"
        if C[T] < rm * (1 - cfg.forming_max_pullback):
            return 4, f"오른쪽 고점 대비 {1 - C[T] / rm:.1%} 조정 — 상승 정체"
        if T - m < cfg.forming_min_right_bars or hlen > hmax:
            return 4, "오른쪽 상승 구간 부족/정체"
        s = dict(variant=V_FORMING, b=T, pivot=lip, right_lip=rm, h_end=T, hl=None, bo=None, pokes=0, poke_hi=0.0)

    # ---- 공통 검증: 기간, U자형(V·L·W 배제), 깊은 컵
    b = s["b"]
    cup_days = b - a
    if cup_days < cfg.min_cup_bars:
        return 5, f"컵 기간 {cup_days}봉 < {cfg.min_cup_bars}봉"
    if cup_days > cfg.max_cup_bars:
        return 5, f"컵 기간 {cup_days}봉 > {cfg.max_cup_bars}봉"
    top = lip if s["variant"] == V_FORMING else min(lip, s["right_lip"])
    sh = _shape(C, a, b, top, cfg)
    if sh["bottom_frac"] < cfg.min_bottom_frac:
        return 6, f"V자형 — 하단 1/3 체류 {sh['bottom_frac']:.0%} < {cfg.min_bottom_frac:.0%}"
    side_min = sh["left_frac"] if s["variant"] == V_FORMING else min(sh["left_frac"], sh["right_frac"])
    if side_min < cfg.min_side_frac:
        return 6, f"한쪽 측면 과소 (좌 {sh['left_frac']:.0%} / 우 {sh['right_frac']:.0%})"
    if not sh["r2"] >= cfg.min_quad_r2 or not sh["convex"]:
        return 6, f"둥근 컵 아님 — 2차 적합 R² {sh['r2']:.2f} < {cfg.min_quad_r2:.2f} (횡보 박스/지그재그)"
    if sh["spike_r"] > cfg.max_right_spike:
        return 6, (f"오른쪽 스파이크(V/L자) — {cfg.spike_bars}봉 만에 컵 범위의 {sh['spike_r']:.0%} 상승 "
                   f"> {cfg.max_right_spike:.0%} (바닥 뒤 수직 상승)")
    if sh["thrust_r"] > cfg.max_right_thrust or (sh["thrust_r"] > cfg.steep_right_thrust
                                                  and sh["thrust_pct"] > cfg.steep_right_pct):
        return 6, (f"오른쪽 급등(V/L자) — {sh['win']}봉 만에 컵 범위의 {sh['thrust_r']:.0%} "
                   f"(+{sh['thrust_pct']:.0%}) 상승 (바닥 뒤 수직 상승)")
    if sh["w_rally"] > cfg.max_w_rally:
        return 6, (f"W자(쌍바닥) — 바닥 구간 중간 반등이 컵 범위의 {sh['w_rally']:.0%} > {cfg.max_w_rally:.0%}"
                   f" (double_bottom 패턴으로 판정)")
    close_depth = 1.0 - float(C[a:b + 1].min()) / close_ref
    if close_depth < cfg.min_close_depth:
        return 6, f"종가 기준 깊이 {close_depth:.1%} < {cfg.min_close_depth:.0%} — 꼬리 저점에 의한 착시(횡보)"
    idx_dd = None
    if depth > cfg.max_depth:
        idx_dd = _index_drawdown(ctx, a - 20, b)
        if cfg.deep_needs_correction and idx_dd is not None and idx_dd < cfg.market_corr_dd:
            return 6, f"깊은 컵 {depth:.0%} 인데 시장 조정 없음 (지수 낙폭 {idx_dd:.0%})"
    s.update(a=a, m=m, lip=lip, low=low, depth=depth, cup_days=cup_days, prior_adv=prior_adv,
             prior_low_i=pl_i, shape=sh, side_min=side_min, idx_dd=idx_dd, close_depth=close_depth)
    return s


# ---------------------------------------------------------------- 점수·결과
def _finalize(ctx: StockContext, cfg: CupHandleConfig, arr, s: dict) -> PatternResult:
    H, L, C, V = arr
    T = len(C) - 1
    res = PatternResult(name=NAME, label=LABEL, detected=True)
    var, a, m, b = s["variant"], s["a"], s["m"], s["b"]
    lip, low, pivot, depth = s["lip"], s["low"], s["pivot"], s["depth"]
    sh = s["shape"]
    rr = s["right_lip"] / lip

    # ---- 단계 (돌파는 거래량 1.4배 이상만 인정 — 미달이면 '미확인 돌파')
    unconf = None                                     # 거래량 미달로 인정되지 않은 피벗 위 종가 봉
    if var == V_FORMING:
        stage, bo = FORMING, None
    else:
        base_end = s["h_end"] if s["bo"] is not None else T
        stage, bo = classify_stage(ctx, pivot, base_end, cfg.near_pct, cfg.buy_range,
                                   cfg.breakout_window, cfg.fail_pct, breakout_vol_mult=cfg.breakout_vol_mult)
        if bo is None and s["bo"] is not None:
            unconf = s["bo"]                          # breakout_date 는 확인된 돌파만 (미확인은 metrics 에)
            if C[T] > pivot * (1 + cfg.buy_range):    # 거래량 없이 매수 범위를 넘어 상승 → 이격 과다
                stage = EXTENDED
    res.stage = stage
    bo_v = bo if bo is not None else unconf           # 돌파 거래량 평가 봉

    # ---- 거래량 지표
    vavg = ctx.vol_sma(50).to_numpy(dtype=float)
    vavg_prev = np.concatenate([[np.nan], vavg[:-1]])
    ud = _ud_ratio(C, V, m, b)
    h_vol_ratio = h_vs_right = None
    hd = hpos = hl = hl_i = None
    h_days = 0
    above50 = drift_ok = None
    if var == V_HANDLE:
        h_end = s["h_end"]
        h_days = h_end - b
        hl = s["hl"]
        hl_i = b + 1 + int(np.argmin(L[b + 1:h_end + 1]))
        hd = 1 - hl / pivot
        hpos = (hl - low) / (lip - low)
        hv = float(V[b + 1:h_end + 1].mean())
        rv = float(V[m:b + 1].mean())
        h_vol_ratio = hv / vavg[h_end] if np.isfinite(vavg[h_end]) and vavg[h_end] > 0 else float("nan")
        h_vs_right = hv / rv if rv > 0 else float("nan")
        s50 = ctx.sma(50).to_numpy(dtype=float)[hl_i]
        above50 = bool(np.isfinite(s50) and hl >= s50)
        # 하락/횡보 판정: 핸들 종가 기울기(피벗 대비 %/봉) ≤ +0.1%, 저점이 계속 높아지는 쐐기형 아님
        hc = C[b:h_end + 1]
        x = np.arange(len(hc), dtype=float)
        c_slope = float(np.polyfit(x, hc, 1)[0]) / pivot if len(hc) >= 3 else 0.0
        hlows = L[b + 1:h_end + 1]
        xl = np.arange(len(hlows), dtype=float)
        l_slope = float(np.polyfit(xl, hlows, 1)[0]) / pivot if len(hlows) >= 3 else 0.0
        wedge = l_slope > 0.001 and (hl_i - b) <= max(1, h_days // 3)
        drift_ok = c_slope <= 0.001 and not wedge
    bv = bval = None
    if bo_v is not None:
        bv = V[bo_v] / vavg_prev[bo_v] if np.isfinite(vavg_prev[bo_v]) and vavg_prev[bo_v] > 0 else float("nan")
        bval = float(ctx.value.iloc[bo_v])

    # ---- 손절
    stop_pct = pivot * (1 - cfg.stop_max_pct)
    stop = max(hl, stop_pct) if hl is not None else stop_pct
    res.pivot, res.stop = float(pivot), float(stop)

    # ---- 점수
    smooth = min(_clip01((cfg.max_right_thrust - sh["thrust_r"]) / (cfg.max_right_thrust - cfg.soft_right_thrust)),
                 _clip01((cfg.max_right_spike - sh["spike_r"]) / (cfg.max_right_spike - cfg.soft_right_spike)))
    w_fac = 1.0 - 0.5 * _clip01((sh["w_rally"] - cfg.soft_w_rally) / (cfg.max_w_rally - cfg.soft_w_rally))
    u_shape = w_fac * (0.40 * _clip01((sh["bottom_frac"] - 0.20) / 0.25)
                       + 0.20 * _clip01((s["side_min"] - 0.15) / 0.20)
                       + 0.20 * _clip01((sh["r2"] - cfg.min_quad_r2) / 0.40) + 0.20 * smooth)
    left_crash = sh["drop_l"] > cfg.max_left_drop
    if depth <= cfg.max_depth:
        d_pts = 10.0 if 0.15 <= depth <= 0.30 else (7.0 if depth < 0.15 else 8.0)
    else:
        d_pts = 8.0 * _clip01(1 - (depth - cfg.max_depth) / (cfg.hard_max_depth - cfg.max_depth))
    cup_pts = (15 * u_shape + d_pts + 5 * _clip01((rr - cfg.right_lip_min) / (0.97 - cfg.right_lip_min))
               - 3.0 * left_crash)
    if var == V_HANDLE:
        lim_d = cfg.handle_max_depth_volatile if hd > cfg.handle_max_depth else cfg.handle_max_depth
        if hd < 0.03:
            hd_pts = 5.0
        elif hd <= 0.10:
            hd_pts = 8.0
        else:
            hd_pts = 8.0 - 5.0 * _clip01((hd - 0.10) / max(lim_d - 0.10, 1e-9))
        pos_pts = 6.0 if hpos >= cfg.handle_ideal_position else 2.0 + 4.0 * _clip01(
            (hpos - cfg.handle_min_position) / (cfg.handle_ideal_position - cfg.handle_min_position))
        vol_pts = (3.0 * _clip01((1.2 - h_vol_ratio) / 0.5) if h_vol_ratio is not None else 0.0) \
            + (2.0 if h_vs_right is not None and h_vs_right < 1 else 0.0)
        handle_pts = hd_pts + pos_pts + 3.0 * bool(above50) + 3.0 * bool(drift_ok) + vol_pts
    elif var == V_NO_HANDLE:
        handle_pts = 8.0
    else:
        handle_pts = 0.0
    ref = s["h_end"] if s["bo"] is not None else T
    try:
        tt = tt_evaluate(ctx, at=-1 if ref == T else ref)   # at=-1 이어야 최신 RS(rs_rating) 대체 사용
        tt_passed = int(tt["passed"])
    except Exception:  # 이력 부족 등
        tt_passed = 0
    rs = ctx.rs_rating
    rs_pts = 4.0 if rs is None or not np.isfinite(rs) else 8.0 * _clip01((rs - 50) / 40)
    trend_pts = 4 + 4 * _clip01((s["prior_adv"] - 0.30) / 0.70) + 9 * tt_passed / 8 + rs_pts
    big = ctx.cfg.big_value_threshold
    if bo_v is not None:
        bvol_pts = 10.0 * _clip01((bv - 1.0) / 0.5) + (4.0 if bval is not None and bval >= big else 0.0)
    else:
        bvol_pts = 5.0
    volume_pts = 6.0 * _clip01((ud - 0.8) / 0.7) + bvol_pts
    adj = -25.0 if stage == FAILED else (-5.0 if stage == EXTENDED else 0.0)
    raw = cup_pts + handle_pts + trend_pts + volume_pts
    s["base_score"] = raw                              # 단계와 무관한 구조 점수 (같은 돌파봉 후보 비교용)
    res.score = round(float(min(100.0, max(0.0, raw + adj))), 1)

    # ---- 날짜
    res.start_date = ctx.date(a)
    res.end_date = ctx.date(bo if bo is not None else T)
    res.breakout_date = ctx.date(bo) if bo is not None else None

    # ---- metrics
    res.metrics = {
        "variant": var,
        "cup_depth": _num(depth),
        "cup_days": int(s["cup_days"]),
        "left_lip": _num(lip, 2),
        "cup_low": _num(low, 2),
        "right_lip": _num(s["right_lip"], 2),
        "right_lip_ratio": _num(rr),
        "handle_days": int(h_days),
        "handle_depth": _num(hd),
        "handle_position": _num(hpos),
        "handle_pokes": int(s["pokes"]),
        "prior_advance": _num(s["prior_adv"]),
        "u_shape": _num(u_shape, 3),
        "bottom_frac": _num(sh["bottom_frac"], 3),
        "side_balance": _num(s["side_min"], 3),
        "quad_r2": _num(sh["r2"], 3),
        "right_thrust": _num(sh["thrust_r"], 3),
        "right_spike": _num(sh["spike_r"], 3),
        "right_thrust_pct": _num(sh["thrust_pct"], 3),
        "left_drop": _num(sh["drop_l"], 3),
        "w_rally": _num(sh["w_rally"], 3),
        "close_depth": _num(s["close_depth"]),
        "handle_vol_ratio": _num(h_vol_ratio, 3),
        "handle_vs_right_vol": _num(h_vs_right, 3),
        "right_ud_ratio": _num(ud, 3),
        "breakout_vol_ratio": _num(bv, 3),
        "breakout_value_eok": _num(bval / 1e8, 1) if bval is not None else None,
        "bars_since_breakout": int(T - bo) if bo is not None else None,
        "unconfirmed_breakout": ctx.date(unconf) if unconf is not None else None,
        "buy_point": _num(pivot + _tick(pivot), 2),
        "stop_handle_low": _num(hl, 2),
        "stop_8pct": _num(stop_pct, 2),
        "trend_template_passed": tt_passed,
        "index_drawdown": _num(s["idx_dd"]),
        "score_cup": round(cup_pts, 1), "score_handle": round(handle_pts, 1),
        "score_trend": round(trend_pts, 1), "score_volume": round(volume_pts, 1),
    }

    # ---- 사유 / 경고
    ok, ng = res.reasons, res.warnings
    ok.append(f"✔ {_VARIANT_LABEL[var]} — 왼쪽 립 {ctx.date(a)} {lip:,.0f} → 저점 {ctx.date(m)} {low:,.0f}"
              f" → 오른쪽 {s['right_lip']:,.0f} ({rr:.0%})")
    ok.append(f"✔ 선행 상승 +{s['prior_adv']:.0%} ({ctx.date(s['prior_low_i'])} 저점 → 왼쪽 립)")
    ok.append(f"✔ 컵 기간 {s['cup_days']}봉 (약 {s['cup_days'] / 5:.0f}주)")
    if depth <= cfg.max_depth:
        ok.append(f"✔ 컵 깊이 {depth:.1%} (정상 범위 {cfg.min_depth:.0%}~{cfg.max_depth:.0%})")
    else:
        dd_txt = f"지수 낙폭 {s['idx_dd']:.0%}" if s["idx_dd"] is not None else "지수 정보 없음 — 확인 불가"
        ng.append(f"✘ 컵 깊이 {depth:.1%} > {cfg.max_depth:.0%} — 시장 조정기 형성으로 허용({dd_txt}), 감점")
    shape_txt = (f"하단 1/3 체류 {sh['bottom_frac']:.0%}, 좌/우 {sh['left_frac']:.0%}/{sh['right_frac']:.0%}, "
                 f"R² {sh['r2']:.2f}, 오른쪽 {sh['win']}봉 최대 상승 {sh['thrust_r']:.0%}, W 반등 {sh['w_rally']:.0%}")
    (ok if u_shape >= 0.5 else ng).append(("✔ U자형 바닥" if u_shape >= 0.5 else "✘ U자형 약함 (V자에 가까움)")
                                          + f" ({shape_txt})")
    if smooth < 0.5:
        ng.append(f"✘ 오른쪽 급등 — {sh['win']}봉 만에 컵 범위의 {sh['thrust_r']:.0%}, {cfg.spike_bars}봉 만에 "
                  f"{sh['spike_r']:.0%} 상승 (V자 성향·추격 위험), 감점")
    if left_crash:
        ng.append(f"✘ 왼쪽 급락 — {sh['win']}봉 만에 컵 범위의 {sh['drop_l']:.0%} 하락 (V자 성향), 감점")
    if sh["w_rally"] > cfg.soft_w_rally:
        ng.append(f"✘ 바닥 중간 반등 {sh['w_rally']:.0%} (컵 범위 대비) — W자 성향, 감점")
    if var == V_HANDLE:
        ok.append(f"✔ 핸들 {h_days}봉, 깊이 {hd:.1%}, 저점이 컵 범위 {hpos:.0%} 위치")
        if hd > cfg.handle_max_depth:
            ng.append(f"✘ 핸들 깊이 {hd:.1%} > {cfg.handle_max_depth:.0%} (고변동 종목 예외 허용)")
        if hpos < cfg.handle_ideal_position:
            ng.append("✘ 핸들 저점이 컵 상단 1/3 아래 (상단 절반 이내)")
        (ok if above50 else ng).append("✔ 핸들 저점이 50일선 위" if above50 else "✘ 핸들 저점이 50일선 아래")
        (ok if drift_ok else ng).append("✔ 핸들 하락/횡보 (쐐기형 상승 아님)" if drift_ok
                                        else "✘ 핸들이 위로 기움(쐐기형) — 결함")
        if (h_vol_ratio is not None and np.isfinite(h_vol_ratio) and h_vol_ratio < 1
                and h_vs_right is not None and np.isfinite(h_vs_right) and h_vs_right < 1):
            ok.append(f"✔ 핸들 거래량 고갈 (50일 평균의 {h_vol_ratio:.0%}, 오른쪽 상승 구간의 {h_vs_right:.0%})")
        else:
            ng.append(f"✘ 핸들 거래량 고갈 미흡 (50일 평균의 {_pct(h_vol_ratio)}, 오른쪽 상승 구간의 "
                      f"{_pct(h_vs_right)})")
        if s["pokes"]:
            ng.append(f"✘ 핸들 중 장중 피벗 상회 후 되밀림 {s['pokes']}회 (최고 {s['poke_hi']:,.0f}) — "
                      f"피벗 위 대기 매물")
    elif var == V_NO_HANDLE:
        ng.append("✘ 핸들 없음 — 피벗은 왼쪽 립 고가 (핸들형 대비 실패율 높음)")
        if bo_v is None and T - b > 0:
            ok.append(f"✔ 오른쪽 립 이후 {T - b}봉 — 핸들 형성 중일 수 있음")
    else:
        ng.append(f"✘ 컵 형성 중 — 오른쪽이 왼쪽 립의 {rr:.0%} 까지 회복, 핸들/돌파 대기")
    if np.isfinite(ud):
        (ok if ud >= 1 else ng).append((f"✔ 오른쪽 상승 구간 매집 우위" if ud >= 1 else "✘ 오른쪽 상승 구간 매도 우위")
                                       + f" (상승/하락 거래량 {ud:.2f})")
    if bo_v is not None:
        bv_ok = bv is not None and np.isfinite(bv) and bv >= cfg.breakout_vol_mult
        bv_txt = f"{bv:.2f}배" if bv is not None and np.isfinite(bv) else "n/a"
        if bv_ok:
            ok.append(f"✔ 돌파({ctx.date(bo_v)}) 거래량 50일 평균의 {bv_txt}")
        else:
            ng.append(f"✘ 돌파({ctx.date(bo_v)}) 거래량 부족: 50일 평균의 {bv_txt} < {cfg.breakout_vol_mult:.2f}배")
        if unconf is not None:
            ng.append(f"✘ 미확인 돌파 — {ctx.date(unconf)} 피벗 위 종가였으나 거래량 미달"
                      + (", 매수 범위 초과로 이격 과다" if stage == EXTENDED else ", 단계 하향(거래량 동반 돌파 대기)"))
        if bval is not None and bval >= big:
            ok.append(f"✔ 돌파일 거래대금 {bval / 1e8:,.0f}억 (≥ {big / 1e8:,.0f}억)")
        if ctx.partial and bo_v == T:
            ng.append("✘ 장중 미완성 봉 기준 돌파 — 거래량은 추정치")
    if stage == FAILED:
        ng.append(f"✘ 돌파 실패 — 종가가 피벗 −{cfg.fail_pct:.0%} 아래로 되밀림")
    elif stage == EXTENDED:
        ng.append(f"✘ 피벗 대비 +{C[T] / pivot - 1:.1%} — 매수 범위(+{cfg.buy_range:.0%}) 초과")
    (ok if tt_passed == 8 else ng).append(f"{'✔' if tt_passed == 8 else '✘'} 트렌드 템플릿 {tt_passed}/8 충족")
    if rs is not None and np.isfinite(rs):
        (ok if rs >= ctx.cfg.rs_min else ng).append(
            f"{'✔' if rs >= ctx.cfg.rs_min else '✘'} RS 레이팅 {rs:.0f}")
    halts = ctx.df.attrs.get("halt_dates") or []
    d0, d1 = ctx.date(a), ctx.date(T)
    hin = [d for d in halts if d0 <= str(d)[:10] <= d1]
    if hin:
        ng.append(f"✘ 패턴 구간 내 거래정지 {len(hin)}일 ({hin[-1]}) — 가격/거래량 왜곡 가능")
    ms = ctx.market_state
    if ms is not None and getattr(ms, "state", None) == "correction":
        ng.append("✘ 시장 조정 국면 — 돌파 성공률 낮음")

    # ---- 주석
    xs = sorted({int(round(x)) for x in np.linspace(a, b, 8)} | {m})
    pts = []
    for x in xs:
        if x == a:
            y = H[a]
        elif x == m:
            y = L[m]
        elif x == b and var != V_FORMING:
            y = H[b] if var == V_HANDLE else s["right_lip"]
        else:
            y = float(C[max(a, x - 2):min(b, x + 2) + 1].mean())
        pts.append((ctx.df.index[x], float(y)))
    ann = [segment(pts, "컵", "#ff6d00")]
    if var == V_HANDLE:
        ann.append(box(ctx.df.index[b], ctx.df.index[s["h_end"]], pivot, hl, "핸들", "#7e57c2"))
    ann.append(hline(pivot, "피벗" if var != V_FORMING else "예상 피벗(왼쪽 립)", "#2962ff"))
    ann.append(hline(stop, "손절", "#d50000", "dotted"))
    if bo is not None:
        ann.append(marker(ctx.df.index[bo], "돌파", "below", "#e91e63", "arrowUp"))
    elif unconf is not None:
        ann.append(marker(ctx.df.index[unconf], "미확인 돌파", "below", "#9e9e9e", "circle"))
    res.annotations = ann
    return res


# ---------------------------------------------------------------- 탐지기
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, CupHandleConfig)
    try:
        return _detect(ctx, cfg)
    except Exception as e:  # 이상 데이터 방어: 절대 예외를 올리지 않음
        res = PatternResult(name=NAME, label=LABEL)
        res.warnings.append(f"✘ 분석 오류로 판정 불가: {type(e).__name__}: {e}")
        return res


def _select(valid: list) -> tuple:
    """유효 구조 중 하나를 결정적으로 선택 (같은 돌파의 피벗이 날마다 바뀌지 않도록).

    1) 같은 컵 저점을 공유하는 후보 → 가장 높은 립(동률이면 이른 립): 베이스는 상승의 꼭지에서 시작.
    2) 같은 돌파봉을 공유하는 후보 → 단계 조정 전 구조 점수(시간 불변) → 높은 립.
    3) 그 외 서로 다른 베이스끼리는 최종 점수 → 높은 립.
    """
    by_m: dict = {}
    for r, s in valid:
        cur = by_m.get(s["m"])
        if cur is None or (s["lip"], -s["a"]) > (cur[1]["lip"], -cur[1]["a"]):
            by_m[s["m"]] = (r, s)
    pool, by_bo = [], {}
    for r, s in by_m.values():
        if s["bo"] is None:
            pool.append((r, s))
            continue
        key = (round(s["base_score"], 6), s["lip"], -s["a"])
        cur = by_bo.get(s["bo"])
        if cur is None or key > cur[0]:
            by_bo[s["bo"]] = (key, r, s)
    pool += [(r, s) for _, r, s in by_bo.values()]
    return max(pool, key=lambda x: (x[0].score, x[1]["lip"], -x[1]["a"]))


def _detect(ctx: StockContext, cfg: CupHandleConfig) -> PatternResult:
    res = PatternResult(name=NAME, label=LABEL)
    n = ctx.n
    if n < cfg.min_history:
        res.warnings.append(f"✘ 이력 부족 ({n}일 < {cfg.min_history}일) — 선행 상승+컵 판정 불가")
        return res
    arr = _prep(ctx)
    if arr is None:
        res.warnings.append("✘ 가격 데이터 비정상 (결측/0 이하) — 판정 불가")
        return res
    H, L, C, V = arr
    T = n - 1
    if float(H[-cfg.search_bars:].max()) <= float(L[-cfg.search_bars:].min()):
        res.warnings.append("✘ 가격 변동 없음 (고가=저가) — 컵 구조 없음")
        return res
    atr = ctx.atr(14).to_numpy(dtype=float)
    atrp = np.where(np.isfinite(atr), atr / C, 0.0)
    allow = np.where(atrp >= cfg.volatile_atr_pct, cfg.handle_max_depth_volatile, cfg.handle_max_depth)
    poke_tol = np.maximum(cfg.poke_max_pct, cfg.poke_max_atr * atrp)
    lo_a = max(cfg.prior_min_bars, T - cfg.search_bars)
    hi_a = T - cfg.min_cup_bars
    cands = _lip_candidates(H, lo_a, hi_a, cfg.lip_left_bars, cfg.lip_right_bars)
    valid = []
    near = (-1, None, "")
    for a in cands[::-1]:                       # 최근 후보부터
        out = _evaluate_lip(ctx, cfg, arr, int(a), allow, poke_tol)
        if isinstance(out, tuple):
            if out[0] > near[0]:
                near = (out[0], int(a), out[1])
            continue
        valid.append((_finalize(ctx, cfg, arr, out), out))
    if valid:
        return _select(valid)[0]
    res.warnings.append(f"✘ 컵 앤 핸들 미탐지 — 최근 {cfg.search_bars}봉 내 왼쪽 립 후보 {len(cands)}개 중 "
                        f"마지막 봉 기준 유효 구조 없음")
    if near[1] is not None:
        res.warnings.append(f"✘ 가장 근접한 후보 (왼쪽 립 {ctx.date(near[1])} {H[near[1]]:,.0f}): {near[2]}")
        res.metrics = {"near_miss_lip": ctx.date(near[1]), "near_miss_level": near[0]}
    return res
