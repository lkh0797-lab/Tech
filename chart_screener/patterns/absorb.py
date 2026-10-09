"""바닥 투매 흡수 (absorb) — 52주 저점에서 대량 아래꼬리로 투매를 받아내고 그 저가를 지키는 종목.

기업추적 ``기술.py`` 의 ``absorb()`` (저평가V2 첫 판의 '바닥 대량 아래꼬리' — 6개월 검증 통과 신호)를 문턱 그대로 옮겼다.

기준 (일봉, 고정 문턱 — 맞추지 않았다)
 1. 최근 60봉(오늘 포함) 안에 흡수봉 k 가 있다. 가장 최근 것부터 찾는다.
 2. 거래량: k 의 거래량 ≥ k '앞' 60봉 평균(그날 제외) × 3
 3. 바닥: k 의 저가 ≤ k 시점 52주 저점(k 까지 250봉 최저 저가, 그날 포함) × 1.05
 4. 긴 아래꼬리: (종가 − 저가) / (고가 − 저가) ≥ 0.6 — 종가가 그날 고저의 위 40% 안 (고저폭 0 인 봉 제외)
 5. 지킴: k 부터 오늘까지 최저 저가 ≥ k 의 저가 (꼬리 저가를 한 번도 깨지 않음)
 이력: 마지막 봉 인덱스 ≥ 260 (원본 ``i < 260`` 이면 판정 안 함 — 261봉 이상)

단계 — 종가가 꼬리 저가 +5% 이내면 피벗 근접, 그 위는 형성 중. 피벗 = 손절 = 꼬리 저가 (깨지면 신호 무효).

**관찰용**: 점수 · 매수 계획 · 실시간 감시에 쓰지 않는다 (scoring.BASE_PATTERNS 밖 — 연결은 통합 단계에서).
score 는 0 으로 둔다 — 검증된 품질 점수가 없다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .base import FORMING, NEAR_PIVOT, PatternResult, StockContext, hline, marker, register

NAME, LABEL = "absorb", "바닥 투매 흡수"


@dataclass
class AbsorbConfig:
    lookback: int = 60          # 최근 60봉(오늘 포함) 안에서 흡수봉 탐색
    vol_avg_bars: int = 60      # 거래량 기준 = 흡수봉 '앞' 60봉 평균 (그날 제외)
    vol_mult: float = 3.0       # 흡수봉 거래량 ≥ 기준 × 3
    low_window: int = 250       # 52주 저점 = 흡수봉까지 250봉 최저 저가 (그날 포함)
    near_low_pct: float = 0.05  # 흡수봉 저가 ≤ 52주 저점 × 1.05
    min_close_pos: float = 0.6  # (종가 − 저가)/(고가 − 저가) ≥ 0.6 — 긴 아래꼬리
    near_pct: float = 0.05      # 오늘 종가가 꼬리 저가 +5% 이내면 피벗 근접
    min_index: int = 260        # 마지막 봉 인덱스 하한 (원본 i < 260 탈락 → 261봉 이상)


def _arrays(ctx: StockContext):
    """(H, L, C, V) float 배열 — 결측 거래량은 0."""
    df = ctx.df
    H, L, C = (df[k].to_numpy(dtype=float) for k in ("high", "low", "close"))
    V = np.nan_to_num(ctx.vol.to_numpy(dtype=float), nan=0.0)
    return H, L, C, V


def find_absorb(ctx: StockContext, cfg: AbsorbConfig | None = None) -> dict | None:
    """마지막 봉 기준 가장 최근 흡수봉. 없으면 None.

    반환: {k, ago, vol_mult, low, low_52w, close_pos, gap_pct}
      gap_pct = 오늘 종가가 꼬리 저가보다 몇 % 위인지."""
    cfg = cfg or AbsorbConfig()
    i = ctx.n - 1
    if i < cfg.min_index:
        return None
    H, L, C, V = _arrays(ctx)
    w = cfg.vol_avg_bars
    for k in range(i, max(i - cfg.lookback, w - 1), -1):
        rng = H[k] - L[k]
        base = V[k - w:k].mean()
        if not (rng > 0 and base > 0 and V[k] >= cfg.vol_mult * base):
            continue
        low52 = L[max(0, k - cfg.low_window + 1):k + 1].min()
        pos = (C[k] - L[k]) / rng
        if L[k] <= low52 * (1 + cfg.near_low_pct) and pos >= cfg.min_close_pos and L[k:i + 1].min() >= L[k]:
            return {"k": k, "ago": i - k, "vol_mult": float(V[k] / base), "low": float(L[k]), "low_52w": float(low52),
                    "close_pos": float(pos), "gap_pct": float((C[i] / L[k] - 1) * 100)}
    return None


@register(NAME, LABEL)
def detect(ctx: StockContext) -> PatternResult:
    cfg = ctx.cfg.pattern_cfg(NAME, AbsorbConfig)
    r = PatternResult(name=NAME, label=LABEL)
    if ctx.n - 1 < cfg.min_index:
        r.warnings.append(f"이력 부족 — {ctx.n}봉 (필요 {cfg.min_index + 1}봉: 52주 저점 + 거래량 기준)")
        return r
    ev = find_absorb(ctx, cfg)
    if ev is None:
        r.warnings.append(f"최근 {cfg.lookback}봉 안에 바닥 투매 흡수봉 없음 (거래량 {cfg.vol_mult:.0f}배↑ · "
                          f"52주 저점 +{cfg.near_low_pct:.0%} 안 · 종가 위치 {cfg.min_close_pos:.0%}↑ · 이후 저가 지킴)")
        return r
    k, low = ev["k"], ev["low"]
    r.detected = True
    r.stage = NEAR_PIVOT if ev["gap_pct"] <= cfg.near_pct * 100 else FORMING
    r.pivot = r.stop = low
    r.start_date, r.end_date = ctx.date(k), ctx.date(ctx.n - 1)
    r.metrics.update(days_since=ev["ago"], vol_mult=round(ev["vol_mult"], 2), gap_pct=round(ev["gap_pct"], 2),
                     tail_low=low, low_52w=ev["low_52w"], close_pos=round(ev["close_pos"], 3),
                     absorb_date=ctx.date(k), observe_only=True)
    r.reasons += [
        f"✔ {ctx.date(k)} ({ev['ago']}봉 전) 거래량 {ev['vol_mult']:.1f}배 (앞 {cfg.vol_avg_bars}봉 평균 대비)",
        f"✔ 그날 저가 {low:,.0f} — 52주 저점 {ev['low_52w']:,.0f} +{(low / ev['low_52w'] - 1) * 100:.1f}% 안",
        f"✔ 긴 아래꼬리: 종가 위치 {ev['close_pos']:.0%} (고저의 위 {1 - cfg.min_close_pos:.0%} 안 마감)",
        f"✔ 이후 꼬리 저가를 깨지 않음 — 오늘 종가가 그 저가보다 +{ev['gap_pct']:.1f}%",
    ]
    if r.stage == FORMING:
        r.warnings.append(f"꼬리 저가에서 +{ev['gap_pct']:.1f}% 떨어짐 — 손절(꼬리 저가)까지 멀다")
    r.warnings.append("관찰용 — 점수 · 매수 계획 · 실시간 감시에 쓰지 않음")
    r.annotations += [
        hline(low, "투매 흡수 저가(손절)", "#1e88e5", "solid"),
        marker(ctx.df.index[k], f"투매 흡수 {ev['vol_mult']:.1f}배", "below", "#e91e63", "arrowUp"),
    ]
    return r
