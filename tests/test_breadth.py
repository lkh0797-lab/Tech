"""시장 폭(breadth): 신고가·신저가, 이동평균 위 비율, 300억 상승 종목 수, 미래 참조 없음."""
import numpy as np
import pandas as pd
import pytest

from chart_screener.breadth import breadth_at, breadth_history, compute_breadth

N = 300
DATES = pd.bdate_range("2023-01-02", periods=N)


def _stock(path: np.ndarray, vol: float = 1e6) -> pd.DataFrame:
    c = np.asarray(path, float)
    df = pd.DataFrame({"open": c, "high": c * 1.005, "low": c * 0.995, "close": c,
                       "volume": np.full(len(c), vol)}, index=DATES[:len(c)])
    df["value"] = (df["high"] + df["low"] + df["close"]) / 3 * df["volume"]
    return df


@pytest.fixture(scope="module")
def universe():
    t = np.arange(N)
    up = 10_000 * 1.002 ** t                       # 마지막 날 52주 신고가
    down = 10_000 * 0.998 ** t                     # 마지막 날 52주 신저가
    flat = 10_000 + 50 * np.sin(t / 5)             # 박스권
    ohlcv = {
        "UP1": _stock(up), "DN1": _stock(down), "FL1": _stock(flat),
        "UP2": _stock(up * 1.5),
        "THIN": _stock(down, vol=100),             # 거래대금 미달 → 집계 제외
        "PENNY": _stock(down / 20),                # 동전주(1,000원 미만) → 집계 제외
    }
    big = ohlcv["UP2"].copy()                       # 마지막 날 300억↑ 상승
    big.iloc[-1, big.columns.get_loc("value")] = 400e8
    ohlcv["UP2"] = big
    markets = {"UP1": "KOSPI", "DN1": "KOSPI", "FL1": "KOSDAQ", "UP2": "KOSDAQ", "THIN": "KOSPI",
               "PENNY": "KOSDAQ"}
    return ohlcv, markets


def test_compute_breadth_counts(universe):
    ohlcv, markets = universe
    b = compute_breadth(ohlcv, 300e8, markets, days=30)
    assert set(b) == {"ALL", "KOSPI", "KOSDAQ"}
    a = b["ALL"]
    for k in ("date", "new_highs", "new_lows", "nh_nl", "nh_nl_10d", "pct_above_50", "pct_above_200",
              "big_value_up", "series"):
        assert k in a
    assert a["date"] == f"{DATES[-1]:%Y-%m-%d}"
    assert a["universe"] == 4                       # THIN·PENNY 제외
    assert (a["new_highs"], a["new_lows"], a["nh_nl"]) == (2, 1, 1)
    assert a["pct_above_50"] == pytest.approx(50.0)  # UP1·UP2 위, DN1 아래, FL1 은 경계 근처
    assert a["big_value_up"] == 1
    assert b["KOSPI"]["new_highs"] == 1 and b["KOSPI"]["new_lows"] == 1 and b["KOSPI"]["universe"] == 2
    assert b["KOSDAQ"]["new_highs"] == 1 and b["KOSDAQ"]["new_lows"] == 0
    s = a["series"]
    assert len(s["dates"]) == len(s["nh_nl"]) == len(s["pct_above_50"]) == 30
    assert s["dates"][-1] == a["date"]


def test_breadth_without_market_map_only_all(universe):
    ohlcv, _ = universe
    b = compute_breadth(ohlcv, 300e8)
    assert "ALL" in b and "KOSPI" not in b and "KOSDAQ" not in b


def test_new_highs_need_a_year_of_history(universe):
    ohlcv, markets = universe
    h = breadth_history(ohlcv, 300e8, markets)["ALL"]
    assert h["new_highs"].iloc[:200].isna().all()  # 252일 창(최소 240일) 전에는 결측
    assert h["nh_nl"].iloc[-1] == 1


def test_breadth_history_has_no_lookahead(universe):
    ohlcv, markets = universe
    full = breadth_history(ohlcv, 300e8, markets)
    cut_at = DATES[270]
    cut = {c: d.loc[:cut_at] for c, d in ohlcv.items()}
    part = breadth_history(cut, 300e8, markets)
    for g in ("ALL", "KOSPI", "KOSDAQ"):
        pd.testing.assert_frame_equal(part[g], full[g].loc[:cut_at])
    # breadth_at 은 그날(포함)까지의 값만
    assert breadth_at(full, "ALL", cut_at)["date"] == f"{cut_at:%Y-%m-%d}"
    assert breadth_at(full, "ALL", cut_at + pd.Timedelta(hours=1))["date"] == f"{cut_at:%Y-%m-%d}"
    assert breadth_at(full, "ALL", DATES[0] - pd.Timedelta(days=1)) is None
    assert breadth_at({}, "ALL", cut_at) is None


def test_empty_input():
    assert compute_breadth({}, 300e8) == {}
