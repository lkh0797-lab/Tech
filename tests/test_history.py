"""일봉 이력 길이(--years) 와 캐시: 짧은 캐시는 다시 받고, 긴 캐시는 최근 n봉만 잘라 쓴다."""
import pandas as pd

from chart_screener.config import Config, bars_for_years
from chart_screener.data import ohlcv as ohlcv_mod
from chart_screener.data.ohlcv import OHLCVCache
from synthetic import make_ohlcv


def _fake_fetch(calls):
    def fetch(code, count=750):
        calls.append(count)
        df = make_ohlcv([(0, 100), (count - 1, 150)], n=count)
        df.attrs["requested"] = count
        return df
    return fetch


def test_bars_for_years():
    assert bars_for_years(3) == 760 and bars_for_years(10) == 2510
    assert Config().data.history_days == bars_for_years(3)


def test_short_cache_is_refetched_long_cache_is_sliced(tmp_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(ohlcv_mod, "fetch_ohlcv", _fake_fetch(calls))
    monkeypatch.setattr(OHLCVCache, "is_fresh", lambda self, code, at=None: True)
    cache = OHLCVCache(root=tmp_path)

    assert len(cache.get("000001", 760)) == 760 and calls == [760]
    assert len(cache.get("000001", 760)) == 760 and calls == [760]          # 신선·충분 → 캐시 사용
    assert len(cache.get("000001", 2510)) == 2510 and calls == [760, 2510]  # 더 긴 기간 요청 → 다시 받음
    df = cache.get("000001", 760)                                            # 긴 캐시 → 최근 760봉만
    assert len(df) == 760 and calls == [760, 2510]
    assert df.index[-1] == cache.load("000001").index[-1]


def test_offline_returns_what_is_cached(tmp_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(ohlcv_mod, "fetch_ohlcv", _fake_fetch(calls))
    cache = OHLCVCache(root=tmp_path)
    assert cache.get("000001", 760, offline=True) is None
    cache.save("000001", _fake_fetch([])("000001", 760))
    assert len(cache.get("000001", 2510, offline=True)) == 760 and calls == []  # 오프라인: 있는 만큼만


def test_old_cache_without_requested_attr(tmp_path, monkeypatch):
    calls: list[int] = []
    monkeypatch.setattr(ohlcv_mod, "fetch_ohlcv", _fake_fetch(calls))
    monkeypatch.setattr(OHLCVCache, "is_fresh", lambda self, code, at=None: True)
    cache = OHLCVCache(root=tmp_path)
    old = make_ohlcv([(0, 100), (749, 120)], n=750)          # 구버전 캐시: requested 없음 → 행 수로 간주
    cache.save("000001", old)
    assert len(cache.get("000001", 760)) == 760 and calls == [760]
    assert isinstance(cache.load("000001"), pd.DataFrame)
