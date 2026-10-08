"""시장 방향(M) 판정: 분산일·랠리 시도·FTD·FTD 실패·시장 폭·장중 잠정."""
import numpy as np
import pandas as pd
import pytest

from chart_screener.market import CONFIRMED, CORRECTION, PRESSURE, MarketConfig, analyze_market


class Idx:
    """지수 일봉 빌더: 하루씩 등락률·거래량·고저를 지정해 쌓는다."""

    def __init__(self, start: float = 1000.0, vol: float = 1e6):
        self.c, self.h, self.l, self.v = [start], [start * 1.002], [start * 0.998], [vol]
        self.base_vol = vol

    def day(self, chg: float, vol: float | None = None, low: float | None = None, high: float | None = None):
        """기본 봉: 상승일은 고가 부근, 하락일은 저가 부근에서 마감 (range 내 종가 위치 ≈ 0.9 / 0.1)."""
        prev = self.c[-1]
        c = prev * (1 + chg)
        rng = max(abs(c - prev), c * 0.002)
        hi, lo = (c + rng / 9, c - rng) if chg >= 0 else (c + rng, c - rng / 9)
        self.c.append(c)
        self.h.append(max(high or hi, c))
        self.l.append(min(low or lo, c))
        self.v.append(self.base_vol if vol is None else vol)
        return self

    def run(self, k: int, chg: float):
        for _ in range(k):
            self.day(chg)
        return self

    @property
    def n(self) -> int:
        return len(self.c)

    def df(self) -> pd.DataFrame:
        idx = pd.bdate_range("2023-01-02", periods=self.n)
        c = np.array(self.c)
        return pd.DataFrame({"open": np.r_[c[0], c[:-1]], "high": self.h, "low": self.l, "close": c,
                             "volume": self.v}, index=idx)


def _uptrend(k: int = 300, chg: float = 0.002) -> Idx:
    return Idx().run(k, chg)


def _correction_then_low() -> tuple[Idx, int]:
    """상승 후 -10% 넘게 하락해 조정 진입, 마지막 봉이 저점. (빌더, 저점 위치)"""
    b = _uptrend(260)
    b.run(14, -0.009)                      # ~ -12%
    return b, b.n - 1


# ---------------------------------------------------------------- 분산일
def test_distribution_day_counted_and_expires_after_window():
    b = _uptrend()
    b.day(-0.005, vol=1.2e6)               # 분산일 (하락 + 거래량 증가)
    d = b.n - 1
    b.run(30, 0.0008)                      # 25일 동안 +5% 미만 상승 → 기간 만료로만 소멸
    df = b.df()
    assert analyze_market("KOSPI", df.iloc[:d + 1]).distribution_days == 1
    assert analyze_market("KOSPI", df.iloc[:d + 25]).distribution_days == 1   # 24일 경과: 유효
    assert analyze_market("KOSPI", df.iloc[:d + 26]).distribution_days == 0   # 25일 경과: 소멸


def test_down_day_on_lower_volume_is_not_distribution():
    b = _uptrend().day(-0.01, vol=0.9e6)
    assert analyze_market("KOSPI", b.df()).distribution_days == 0


def test_distribution_day_expires_after_5pct_rally():
    b = _uptrend()
    b.day(-0.005, vol=1.2e6)
    b.run(3, 0.01)                          # +3%: 아직 유효
    assert analyze_market("KOSPI", b.df()).distribution_days == 1
    b.run(3, 0.01)                          # +6%: 분산일 종가 대비 5% 넘게 상승 → 소멸
    assert analyze_market("KOSPI", b.df()).distribution_days == 0


def test_distribution_cluster_pressure_then_correction():
    b = _uptrend(300, 0.004)
    for _ in range(4):
        b.day(-0.003, vol=1.3e6).day(0.004).day(0.004)
    st = analyze_market("KOSPI", b.df())
    assert st.distribution_days == 4 and st.state == PRESSURE
    for _ in range(2):
        b.day(-0.003, vol=1.3e6).day(0.004).day(0.004)
    assert analyze_market("KOSPI", b.df()).state == CORRECTION


# ---------------------------------------------------------------- 랠리 시도 / FTD
def test_ftd_requires_day4_or_later():
    b, _ = _correction_then_low()
    assert analyze_market("KOSPI", b.df()).state == CORRECTION
    b.day(0.004).day(0.003)                         # 1·2일차
    b.day(0.02, vol=1.5e6)                          # 3일차 큰 상승: FTD 아님
    st3 = analyze_market("KOSPI", b.df())
    assert st3.state == CORRECTION and st3.rally_day == 3 and st3.last_ftd is None
    b.day(0.02, vol=2.0e6)                          # 4일차 +2% & 거래량 증가 → FTD
    st4 = analyze_market("KOSPI", b.df())
    assert st4.state == CONFIRMED
    assert st4.last_ftd == f"{b.df().index[-1]:%Y-%m-%d}"


def test_ftd_needs_volume_increase():
    b, _ = _correction_then_low()
    b.day(0.004).day(0.003).day(0.002)
    b.day(0.02, vol=0.8e6)                          # 4일차 상승이지만 거래량 감소
    assert analyze_market("KOSPI", b.df()).state == CORRECTION


def _undercut_case(close_chg: float, close_pos: float) -> tuple[Idx, float]:
    """조정 저점 → 소폭 반등 2일 → 저점을 깨는 날 (등락률 close_chg, range 내 종가 위치 close_pos)."""
    b, lo_i = _correction_then_low()
    low = b.l[lo_i]
    b.day(0.003).day(0.003)
    prev = b.c[-1]
    c = prev * (1 + close_chg)
    lo = low * 0.99                                  # 직전 저점 언더컷
    hi = lo + (c - lo) / close_pos if close_pos > 0 else c * 1.001
    b.day(close_chg, low=lo, high=hi)
    return b, lo


def test_undercut_day_closing_up_is_day1():
    b, _ = _undercut_case(0.002, 0.95)
    st = analyze_market("KOSPI", b.df())
    assert st.state == CORRECTION and st.rally_day == 1
    b.day(0.003).day(0.003)                          # 2·3일차
    b.day(0.02, vol=1.6e6)                           # 언더컷일 기준 4일차 → FTD
    assert analyze_market("KOSPI", b.df()).state == CONFIRMED


def test_undercut_day_closing_down_in_upper_half_is_day1():
    b, _ = _undercut_case(-0.002, 0.7)
    st = analyze_market("KOSPI", b.df())
    assert st.state == CORRECTION and st.rally_day == 1


def test_undercut_day_closing_weak_resets_rally():
    b, _ = _undercut_case(-0.006, 0.2)
    st = analyze_market("KOSPI", b.df())
    assert st.state == CORRECTION and st.rally_day is None
    b.day(0.003)                                      # 다음 상승일이 1일차
    assert analyze_market("KOSPI", b.df()).rally_day == 1


def _after_ftd() -> tuple[Idx, float]:
    b, lo_i = _correction_then_low()
    low = b.l[lo_i]
    b.day(0.004).day(0.003).day(0.002).day(0.02, vol=1.6e6)
    assert analyze_market("KOSPI", b.df()).state == CONFIRMED
    return b, low


def test_ftd_failure_when_rally_low_undercut():
    b, low = _after_ftd()
    st = analyze_market("KOSPI", b.df())
    assert st.rally_low == pytest.approx(low)
    # 거래량 증가 없는 완만한 하락(분산일 아님, 고점 대비 -10% 미만)으로 랠리 저점 이탈
    while b.c[-1] > low * 1.004:
        b.day(-0.006)
    b.day(-0.006, low=low * 0.995)
    st = analyze_market("KOSPI", b.df())
    assert st.state == CORRECTION
    assert st.drawdown > -0.10                       # 낙폭·분산일이 아니라 랠리 저점 이탈 때문
    assert any("FTD 실패(" in n for n in st.notes)


def test_ftd_holds_above_rally_low():
    b, low = _after_ftd()
    while b.c[-1] > low * 1.02:
        b.day(-0.006)
    st = analyze_market("KOSPI", b.df())
    assert st.state in (CONFIRMED, PRESSURE)
    assert not any("FTD 실패(" in n for n in st.notes)


# ---------------------------------------------------------------- 시장 폭
def test_breadth_downgrade_and_penalty():
    df = _uptrend().df()
    base = analyze_market("KOSPI", df)
    assert base.state == CONFIRMED and base.breadth is None and base.breadth_penalty == 0

    one = analyze_market("KOSPI", df, breadth={"nh_nl_10d": -12.0, "pct_above_50": 55.0})
    assert one.state == CONFIRMED
    assert one.score == pytest.approx(max(0.0, base.score - MarketConfig.breadth_penalty))
    assert any("시장 폭 약화" in n for n in one.notes)

    weak = {"nh_nl_10d": -30.0, "pct_above_50": 28.0}
    both = analyze_market("KOSPI", df, breadth=weak)
    assert both.state == PRESSURE and both.breadth == weak
    assert both.breadth_penalty == 2 * MarketConfig.breadth_penalty
    assert both.score < base.score

    healthy = analyze_market("KOSPI", df, breadth={"nh_nl_10d": 25.0, "pct_above_50": 70.0})
    assert healthy.state == CONFIRMED and healthy.score == base.score

    off = analyze_market("KOSPI", df, MarketConfig(breadth_downgrade=False), breadth=weak)
    assert off.state == CONFIRMED


def test_breadth_missing_values_ignored():
    df = _uptrend().df()
    st = analyze_market("KOSPI", df, breadth={"nh_nl_10d": None, "pct_above_50": float("nan")})
    assert st.state == CONFIRMED and st.breadth_penalty == 0


# ---------------------------------------------------------------- 장중 미완성 봉
def test_partial_bar_volume_scaled_for_distribution():
    b = _uptrend()
    b.day(-0.005, vol=0.6e6)                         # 장중 누적 0.6배 (하루치 환산 1.2배)
    df = b.df()
    assert analyze_market("KOSPI", df).distribution_days == 0
    st = analyze_market("KOSPI", df, partial_frac=0.5)
    assert st.distribution_days == 1 and st.provisional
    assert any("장중 잠정" in n for n in st.notes)
    early = analyze_market("KOSPI", df, partial_frac=0.03)   # 체결 비율이 너무 낮으면 거래량 비교 생략
    assert early.distribution_days == 0 and early.provisional
