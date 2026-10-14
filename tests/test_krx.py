"""KRX 공용 규칙 (krx.py) — 호가 단위 · 컵 앤 핸들 식에 넘기는 호가 표 · 휴장일 달력."""
import math

import numpy as np

from chart_screener import krx
from chart_screener.live import krx_holiday
from chart_screener.patterns import cwh_reference as ref


def test_krx_tick():
    assert krx.krx_tick(1_500) == 1 and krx.krx_tick(4_990) == 5 and krx.krx_tick(15_000) == 10
    assert krx.krx_tick(30_000) == 50 and krx.krx_tick(150_000) == 100 and krx.krx_tick(300_000) == 500
    assert krx.krx_tick(800_000) == 1_000
    assert list(krx.krx_tick(np.array([1_999, 2_000, 499_999, 500_000]))) == [1, 5, 500, 1_000]


def test_tick_table_matches_krx_tick_for_formula_entry():
    """식의 next_entry(pivot, tick_table) = krx_tick 기준 '피벗보다 큰 첫 호가' (구간 경계 포함)."""
    assert krx.TICK_TABLE == [[0.0, 1.0], [2000.0, 5.0], [5000.0, 10.0], [20000.0, 50.0], [50000.0, 100.0],
                              [200000.0, 500.0], [500000.0, 1000.0]]
    prices = [1, 999.5, 1999, 1999.5, 2000, 2003.2, 4999, 4995, 5000, 19990, 19999.9, 20000, 49950, 50000,
              199900, 200000, 499500, 500000, 812345.6]
    prices += list(np.random.default_rng(3).uniform(1000, 900_000, 300))
    for p in prices:
        e = ref.next_entry(float(p), tick_table=krx.TICK_TABLE)
        t = krx.krx_tick(p)
        assert e > p and math.isclose(e, (math.floor(p / t) + 1) * t), (p, e)   # 경계 = 아래 구간 호가의 배수라 같다
        assert math.isclose(e / krx.krx_tick(e), round(e / krx.krx_tick(e)))  # 진입가는 그 가격대의 호가 위


def test_holidays_moved_from_old_pattern_module():
    from datetime import date
    assert "10-09" in krx.FIXED_HOLIDAYS and "2026-10-05" in krx.KRX_EXTRA_HOLIDAYS
    assert krx_holiday(date(2026, 10, 9)) and krx_holiday(date(2026, 10, 5)) and not krx_holiday(date(2026, 10, 8))
