"""하이 타이트 플래그 (High Tight Flag) — 오닐 / 미너비니 '파워 플레이'.

가장 드물고 강력한 패턴. 완화해서 더 많이 찾으려 하지 말 것 (탐지율 0~0.5% 가 정상).
최근 봉 기준 가장 최근의 깃대+깃발 1개만 평가한다.

판정 기준 (O'Neil *How to Make Money in Stocks*, Minervini *Trade Like a Stock Market Wizard*):
 1. 깃대(pole): 깃대 저점 → 깃대 고점 상승률 +90% 이상 (정석 100~120%), 8주(40거래일) 이내
 2. 깃발(flag): 깃대 고점 이후 1~5주(5~25거래일) 옆걸음 (정석 3~5주), 깃대 고점을 넘는 고가 없음
 3. 깃발 조정폭: 깃대 고점 대비 25% 이내 (정석 10~20%)
 4. 거래량: 깃대 평균 ≥ 직전 50일 평균 × 1.5 (폭증), 깃발 평균 ≤ 깃대 평균 × 0.8 (고갈),
    깃발 마지막 5봉 평균 ≤ 깃대 평균 × 0.8 (후반 거래량 재증가 배제; 0.6 초과면 고갈 미흡 경고).
    깃발 후반이 깃대 이전 50일 평균의 2배를 넘으면 '아직 과열' 경고 (깃대 대비로만 재면 놓치는 부분)
 5. 깃대 품질 (실데이터 보정 결과 추가한 배제 규칙)
    - 깃대 고점이 52주(가용 이력) 최고가
    - 종가 기준 상승률 +75% 이상 (장중 윗꼬리 한 번으로 만든 '가짜 깃대' 배제)
    - 깃대 중간 최대 되돌림 20% 이하 (깃발 깊이에 해당하는 되돌림이 있었다면 단일 깃대가 아님)
    - 깃대 고점이 깃대 이전 60봉 고점 대비 +30% 이상 (급락 후 V자 회복 배제)
 6. 데이터 왜곡 배제: 깃대~현재 구간에 거래정지일(attrs['halt_dates'] 또는 거래량 0 봉)이 있거나 일간 등락이
    ±30% 가격제한폭을 넘으면 액면분할·병합 등 수정주가 오류 가능성 → 탐지하지 않음
피벗 = 깃발 최고가(= 깃대 고점) + 1호가, 손절 = max(깃발 저점, 피벗 -8%)
돌파 = 깃발 종료 후 종가가 피벗을 처음 넘은 봉 (거래량 50일 평균 1.4배 미만이면 경고)

점수(0~100) = 깃대 상승률 25 + 깃대 속도 10 + 깃발 깊이 20 + 깃발 기간 10
              + 깃발 거래량 감소 15(깃발 평균 8 + 후반 5봉/깃대 4 + 후반 5봉/깃대 이전 평균 3)
              + 깃발 후반 종가 타이트니스 5 + RS 5 + 실행 10(돌파 시 돌파 거래량, 미돌파 시 피벗 근접도)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import (BREAKOUT, EXTENDED, FAILED, NEAR_PIVOT, PatternResult, StockContext, box, classify_stage, hline,
                   marker, register, segment)
from .flat_base import finite_ohlc, fmt_dates, halts_between, krx_tick, lin

NAME, LABEL = "high_tight_flag", "하이 타이트 플래그"


@dataclass
class HighTightFlagConfig:
    pole_max_bars: int = 40            # 깃대 저점→고점 8주 이내
    min_pole_gain: float = 0.90        # 깃대 상승률 +90% 이상 (오닐 100~120%, IBD 90% 허용)
    ideal_pole_gain: float = 1.00      # +100% 이상이 정석
    flag_min_bars: int = 5             # 깃발 최소 1주 (정석 3~5주)
    flag_ideal_min_bars: int = 10
    flag_max_bars: int = 25            # 깃발 최대 5주
    max_flag_depth: float = 0.25       # 깃대 고점 대비 조정 25% 이내 (저가주 허용치)
    ideal_flag_depth: float = 0.20     # 정석 10~20%
    max_flag_vol_ratio: float = 0.80   # 깃발 평균 거래량 / 깃대 평균 거래량 상한
    late_flag_bars: int = 5            # 깃발 후반(마지막 1주) 거래량 측정 봉 수
    max_late_flag_vol_ratio: float = 0.80   # 깃발 후반 평균 / 깃대 평균 상한 (후반 재증가 = 고갈 아님)
    ideal_late_flag_vol_ratio: float = 0.60  # 이하면 '고갈' 정석, 초과~상한은 경고
    max_late_vs_pre_pole: float = 2.0  # 깃발 후반 평균 / 깃대 이전 50일 평균 — 넘으면 '아직 과열' 경고
    min_pole_close_gain: float = 0.75  # 종가 기준 깃대 상승률 하한 (장중 윗꼬리로 만든 깃대 배제)
    max_pole_drawdown: float = 0.20    # 깃대 중간 최대 되돌림 (넘으면 단일 급등이 아닌 2단 상승)
    pre_pole_bars: int = 60            # 깃대 이전 고점 측정 구간
    min_net_advance: float = 0.30      # 깃대 고점 ≥ 깃대 이전 60봉 고점 × 1.3 (V자 반등 배제)
    min_pole_vol_mult: float = 1.5     # 깃대 평균 거래량 ≥ 직전 50일 평균 × 1.5 (거래량 폭증)
    high_lookback: int = 252           # 깃대 고점은 이 기간 최고가여야 함
    max_daily_move: float = 0.305      # 가격제한폭(±30%) 초과 일간 변동 → 데이터 왜곡
    breakout_lookback: int = 10        # 최근 10봉 이내 돌파까지 '최근 패턴'으로 인정
    breakout_vol_mult: float = 1.4
    stop_pct: float = 0.08
    near_pct: float = 0.05
    buy_range: float = 0.05
    breakout_window: int = 5
    fail_pct: float = 0.03
    min_history: int = 30


def _find_flag(H: np.ndarray, L: np.ndarray, e: int, cfg: HighTightFlagConfig):
    """e 봉에서 끝나는 깃발과 그 앞의 깃대. 반환: (dict | None, 탈락 사유)."""
    w0 = max(0, e - cfg.flag_max_bars)
    ph = w0 + int(np.argmax(H[w0:e + 1]))          # 깃발 구간 내 최고가 = 깃대 고점 후보
    flag_bars = e - ph
    if flag_bars < cfg.flag_min_bars:
        return None, f"깃대 고점 이후 {flag_bars}봉 — 깃발 미형성 (최소 {cfg.flag_min_bars}봉)"
    pl0 = max(0, ph - cfg.pole_max_bars)
    if ph > pl0 and H[pl0:ph].max() > H[ph]:
        return None, f"최근 {cfg.flag_max_bars}봉 이전에 더 높은 고점 — 깃발이 {cfg.flag_max_bars}봉 초과"
    pl = pl0 + int(np.argmin(L[pl0:ph + 1]))
    gain = H[ph] / L[pl] - 1
    if gain < cfg.min_pole_gain:
        return None, f"깃대 상승률 {gain:+.0%} < {cfg.min_pole_gain:.0%} (최근 {cfg.pole_max_bars}봉 저점 기준)"
    flo = float(L[ph + 1:e + 1].min())
    depth = 1 - flo / H[ph]
    if depth > cfg.max_flag_depth:
        return None, f"깃발 조정폭 {depth:.0%} > {cfg.max_flag_depth:.0%}"
    return {"pl": pl, "ph": ph, "e": e, "gain": float(gain), "pole_bars": ph - pl, "flag_bars": flag_bars,
            "flag_lo": flo, "flag_lo_i": ph + 1 + int(np.argmin(L[ph + 1:e + 1])), "depth": float(depth)}, ""


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, HighTightFlagConfig)
    res = PatternResult(name=NAME, label=LABEL)
    if ctx.n < cfg.min_history:
        res.warnings.append(f"✘ 이력 부족 ({ctx.n}일 < {cfg.min_history}일)")
        return res
    span = cfg.pole_max_bars + cfg.flag_max_bars + cfg.breakout_lookback + cfg.pre_pole_bars + 2
    if not finite_ohlc(ctx, ctx.n - span):
        res.warnings.append("✘ 가격 데이터 이상 (결측·0 이하 값)")
        return res
    try:
        with np.errstate(all="ignore"):
            _analyze(ctx, cfg, res)
    except (ValueError, IndexError, ZeroDivisionError, FloatingPointError) as e:  # 방어: 이상 데이터
        res.detected = False
        res.warnings.append(f"✘ 계산 불가 데이터: {type(e).__name__}")
    return res


def _analyze(ctx: StockContext, cfg: HighTightFlagConfig, res: PatternResult) -> None:
    H = ctx.high.to_numpy(dtype=float)
    L = ctx.low.to_numpy(dtype=float)
    C = ctx.close.to_numpy(dtype=float)
    V = ctx.vol.to_numpy(dtype=float)
    last = ctx.n - 1

    # 1) 가장 최근 깃발: e=last(미돌파) → 최근 돌파 직전 봉 순으로 탐색
    f, why_now = None, ""
    for e in range(last, max(last - cfg.breakout_lookback, cfg.flag_min_bars + 1) - 1, -1):
        b, why = _find_flag(H, L, e, cfg)
        if e == last:
            why_now = why
        if b is None:
            continue
        if e < last and not C[e + 1] > H[b["ph"]] + krx_tick(H[b["ph"]]):
            continue  # e 다음 봉이 돌파가 아니면 e 는 깃발 끝이 아님
        f = b
        break
    if f is None:
        res.warnings.append(f"✘ 하이 타이트 플래그 없음: {why_now or '최근 돌파 직전 깃발도 없음'}")
        return

    pl, ph, e = f["pl"], f["ph"], f["e"]
    pole_hi = float(H[ph])
    pivot = pole_hi + krx_tick(pole_hi)
    stop = max(f["flag_lo"], pivot * (1 - cfg.stop_pct))
    ok = True
    res.reasons.append(f"✔ 깃대 {f['pole_bars']}봉(약 {f['pole_bars'] / 5:.0f}주) 동안 {f['gain']:+.0%} 상승"
                       + (" (100% 이상 정석)" if f["gain"] >= cfg.ideal_pole_gain else ""))
    res.reasons.append(f"✔ 깃발 {f['flag_bars']}봉, 조정폭 {f['depth']:.1%} ≤ {cfg.max_flag_depth:.0%}")
    if f["flag_bars"] < cfg.flag_ideal_min_bars:
        res.warnings.append(f"✘ 깃발 {f['flag_bars']}봉 — 정석(3~5주)보다 짧음")
    if f["depth"] > cfg.ideal_flag_depth:
        res.warnings.append(f"✘ 깃발 조정폭 {f['depth']:.0%} — 정석(20% 이내)보다 깊음")

    # 2) 데이터 왜곡 (분할·병합 등) 배제
    halts = halts_between(ctx, pl, last)
    if halts:
        ok = False
        res.warnings.append(f"✘ 깃대·깃발 구간에 거래정지 {fmt_dates(halts)} — 액면분할 등 수정주가 왜곡 가능, 제외")
    if pl >= 1:
        moves = np.abs(C[pl:last + 1] / C[pl - 1:last] - 1)
        big = float(np.nanmax(moves)) if moves.size else 0.0
        if big > cfg.max_daily_move:
            ok = False
            res.warnings.append(f"✘ 일간 변동 {big:.0%} — 가격제한폭(±30%) 초과, 수정주가 왜곡 의심, 제외")

    # 3) 깃대 품질: 신고가 · 종가 기준 상승 · 단일 급등 · 직전 고점 대비 순상승 · 거래량 폭증
    h0 = max(0, ph - cfg.high_lookback)
    prev_hi = float(np.nanmax(H[h0:ph])) if ph > h0 else 0.0
    if prev_hi > pole_hi:
        ok = False
        res.warnings.append(f"✘ 깃대 고점이 {cfg.high_lookback}일 최고가 아님 ({prev_hi:,.0f} > {pole_hi:,.0f})")
    else:
        res.reasons.append("✔ 깃대 고점이 52주(가용 이력) 신고가")
    close_gain = C[pl:ph + 1].max() / C[max(0, ph - cfg.pole_max_bars):ph + 1].min() - 1
    if close_gain >= cfg.min_pole_close_gain:
        res.reasons.append(f"✔ 종가 기준 깃대 상승률 {close_gain:+.0%}")
    else:
        ok = False
        res.warnings.append(f"✘ 종가 기준 깃대 상승률 {close_gain:+.0%} < {cfg.min_pole_close_gain:.0%} — 윗꼬리로 만든 깃대")
    # 깃대 중간 최대 되돌림: 깃대 저점 봉 자체의 장중 폭은 제외 (저점 봉 종가부터 누적 고점)
    run_hi = np.maximum.accumulate(np.r_[C[pl], H[pl + 1:ph + 1]])
    pole_dd = float(np.max(1 - np.r_[C[pl], L[pl + 1:ph + 1]] / run_hi))
    if pole_dd <= cfg.max_pole_drawdown:
        res.reasons.append(f"✔ 깃대 중간 최대 되돌림 {pole_dd:.0%} (단일 급등)")
    else:
        ok = False
        res.warnings.append(f"✘ 깃대 중간 되돌림 {pole_dd:.0%} > {cfg.max_pole_drawdown:.0%} — 단일 급등이 아닌 2단 상승")
    pre_hi = H[max(0, pl - cfg.pre_pole_bars):pl]
    net_adv = pole_hi / pre_hi.max() - 1 if pre_hi.size else np.inf
    if net_adv >= cfg.min_net_advance:
        res.reasons.append(f"✔ 깃대 고점이 깃대 이전 {cfg.pre_pole_bars}봉 고점 대비 {net_adv:+.0%}" if pre_hi.size
                           else "✔ 신규 상장 — 깃대 이전 고점 없음")
    else:
        ok = False
        res.warnings.append(f"✘ 깃대 이전 {cfg.pre_pole_bars}봉 고점 대비 {net_adv:+.0%} (기준 +{cfg.min_net_advance:.0%})"
                            " — 급락 후 회복(V자 반등)에 가까움")

    # 4) 거래량: 깃대 폭증, 깃발 고갈
    pole_v = float(V[pl:ph + 1].mean())
    flag_v = float(V[ph + 1:e + 1].mean())
    flag_vol_ratio = flag_v / pole_v if pole_v > 0 else np.nan
    late = V[max(ph + 1, e - cfg.late_flag_bars + 1):e + 1]
    late_vs_pole = float(late.mean()) / pole_v if pole_v > 0 and late.size else np.nan
    vavg = ctx.vol_sma(50).to_numpy(dtype=float)
    pre_avg = vavg[pl - 1] if pl >= 1 and np.isfinite(vavg[pl - 1]) and vavg[pl - 1] > 0 else np.nan
    pole_vol_mult = pole_v / pre_avg if np.isfinite(pre_avg) else np.nan
    late_vs_pre = float(late.mean()) / pre_avg if np.isfinite(pre_avg) and late.size else np.nan
    if not np.isfinite(pole_vol_mult):
        res.warnings.append("✘ 깃대 이전 50일 거래량 이력 부족 — 깃대 거래량 폭증 여부 확인 불가")
    elif pole_vol_mult >= cfg.min_pole_vol_mult:
        res.reasons.append(f"✔ 깃대 구간 거래량 직전 50일 평균의 {pole_vol_mult:.1f}배 (폭증)")
    else:
        ok = False
        res.warnings.append(f"✘ 깃대 구간 거래량 직전 50일 평균의 {pole_vol_mult:.1f}배 (기준 {cfg.min_pole_vol_mult}배)")
    if np.isfinite(flag_vol_ratio) and flag_vol_ratio <= cfg.max_flag_vol_ratio:
        res.reasons.append(f"✔ 깃발 거래량 깃대 대비 {flag_vol_ratio:.2f}배 (고갈)")
    else:
        ok = False
        res.warnings.append(f"✘ 깃발 거래량 깃대 대비 {flag_vol_ratio:.2f}배 (기준 {cfg.max_flag_vol_ratio}배 이하)")
    if not np.isfinite(late_vs_pole) or late_vs_pole > cfg.max_late_flag_vol_ratio:
        ok = False
        res.warnings.append(f"✘ 깃발 마지막 {len(late)}봉 거래량 깃대 대비 {late_vs_pole:.2f}배"
                            f" (기준 {cfg.max_late_flag_vol_ratio}배 이하) — 깃발 후반 거래량 재증가, 고갈 아님")
    elif late_vs_pole > cfg.ideal_late_flag_vol_ratio:
        res.warnings.append(f"✘ 깃발 마지막 {len(late)}봉 거래량 깃대 대비 {late_vs_pole:.2f}배"
                            f" — 고갈 미흡 ({cfg.ideal_late_flag_vol_ratio}배 이하가 바람직)")
    else:
        res.reasons.append(f"✔ 깃발 마지막 {len(late)}봉 거래량 깃대 대비 {late_vs_pole:.2f}배 (후반 고갈)")
    if np.isfinite(late_vs_pre) and late_vs_pre > cfg.max_late_vs_pre_pole:
        res.warnings.append(f"✘ 깃발 후반 거래량이 깃대 이전 50일 평균의 {late_vs_pre:.1f}배 — 아직 거래 과열")

    # 5) 단계 판정 · 돌파 거래량
    stage, bo = classify_stage(ctx, pivot, e, cfg.near_pct, cfg.buy_range, cfg.breakout_window, cfg.fail_pct)
    bo_vol = float(V[bo] / vavg[bo - 1]) if bo is not None and vavg[bo - 1] > 0 else np.nan
    if bo is not None:
        if bo_vol >= cfg.breakout_vol_mult:
            res.reasons.append(f"✔ 돌파 거래량 50일 평균 대비 {bo_vol:.1f}배")
        else:
            res.warnings.append(f"✘ 돌파 거래량 부족 {bo_vol:.1f}배 (기준 {cfg.breakout_vol_mult}배)")
        if ctx.partial and bo == last:
            res.warnings.append("✘ 돌파봉이 장중 미완성 봉 — 종가·거래량 추정치")
    dist = C[last] / pivot - 1
    if stage == FAILED:
        res.warnings.append("✘ 돌파 후 피벗 아래로 되밀림 (돌파 실패)")
    elif stage == EXTENDED:
        res.warnings.append(f"✘ 피벗 대비 {dist:+.1%} — 매수 범위(+{cfg.buy_range:.0%}) 초과")
    tail = C[max(ph + 1, e - 4):e + 1]
    tail_tight = float((tail.max() - tail.min()) / pole_hi) if tail.size else np.nan

    # 6) 점수
    rs = ctx.rs_rating if ctx.rs_rating is not None else 0.0
    if ctx.rs_rating_hist is not None and len(ctx.rs_rating_hist):
        rs_s = ctx.rs_rating_hist.loc[:ctx.df.index[e]]
        rs = float(rs_s.iloc[-1]) if len(rs_s) else rs
    s_gain = lin(f["gain"], cfg.min_pole_gain, 1.5, 10, 25)
    s_speed = lin(f["pole_bars"], 20, cfg.pole_max_bars, 10, 4)
    s_depth = lin(f["depth"], 0.10, cfg.max_flag_depth, 20, 4)
    s_dur = 10.0 if cfg.flag_ideal_min_bars <= f["flag_bars"] <= cfg.flag_max_bars else 5.0
    s_vol = (lin(flag_vol_ratio, 0.4, 1.0, 8, 0) + lin(late_vs_pole, 0.3, cfg.max_late_flag_vol_ratio, 4, 0)
             + lin(late_vs_pre, 1.0, 3.0, 3, 0))
    s_tight = lin(tail_tight, 0.04, 0.12, 5, 0)
    s_rs = lin(rs, 70, 99, 0, 5)
    s_act = lin(bo_vol, 1.0, 2.0, 0, 10) if bo is not None else lin(dist, -0.15, 0.0, 0, 10)
    res.score = float(round(min(100.0, s_gain + s_speed + s_depth + s_dur + s_vol + s_tight + s_rs + s_act), 1))

    res.detected = ok
    res.stage = stage
    res.pivot = float(pivot)
    res.stop = float(stop)
    res.start_date = ctx.date(pl)
    res.end_date = ctx.date(e)
    res.breakout_date = ctx.date(bo) if bo is not None else None
    res.metrics = {
        "pole_gain_pct": round(f["gain"] * 100, 1), "pole_bars": f["pole_bars"],
        "pole_close_gain_pct": round(close_gain * 100, 1), "net_advance_pct": round(net_adv * 100, 1),
        "pole_max_dd_pct": round(pole_dd * 100, 1),
        "flag_bars": f["flag_bars"], "flag_depth_pct": round(f["depth"] * 100, 2),
        "flag_vol_ratio": round(flag_vol_ratio, 2) if np.isfinite(flag_vol_ratio) else None,
        "late_flag_vol_ratio": round(late_vs_pole, 2) if np.isfinite(late_vs_pole) else None,
        "late_flag_vs_pre_pole": round(late_vs_pre, 2) if np.isfinite(late_vs_pre) else None,
        "pole_vol_mult": round(pole_vol_mult, 2) if np.isfinite(pole_vol_mult) else None,
        "breakout_vol_ratio": round(bo_vol, 2) if np.isfinite(bo_vol) else None,
        "dist_to_pivot_pct": round(dist * 100, 2), "flag_tail_tight_pct": round(tail_tight * 100, 2),
        "pole_low": float(L[pl]), "pole_high": pole_hi, "flag_low": f["flag_lo"], "rs": rs or None,
        "score_parts": (f"gain{s_gain:.0f}/speed{s_speed:.0f}/depth{s_depth:.0f}/dur{s_dur:.0f}/vol{s_vol:.0f}"
                        f"/tight{s_tight:.0f}/rs{s_rs:.0f}/act{s_act:.0f}"),
    }

    # 7) 차트 주석
    idx = ctx.df.index
    res.annotations = [
        hline(pivot, f"피벗 {pivot:,.0f}"),
        hline(stop, f"손절 {stop:,.0f}", color="#d50000"),
        segment([(idx[pl], L[pl]), (idx[ph], pole_hi)], f"깃대 {f['gain']:+.0%} / {f['pole_bars']}봉", color="#2e7d32"),
        box(idx[ph], idx[e], pole_hi, f["flag_lo"], f"깃발 {f['flag_bars']}봉 -{f['depth']:.0%}"),
    ]
    if bo is not None:
        res.annotations.append(marker(idx[bo], f"돌파 {bo_vol:.1f}x", position="below", shape="arrowUp",
                                      color="#00c853" if stage in (BREAKOUT, EXTENDED, NEAR_PIVOT) else "#e91e63"))
