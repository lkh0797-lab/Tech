"""플랫 베이스 (Flat Base) — 윌리엄 오닐.

컵앤핸들 등 1차 베이스를 돌파해 20% 이상 오른 뒤, 신고가 부근에서 좁게 옆걸음하는
'2차 베이스(베이스 온 베이스)'. 최근 봉 기준 가장 최근의 베이스 1개만 평가한다.

판정 기준 (O'Neil, *How to Make Money in Stocks*):
 1. 좌측 고점: 베이스는 뚜렷한 고점(직전 25거래일 중 최고가)에서 시작하며, 이후 장중 고가가
    좌측 고점을 3% 넘게 웃돌지 않음 (윗꼬리 급등이 상단을 바꾸면 베이스 구조 불명확)
 2. 신고가권: 좌측 고점이 직전 52주 최고가 대비 -3% 이내. -3~-8% 이면 그 사이 조정이 15% 이하일 때만 인정
    (직전 고점에서 깊게 빠졌다 회복한 '큰 컵의 우측·손잡이'는 플랫 베이스가 아님), -8% 미만은 제외
 3. 기간: 좌측 고점부터 최소 5주(25거래일). 좌측 고점 이전에도 베이스 가격대에 머물며 이미 상단(-3% 이내)을
    찍은 적이 있으면 그 봉부터를 박스권으로 보고, 박스권 길이가 16주(80거래일)를 넘으면 장기 박스권으로 제외
    (좌측 고점으로 올라오는 상승 구간은 횡보가 아니므로 박스권에 넣지 않음)
 4. 깊이: 베이스 최고가 → 최저가 조정폭 15% 이하 (10% 이하 우수). 원전은 10~15%이며 KOSDAQ 의 높은 변동성을
    감안해 상한 15% 채택. 5% 미만이거나 일평균 변동폭 1% 미만이면 공개매수·합병 등 '가격 고정' 의심으로 제외.
    좌측 고점 직전 50일의 일중 변동폭 중앙값이 1% 미만이어도 제외 (가격 고정 국면 뒤의 횡보 — 선행 상승이 추세가 아님)
 5. 베이스 내부 종가가 그때까지의 베이스 고점(+1호가)을 넘지 않음 (넘는 봉이 곧 돌파)
 6. 선행 상승: 좌측 고점이 직전 120거래일 최저가 대비 +25% 이상 (오닐 20~30%, 직전 피벗이 아닌 저점 기준이라 중간값)
 7. Stage 2: 트렌드 템플릿 8개 중 7개 이상 (베이스 종료 시점 기준)
 8. 거래량 (기준 = 베이스 직전 50일 평균, 대개 선행 상승 구간): 베이스 평균 0.85배 이하면 '감소'.
    1.0배 초과(상승기보다 많은 거래)면 베이스 마지막 2주가 1.0배 이하로 고갈될 때만 인정하고, 아니면 매물 출회로 제외.
    1.2배 초과는 무조건 제외. 0.85배 초과는 모두 감소 미흡 경고(✘)와 점수 감점
 9. 거래정지: 거래량 0 봉(캐시 데이터는 정지일을 O=H=L=C·거래량 0 으로 남김)과 attrs['halt_dates'] 를 정지일로 본다.
    베이스 또는 직전 50일의 10% 초과면 제외, 그 외에는 경고. 거래량 평균은 정지 봉을 빼고 계산
피벗 = 베이스 최고가 + 1호가, 손절 = max(베이스 저점, 피벗 -8%)
돌파 = 베이스 종료 후 종가가 피벗을 처음 넘은 봉. 거래량이 50일 평균의 1.4배 미만이면 경고.
돌파 후 종가가 베이스 저점 아래로 내려가면 패턴 무효.

점수(0~100) = 깊이 20 + 거래량 감소 15(베이스 10 + 우측 2주 5) + 선행 상승 10 + 트렌드 템플릿 15 + RS 10
              + 기간 5 + 우측 종가 타이트니스 10 + 실행 15(돌파 시 돌파 거래량, 미돌파 시 피벗 근접도)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import trend_template as tt
from .base import (BREAKOUT, EXTENDED, FAILED, NEAR_PIVOT, PatternResult, StockContext, box, classify_stage,
                   hline, marker, register, segment)

NAME, LABEL = "flat_base", "플랫 베이스"


@dataclass
class FlatBaseConfig:
    min_bars: int = 25                 # 최소 5주 (오닐: 5주 이상)
    max_bars: int = 80                 # 좌측 고점 이전 박스 포함 최대 16주 (이보다 길면 장기 박스권)
    box_tol: float = 0.02              # 좌측 고점 이전 봉이 베이스 가격대 안이라고 볼 허용 오차
    box_top_tol: float = 0.03          # 좌측 고점 이전 봉이 베이스 상단 -3% 이내면 '이미 상단을 찍은' 박스권 봉
    max_depth: float = 0.15            # 베이스 고점 대비 최대 조정폭 (오닐 10~15%)
    ideal_depth: float = 0.10          # 이 이하면 우수
    min_depth: float = 0.05            # 이보다 얕으면 가격 고정 의심 (실데이터 정상 베이스 5퍼센타일 8.4%)
    min_day_range: float = 0.01        # 베이스 일평균 (고가-저가)/종가 하한 (정상 베이스 최저 1.8%, 가격 고정 0.4%)
    min_pre_day_range: float = 0.01    # 좌측 고점 직전 50일 일중 변동폭 중앙값 하한 (정상 최저 1.35%, 고정 국면 0.3%)
    left_peak_lookback: int = 25       # 좌측 고점은 직전 25봉 중 최고가여야 함 (하락 중 구간 배제)
    max_right_overshoot: float = 0.03  # 이후 장중 고가가 좌측 고점을 3% 넘게 웃돌면 베이스 상단 불명확
    high_lookback: int = 252           # 신고가권 판정 구간 (52주)
    near_high_pct: float = 0.03        # 좌측 고점이 직전 52주 고점 대비 -3% 이내면 신고가권
    max_left_below_high: float = 0.08  # 직전 52주 고점 대비 -8% 미만이면 제외 (-3~-8% 는 중간 조정 ≤ max_depth 일 때만)
    prior_adv_bars: int = 120          # 선행 상승 측정 구간 (약 6개월)
    min_prior_advance: float = 0.25    # 선행 상승 25% 이상 (오닐 20~30%; 저점 기준 측정이라 중간값)
    tt_min_pass: int = 7               # 트렌드 템플릿 8개 중 7개 이상
    max_base_vol_ratio: float = 1.2    # 베이스 평균 거래량 / 베이스 직전 50일 평균 절대 상한
    heavy_base_vol_ratio: float = 1.0  # 초과 시 우측 2주 고갈(≤ max_right_vol_ratio) 필수 — 아니면 매물 출회
    ideal_base_vol_ratio: float = 0.85  # 이하면 '감소' 인정, 초과는 감소 미흡 경고
    max_right_vol_ratio: float = 1.0   # 베이스 마지막 2주 거래량 / 직전 50일 평균 — 넘으면 경고 (위 조건에선 탈락)
    max_halt_frac: float = 0.10        # 베이스·직전 50일 중 거래정지 봉 비율 상한
    right_side_bars: int = 10          # 우측 타이트니스·거래량 측정 구간 (최근 2주)
    breakout_lookback: int = 15        # 최근 15봉 이내 돌파까지 '최근 패턴'으로 인정
    breakout_vol_mult: float = 1.4     # 돌파 거래량 50일 평균 1.4배 이상 (오닐 +40~50%)
    stop_pct: float = 0.08             # 손절 상한: 피벗 -8% (오닐 7~8% 규칙)
    near_pct: float = 0.05
    buy_range: float = 0.05
    breakout_window: int = 5
    fail_pct: float = 0.03
    min_history: int = 220             # 200일선 + 상승 판정에 필요한 최소 이력


# ---------------------------------------------------------------- 공용 헬퍼 (이 트랙의 다른 모듈도 사용)
_TICK_EDGES = np.array([2_000, 5_000, 20_000, 50_000, 200_000, 500_000], dtype=float)
_TICK_SIZES = np.array([1, 5, 10, 50, 100, 500, 1_000], dtype=float)


def krx_tick(price):
    """KRX 호가 단위 (2023 개편, KOSPI·KOSDAQ 공통). 배열도 받는다."""
    p = np.asarray(price, dtype=float)
    t = _TICK_SIZES[np.searchsorted(_TICK_EDGES, p, side="right")]
    return float(t) if t.ndim == 0 else t


def lin(x: float, x0: float, x1: float, y0: float, y1: float) -> float:
    """x0→y0, x1→y1 선형 보간 (구간 밖은 끝값으로 고정)."""
    if not np.isfinite(x):
        return float(min(y0, y1))
    if x1 == x0:
        return float(y1)
    t = min(1.0, max(0.0, (x - x0) / (x1 - x0)))
    return float(y0 + (y1 - y0) * t)


def stage2_eval(ctx: StockContext, i: int) -> dict:
    """i 봉 시점 트렌드 템플릿 평가 (마지막 봉이면 at=-1 로 최신 RS 사용)."""
    return tt.evaluate(ctx, at=-1 if i == ctx.n - 1 else i)


def halt_mask(ctx: StockContext) -> np.ndarray:
    """거래정지(거래 없음)로 보이는 봉: 원시 거래량 0 이하·결측.

    공용 로더는 시가·고가까지 0 인 봉만 제거하므로, 네이버가 O=H=L=C=직전 종가·거래량 0 으로 주는 정지일은
    df 에 남고 attrs['halt_dates'] 에도 없다. 장중 미완성 마지막 봉은 제외."""
    v = ctx.df["volume"].to_numpy(dtype=float)
    m = ~(v > 0)
    if ctx.partial and m.size:
        m[-1] = False
    return m


def halts_between(ctx: StockContext, i0: int, i1: int, mask: np.ndarray | None = None) -> list[str]:
    """[i0, i1] 봉 기간의 거래정지일 (정렬된 'YYYY-MM-DD').

    attrs['halt_dates'](df 에서 제거된 날) + 거래량 0 봉(df 에 남은 정지일)을 합친다."""
    if ctx.n == 0:
        return []
    i0, i1 = max(0, i0), min(ctx.n - 1, i1)
    if i1 < i0:
        return []
    a, b = ctx.date(i0), ctx.date(i1)
    out = {d for d in (ctx.df.attrs.get("halt_dates") or []) if a <= d <= b}
    m = halt_mask(ctx) if mask is None else mask
    z = np.flatnonzero(m[i0:i1 + 1])
    if z.size:
        idx = ctx.df.index[i0 + z]
        out.update(idx.strftime("%Y-%m-%d"))
    return sorted(out)


def fmt_dates(ds: list[str], k: int = 3) -> str:
    """'n일 (d1, d2, d3 등)' 형식."""
    return f"{len(ds)}일 ({', '.join(ds[:k])}{' 등' if len(ds) > k else ''})"


def pos_mean(x: np.ndarray, min_n: int = 1) -> float:
    """거래가 있는 봉(양수)만의 평균 — 거래정지 봉(0)·결측 제외. 유효 봉이 min_n 미만이면 NaN."""
    v = x[x > 0]
    return float(v.mean()) if v.size >= min_n else float("nan")


def finite_ohlc(ctx: StockContext, i0: int) -> bool:
    """i0 이후 OHLC 가 모두 유한한 양수인지."""
    a = ctx.df[["open", "high", "low", "close"]].to_numpy(dtype=float)[max(0, i0):]
    return bool(a.size) and bool(np.all(np.isfinite(a))) and bool(np.all(a > 0))


# ---------------------------------------------------------------- 베이스 탐색
def _find_base(H: np.ndarray, L: np.ndarray, C: np.ndarray, e: int, cfg: FlatBaseConfig):
    """e 봉에서 끝나는 플랫 베이스 (좌측 고점 p ~ e). 반환: (dict | None, 탈락 사유)."""
    lo = max(0, e - cfg.max_bars + 1)
    hs, ls = H[lo:e + 1][::-1], L[lo:e + 1][::-1]
    run_hi, run_lo = np.maximum.accumulate(hs), np.minimum.accumulate(ls)
    bad = np.flatnonzero(run_lo < run_hi * (1 - cfg.max_depth))
    span = int(bad[0]) if bad.size else len(hs)   # e 에서 거슬러 깊이 조건을 만족하는 봉 수
    if span < cfg.min_bars:
        return None, f"최근 {span}봉만 조정폭 {cfg.max_depth:.0%} 이내 (최소 {cfg.min_bars}봉 필요)"
    k0 = e - span + 1
    p = k0 + int(np.argmax(H[k0:e - cfg.min_bars + 2]))
    run = np.maximum.accumulate(H[p:e + 1])
    brk = np.flatnonzero(C[p + 1:e + 1] > run[:-1] + krx_tick(run[:-1]))
    if brk.size:
        g = p + len(run) - 1 - int(np.argmax(H[p:e + 1][::-1]))  # 최근 최고가 위치
        return None, f"고점 갱신(종가 돌파) 후 {e - g + 1}봉 — 새 베이스 형성 중 (최소 {cfg.min_bars}봉)"
    l0 = max(0, p - cfg.left_peak_lookback)
    left = H[l0:p]
    if left.size and left.max() > H[p]:
        j = l0 + int(np.argmax(left))                # 실제 좌측 고점 기준 조정폭으로 사유 안내
        true_depth = 1 - float(L[j:e + 1].min()) / H[j]
        if true_depth > cfg.max_depth:
            return None, (f"좌측 고점 {H[j]:,.0f} 대비 조정폭 {true_depth:.1%} > {cfg.max_depth:.0%}"
                          " — 플랫 베이스로는 깊음")
        return None, "좌측 고점이 하락 중 구간 — 뚜렷한 고점에서 시작한 베이스 아님"
    over = run[-1] / H[p] - 1
    if over > cfg.max_right_overshoot:
        return None, f"좌측 고점 이후 장중 고가가 {over:+.1%} 더 높음 — 베이스 상단 불명확"
    seg_lo = L[p:e + 1]
    base_hi, base_lo = float(run[-1]), float(seg_lo.min())
    # 박스권 길이: 좌측 고점 직전까지 베이스 가격대(± box_tol)에 연속으로 머문 봉 중, 이미 상단 부근까지
    # 올랐던 가장 이른 봉부터 센다 (상단에 닿지 않은 상승 접근 구간은 횡보가 아님)
    j0 = max(0, p - cfg.max_bars)
    hb, lb = H[j0:p][::-1], L[j0:p][::-1]
    out = np.flatnonzero(~((hb <= base_hi * (1 + cfg.box_tol)) & (lb >= base_lo * (1 - cfg.box_tol))))
    run_len = int(out[0]) if out.size else len(hb)
    tops = np.flatnonzero(hb[:run_len] >= base_hi * (1 - cfg.box_top_tol))
    pre_in = int(tops[-1]) + 1 if tops.size else 0
    box_len = e - p + 1 + pre_in
    return {
        "p": p, "e": e, "hi": base_hi, "lo": base_lo, "lo_i": p + int(np.argmin(seg_lo)),
        "depth": 1 - base_lo / base_hi, "bars": e - p + 1, "pre_in": pre_in, "box_len": box_len,
        "capped": box_len > cfg.max_bars, "overshoot": float(over),
    }, ""


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, FlatBaseConfig)
    res = PatternResult(name=NAME, label=LABEL)
    if ctx.n < cfg.min_history:
        res.warnings.append(f"✘ 이력 부족 ({ctx.n}일 < {cfg.min_history}일) — Stage 2 판정 불가")
        return res
    i_chk = ctx.n - cfg.max_bars - cfg.breakout_lookback - cfg.prior_adv_bars - 30
    if not finite_ohlc(ctx, i_chk):
        res.warnings.append("✘ 가격 데이터 이상 (결측·0 이하 값)")
        return res
    try:
        with np.errstate(all="ignore"):
            _analyze(ctx, cfg, res)
    except (ValueError, IndexError, ZeroDivisionError, FloatingPointError) as e:  # 방어: 이상 데이터
        res.detected = False
        res.warnings.append(f"✘ 계산 불가 데이터: {type(e).__name__}")
    return res


def _analyze(ctx: StockContext, cfg: FlatBaseConfig, res: PatternResult) -> None:
    H = ctx.high.to_numpy(dtype=float)
    L = ctx.low.to_numpy(dtype=float)
    C = ctx.close.to_numpy(dtype=float)
    V = ctx.vol.to_numpy(dtype=float)
    last = ctx.n - 1
    idx = ctx.df.index

    # 1) 가장 최근 베이스: e=last(미돌파) → 최근 돌파 직전 봉 순으로 탐색
    base, why_now = None, ""
    for e in range(last, max(last - cfg.breakout_lookback, cfg.min_bars) - 1, -1):
        b, why = _find_base(H, L, C, e, cfg)
        if e == last:
            why_now = why
        if b is None:
            continue
        if e < last and not C[e + 1] > b["hi"] + krx_tick(b["hi"]):
            continue  # e 다음 봉이 돌파가 아니면 e 는 베이스 끝이 아님
        base = b
        break
    if base is None:
        res.warnings.append(f"✘ 플랫 베이스 없음: {why_now or '최근 돌파 직전 베이스도 없음'}")
        return

    p, e = base["p"], base["e"]
    pivot = base["hi"] + krx_tick(base["hi"])
    stop = max(base["lo"], pivot * (1 - cfg.stop_pct))
    ok = True
    hm = halt_mask(ctx)
    live = ~hm[p:e + 1]                                   # 거래가 있었던 베이스 봉

    # 2) 선행 상승
    a0 = max(0, p - cfg.prior_adv_bars)
    adv_lo_i = a0 + int(np.argmin(L[a0:p + 1]))
    prior_adv = H[p] / L[adv_lo_i] - 1
    if prior_adv >= cfg.min_prior_advance:
        res.reasons.append(f"✔ 선행 상승 {prior_adv:+.0%} (기준 {cfg.min_prior_advance:.0%} 이상)")
    else:
        ok = False
        res.warnings.append(f"✘ 선행 상승 부족 {prior_adv:+.0%} (기준 {cfg.min_prior_advance:.0%} 이상)")

    # 3) 기하 조건: 기간·깊이(탐색 단계에서 보장) + 최소 변동성 + 박스권 길이
    weeks = base["bars"] / 5
    res.reasons.append(f"✔ 횡보 {base['bars']}봉(약 {weeks:.0f}주) ≥ {cfg.min_bars}봉")
    res.reasons.append(f"✔ 조정폭 {base['depth']:.1%} ≤ {cfg.max_depth:.0%}"
                       + (" (10% 이하 우수)" if base["depth"] <= cfg.ideal_depth else ""))
    day_rng = (H[p:e + 1] - L[p:e + 1]) / C[p:e + 1]
    day_range = float(day_rng[live].mean()) if live.any() else 0.0
    if base["depth"] < cfg.min_depth or day_range < cfg.min_day_range:
        ok = False
        res.warnings.append(f"✘ 조정폭 {base['depth']:.1%}·일평균 변동폭 {day_range:.2%} — 비정상적으로 좁은 횡보"
                            f" (기준 {cfg.min_depth:.0%}·{cfg.min_day_range:.0%} 이상, 공개매수·합병 등 가격 고정 의심)")
    pre = slice(max(0, p - 50), p)
    pre_rng = ((H[pre] - L[pre]) / C[pre])[~hm[pre]]
    pre_day_range = float(np.median(pre_rng)) if pre_rng.size else np.nan
    if np.isfinite(pre_day_range) and pre_day_range < cfg.min_pre_day_range:
        ok = False
        res.warnings.append(f"✘ 좌측 고점 직전 50일 일중 변동폭 중앙값 {pre_day_range:.2%} < {cfg.min_pre_day_range:.0%}"
                            " — 가격 고정 국면(공개매수·합병 등) 뒤의 횡보, 선행 상승이 추세가 아님")
    if base["capped"]:
        ok = False
        res.warnings.append(f"✘ 베이스 가격대 횡보가 {base['box_len']}봉 지속 (좌측 고점 이전 {base['pre_in']}봉 포함,"
                            f" 기준 {cfg.max_bars}봉 이하) — 플랫 베이스가 아닌 장기 박스권")

    # 4) 신고가권: 좌측 고점 vs 직전 52주 고점
    w0 = max(0, p - cfg.high_lookback)
    if p > w0:
        ph_i = w0 + int(np.argmax(H[w0:p]))
        prior_hi = float(H[ph_i])
    else:
        ph_i, prior_hi = p, float(H[p])
    lp_vs_hi = H[p] / prior_hi - 1
    mid_dd = 1 - float(L[ph_i:p + 1].min()) / prior_hi if prior_hi > H[p] else 0.0
    if lp_vs_hi >= -cfg.near_high_pct:
        res.reasons.append(f"✔ 좌측 고점이 신고가권 (직전 52주 고점 대비 {lp_vs_hi:+.1%})")
    elif lp_vs_hi < -cfg.max_left_below_high:
        ok = False
        res.warnings.append(f"✘ 좌측 고점이 직전 52주 고점({ctx.date(ph_i)}, {prior_hi:,.0f}) 대비 {lp_vs_hi:+.1%}"
                            f" (기준 -{cfg.max_left_below_high:.0%} 이내) — 신고가권 베이스 아님")
    elif mid_dd > cfg.max_depth:
        ok = False
        res.warnings.append(f"✘ 직전 고점({ctx.date(ph_i)}, {prior_hi:,.0f}) 이후 -{mid_dd:.0%} 조정 뒤 회복 중"
                            f" (좌측 고점 {lp_vs_hi:+.1%}) — 큰 컵의 우측·손잡이 구간이며 플랫 베이스 아님")
    else:
        res.reasons.append(f"✔ 좌측 고점이 직전 52주 고점 대비 {lp_vs_hi:+.1%}, 중간 조정 -{mid_dd:.0%} (베이스 온 베이스)")

    # 5) Stage 2
    ev = stage2_eval(ctx, e)
    from_hi = base["hi"] / ev["high52"] - 1 if ev["high52"] else np.nan
    if ev["passed"] >= cfg.tt_min_pass:
        res.reasons.append(f"✔ Stage 2 트렌드 템플릿 {ev['passed']}/8")
    else:
        ok = False
        failed = [k for k, v in ev["checks"].items() if not v]
        res.warnings.append(f"✘ Stage 2 미충족 {ev['passed']}/8 (미충족: {', '.join(failed)})")

    # 6) 거래정지 (거래량 0 봉 + attrs['halt_dates'])
    halts = halts_between(ctx, p - 50, last, hm)
    d_p, d_e = ctx.date(p), ctx.date(e)
    n_halt_base = sum(d_p <= d <= d_e for d in halts)
    n_halt_pre = sum(d < d_p for d in halts)
    if n_halt_base > cfg.max_halt_frac * base["bars"] or n_halt_pre > cfg.max_halt_frac * 50:
        ok = False
        res.warnings.append(f"✘ 베이스·직전 50일에 거래정지 {fmt_dates(halts)} — 정지 봉은 가격·거래량 정보가 없어"
                            " 베이스로 볼 수 없음, 제외")
    elif halts:
        res.warnings.append(f"✘ 기간 내 거래정지 {fmt_dates(halts)} — 액면분할 등으로 거래량 비교 왜곡 가능")

    # 7) 거래량: 베이스 중 감소 (거래정지 봉 제외)
    pre_avg = pos_mean(V[max(0, p - 50):p], 10)
    base_vol_ratio = pos_mean(V[p:e + 1]) / pre_avg
    right_vol_ratio = pos_mean(V[max(p, e - cfg.right_side_bars + 1):e + 1]) / pre_avg
    right_dry = bool(np.isfinite(right_vol_ratio) and right_vol_ratio <= cfg.max_right_vol_ratio)
    if not np.isfinite(base_vol_ratio):
        ok = False
        res.warnings.append("✘ 거래량 정보 부족 — 베이스 거래량 감소 확인 불가")
    elif base_vol_ratio > cfg.max_base_vol_ratio:
        ok = False
        res.warnings.append(f"✘ 베이스 거래량 과다 — 직전 50일 대비 {base_vol_ratio:.2f}배"
                            f" (기준 {cfg.max_base_vol_ratio}배 이하) — 상승기보다 많은 거래는 매물 출회")
    elif base_vol_ratio > cfg.heavy_base_vol_ratio and not right_dry:
        ok = False
        res.warnings.append(f"✘ 베이스 거래량 과다 — 직전 50일 대비 {base_vol_ratio:.2f}배, 마지막 2주도"
                            f" {right_vol_ratio:.2f}배로 고갈 없음 — 매물 출회")
    elif base_vol_ratio > cfg.ideal_base_vol_ratio:
        res.warnings.append(f"✘ 베이스 거래량 감소 미흡 — 직전 50일 대비 {base_vol_ratio:.2f}배"
                            f" ({cfg.ideal_base_vol_ratio}배 이하가 바람직"
                            + (f", 마지막 2주 {right_vol_ratio:.2f}배로 고갈)" if right_dry else ")"))
    else:
        res.reasons.append(f"✔ 베이스 거래량 직전 50일 대비 {base_vol_ratio:.2f}배 (감소)")
    if ok and np.isfinite(right_vol_ratio) and not right_dry:
        res.warnings.append(f"✘ 베이스 마지막 2주 거래량이 직전 50일 평균의 {right_vol_ratio:.2f}배 — 우측 거래량 고갈 아님")

    # 8) 단계 판정 · 돌파 거래량
    stage, bo = classify_stage(ctx, pivot, e, cfg.near_pct, cfg.buy_range, cfg.breakout_window, cfg.fail_pct)
    vavg = ctx.vol_sma(50).to_numpy(dtype=float)
    bo_vol = float(V[bo] / vavg[bo - 1]) if bo is not None and vavg[bo - 1] > 0 else np.nan
    if bo is not None:
        if bo_vol >= cfg.breakout_vol_mult:
            res.reasons.append(f"✔ 돌파 거래량 50일 평균 대비 {bo_vol:.1f}배")
        else:
            res.warnings.append(f"✘ 돌파 거래량 부족 {bo_vol:.1f}배 (기준 {cfg.breakout_vol_mult}배) — 신뢰도 낮음")
        if ctx.partial and bo == last:
            res.warnings.append("✘ 돌파봉이 장중 미완성 봉 — 종가·거래량 추정치")
        if float(np.min(C[bo:last + 1])) < base["lo"]:
            ok = False
            res.warnings.append(f"✘ 돌파 후 종가가 베이스 저점 {base['lo']:,.0f} 아래로 마감 — 패턴 무효")
    rt = C[max(p, e - cfg.right_side_bars + 1):e + 1]
    right_tight = float((rt.max() - rt.min()) / base["hi"])
    dist = C[last] / pivot - 1
    if stage == FAILED:
        res.warnings.append("✘ 돌파 후 피벗 아래로 되밀림 (돌파 실패)")
    elif stage == EXTENDED:
        res.warnings.append(f"✘ 피벗 대비 {dist:+.1%} — 매수 범위(+{cfg.buy_range:.0%}) 초과")

    # 9) 점수
    rs = ev["rs"] or 0.0
    s_depth = lin(base["depth"], 0.08, cfg.max_depth, 20, 5)
    s_vol = (lin(base_vol_ratio, 0.6, cfg.heavy_base_vol_ratio, 10, 0)
             + lin(right_vol_ratio, 0.6, 1.2, 5, 0))
    s_adv = lin(prior_adv, cfg.min_prior_advance, 0.60, 3, 10)
    s_tt = 15.0 if ev["passed"] >= 8 else (8.0 if ev["passed"] >= cfg.tt_min_pass else 0.0)
    s_rs = lin(rs, 70, 99, 0, 10)
    s_dur = 5.0 if base["bars"] <= 60 else 3.0
    s_tight = lin(right_tight, 0.03, 0.10, 10, 0)
    if bo is not None:
        s_act = lin(bo_vol, 1.0, 2.0, 0, 15)
    else:
        s_act = lin(dist, -0.10, 0.0, 0, 15)
    res.score = float(round(min(100.0, s_depth + s_vol + s_adv + s_tt + s_rs + s_dur + s_tight + s_act), 1))

    res.detected = ok
    res.stage = stage
    res.pivot = float(pivot)
    res.stop = float(stop)
    res.start_date = ctx.date(p)
    res.end_date = ctx.date(e)
    res.breakout_date = ctx.date(bo) if bo is not None else None
    res.metrics = {
        "base_bars": base["bars"], "base_weeks": round(weeks, 1), "depth_pct": round(base["depth"] * 100, 2),
        "prior_advance_pct": round(prior_adv * 100, 1),
        "base_vol_ratio": round(base_vol_ratio, 2) if np.isfinite(base_vol_ratio) else None,
        "right_vol_ratio": round(right_vol_ratio, 2) if np.isfinite(right_vol_ratio) else None,
        "breakout_vol_ratio": round(bo_vol, 2) if np.isfinite(bo_vol) else None,
        "dist_to_pivot_pct": round(dist * 100, 2), "right_tight_pct": round(right_tight * 100, 2),
        "day_range_pct": round(day_range * 100, 2),
        "pre_day_range_pct": round(pre_day_range * 100, 2) if np.isfinite(pre_day_range) else None,
        "base_high": base["hi"], "base_low": base["lo"], "from_52w_high_pct": round(from_hi * 100, 1),
        "left_peak_vs_prior_high_pct": round(lp_vs_hi * 100, 1), "prior_high_dd_pct": round(mid_dd * 100, 1),
        "right_overshoot_pct": round(base["overshoot"] * 100, 2), "tt_passed": ev["passed"], "rs": ev["rs"],
        "box_bars": base["box_len"], "capped": base["capped"], "halt_days": len(halts),
        "score_parts": (f"depth{s_depth:.0f}/vol{s_vol:.0f}/adv{s_adv:.0f}/tt{s_tt:.0f}/rs{s_rs:.0f}"
                        f"/dur{s_dur:.0f}/tight{s_tight:.0f}/act{s_act:.0f}"),
    }

    # 10) 차트 주석
    res.annotations = [
        hline(pivot, f"피벗 {pivot:,.0f}"),
        hline(stop, f"손절 {stop:,.0f}", color="#d50000"),
        box(idx[p], idx[e], base["hi"], base["lo"], f"플랫 베이스 {weeks:.0f}주 -{base['depth']:.0%}"),
        segment([(idx[adv_lo_i], L[adv_lo_i]), (idx[p], H[p])], f"선행 상승 {prior_adv:+.0%}", color="#2e7d32"),
    ]
    if bo is not None:
        res.annotations.append(marker(idx[bo], f"돌파 {bo_vol:.1f}x", position="below", shape="arrowUp",
                                      color="#00c853" if stage in (BREAKOUT, EXTENDED, NEAR_PIVOT) else "#e91e63"))
