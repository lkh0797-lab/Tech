"""3주 타이트 마감 (Three Weeks Tight, 3WT) — 윌리엄 오닐.

돌파 후 상승한 주도주가 3주 이상 연속으로 주간 종가를 거의 같은 가격에 마감하는 패턴.
기관이 물량을 내놓지 않고 보유한다는 신호로, 추가 매수(피라미딩) 지점으로 쓰인다.

판정 기준 (O'Neil, *How to Make Money in Stocks*):
 1. 주봉 변환: 일봉을 월~일 주 단위로 묶고 각 주의 '마지막 거래일 종가'를 주간 종가로 사용
    - 마지막 주는 금요일 확정 종가(또는 남은 평일이 모두 휴장일)일 때만 '완성 주'로 인정
    - 미완성 주(장중 봉 포함)의 종가는 패턴에 넣지 않고 '이후 움직임(돌파 여부)'으로만 사용
 2. 완성된 주간 종가 3주 이상 연속, 최고/최저 종가 차이 1.5% 이내 (오닐: 약 1% — 1% 이하 우수).
    4~5주 이상 이어지면 더 강한 신호로 평가. 단 8주를 넘게 고정되면 공개매수·합병 등 '가격 고정' 의심으로 제외
 3. 선행 상승: 타이트 구간 첫 주 종가가 직전 13주(65거래일) 최저가 대비 +20% 이상
    (오닐: 돌파 후 20% 이상 오른 뒤 형성 — 26주로 재면 수개월 횡보주도 통과해 13주로 제한)
 4. 고점 부근: 타이트 구간 최고 종가가 직전 26주 최고가 대비 -10% 이내
 5. 장중 변동도 타이트: 첫 주(상승해 들어온 주) 이후 장중 고저폭 12% 이내, 첫 주 포함 전체 고저폭 15% 이내,
    주간 평균 고저폭 10% 이내 (종가만 우연히 모이고 장중 변동이 큰 종목 배제)
 6. 최소 변동성: 타이트 구간 주간 평균 고저폭 2% 이상, 타이트 구간을 포함한 최근 13주 주간 고저폭 중앙값 2% 이상
    (그보다 좁으면 공개매수·합병 등 가격 고정 국면 의심 — 정상 3WT 는 각각 최저 2.6%·3.5%)
 7. 거래량: 타이트 구간 평균 ≤ 직전 50일 평균 × 1.3 (1.0 이하 '감소', 1.0~1.3 경고). 거래정지 봉은 평균에서 제외
 8. 거래정지: 거래량 0 봉(O=H=L=C 로 남은 정지일)·attrs['halt_dates'] 가 타이트 구간이나 직전 13주에 있으면 제외
    (정지 주의 주간 종가는 직전 종가 그대로라 '완벽한 타이트'로 오인됨)
 9. Stage 2: 트렌드 템플릿 8개 중 7개 이상 (타이트 구간 마지막 봉 기준)
10. 가장 최근 패턴만: 타이트 구간이 마지막 완성 주에서 끝나거나, 그 뒤 최대 2주 안에 돌파했거나
    아직 타이트 구간 저점을 종가로 이탈하지 않은 경우
피벗 = 타이트 구간 장중 최고가 + 1호가, 손절 = max(타이트 구간 저가, 피벗 -8%)
돌파 = 타이트 구간 이후 종가가 피벗을 처음 넘은 봉 (거래량 50일 평균 1.4배 미만이면 경고)

점수(0~100) = 주 수 15 + 종가 타이트니스 25 + 장중 폭 10 + 거래량 감소 15 + 선행 상승 10
              + 트렌드 템플릿 10 + RS 5 + 실행 10(돌파 시 돌파 거래량, 미돌파 시 피벗 근접도)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import (BREAKOUT, EXTENDED, FAILED, NEAR_PIVOT, PatternResult, StockContext, box, classify_stage,
                   hline, marker, register, segment)
from .flat_base import finite_ohlc, fmt_dates, halt_mask, halts_between, krx_tick, lin, pos_mean, stage2_eval

NAME, LABEL = "three_weeks_tight", "3주 타이트 마감(3WT)"

# KRX 고정 휴장일 (월-일): 신정, 삼일절, 근로자의 날, 어린이날, 현충일, 광복절, 개천절, 한글날, 성탄절, 연말 휴장
FIXED_HOLIDAYS = frozenset({"01-01", "03-01", "05-01", "05-05", "06-06", "08-15", "10-03", "10-09", "12-25", "12-31"})
# 음력·대체·선거 등 비정기 휴장일 (KOSPI 지수 일봉 결측 평일에서 추출, 2023-09 ~ 2026-10)
KRX_EXTRA_HOLIDAYS = (
    "2023-09-28", "2023-09-29", "2023-10-02", "2023-12-29", "2024-02-09", "2024-02-12", "2024-04-10",
    "2024-05-06", "2024-05-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-01", "2025-01-27",
    "2025-01-28", "2025-01-29", "2025-01-30", "2025-03-03", "2025-05-06", "2025-06-03", "2025-10-06",
    "2025-10-07", "2025-10-08", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-25",
    "2026-06-03", "2026-07-17", "2026-08-17", "2026-09-24", "2026-09-25", "2026-10-05",
)


@dataclass
class ThreeWeeksTightConfig:
    tight_pct: float = 0.015           # 주간 종가 (최고-최저)/최저 상한 (오닐 약 1%, 변동성 감안 1.5%)
    ideal_tight_pct: float = 0.010     # 1% 이하면 정석
    min_weeks: int = 3                 # 최소 3주 연속
    max_weeks: int = 8                 # 이보다 길게 종가가 고정되면 가격 고정(공개매수·합병 등) 의심 → 제외
    max_weeks_after: int = 2           # 타이트 구간 종료 후 허용하는 완성 주 수 (돌파 대기·진행)
    prior_adv_bars: int = 65           # 선행 상승 측정 구간 (13주)
    min_prior_advance: float = 0.20    # 선행 상승 20% 이상 (돌파 후 +20% 상승 뒤 형성)
    high_lookback: int = 130           # 고점 부근 판정 구간 (26주)
    max_below_high: float = 0.10       # 직전 26주 최고가 대비 10% 이내
    max_hold_range: float = 0.12       # 첫 주 이후 구간 장중 고저폭 상한
    max_area_range: float = 0.15       # 첫 주 포함 타이트 구간 장중 고저폭 상한 (플랫 베이스 최대 깊이와 동일)
    max_avg_week_range: float = 0.10   # 주간 평균 고저폭 상한 (실데이터 3WT 90퍼센타일)
    min_avg_week_range: float = 0.02   # 주간 평균 고저폭 하한 — 미만이면 가격 고정 의심 (정상 3WT 5퍼센타일 3.3%)
    regime_weeks: int = 13             # 가격 고정 국면 판정 구간 (타이트 구간 포함 최근 13주)
    min_regime_week_range: float = 0.02  # 그 구간 주간 고저폭 중앙값 하한 (정상 3WT 최저 3.5%, 고정 국면 0.6~1.3%)
    max_vol_ratio: float = 1.3         # 타이트 구간 평균 거래량 / 직전 50일 평균 상한 (1.0 초과는 경고)
    halt_lookback: int = 65            # 타이트 구간 직전 거래정지 확인 구간 (선행 상승 13주)
    tt_min_pass: int = 7               # 트렌드 템플릿 8개 중 7개 이상
    breakout_vol_mult: float = 1.4
    stop_pct: float = 0.08             # 손절 상한: 피벗 -8%
    near_pct: float = 0.05
    buy_range: float = 0.05
    breakout_window: int = 5
    fail_pct: float = 0.03
    min_history: int = 220
    extra_holidays: tuple = KRX_EXTRA_HOLIDAYS


# ---------------------------------------------------------------- 주봉 변환
def weekly_groups(index: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """월요일 시작 주 단위 그룹의 (시작 위치, 끝 위치) 배열."""
    days = index.values.astype("datetime64[D]").astype(np.int64)
    wk = (days + 3) // 7                      # 1970-01-01(목) 기준 → 월요일 시작 주 번호
    starts = np.flatnonzero(np.r_[True, wk[1:] != wk[:-1]])
    ends = np.r_[starts[1:] - 1, len(index) - 1]
    return starts, ends


def last_week_complete(ctx: StockContext, extra_holidays=KRX_EXTRA_HOLIDAYS) -> bool:
    """마지막 주가 완성되었는지: 장중 봉이 아니고, 금요일이거나 같은 주 남은 평일이 모두 휴장일."""
    if ctx.partial or ctx.n == 0:
        return False
    d = ctx.df.index[-1]
    wd = d.weekday()
    if wd >= 4:
        return True
    extra = set(extra_holidays)
    for k in range(1, 5 - wd):
        x = d + pd.Timedelta(days=k)
        if x.strftime("%m-%d") not in FIXED_HOLIDAYS and x.strftime("%Y-%m-%d") not in extra:
            return False
    return True


def _run_back(WC: np.ndarray, j: int, cfg: ThreeWeeksTightConfig) -> tuple[int, float, float]:
    """j 주에서 끝나는 최장 타이트 구간의 시작 주 i 와 종가 최고·최저.

    max_weeks + 1 주까지만 거슬러 본다 (그 이상이면 어차피 '가격 고정'으로 제외)."""
    i, mx, mn = j, WC[j], WC[j]
    while i - 1 >= 0 and j - i + 1 <= cfg.max_weeks:
        c = WC[i - 1]
        mx2, mn2 = max(mx, c), min(mn, c)
        if not mn2 > 0 or (mx2 - mn2) / mn2 > cfg.tight_pct:
            break
        i, mx, mn = i - 1, mx2, mn2
    return i, mx, mn


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, ThreeWeeksTightConfig)
    res = PatternResult(name=NAME, label=LABEL)
    if ctx.n < cfg.min_history:
        res.warnings.append(f"✘ 이력 부족 ({ctx.n}일 < {cfg.min_history}일) — Stage 2 판정 불가")
        return res
    span = max(cfg.prior_adv_bars, cfg.high_lookback) + (cfg.max_weeks + cfg.max_weeks_after + 2) * 5
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


def _analyze(ctx: StockContext, cfg: ThreeWeeksTightConfig, res: PatternResult) -> None:
    H = ctx.high.to_numpy(dtype=float)
    L = ctx.low.to_numpy(dtype=float)
    C = ctx.close.to_numpy(dtype=float)
    V = ctx.vol.to_numpy(dtype=float)
    last = ctx.n - 1
    starts, ends = weekly_groups(ctx.df.index)
    WC = C[ends]
    complete = last_week_complete(ctx, cfg.extra_holidays)
    Wc = len(starts) if complete else len(starts) - 1      # 완성 주 수 (패턴은 완성 주로만 판정)

    # 1) 가장 최근 타이트 구간 탐색 (마지막 완성 주 → 최대 max_weeks_after 주 전)
    found, why_now = None, ""
    for j in range(Wc - 1, max(Wc - 2 - cfg.max_weeks_after, cfg.min_weeks - 2), -1):
        i, mx, mn = _run_back(WC, j, cfg)
        k = j - i + 1
        if k < cfg.min_weeks:
            if j == Wc - 1:
                why_now = f"최근 완성 주 기준 타이트 마감 {k}주 (최소 {cfg.min_weeks}주)"
            continue
        if j < Wc - 1:
            c = WC[j + 1]
            if (max(mx, c) - min(mn, c)) / min(mn, c) <= cfg.tight_pct:
                continue  # 다음 주까지 이어지는 구간의 일부
        a, z = int(starts[i]), int(ends[j])
        hi, lo = float(H[a:z + 1].max()), float(L[a:z + 1].min())
        post = C[z + 1:]
        if j < Wc - 1 and not np.any(post > hi + krx_tick(hi)) and post.size and post.min() < lo:
            continue  # 돌파 없이 타이트 구간 저점 이탈 → 무효
        found = (i, j, a, z, mx, mn, hi, lo)
        break
    if found is None:
        msg = why_now or "최근 완성 주 기준 3주 이상 타이트 마감 없음"
        if not complete and Wc >= 2:
            i2, mx2, mn2 = _run_back(WC[:Wc], Wc - 1, cfg)
            cur = WC[-1]
            if Wc - i2 == cfg.min_weeks - 1 and (max(mx2, cur) - min(mn2, cur)) / min(mn2, cur) <= cfg.tight_pct:
                msg += " — 진행 중인 이번 주 종가가 범위 안: 주간 종가 확정 시 3WT 성립 가능"
        res.warnings.append(f"✘ {msg}")
        res.metrics = {"last_week_complete": complete}
        return

    i, j, a, z, mx, mn, hi, lo = found
    weeks = j - i + 1
    spread = (mx - mn) / mn
    pivot = hi + krx_tick(hi)
    stop = max(lo, pivot * (1 - cfg.stop_pct))
    ok = True
    hm = halt_mask(ctx)
    res.reasons.append(f"✔ 주간 종가 {weeks}주 연속 {spread:.2%} 이내 마감 (기준 {cfg.tight_pct:.1%})"
                       + (" — 1% 이내 정석" if spread <= cfg.ideal_tight_pct else ""))
    if weeks > cfg.max_weeks:
        ok = False
        res.warnings.append(f"✘ 주간 종가가 {weeks}주 이상 {cfg.tight_pct:.1%} 이내에 고정 (기준 {cfg.max_weeks}주 이하)"
                            " — 3WT가 아닌 가격 고정(공개매수·합병 등) 의심")
    elif weeks >= 4:
        res.reasons.append(f"✔ {weeks}주 연속 타이트 — 3주보다 강한 신호")
    if not complete:
        res.warnings.append("✘ 이번 주는 미완성 — 주간 종가 미확정 (패턴은 지난 완성 주까지로 판정)")
        if j == Wc - 1 and (max(mx, WC[-1]) - min(mn, WC[-1])) / min(mn, WC[-1]) <= cfg.tight_pct:
            res.reasons.append("✔ 진행 중인 이번 주 종가도 범위 안 (확정 시 1주 연장)")

    # 2) 선행 상승 · 고점 부근
    p0 = max(0, a - cfg.prior_adv_bars)
    seg = L[p0:a]
    adv_lo_i = p0 + int(np.argmin(seg)) if seg.size else a
    prior_adv = WC[i] / L[adv_lo_i] - 1
    if prior_adv >= cfg.min_prior_advance:
        res.reasons.append(f"✔ 선행 상승 {prior_adv:+.0%} (직전 13주 저점 대비)")
    else:
        ok = False
        res.warnings.append(f"✘ 선행 상승 부족 {prior_adv:+.0%} (직전 13주 저점 대비, 기준 {cfg.min_prior_advance:.0%} 이상)")
    hi26 = float(H[max(0, a - cfg.high_lookback):z + 1].max())
    from_hi = mx / hi26 - 1
    if from_hi >= -cfg.max_below_high:
        res.reasons.append(f"✔ 직전 26주 고점 대비 {from_hi:+.1%}")
    else:
        ok = False
        res.warnings.append(f"✘ 직전 26주 고점 대비 {from_hi:+.1%} (기준 -{cfg.max_below_high:.0%} 이내)")

    # 3) 장중 변동: 첫 주 이후 '버티는' 구간 · 첫 주 포함 전체 · 주간 평균 (상한과 가격 고정 하한)
    s2 = int(starts[i + 1])                                   # 첫 주(상승해 들어온 주) 이후 '버티는' 구간
    hold_hi, hold_lo = float(H[s2:z + 1].max()), float(L[s2:z + 1].min())
    hold_range = (hold_hi - hold_lo) / hold_hi
    area_range = (hi - lo) / hi
    w0 = max(0, j - cfg.regime_weeks + 1)
    wk_all = np.array([(H[int(starts[w]):int(ends[w]) + 1].max() - L[int(starts[w]):int(ends[w]) + 1].min()) / WC[w]
                       for w in range(min(w0, i), j + 1)])
    avg_week_range = float(np.mean(wk_all[i - min(w0, i):]))
    regime_range = float(np.median(wk_all[w0 - min(w0, i):]))
    if hold_range <= cfg.max_hold_range:
        res.reasons.append(f"✔ 첫 주 이후 장중 고저폭 {hold_range:.1%} (조용한 횡보)")
    else:
        ok = False
        res.warnings.append(f"✘ 첫 주 이후 장중 고저폭 {hold_range:.1%} > {cfg.max_hold_range:.0%} — 종가만 모인 변동성 구간")
    if area_range > cfg.max_area_range or avg_week_range > cfg.max_avg_week_range:
        ok = False
        res.warnings.append(f"✘ 타이트 구간 장중 고저폭 {area_range:.1%}·주간 평균 고저폭 {avg_week_range:.1%}"
                            f" (기준 {cfg.max_area_range:.0%}·{cfg.max_avg_week_range:.0%} 이하) — 주봉이 넓어 '타이트'하지 않음")
    elif avg_week_range < cfg.min_avg_week_range or regime_range < cfg.min_regime_week_range:
        ok = False
        res.warnings.append(f"✘ 주간 고저폭 타이트 구간 평균 {avg_week_range:.2%}·최근 {cfg.regime_weeks}주 중앙값 {regime_range:.2%}"
                            f" (기준 각 {cfg.min_avg_week_range:.0%} 이상) — 비정상적으로 좁음 (공개매수·합병 등 가격 고정 의심)")

    # 4) Stage 2
    ev = stage2_eval(ctx, z)
    if ev["passed"] >= cfg.tt_min_pass:
        res.reasons.append(f"✔ Stage 2 트렌드 템플릿 {ev['passed']}/8")
    else:
        ok = False
        failed = [k for k, v in ev["checks"].items() if not v]
        res.warnings.append(f"✘ Stage 2 미충족 {ev['passed']}/8 (미충족: {', '.join(failed)})")

    # 5) 거래정지: 정지 주의 주간 종가는 직전 종가 그대로라 '완벽한 타이트'로 오인됨
    h_pre = halts_between(ctx, a - cfg.halt_lookback, z, hm)
    h_post = halts_between(ctx, z + 1, last, hm)
    if h_pre:
        ok = False
        res.warnings.append(f"✘ 타이트 구간·직전 13주에 거래정지 {fmt_dates(h_pre)} — 정지 주의 종가는 의미 없음, 제외")
    if h_post:
        res.warnings.append(f"✘ 타이트 구간 이후 거래정지 {fmt_dates(h_post)} — 거래량·가격 비교 왜곡 가능")

    # 6) 거래량 (거래정지 봉 제외): 감소가 바람직, 직전 50일 평균의 1.3배 초과는 제외
    vol_ratio = pos_mean(V[a:z + 1]) / pos_mean(V[max(0, a - 50):a], 10)
    if not np.isfinite(vol_ratio):
        ok = False
        res.warnings.append("✘ 거래량 정보 부족 — 타이트 구간 거래량 확인 불가")
    elif vol_ratio > cfg.max_vol_ratio:
        ok = False
        res.warnings.append(f"✘ 타이트 구간 거래량 직전 50일 평균의 {vol_ratio:.2f}배 (기준 {cfg.max_vol_ratio}배 이하)"
                            " — 보유가 아닌 손바뀜")
    elif vol_ratio > 1.0:
        res.warnings.append(f"✘ 타이트 구간 거래량 직전 50일 평균의 {vol_ratio:.2f}배 — 감소 아님")
    else:
        res.reasons.append(f"✔ 타이트 구간 거래량 직전 50일 평균의 {vol_ratio:.2f}배 (감소)")

    # 7) 단계 판정 · 돌파 거래량
    vavg = ctx.vol_sma(50).to_numpy(dtype=float)
    stage, bo = classify_stage(ctx, pivot, z, cfg.near_pct, cfg.buy_range, cfg.breakout_window, cfg.fail_pct)
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
    if bo is None and C[last] < lo:
        ok = False
        res.warnings.append("✘ 타이트 구간 저점 아래로 마감 — 패턴 훼손")

    # 8) 점수
    rs = ev["rs"] or 0.0
    s_weeks = 9.0 if weeks == 3 else (12.0 if weeks == 4 else (15.0 if weeks <= cfg.max_weeks else 0.0))
    s_tight = lin(spread, 0.003, cfg.tight_pct, 25, 8)
    s_range = lin(area_range, 0.06, 0.15, 10, 0)
    s_vol = lin(vol_ratio, 0.6, 1.2, 15, 0)
    s_adv = lin(prior_adv, cfg.min_prior_advance, 0.60, 3, 10)
    s_tt = 10.0 if ev["passed"] >= 8 else (5.0 if ev["passed"] >= cfg.tt_min_pass else 0.0)
    s_rs = lin(rs, 70, 99, 0, 5)
    s_act = lin(bo_vol, 1.0, 2.0, 0, 10) if bo is not None else lin(dist, -0.08, 0.0, 0, 10)
    res.score = float(round(min(100.0, s_weeks + s_tight + s_range + s_vol + s_adv + s_tt + s_rs + s_act), 1))

    res.detected = ok
    res.stage = stage
    res.pivot = float(pivot)
    res.stop = float(stop)
    res.start_date = ctx.date(a)
    res.end_date = ctx.date(z)
    res.breakout_date = ctx.date(bo) if bo is not None else None
    res.metrics = {
        "weeks": weeks, "close_spread_pct": round(spread * 100, 2), "area_range_pct": round(area_range * 100, 2),
        "hold_range_pct": round(hold_range * 100, 2), "avg_week_range_pct": round(avg_week_range * 100, 2),
        "regime_week_range_pct": round(regime_range * 100, 2),
        "last_week_complete": complete, "weeks_since_tight": Wc - 1 - j,
        "prior_advance_pct": round(prior_adv * 100, 1), "from_26w_high_pct": round(from_hi * 100, 1),
        "vol_ratio": round(vol_ratio, 2) if np.isfinite(vol_ratio) else None,
        "breakout_vol_ratio": round(bo_vol, 2) if np.isfinite(bo_vol) else None,
        "dist_to_pivot_pct": round(dist * 100, 2), "tight_high": hi, "tight_low": lo,
        "tt_passed": ev["passed"], "rs": ev["rs"], "halt_days": len(h_pre) + len(h_post),
        "score_parts": (f"weeks{s_weeks:.0f}/tight{s_tight:.0f}/range{s_range:.0f}/vol{s_vol:.0f}/adv{s_adv:.0f}"
                        f"/tt{s_tt:.0f}/rs{s_rs:.0f}/act{s_act:.0f}"),
    }

    # 9) 차트 주석
    idx = ctx.df.index
    res.annotations = [
        hline(pivot, f"피벗 {pivot:,.0f}"),
        hline(stop, f"손절 {stop:,.0f}", color="#d50000"),
        box(idx[a], idx[z], hi, lo, f"{weeks}주 타이트 (종가폭 {spread:.1%})"),
        segment([(idx[int(ends[w])], WC[w]) for w in range(i, j + 1)], "주간 종가", color="#ff6d00"),
    ]
    if bo is not None:
        res.annotations.append(marker(idx[bo], f"돌파 {bo_vol:.1f}x", position="below", shape="arrowUp",
                                      color="#00c853" if stage in (BREAKOUT, EXTENDED, NEAR_PIVOT) else "#e91e63"))
