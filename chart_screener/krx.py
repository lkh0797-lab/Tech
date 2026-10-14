"""KRX 시장 규칙 — 호가 단위 · 휴장일 달력. 패턴 식과 무관한 공용 규칙이다.

2026-10-14 패턴 초기화 때 옛 탐지기 모듈(flat_base · three_weeks_tight)에서 값 그대로 옮겼다.
    krx_tick(price)       2023 개편 호가 단위 (KOSPI · KOSDAQ 공통). 배열도 받는다.
    TICK_TABLE            같은 구간을 [[가격 하한, 호가 단위], ...] 로 — 컵 앤 핸들 식(cwh_reference)의 tick_table 형식.
    FIXED_HOLIDAYS        매년 같은 날 휴장 (MM-DD)
    KRX_EXTRA_HOLIDAYS    음력 · 대체 · 선거 등 비정기 휴장일 (YYYY-MM-DD)
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------- 호가 단위
_TICK_EDGES = np.array([2_000, 5_000, 20_000, 50_000, 200_000, 500_000], dtype=float)
_TICK_SIZES = np.array([1, 5, 10, 50, 100, 500, 1_000], dtype=float)
# 구간 하한은 그 구간에 속한다 (krx_tick(2000) = 5) — searchsorted(side='right') 와 같은 경계
TICK_TABLE: list[list[float]] = [[0.0, float(_TICK_SIZES[0])]] + [
    [float(e), float(s)] for e, s in zip(_TICK_EDGES, _TICK_SIZES[1:])]


def krx_tick(price):
    """KRX 호가 단위 (2023 개편, KOSPI·KOSDAQ 공통). 배열도 받는다."""
    p = np.asarray(price, dtype=float)
    t = _TICK_SIZES[np.searchsorted(_TICK_EDGES, p, side="right")]
    return float(t) if t.ndim == 0 else t


# ---------------------------------------------------------------- 휴장일
FIXED_HOLIDAYS = frozenset({"01-01", "03-01", "05-01", "05-05", "06-06", "08-15", "10-03", "10-09", "12-25", "12-31"})
# 음력·대체·선거 등 비정기 휴장일 (KOSPI 지수 일봉 결측 평일에서 추출, 2023-09 ~ 2026-10)
KRX_EXTRA_HOLIDAYS = (
    "2023-09-28", "2023-09-29", "2023-10-02", "2023-12-29", "2024-02-09", "2024-02-12", "2024-04-10",
    "2024-05-06", "2024-05-15", "2024-09-16", "2024-09-17", "2024-09-18", "2024-10-01", "2025-01-27",
    "2025-01-28", "2025-01-29", "2025-01-30", "2025-03-03", "2025-05-06", "2025-06-03", "2025-10-06",
    "2025-10-07", "2025-10-08", "2026-02-16", "2026-02-17", "2026-02-18", "2026-03-02", "2026-05-25",
    "2026-06-03", "2026-07-17", "2026-08-17", "2026-09-24", "2026-09-25", "2026-10-05",
)
