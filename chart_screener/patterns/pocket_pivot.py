"""길 모랄레스 & 크리스 카셰르 포켓 피벗(Pocket Pivot).

기준 (Morales & Kacher, *Trade Like an O'Neil Disciple*):
 1. 상승일: 종가 > 전일 종가, 종가가 당일 범위 상단 (종가 위치 ≥ 40%, 50% 이상 바람직)
 2. 거래량: 당일 거래량 > 직전 10거래일 중 '하락일' 최대 거래량
    (직전 10일에 하락일이 없으면 10일 최대 거래량과 비교 — 더 엄격)
 3. 건설적 위치
    - 상승 추세: 종가 > 50일선 이고, 50일선 상승(10봉 전 대비) 또는 (50일선 > 200일선 & 200일선 상승)
      + (기본) Stage 2 구조: 종가 > 200일선 이고 (50일선 > 200일선 또는 200일선 상승)
        — 200일선 아래 바닥권 '바텀 피싱' 포켓 피벗 제외 (200일선이 없는 신규 상장주는 면제)
    - 10일선 또는 50일선 '근처'에서 출발: 당일 저가 또는 시가가 '전일' 이평선(시가 시점의 선, 신호일 종가
      미포함) ±tol 이내 (tol = 전일 1×ATR%, 2~4% 로 제한), 종가는 그 이평선 위.
      시가가 이평선 근처면 저가가 2×tol 까지 하회(흔들기 후 회복)해도 인정
    - 이격 과다 금지: 전일 종가가 10일선 대비 +5% 이하, 신호일 종가가 50일선 대비 +25% 이하
    - V자 반등 금지: 직전 15봉 안에 종가가 50일선 -7% 아래였으면 제외 (50일선 한참 아래에서 수직 상승)
    - 분산 직후 금지: 직전 10일 안에 신호일 거래량의 3배 넘는 '하단 20% 마감' 봉(장중 반전·투매)이 있으면 제외
      (상승 마감이라 하락일 비교에서 빠지는 대량 반전봉 — 그보다 약한 매물 흔적은 감점)
 4. 신호: 최근 5봉 이내 가장 최근 포켓 피벗. 단계는 다음 순서로 판정
    failed(종가 < 손절가) → extended(종가 > 피벗 +5%)
    → breakout(신호가 마지막 봉·1봉 전이고, 종가가 피벗 -5% 이내이면서 매수가(신호일 종가) -3% 이상 유지)
    → near_pivot(종가 ≥ 피벗 -5%) → forming(피벗 -5% 아래 — 윗꼬리·되밀림, 손절가 위)
    ※ breakout 은 신호 후 2봉뿐이므로 워크포워드 백테스트는 step ≤ 2 이거나 stages 에 near_pivot 을 포함해야
      신호 대부분을 표본으로 잡는다 (step=5, breakout 만이면 약 40%).
 5. 피벗 = 신호일 고가 (매수는 신호일 종가 부근). 손절 = 10일선 포켓 피벗이면 신호일 저가(-1호가),
    50일선 포켓 피벗이면 min(신호일 저가, 50일선 -1%) (모랄레스: 50일선 명확한 이탈 시 매도),
    단 매수가(신호일 종가) 대비 -8% 를 넘지 않도록 제한 (오닐 7~8% 손절 규칙). 손절가는 KRX 호가 단위로 맞춤
    (구조적 손절은 내림, -8% 한도는 올림 — 한도를 넘지 않게).
 6. 매집 근거: 최근 30봉 안의 포켓 피벗 횟수 (거래량 조건만 충족한 '거래량 시그니처' 횟수도 함께 보고)

점수(0~100) = 거래량 강도 25 (하락일 최대 대비 배수) + 50일 평균 대비 거래량 10 + 종가 위치 10
            + 이평선 근접도 10 + 추세·RS 25 (50일선 상승 5, 50>200 & 종가>200 5, RS 10, 52주 고점 -15% 이내 5)
            + 매집 15 (30봉 포켓 피벗 횟수 10, 50일 상승/하락 거래량비 5) + 이격 적음 5
            - 후속 흐름 (failed -20, extended -5)
            - 매물 흔적 5~15 (직전 10일 안에 신호일보다 거래량이 큰 하단 30% 마감 봉 — 상승일이라도 장중 반전·분산.
              신호일 대비 거래량 배수가 클수록 가중: 1배 -5 → 3배 -15)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .base import BREAKOUT, EXTENDED, FAILED, FORMING, NEAR_PIVOT, PatternResult, StockContext, box, hline, marker, \
    register, segment

NAME, LABEL = "pocket_pivot", "포켓 피벗"


@dataclass
class PocketPivotConfig:
    lookback_bars: int = 5              # 최근 N봉 이내 신호 탐색
    breakout_bars: int = 2              # 신호가 최근 2봉(마지막 봉·1봉 전)이고 매수 범위 유지면 breakout
    down_vol_window: int = 10           # 모랄레스: 직전 10일 하락일 최대 거래량
    min_close_pos: float = 0.40         # 종가 위치 하한 (일중 범위 하단 마감은 제외)
    good_close_pos: float = 0.50        # 상단 절반 마감 권장
    sma50_rising_bars: int = 10         # 50일선 상승 판정 (10봉 전 대비)
    sma200_rising_bars: int = 20
    near_atr_mult: float = 1.0          # 이평선 근접 허용폭 = 전일 1×ATR% (2~4%) — '이평선에서 출발'
    near_pct_min: float = 0.02
    near_pct_max: float = 0.04
    undercut_mult: float = 2.0          # 시가가 이평선 근처일 때 저가 하회 허용폭 = 2×tol
    ext_max: float = 0.05               # 전일 종가가 10일선 +5% 초과면 이격 과다
    max_above_50: float = 0.25          # 신호일 종가가 50일선 +25% 초과면 이격 과다 (클라이맥스성 급등 제외)
    require_stage2: bool = True         # 종가 > 200일선 & (50>200 또는 200일선 상승) — 바닥권 포켓 피벗 제외
    failed_penalty: float = 20.0        # 후속 흐름 감점
    extended_penalty: float = 5.0
    supply_close_pos: float = 0.30      # 직전 10일 중 신호일보다 거래량 큰 봉이 범위 하단 30% 마감이면 매물 경고
    supply_penalty: float = 5.0         # 매물 흔적 기본 감점 (거래량 = 신호일 1배)
    supply_penalty_max: float = 15.0    # 신호일 거래량의 supply_exclude_mult 배에서 최대 감점
    supply_exclude_mult: float = 3.0    # 직전 10일 안에 신호일 거래량 3배 초과 & 하단 20% 마감 봉 → 분산 직후, 제외
    supply_exclude_close_pos: float = 0.20
    entry_hold_pct: float = 0.03        # breakout 단계 유지 조건: 종가 ≥ 매수가(신호일 종가) -3%
    v_lookback: int = 15                # V자 반등 판정 구간
    v_depth: float = 0.07               # 그 구간 종가가 50일선 -7% 아래였으면 V자 반등
    count_window: int = 30              # 매집 근거: 최근 30봉 포켓 피벗 횟수
    buy_range: float = 0.05             # 피벗 +5% 초과 → extended
    near_pct: float = 0.05              # 피벗 -5% 이내 → near_pivot, 그 아래(손절 위) → forming
    stop_ma_buffer: float = 0.01        # 50일선 손절 버퍼
    stop_max_pct: float = 0.08          # 손절 최대폭 (매수가 = 신호일 종가 대비)
    min_history: int = 80               # 50일선 + 기울기 + 비교 구간
    rs_warn: float = 70.0
    rs_min: float | None = None         # 지정 시 RS 레이팅 하한(하드 필터). 기본은 점수·경고에만 반영


# ---------------------------------------------------------------- 유틸
def _tick(price: float) -> float:
    """KRX 호가 단위 (2023-01 개편)."""
    for lim, t in ((2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50), (200_000, 100), (500_000, 500)):
        if price < lim:
            return float(t)
    return 1000.0


def _floor_tick(p: float) -> float:
    """호가 단위로 내림 (구조적 손절가: 저가·이평선 아래)."""
    t = _tick(p)
    return float(math.floor(p / t + 1e-9) * t)


def _ceil_tick(p: float) -> float:
    """호가 단위로 올림 (최대 손실 한도 손절가: 한도를 넘지 않게)."""
    t = _tick(p)
    return float(math.ceil(p / t - 1e-9) * t)


def _clip01(x: float) -> float:
    return float(min(1.0, max(0.0, x))) if x == x else 0.0


def _shift(x: np.ndarray, k: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if k < len(x):
        out[k:] = x[:len(x) - k]
    return out


def _prev_window(x: np.ndarray, w: int, fn) -> np.ndarray:
    """out[s] = fn(x[s-w:s]) (당일 제외 직전 w봉). s < w 는 NaN."""
    out = np.full(len(x), np.nan)
    if len(x) > w:
        out[w:] = fn(sliding_window_view(x, w)[:-1], axis=1)
    return out


def _arrays(ctx: StockContext):
    """결측·비정상 가격을 보정한 (O, H, L, C, V). 보정 불가면 None."""
    df = ctx.df
    cols, dirty = [], False
    for k in ("open", "high", "low", "close"):
        a = df[k].to_numpy(dtype=float, copy=True)
        bad = ~np.isfinite(a) | (a <= 0)
        if bad.any():
            dirty = True
            a[bad] = np.nan
        cols.append(a)
    if dirty:
        import pandas as pd
        fr = pd.DataFrame(np.column_stack(cols)).ffill().bfill()
        if fr.isna().any().any():
            return None
        cols = [fr[i].to_numpy() for i in range(4)]
    O, H, L, C = cols
    H = np.maximum(H, np.maximum(O, C))
    L = np.minimum(L, np.minimum(O, C))
    V = ctx.vol.to_numpy(dtype=float, copy=True)
    V[~np.isfinite(V) | (V < 0)] = 0.0
    return O, H, L, C, V, dirty


def _sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.concatenate([[0.0], x]))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def _atr(H, L, C, n: int = 14) -> np.ndarray:
    prev = _shift(C, 1)
    tr = np.nanmax(np.column_stack([H - L, np.abs(H - prev), np.abs(L - prev)]), axis=1)
    out = np.full(len(C), np.nan)
    if len(C) >= n:
        out[n - 1] = tr[:n].mean()
        a = 1.0 / n
        for i in range(n, len(C)):   # Wilder 평활 (750봉, 1회) — 충분히 빠름
            out[i] = out[i - 1] + a * (tr[i] - out[i - 1])
    return out


def _compute(ctx: StockContext, cfg: PocketPivotConfig):
    """모든 봉에 대한 포켓 피벗 조건 배열 (벡터화)."""
    arr = _arrays(ctx)
    if arr is None:
        return None
    O, H, L, C, V, dirty = arr
    if dirty:
        s10, s50, s200 = _sma(C, 10), _sma(C, 50), _sma(C, 200)
        atr = _atr(H, L, C, 14)
    else:
        s10, s50, s200 = (ctx.sma(k).to_numpy(dtype=float) for k in (10, 50, 200))
        atr = ctx.atr(14).to_numpy(dtype=float)
    prev_c = _shift(C, 1)
    up = C > prev_c
    down = C < prev_c
    w = cfg.down_vol_window
    dv = np.where(down, V, 0.0)
    max_dv = _prev_window(dv, w, np.max)
    n_down = _prev_window(down.astype(float), w, np.sum)
    max_v = _prev_window(V, w, np.max)
    thr = np.where(n_down > 0, max_dv, max_v)
    with np.errstate(invalid="ignore", divide="ignore"):
        vol_ok = V > thr
        rng = H - L
        close_pos = np.where(rng > 0, (C - L) / np.where(rng > 0, rng, 1.0), np.where(up, 1.0, 0.0))
        # 근접 판정은 시가 시점의 선(전일 이평선·전일 ATR) 기준 — 신호일 대량 상승 종가가 이평선을 끌어올려
        # 허용폭을 넓히지 않도록
        s10p, s50p = _shift(s10, 1), _shift(s50, 1)
        atr_pct = _shift(atr, 1) / prev_c
        tol = np.clip(cfg.near_atr_mult * atr_pct, cfg.near_pct_min, cfg.near_pct_max)
        tol = np.where(np.isfinite(tol), tol, cfg.near_pct_min)

        def near(ma):
            near_low = np.abs(L / ma - 1) <= tol
            near_open = (np.abs(O / ma - 1) <= tol) & (L >= ma * (1 - cfg.undercut_mult * tol))
            return (C > ma) & (near_low | near_open)

        near10, near50 = near(s10p), near(s50p)
        s50_prev = _shift(s50, cfg.sma50_rising_bars)
        s200_prev = _shift(s200, cfg.sma200_rising_bars)
        uptrend = (C > s50) & ((s50 > s50_prev) | ((s50 > s200) & (s200 > s200_prev)))
        if cfg.require_stage2:
            stage2 = ~np.isfinite(s200) | ((C > s200) & ((s50 > s200) | (s200 > s200_prev)))
        else:
            stage2 = np.ones(len(C), dtype=bool)
        ext_prev = prev_c / s10p - 1
        ext50 = C / s50 - 1
        not_ext = (ext_prev <= cfg.ext_max) & (ext50 <= cfg.max_above_50)
        r50 = C / s50 - 1
        v_min = _prev_window(np.where(np.isfinite(r50), r50, 0.0), cfg.v_lookback, np.min)
        not_v = ~(v_min < -cfg.v_depth)
        cpos_ok = close_pos >= cfg.min_close_pos
        # 분산 직후: 직전 10일 안의 하단 20% 마감 대량 봉(신호일 거래량의 3배 초과)
        dump_v = _prev_window(np.where(close_pos < cfg.supply_exclude_close_pos, V, 0.0), w, np.max)
        no_dump = ~(dump_v > cfg.supply_exclude_mult * V)
    sig = up & vol_ok
    pp = sig & cpos_ok & uptrend & stage2 & (near10 | near50) & not_ext & not_v & no_dump
    return dict(O=O, H=H, L=L, C=C, V=V, s10=s10, s50=s50, s200=s200, s10p=s10p, s50p=s50p, s50_prev=s50_prev,
                s200_prev=s200_prev, thr=thr, n_down=n_down, vol_ok=vol_ok, up=up, close_pos=close_pos, tol=tol,
                near10=near10, near50=near50, uptrend=uptrend, stage2=stage2, ext_prev=ext_prev, ext50=ext50,
                not_ext=not_ext, v_min=v_min, not_v=not_v, cpos_ok=cpos_ok, dump_v=dump_v, no_dump=no_dump,
                sig=sig, pp=pp)


def _why_not(d: dict, s: int, cfg: PocketPivotConfig) -> list[str]:
    """거래량 시그니처가 있는 봉 s 가 포켓 피벗이 못 된 이유."""
    out = []
    if not d["cpos_ok"][s]:
        out.append(f"종가 위치 {d['close_pos'][s]:.0%} < {cfg.min_close_pos:.0%} (일중 하단 마감)")
    if not d["uptrend"][s]:
        out.append("상승 추세 아님 (종가 ≤ 50일선 또는 50일선 하락)")
    if not d["stage2"][s]:
        out.append("Stage 2 아님 (종가 ≤ 200일선, 또는 50일선 ≤ 200일선이면서 200일선 하락) — 바닥권 신호")
    if not (d["near10"][s] or d["near50"][s]):
        L, O, s10, s50 = d["L"][s], d["O"][s], d["s10p"][s], d["s50p"][s]
        out.append(f"10일선·50일선(전일) 근처가 아님 (저가-10일선 {L / s10 - 1:+.1%}, 저가-50일선 {L / s50 - 1:+.1%}, "
                   f"시가-10일선 {O / s10 - 1:+.1%}, 허용 ±{d['tol'][s]:.1%})")
    if d["ext_prev"][s] > cfg.ext_max:
        out.append(f"전일 종가가 10일선 대비 {d['ext_prev'][s]:+.1%} — 이격 과다(>{cfg.ext_max:.0%})")
    if d["ext50"][s] > cfg.max_above_50:
        out.append(f"종가가 50일선 대비 {d['ext50'][s]:+.1%} — 이격 과다(>{cfg.max_above_50:.0%})")
    if not d["not_v"][s]:
        out.append(f"직전 {cfg.v_lookback}봉 내 50일선 대비 {d['v_min'][s]:+.1%} — V자 반등")
    if not d["no_dump"][s]:
        out.append(f"직전 {cfg.down_vol_window}일 안에 신호일 거래량의 {d['dump_v'][s] / max(d['V'][s], 1.0):.1f}배인 "
                   f"하단 마감 반전봉 — 분산 직후(건설적 위치 아님)")
    return out


# ---------------------------------------------------------------- 탐지기
@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, PocketPivotConfig)
    res = PatternResult(name=NAME, label=LABEL)
    if ctx.n < cfg.min_history:
        res.warnings.append(f"✘ 이력 부족 ({ctx.n}봉 < {cfg.min_history}봉) — 50일선 기반 판정 불가")
        return res
    d = _compute(ctx, cfg)
    if d is None:
        res.warnings.append("✘ 가격 데이터 결측/비정상 — 판정 불가")
        return res
    last = ctx.n - 1
    lb0 = last - cfg.lookback_bars + 1
    hits = np.flatnonzero(d["pp"][lb0:last + 1])
    if not len(hits):
        res.warnings.append(f"✘ 최근 {cfg.lookback_bars}봉 내 포켓 피벗 없음")
        sig = np.flatnonzero(d["sig"][lb0:last + 1])
        if len(sig):
            s = lb0 + int(sig[-1])
            res.warnings += [f"✘ {ctx.date(s)} 거래량 조건 충족했으나 {w}" for w in _why_not(d, s, cfg)]
        else:
            res.warnings.append(f"✘ 직전 {cfg.down_vol_window}일 하락일 최대 거래량을 넘는 상승일 없음")
        return res

    s = lb0 + int(hits[-1])
    rs = ctx.rs_rating
    if cfg.rs_min is not None and (rs is None or rs != rs or rs < cfg.rs_min):
        res.warnings.append(f"✘ {ctx.date(s)} 포켓 피벗이나 RS 레이팅 {rs if rs is not None else '-'} < {cfg.rs_min:.0f}")
        return res
    O, H, L, C, V = d["O"], d["H"], d["L"], d["C"], d["V"]
    s10, s50, s200 = d["s10"], d["s50"], d["s200"]
    s10p, s50p = d["s10p"], d["s50p"]
    pivot = float(H[s])
    c_last = float(C[last])
    # 기준 이평선(전일 값): 두 곳 모두 근접하면 저가·시가가 더 가까운 쪽
    def ma_dist(ma: float) -> float:   # 저가·시가 중 이평선에 더 가까운 쪽의 거리
        return min(abs(L[s] / ma - 1), abs(O[s] / ma - 1))

    if d["near10"][s] and d["near50"][s]:
        ref = 10 if ma_dist(s10p[s]) <= ma_dist(s50p[s]) else 50
    else:
        ref = 10 if d["near10"][s] else 50
    ma_ref = float(s10p[s] if ref == 10 else s50p[s])
    low_stop = _floor_tick(L[s] - _tick(L[s]))
    if ref == 10:
        stop, stop_basis = low_stop, "신호일 저가"
    else:
        ma_stop = _floor_tick(s50[s] * (1 - cfg.stop_ma_buffer))
        stop, stop_basis = (ma_stop, "50일선 -1%") if ma_stop < low_stop else (low_stop, "신호일 저가")
    entry = float(C[s])
    if stop < entry * (1 - cfg.stop_max_pct):
        stop, stop_basis = _ceil_tick(entry * (1 - cfg.stop_max_pct)), "매수가 -8% 한도"

    # 단계: breakout 은 '신호 직후 + 매수 범위 유지'일 때만 (되밀린 신호는 near_pivot/forming)
    after_low = L[s + 1:last + 1].min() if s < last else np.inf
    fresh = last - s < cfg.breakout_bars
    held = c_last >= pivot * (1 - cfg.near_pct) and c_last >= entry * (1 - cfg.entry_hold_pct)
    if c_last < stop:
        stage = FAILED
    elif c_last > pivot * (1 + cfg.buy_range):
        stage = EXTENDED
    elif fresh and held:
        stage = BREAKOUT
    elif c_last >= pivot * (1 - cfg.near_pct):
        stage = NEAR_PIVOT
    else:
        stage = FORMING

    # 부가 지표
    cw0 = max(0, last - cfg.count_window + 1)
    pp_count = int(d["pp"][cw0:last + 1].sum())
    sig_count = int(d["sig"][cw0:last + 1].sum())
    vavg50 = _sma(V, 50)
    va = vavg50[s - 1] if s >= 1 else np.nan
    vol50 = float(V[s] / va) if np.isfinite(va) and va > 0 else float("nan")
    vol_dn = float(V[s] / d["thr"][s]) if d["thr"][s] > 0 else float("inf")
    u0 = max(1, last - 49)
    chg = C[u0:last + 1] - C[u0 - 1:last]
    vv = V[u0:last + 1]
    dn_sum = vv[chg < 0].sum()
    ud50 = float(vv[chg > 0].sum() / dn_sum) if dn_sum > 0 else float("nan")
    hi52 = float(H[max(0, last - 251):last + 1].max())
    s50_rising = bool(s50[s] > d["s50_prev"][s])
    above200 = bool(np.isfinite(s200[s]) and C[s] > s200[s] and s50[s] > s200[s])
    val_s = float(ctx.value.iloc[s])

    # 점수
    parts = {
        "vol_dn": 8 + 17 * _clip01((vol_dn - 1.0) / 1.0),
        "vol50": 10 * _clip01((vol50 - 0.8) / 1.2) if vol50 == vol50 else 3.0,
        "close_pos": 10 * _clip01((d["close_pos"][s] - cfg.min_close_pos) / (1.0 - cfg.min_close_pos)),
        "near": 10 * _clip01(1 - ma_dist(ma_ref) / d["tol"][s]),
        "s50_rising": 5.0 if s50_rising else 0.0,
        "above200": 5.0 if above200 else 0.0,
        "rs": 10 * _clip01((rs - 50) / 49) if rs is not None and rs == rs else 3.0,
        "near_high": 5.0 if c_last >= hi52 * 0.85 else 0.0,
        "pp_count": min(10.0, 5.0 * (pp_count - 1)),
        "ud": 5 * _clip01((ud50 - 0.9) / 0.6) if ud50 == ud50 else 2.5,
        "ext": 5 * _clip01(1 - max(0.0, d["ext_prev"][s]) / cfg.ext_max),
    }
    w0 = max(0, s - cfg.down_vol_window)
    heavy = np.flatnonzero((V[w0:s] > V[s]) & (d["close_pos"][w0:s] < cfg.supply_close_pos)) + w0
    heavy_k, heavy_mult = None, 0.0
    if len(heavy):
        heavy_k = int(heavy[np.argmax(V[heavy])])
        heavy_mult = float(V[heavy_k] / V[s]) if V[s] > 0 else float("inf")
        sev = _clip01((heavy_mult - 1.0) / max(cfg.supply_exclude_mult - 1.0, 1e-9))
        parts["supply"] = -(cfg.supply_penalty + (cfg.supply_penalty_max - cfg.supply_penalty) * sev)
    if stage == FAILED:
        parts["follow"] = -cfg.failed_penalty
    elif stage == EXTENDED:
        parts["follow"] = -cfg.extended_penalty
    score = float(min(100.0, max(0.0, sum(parts.values()))))

    res.detected = True
    res.score = round(score, 1)
    res.stage = stage
    res.pivot = round(pivot, 2)
    res.stop = round(float(stop), 2)
    res.start_date = ctx.date(max(0, s - cfg.down_vol_window))
    res.end_date = ctx.date(last)
    res.breakout_date = ctx.date(s)
    res.metrics = {
        "signal_date": ctx.date(s), "bars_ago": last - s, "ref_ma": f"{ref}일선",
        "vol_vs_down_max": round(vol_dn, 2) if np.isfinite(vol_dn) else None,
        "vol_vs_avg50": round(vol50, 2) if vol50 == vol50 else None,
        "close_pos": round(float(d["close_pos"][s]), 2),
        "low_vs_ma10_pct": round((L[s] / s10p[s] - 1) * 100, 2),    # 전일 10일선 대비
        "low_vs_ma50_pct": round((L[s] / s50p[s] - 1) * 100, 2),    # 전일 50일선 대비
        "near_tol_pct": round(float(d["tol"][s]) * 100, 2),
        "prev_close_vs_ma10_pct": round(float(d["ext_prev"][s]) * 100, 2),
        "close_vs_ma50_pct": round(float(d["ext50"][s]) * 100, 2),
        "close_vs_ma200_pct": round((C[s] / s200[s] - 1) * 100, 2) if np.isfinite(s200[s]) else None,
        "min_close_vs_ma50_15d_pct": round(float(d["v_min"][s]) * 100, 2),
        "chg_pct": round((C[s] / C[s - 1] - 1) * 100, 2),
        "pp_count_30": pp_count, "vol_signature_count_30": sig_count,
        "ud_ratio_50": round(ud50, 2) if ud50 == ud50 else None,
        "from_52w_high_pct": round((c_last / hi52 - 1) * 100, 1),
        "value_eok": round(val_s / 1e8, 1),
        "dist_to_pivot_pct": round((c_last / pivot - 1) * 100, 2),
        "entry_close": round(entry, 2),
        "stop_basis": stop_basis,
        "rs": rs,
    } | {f"score_{k}": round(v, 1) for k, v in parts.items()}

    # ---- 설명
    R, W = res.reasons, res.warnings
    R.append(f"✔ {ctx.date(s)} 포켓 피벗 ({last - s}봉 전): 상승 {C[s] / C[s - 1] - 1:+.1%}, "
             f"거래량이 직전 {cfg.down_vol_window}일 하락일 최대의 {vol_dn:.1f}배")
    if heavy_k is not None:
        k = heavy_k
        chg_k = f", {C[k] / C[k - 1] - 1:+.1%}" if k >= 1 else ""
        W.append(f"✘ {ctx.date(k)} 신호일 거래량의 {heavy_mult:.1f}배인 하단 마감 봉(종가 위치 "
                 f"{d['close_pos'][k]:.0%}{chg_k}) — 장중 반전 매물 가능성")
    if d["n_down"][s] == 0:
        W.append(f"✘ 직전 {cfg.down_vol_window}일 하락일 없음 — 10일 최대 거래량과 비교함 (단기 과열 가능)")
    cp = d["close_pos"][s]
    if cp >= cfg.good_close_pos:
        R.append(f"✔ 종가가 일중 범위 상단 {cp:.0%} 위치")
    else:
        W.append(f"✘ 종가 위치 {cp:.0%} — 상단 절반 마감이 바람직")
    R.append(f"✔ {ref}일선(전일 {ma_ref:,.0f}) 근처에서 출발 (저가 {L[s] / ma_ref - 1:+.1%}, "
             f"시가 {O[s] / ma_ref - 1:+.1%}, 허용 ±{d['tol'][s]:.1%})")
    R.append(f"✔ 상승 추세: 종가 > 50일선" + (", 50일선 상승 중" if s50_rising else ", 50일선 > 200일선(200일선 상승)"))
    R.append(f"✔ 전일 종가 10일선 대비 {d['ext_prev'][s]:+.1%}, 종가 50일선 대비 {d['ext50'][s]:+.1%} — 이격 과다 아님")
    if vol50 == vol50:
        (R.append(f"✔ 거래량 50일 평균의 {vol50:.1f}배") if vol50 >= 1.0
         else W.append(f"✘ 거래량이 50일 평균의 {vol50:.1f}배 — 평균 이하 (조용한 포켓 피벗)"))
    if val_s >= ctx.cfg.big_value_threshold:
        R.append(f"✔ 신호일 거래대금 {val_s / 1e8:,.0f}억 (≥{ctx.cfg.big_value_threshold / 1e8:,.0f}억)")
    if pp_count >= 2:
        R.append(f"✔ 최근 {cfg.count_window}봉 포켓 피벗 {pp_count}회 — 기관 매집 흔적")
    else:
        W.append(f"✘ 최근 {cfg.count_window}봉 포켓 피벗 {pp_count}회 (거래량 시그니처 {sig_count}회) — 매집 근거 약함")
    if ud50 == ud50:
        (R.append(f"✔ 50일 상승/하락 거래량비 {ud50:.2f}") if ud50 >= 1.0
         else W.append(f"✘ 50일 상승/하락 거래량비 {ud50:.2f} < 1"))
    if not above200:
        W.append("✘ 50일선·종가가 200일선 위 정배열 아님")
    if rs is None or rs != rs:
        W.append("✘ RS 레이팅 없음")
    elif rs >= cfg.rs_warn:
        R.append(f"✔ RS 레이팅 {rs:.0f}")
    else:
        W.append(f"✘ RS 레이팅 {rs:.0f} < {cfg.rs_warn:.0f}")
    if stage == FAILED:
        W.append(f"✘ 종가가 손절가 {stop:,.0f} 아래 — 포켓 피벗 실패")
    elif stage == FORMING:
        W.append(f"✘ 종가가 피벗(신호일 고가) 대비 {c_last / pivot - 1:+.1%} — 매수 범위 아래로 눌림/윗꼬리, "
                 f"손절가 위에서 재정비 중")
    elif stage == EXTENDED:
        W.append(f"✘ 신호일 고가 대비 +{c_last / pivot - 1:.1%} — 추격 매수 구간")
    elif s < last and after_low < L[s] * 1.0:
        W.append("✘ 신호 이후 신호일 저가를 장중 하회")
    if fresh and stage in (NEAR_PIVOT, FORMING):
        W.append(f"✘ 신호 직후지만 종가가 피벗 대비 {c_last / pivot - 1:+.1%}, 매수가(신호일 종가) 대비 "
                 f"{c_last / entry - 1:+.1%} — 돌파 단계 아님 (피벗 -{cfg.near_pct:.0%}·매수가 "
                 f"-{cfg.entry_hold_pct:.0%} 이내 유지 필요)")
    ms = ctx.market_state
    if ms is not None and getattr(ms, "state", None) == "correction":
        W.append(f"✘ 시장 조정 국면 ({ms.name}) — 포켓 피벗 신뢰도 낮음")
    if s == last and ctx.partial:
        W.append("✘ 장중 미완성 봉 — 거래량은 추정치(종가 확정 전)")
    R.append(f"✔ 손절 {stop:,.0f} ({stop_basis}, 매수가(신호일 종가) 대비 -{1 - stop / entry:.1%})")
    halts = ctx.df.attrs.get("halt_dates") or []
    if halts:
        s_d = ctx.date(max(0, s - cfg.down_vol_window))
        inside = [x for x in halts if s_d <= str(x)[:10] <= ctx.date(last)]
        if inside:
            W.append(f"✘ 비교 구간 내 거래정지 {len(inside)}일 ({inside[0]}~) — 거래량 비교 왜곡 가능")
    if s >= 60:
        m_old, m_new = np.median(V[s - 60:s - 10]), np.median(V[s - 10:s])
        if m_old > 0 and m_new > 0 and (m_new / m_old > 5 or m_old / m_new > 5):
            W.append("✘ 거래량 수준 급변(액면분할·병합 가능성) — 거래량 비교 신뢰도 낮음")

    # ---- 차트 주석
    dts = ctx.df.index
    ma = s10 if ref == 10 else s50
    seg0 = max(0, s - 20)
    pts = [(dts[i], float(ma[i])) for i in range(seg0, last + 1) if np.isfinite(ma[i])]
    res.annotations = [
        hline(pivot, f"피벗(신호일 고가) {pivot:,.0f}"),
        hline(stop, f"손절 {stop:,.0f}", "#d50000"),
        box(dts[w0], dts[s - 1], float(H[w0:s].max()), float(L[w0:s].min()), "하락일 거래량 비교 구간", "#9e9e9e"),
        marker(dts[s], "PP", "below", "#00c853", "arrowUp"),
    ]
    if len(pts) >= 2:
        res.annotations.append(segment(pts, f"{ref}일선", "#ff6d00"))
    for i in np.flatnonzero(d["pp"][cw0:last + 1]) + cw0:
        if i != s:
            res.annotations.append(marker(dts[i], "pp", "below", "#69f0ae", "circle"))
    return res
