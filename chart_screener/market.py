"""시장 방향 판정 (CAN SLIM 의 M).

O'Neil/IBD 방식 단순화:
- 분산일(distribution day): 지수 종가가 전일 대비 -0.2% 이하 하락 + 거래량 전일 초과.
  25 거래일이 지나거나, 지수가 해당일 종가 대비 +5% 이상 오르면 소멸.
- 조정 국면 진입: 유효 분산일 6개 이상, 또는 50일선 아래 + 분산일 4개 이상,
  또는 최근 고점 대비 -10% 이상 하락.
- 랠리 시도: 조정 중 저점 이후 첫 상승 마감일 = 1일차. 저점을 깨면(언더컷) 무효이지만,
  언더컷한 날이 상승 마감하거나 당일 range 의 위쪽 절반에서 마감하면 그날이 새 랠리 시도 1일차가 된다.
- 팔로스루데이(FTD): 랠리 4일차 이후, 지수 +ftd_pct% 이상 + 거래량 전일 초과 → 상승 확인.
  FTD 를 만든 랠리 시도의 저점을 기록해 두고, 지수가 그 저점을 깨면 FTD 실패 → 다시 조정.
- 장중 미완성 봉(partial_frac < 1): 마지막 봉 거래량을 체결 비율로 나눠 하루치로 환산한 뒤
  분산일·FTD 를 판정하고 '장중 잠정'으로 표시한다(비율 5% 이하면 거래량 비교 자체를 생략).
- 시장 폭(breadth, breadth.compute_breadth 의 시장별 값): 신고가-신저가 10일 평균 < 0 이거나
  50일선 위 종목 비율 < 40% 이면 조건당 점수 -8 과 메모. 두 조건이 모두 약하면 '상승 확인'을
  '상승 압박'으로 낮춘다(지수만 오르고 종목 대다수는 빠지는 좁은 장 경계).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import indicators as ind

CONFIRMED, PRESSURE, CORRECTION = "confirmed_uptrend", "uptrend_under_pressure", "correction"
STATE_LABELS = {CONFIRMED: "상승 확인", PRESSURE: "상승 압박", CORRECTION: "조정"}


@dataclass
class MarketConfig:
    dd_drop: float = -0.002          # 분산일 하락 기준
    dd_window: int = 25              # 분산일 유효 기간(거래일)
    dd_expire_rally: float = 0.05    # 분산일 종가 대비 이 이상 상승 시 소멸
    dd_pressure: int = 4             # 상승 압박 분류 기준
    dd_correction: int = 6           # 조정 전환 기준
    drawdown_correction: float = 0.10
    ftd_pct: float = 0.0125          # FTD 최소 상승률 (KOSDAQ 은 변동성 높아 0.015 권장)
    ftd_min_day: int = 4
    ftd_max_day: int = 25            # 이 이후의 FTD 는 신뢰도 낮음 → 인정하지 않음
    day1_upper_half: float = 0.5     # 언더컷 당일 range 내 종가 위치가 이 이상이면 랠리 1일차로 인정
    partial_min_frac: float = 0.05   # 장중 체결 비율이 이 이하면 마지막 봉 거래량 비교 생략
    # 시장 폭 (pct_above_50 은 0~100 퍼센트)
    breadth_weak_nhnl: float = 0.0   # 신고가-신저가 10일 평균이 이 미만이면 폭 약화
    breadth_weak_pct50: float = 40.0 # 50일선 위 종목 비율(%)이 이 미만이면 폭 약화
    breadth_penalty: float = 8.0     # 폭 약화 조건 하나당 점수 차감
    breadth_downgrade: bool = True   # 두 조건 모두 약화 → 상승 확인을 상승 압박으로


@dataclass
class MarketState:
    name: str
    state: str
    label: str
    date: str
    close: float
    above_21ema: bool
    above_50sma: bool
    above_200sma: bool
    sma50_rising: bool
    sma200_rising: bool
    distribution_days: int
    dd_dates: list[str] = field(default_factory=list)
    last_ftd: str | None = None
    rally_day: int | None = None
    drawdown: float = 0.0
    notes: list[str] = field(default_factory=list)
    rally_low: float | None = None   # 진행 중 랠리 시도(또는 직전 FTD)의 기준 저점
    provisional: bool = False        # 장중 미완성 봉으로 판정한 잠정 상태
    breadth: dict | None = None      # 이 시장의 시장 폭 (breadth.compute_breadth 의 시장별 값)
    breadth_penalty: float = 0.0     # 시장 폭 약화로 깎은 점수

    @property
    def score(self) -> float:
        """0~100: 시장 우호도."""
        s = {CONFIRMED: 70, PRESSURE: 45, CORRECTION: 15}.get(self.state, 40)
        s += 10 * self.above_50sma + 10 * self.above_200sma + 5 * self.sma50_rising + 5 * self.sma200_rising
        s -= 3 * max(0, self.distribution_days - 3)
        s -= self.breadth_penalty
        return float(max(0, min(100, s)))


def _breadth_weakness(breadth: dict | None, cfg: MarketConfig) -> list[str]:
    """시장 폭 약화 조건 목록 (한글 설명)."""
    if not breadth:
        return []
    weak = []
    nh = breadth.get("nh_nl_10d")
    p50 = breadth.get("pct_above_50")
    if nh is not None and nh == nh and nh < cfg.breadth_weak_nhnl:
        weak.append(f"신고가-신저가 10일 평균 {nh:+.1f}")
    if p50 is not None and p50 == p50 and p50 < cfg.breadth_weak_pct50:
        weak.append(f"50일선 위 종목 {p50:.0f}%")
    return weak


def analyze_market(name: str, df: pd.DataFrame, cfg: MarketConfig | None = None,
                   lookback: int = 260, partial_frac: float | None = None,
                   breadth: dict | None = None) -> MarketState:
    """지수 일봉으로 시장 상태 판정.

    partial_frac: 마지막 봉이 장중 미완성이면 하루 거래량 중 체결 비율(0~1), 확정 봉이면 None.
    breadth: 이 시장의 시장 폭 dict (없으면 지수만으로 판정).
    """
    cfg = cfg or MarketConfig()
    if name == "KOSDAQ" and cfg.ftd_pct == MarketConfig.ftd_pct:
        cfg = MarketConfig(**{**cfg.__dict__, "ftd_pct": 0.015})
    c = df["close"]
    v = df["volume"].astype(float).copy()
    provisional = partial_frac is not None and partial_frac < 1
    if provisional and len(v):
        v.iloc[-1] = v.iloc[-1] / partial_frac if partial_frac > cfg.partial_min_frac else np.nan
    e21, s50, s200 = ind.ema(c, 21), ind.sma(c, 50), ind.sma(c, 200)
    chg = c.pct_change()
    C, H, L, V, CH = (x.to_numpy(float) for x in (c, df["high"], df["low"], v, chg))
    S50 = s50.to_numpy(float)
    n = len(df)
    start = max(1, n - lookback)

    def vol_up(i: int) -> bool:
        return bool(V[i] > V[i - 1])          # NaN 비교는 False

    def day1_on_undercut(i: int) -> bool:
        """저점을 깬 날이 상승 마감 또는 range 위쪽 절반 마감이면 랠리 시도 1일차."""
        if CH[i] > 0:
            return True
        rng = H[i] - L[i]
        return bool(rng > 0 and (C[i] - L[i]) / rng >= cfg.day1_upper_half)

    state = CONFIRMED if C[start] > (S50[start] if np.isfinite(S50[start]) else 0) else CORRECTION
    dds: list[int] = []
    peak = float(np.max(C[:start + 1]))
    corr_low_i: int | None = None
    rally_start: int | None = None
    last_ftd: int | None = None
    ftd_low: float | None = None              # FTD 를 만든 랠리 시도의 저점 (이탈 = FTD 실패)
    ftd_failed: int | None = None

    for i in range(start, n):
        ci = C[i]
        # 분산일 갱신
        dds = [d for d in dds if i - d < cfg.dd_window and ci < C[d] * (1 + cfg.dd_expire_rally)]
        if CH[i] <= cfg.dd_drop and vol_up(i):
            dds.append(i)
        peak = max(peak, ci)
        dd_cnt = len(dds)

        if state in (CONFIRMED, PRESSURE):
            if ftd_low is not None and L[i] < ftd_low:
                # FTD 실패: 랠리 시도 저점 이탈 → 조정 복귀, 이날이 새 저점
                state, ftd_failed, ftd_low = CORRECTION, i, None
                corr_low_i = i
                rally_start = i if day1_on_undercut(i) else None
                continue
            below50 = np.isfinite(S50[i]) and ci < S50[i]
            if dd_cnt >= cfg.dd_correction or (below50 and dd_cnt >= cfg.dd_pressure) \
                    or ci <= peak * (1 - cfg.drawdown_correction):
                state, corr_low_i, rally_start, ftd_low = CORRECTION, i, None, None
            else:
                state = PRESSURE if dd_cnt >= cfg.dd_pressure else CONFIRMED
        else:  # CORRECTION: 랠리 시도와 FTD 추적
            if corr_low_i is None or L[i] < L[corr_low_i]:
                # 신저점(언더컷) → 랠리 시도 리셋. 단 상승/위쪽 절반 마감이면 오늘이 1일차
                corr_low_i = i
                rally_start = i if day1_on_undercut(i) else None
                continue
            if rally_start is None:
                if CH[i] > 0:
                    rally_start = i
                continue
            day = i - rally_start + 1
            if cfg.ftd_min_day <= day <= cfg.ftd_max_day and CH[i] >= cfg.ftd_pct and vol_up(i):
                state, last_ftd, dds = CONFIRMED, i, []
                ftd_low = float(L[corr_low_i])
                peak = ci
            elif day > cfg.ftd_max_day:
                rally_start = None  # 너무 오래된 랠리 시도 → 재시작 대기

    last = n - 1
    rally_day = (last - rally_start + 1) if (state == CORRECTION and rally_start is not None) else None
    rally_low = ftd_low if state != CORRECTION else (float(L[corr_low_i]) if corr_low_i is not None else None)
    notes = []
    if state == CORRECTION and rally_day:
        notes.append(f"랠리 시도 {rally_day}일차 (FTD 대기, 저점 {rally_low:,.2f} 이탈 시 무효)")
    if last_ftd is not None:
        notes.append(f"최근 팔로스루데이: {df.index[last_ftd]:%Y-%m-%d}")
        if ftd_low is not None and state != CORRECTION and last - last_ftd <= cfg.ftd_max_day:
            notes.append(f"랠리 저점 {ftd_low:,.2f} 이탈 시 FTD 무효")
    if ftd_failed is not None and (last_ftd is None or ftd_failed > last_ftd):
        notes.append(f"FTD 실패(랠리 저점 이탈): {df.index[ftd_failed]:%Y-%m-%d}")

    # 시장 폭 반영
    weak = _breadth_weakness(breadth, cfg)
    penalty = cfg.breadth_penalty * len(weak)
    if weak:
        notes.append("시장 폭 약화: " + ", ".join(weak))
        if len(weak) >= 2 and state == CONFIRMED and cfg.breadth_downgrade:
            state = PRESSURE
            notes.append("시장 폭 약화로 '상승 확인' → '상승 압박' 하향")
    if provisional:
        frac_txt = f"{partial_frac:.0%}" if partial_frac and partial_frac > 0 else "0%"
        notes.append(f"장중 잠정 판정 (체결 비율 {frac_txt}로 당일 거래량 환산)")

    return MarketState(
        name=name, state=state, label=STATE_LABELS[state], date=f"{df.index[last]:%Y-%m-%d}",
        close=float(C[last]),
        above_21ema=bool(c.iloc[last] > e21.iloc[last]),
        above_50sma=bool(c.iloc[last] > s50.iloc[last]),
        above_200sma=bool(c.iloc[last] > s200.iloc[last]),
        sma50_rising=ind.is_rising(s50, 10), sma200_rising=ind.is_rising(s200, 20),
        distribution_days=len(dds), dd_dates=[f"{df.index[d]:%Y-%m-%d}" for d in dds],
        last_ftd=f"{df.index[last_ftd]:%Y-%m-%d}" if last_ftd is not None else None,
        rally_day=rally_day, drawdown=float(C[last] / peak - 1), notes=notes,
        rally_low=rally_low, provisional=provisional, breadth=breadth, breadth_penalty=penalty,
    )
