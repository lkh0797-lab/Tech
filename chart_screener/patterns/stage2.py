"""바닥 탈출 (stage2) — 와인스타인 1→2단계: 긴 옆걸음 끝에 30주선(150일선)을 거래량 실어 넘은 종목.

기업추적 ``기술.py`` 의 ``stage2()`` 를 문턱 그대로 옮겼다 (책에 적힌 문턱 — 맞추지 않았다).

기준 (일봉, i = 마지막 봉)
 1. 돌파: 최근 10봉(오늘 포함) 안에 종가가 150일선을 위로 뚫은 봉 k — close[k−1] ≤ ma150[k−1] 이고
    close[k] > ma150[k]. 가장 최근 것을 쓴다. 오늘 종가도 150일선 위.
 2. 1단계 바닥: i−130 ~ i−11 봉(120봉, 약 6달) 중 종가가 150일선 아래인 봉이 50% 이상,
    그 구간 고가 최고 / 저가 최저 − 1 ≤ 60% (옆걸음).
 3. 150일선 평평 · 오름: ma150[i] ≥ ma150[i−20] × 0.99 (20봉 전보다 1% 넘게 내려가지 않음)
 4. 거래량: 돌파봉부터 오늘까지 하루 최대 거래량 ≥ 돌파봉 '앞' 50봉 평균(그날 제외) × 2
 5. 오늘 종가 > i−60 ~ i−11 봉(석 달) 종가 고점
 이력: 마지막 봉 인덱스 ≥ 320 (원본 ``i < 320`` 이면 판정 안 함 — 321봉 이상)

단계 — 돌파가 5봉 이내(오늘 포함 0~5봉 전)면 돌파, 그보다 오래면 형성 중.
피벗 = 손절 = 돌파일의 150일선 (다시 그 아래로 마감하면 1단계 복귀). 지금 150일선은 metrics['ma150'].
돌파일 기준으로 고정해야 백테스트가 한 번의 돌파를 날마다 다른 사건으로 세지 않는다.

**관찰용**: 점수 · 매수 계획 · 실시간 감시에 쓰지 않는다 (scoring.BASE_PATTERNS 밖 — 연결은 통합 단계에서).
score 는 0 으로 둔다 — 검증된 품질 점수가 없다. 150일선은 차트가 이미 그리므로 바닥 박스와 돌파 표시만 단다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import BREAKOUT, FORMING, PatternResult, StockContext, box, marker, register

NAME, LABEL = "stage2", "바닥 탈출"


@dataclass
class Stage2Config:
    ma_bars: int = 150             # 30주선 = 150일 종가 이동평균
    cross_window: int = 10         # 최근 10봉(오늘 포함) 안에 150일선 상향 돌파
    base_from: int = 130           # 1단계 바닥 구간 시작 = i−130
    base_to: int = 10              # 바닥 구간 끝 = i−10 (그 봉 제외, 120봉)
    min_below_frac: float = 0.5    # 바닥 구간 종가가 150일선 아래인 비율 ≥ 50%
    max_base_range: float = 0.6    # 바닥 구간 고가 최고 / 저가 최저 − 1 ≤ 60% (옆걸음)
    slope_bars: int = 20           # 150일선 기울기 비교 봉수
    min_slope: float = -0.01       # ma150 ≥ 20봉 전 × (1 − 1%) — 평평하거나 오름
    vol_avg_bars: int = 50         # 거래량 기준 = 돌파봉 '앞' 50봉 평균 (그날 제외)
    vol_mult: float = 2.0          # 돌파 뒤 하루 최대 거래량 ≥ 기준 × 2
    prior_from: int = 60           # 직전 고점 구간 시작 = i−60
    prior_to: int = 10             # 직전 고점 구간 끝 = i−10 (그 봉 제외)
    breakout_bars: int = 5         # 돌파가 5봉 전 이내면 '돌파' 단계
    min_index: int = 320           # 마지막 봉 인덱스 하한 (원본 i < 320 탈락 → 321봉 이상)


def _arrays(ctx: StockContext, cfg: Stage2Config):
    """(H, L, C, V, MA) float 배열 — 결측 거래량은 0."""
    df = ctx.df
    H, L, C = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    V = np.nan_to_num(ctx.vol.to_numpy(dtype=float), nan=0.0)
    return H, L, C, V, ctx.sma(cfg.ma_bars).to_numpy(dtype=float)


def find_cross(C: np.ndarray, M: np.ndarray, i: int, window: int) -> int | None:
    """i 부터 거꾸로 window 봉 안에서 가장 최근 150일선 상향 돌파봉."""
    for k in range(i, i - window, -1):
        if C[k] > M[k] and C[k - 1] <= M[k - 1]:
            return k
    return None


def evaluate(ctx: StockContext, cfg: Stage2Config | None = None) -> dict:
    """마지막 봉 기준 조건별 수치와 통과 여부. 이력 부족이면 {'short': True}.

    반환 키: ok, cross, ago, ma150_pct, slope_pct, below_pct, base_range_pct, vol_mult, prior_high, fails(탈락 사유 목록)"""
    cfg = cfg or Stage2Config()
    i = ctx.n - 1
    if i < cfg.min_index:
        return {"short": True, "ok": False, "fails": []}
    H, L, C, V, M = _arrays(ctx, cfg)
    out: dict = {"short": False, "fails": []}
    fails = out["fails"]
    out["ma150"] = float(M[i])
    out["ma150_pct"] = float((C[i] / M[i] - 1) * 100)
    if not C[i] > M[i]:
        fails.append(f"종가가 150일선 아래 ({out['ma150_pct']:+.1f}%)")
    k = find_cross(C, M, i, cfg.cross_window)
    out["cross"] = k
    out["ago"] = None if k is None else i - k
    if k is None:
        fails.append(f"최근 {cfg.cross_window}봉 안에 150일선 상향 돌파 없음")
    b0, b1 = i - cfg.base_from, i - cfg.base_to
    out["base_start"], out["base_end"] = b0, b1 - 1
    below = float(np.mean(C[b0:b1] < M[b0:b1]))
    top, bot = float(H[b0:b1].max()), float(L[b0:b1].min())
    rng = top / bot - 1
    out.update(below_pct=below * 100, base_range_pct=rng * 100, base_top=top, base_bottom=bot)
    if below < cfg.min_below_frac:
        fails.append(f"바닥 구간 종가가 150일선 아래인 비율 {below:.0%} < {cfg.min_below_frac:.0%}")
    if rng > cfg.max_base_range:
        fails.append(f"바닥 구간 고저폭 {rng:.0%} > {cfg.max_base_range:.0%} (옆걸음 아님)")
    slope = M[i] / M[i - cfg.slope_bars] - 1
    out["slope_pct"] = float(slope * 100)
    if slope < cfg.min_slope:
        fails.append(f"150일선 {cfg.slope_bars}봉 기울기 {slope:+.1%} < {cfg.min_slope:+.0%} (하락 중)")
    vm = 0.0
    if k is not None:
        v50 = V[k - cfg.vol_avg_bars:k].mean()
        vm = float(V[k:i + 1].max() / v50) if v50 > 0 else 0.0
        if vm < cfg.vol_mult:
            fails.append(f"돌파 뒤 최대 거래량 {vm:.1f}배 < {cfg.vol_mult:.0f}배 (돌파 앞 {cfg.vol_avg_bars}봉 평균 대비)")
    out["vol_mult"] = vm
    prior = float(C[i - cfg.prior_from:i - cfg.prior_to].max())
    out["prior_high"] = prior
    if not C[i] > prior:
        fails.append(f"종가가 석 달(i−{cfg.prior_from}~i−{cfg.prior_to + 1}) 종가 고점 {prior:,.0f} 이하")
    out["ok"] = not fails
    return out


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, Stage2Config)
    r = PatternResult(name=NAME, label=LABEL)
    ev = evaluate(ctx, cfg)
    if ev["short"]:
        r.warnings.append(f"이력 부족 — {ctx.n}봉 (필요 {cfg.min_index + 1}봉: 150일선 + 6달 바닥)")
        return r
    if not ev["ok"]:
        r.warnings += ev["fails"]
        return r
    i, k = ctx.n - 1, ev["cross"]
    r.detected = True
    r.stage = BREAKOUT if ev["ago"] <= cfg.breakout_bars else FORMING
    # 피벗 · 손절 · 시작일은 돌파일(k) 기준으로 고정 — 오늘 기준(150일선 · i−130)이면 날마다 바뀌어 백테스트가 한 번의
    # 돌파를 여러 사건으로 센다. 손절만 지금 선으로 두면 선이 오른 뒤 피벗 < 손절로 뒤집혀 보인다.
    r.pivot = r.stop = float(ctx.sma(cfg.ma_bars).iloc[k])
    r.start_date, r.end_date = ctx.date(max(0, k - cfg.base_from)), ctx.date(i)
    r.breakout_date = ctx.date(k)
    r.metrics.update(ma150_pct=round(ev["ma150_pct"], 2), ma150_slope_20=round(ev["slope_pct"], 2),
                     base_below_pct=round(ev["below_pct"], 1), base_range_pct=round(ev["base_range_pct"], 1),
                     vol_mult=round(ev["vol_mult"], 2), days_since_cross=ev["ago"], ma150=ev["ma150"],
                     prior_high=ev["prior_high"], cross_date=ctx.date(k), observe_only=True)
    r.reasons += [
        f"✔ {ctx.date(k)} ({ev['ago']}봉 전) 종가가 150일선 상향 돌파 — 지금 150일선 {ev['ma150_pct']:+.1f}%",
        f"✔ 1단계 바닥: 6달(i−{cfg.base_from}~i−{cfg.base_to + 1}) 종가 {ev['below_pct']:.0f}%가 150일선 아래 · "
        f"고저폭 {ev['base_range_pct']:.0f}%",
        f"✔ 150일선 {cfg.slope_bars}봉 기울기 {ev['slope_pct']:+.1f}% (평평 · 오름)",
        f"✔ 돌파 뒤 최대 거래량 {ev['vol_mult']:.1f}배 (돌파 앞 {cfg.vol_avg_bars}봉 평균 대비)",
        f"✔ 종가가 석 달 종가 고점 {ev['prior_high']:,.0f} 위",
    ]
    if r.stage == FORMING:
        r.warnings.append(f"돌파 {ev['ago']}봉 경과 — 첫 돌파 구간({cfg.breakout_bars}봉) 지남")
    r.warnings.append("관찰용 — 점수 · 매수 계획 · 실시간 감시에 쓰지 않음")
    d = ctx.df.index
    r.annotations += [
        box(d[ev["base_start"]], d[ev["base_end"]], ev["base_top"], ev["base_bottom"], "1단계 바닥", "#7e57c2"),
        marker(d[k], "30주선 돌파", "below", "#e91e63", "arrowUp"),
    ]
    return r
