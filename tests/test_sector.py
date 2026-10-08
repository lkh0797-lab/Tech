"""업종·테마 매핑(data/sector.py) 파서·캐시와 그룹 강도(sector.py) 테스트 — 네트워크 없음."""
from __future__ import annotations

import re
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from chart_screener.data import sector as sd
from chart_screener.patterns.trend_template import evaluate
from chart_screener.sector import (STRENGTH_COLUMNS, SectorConfig, group_strength, stock_groups,
                                   stock_metrics, tt_pass)
from chart_screener.universe_data import UniverseData
from synthetic import make_context, make_ohlcv, set_bar

# ---------------------------------------------------------------- 응답 견본 (실제 응답에서 필드 일부만 남김)
INDUSTRY_LIST = {
    "stockListSortType": "INDUSTRY",
    "groups": [
        {"no": 278, "name": "반도체와반도체장비", "totalCount": 3, "changeRate": "2.10",
         "riseCount": 2, "fallCount": 1, "steadyCount": 0},
        {"no": 261, "name": "제약", "totalCount": 175, "changeRate": "-0.75",
         "riseCount": 100, "fallCount": 57, "steadyCount": 18},
        {"name": "번호없음", "totalCount": 1},                 # 깨진 항목 → 건너뜀
        {"no": "x", "name": "번호오류", "totalCount": 1},
    ],
    "totalCount": 2, "page": 1, "pageSize": 100, "marketStatus": "CLOSE",
}

MEMBERS_278 = {
    "stockListSortType": "INDUSTRY",
    "stocks": [
        {"stockType": "domestic", "stockEndType": "stock", "itemCode": "092870", "stockName": "엑시콘",
         "sosok": "1", "closePrice": "31,250", "fluctuationsRatio": "8.32",
         "accumulatedTradingValueRaw": "61234000000"},
        {"stockType": "domestic", "stockEndType": "stock", "itemCode": "131290", "stockName": "티에스이"},
        {"stockType": "domestic", "stockEndType": "etf", "itemCode": "091160", "stockName": "KODEX 반도체"},
        {"stockType": "domestic", "stockEndType": "stock", "itemCode": "", "stockName": "코드없음"},
    ],
    "groupInfo": {"no": 278, "name": "반도체와반도체장비", "totalCount": 3},
    "totalCount": 3, "page": 1, "pageSize": 100,
}


def test_parse_group_list():
    groups, total = sd.parse_group_list(INDUSTRY_LIST)
    assert total == 2
    assert groups == [{"no": 278, "name": "반도체와반도체장비", "count": 3},
                      {"no": 261, "name": "제약", "count": 175}]
    assert sd.parse_group_list(None) == ([], 0)
    assert sd.parse_group_list({"groups": None}) == ([], 0)


def test_parse_group_members_skips_etf_and_bad_codes():
    members, total = sd.parse_group_members(MEMBERS_278)
    assert total == 3
    assert members == [("092870", "엑시콘"), ("131290", "티에스이")]
    assert sd.parse_group_members([]) == ([], 0)


def test_build_map_assigns_one_sector_and_sorted_themes():
    df = sd.build_map(
        {"반도체와반도체장비": ["A", "B", "C"], "전자장비와기기": ["C", "D"]},
        {"반도체 장비": ["A", "B", "B"], "CXL": ["A", "E"]},
    )
    assert list(df.columns) == sd.COLUMNS
    rows = {r.code: (r.sector, r.themes) for r in df.itertuples()}
    assert rows["A"] == ("반도체와반도체장비", ["CXL", "반도체 장비"])
    assert rows["B"] == ("반도체와반도체장비", ["반도체 장비"])       # 중복 편입은 한 번만
    assert rows["C"][0] == "전자장비와기기"                           # 두 업종이면 더 작은 업종
    assert rows["E"] == (None, ["CXL"])                               # 테마만 있는 종목
    assert sd.build_map({}, {}).columns.tolist() == sd.COLUMNS


# ---------------------------------------------------------------- 수집·캐시 (가짜 http)
class _Resp:
    def __init__(self, js):
        self._js = js

    def json(self):
        return self._js


def _fake_api(groups: dict[str, list[tuple[int, str, list[str]]]], fail: set[int] = frozenset(), calls=None):
    """groups: {'industry'|'theme': [(no, name, [codes])]} → http.get 대역 (pageSize 를 존중해 페이지 분할)."""
    def get(url, **kw):
        if calls is not None:
            calls.append(url)
        q = dict(re.findall(r"(\w+)=(\w+)", url.split("?", 1)[1]))
        page, size = int(q["page"]), int(q["pageSize"])
        m = re.search(r"/api/stocks/(industry|theme)(?:/(\d+))?\?", url)
        kind, no = m.group(1), m.group(2)
        gs = groups.get(kind, [])
        if no is None:
            part = gs[(page - 1) * size: page * size]
            return _Resp({"groups": [{"no": g[0], "name": g[1], "totalCount": len(g[2])} for g in part],
                          "totalCount": len(gs), "page": page, "pageSize": size})
        if int(no) in fail:
            raise RuntimeError(f"요청 실패: {url}")
        codes = next(g[2] for g in gs if g[0] == int(no))
        part = codes[(page - 1) * size: page * size]
        return _Resp({"stocks": [{"itemCode": c, "stockName": f"종목{c}", "stockEndType": "stock"} for c in part],
                      "totalCount": len(codes), "page": page, "pageSize": size})
    return get


_GROUPS = {
    "industry": [(1, "반도체", ["000010", "000020", "000030"]), (2, "제약", ["000040", "000050"])],
    "theme": [(11, "HBM", ["000010", "000020"]), (12, "CXL", ["000010", "000030", "000060"]),
              (13, "바이오", ["000040"])],
}


def test_fetch_sector_map_paginates(monkeypatch):
    monkeypatch.setattr(sd, "PAGE_SIZE", 2)   # 목록·구성 모두 2쪽 이상으로 쪼개짐
    monkeypatch.setattr(sd.http, "get", _fake_api(_GROUPS))
    df = sd.fetch_sector_map(verbose=False, workers=2)
    rows = {r.code: (r.sector, r.themes) for r in df.itertuples()}
    assert rows["000010"] == ("반도체", ["CXL", "HBM"])
    assert rows["000030"] == ("반도체", ["CXL"])
    assert rows["000060"] == (None, ["CXL"])            # 2쪽째 구성 종목
    assert rows["000040"] == ("제약", ["바이오"])        # 2쪽째 테마
    assert df.attrs["group_no"]["테마"]["바이오"] == 13
    assert df.attrs["failed"] == []
    assert df.attrs["fetched_at"].tzinfo is not None


def test_fetch_sector_map_skips_failed_group(monkeypatch):
    monkeypatch.setattr(sd.http, "get", _fake_api(_GROUPS, fail={12}))
    df = sd.fetch_sector_map(verbose=False)
    assert len(df.attrs["failed"]) == 1 and "CXL" in df.attrs["failed"][0]
    assert "000060" not in set(df["code"])
    assert df.loc[df.code == "000010", "themes"].iloc[0] == ["HBM"]


def test_load_sector_map_cache_cycle(monkeypatch, tmp_path):
    path = tmp_path / "sector.pkl"
    # 오프라인 + 캐시 없음 → 빈 표
    empty = sd.load_sector_map(offline=True, path=path)
    assert empty.empty and list(empty.columns) == sd.COLUMNS

    calls: list[str] = []
    monkeypatch.setattr(sd.http, "get", _fake_api(_GROUPS, calls=calls))
    df = sd.load_sector_map(path=path, verbose=False)
    assert path.exists() and len(df) == 6 and calls
    assert df.attrs["group_no"]["업종"]["반도체"] == 1

    # 신선한 캐시 → 요청 없음, 오프라인도 같은 내용
    calls.clear()
    again = sd.load_sector_map(path=path, verbose=False)
    assert not calls
    pd.testing.assert_frame_equal(again, df)
    pd.testing.assert_frame_equal(sd.load_sector_map(offline=True, path=path), df)

    # 30일 지난 캐시 → 다시 받음
    payload = pd.read_pickle(path)
    payload["fetched_at"] = pd.Timestamp(sd.now_kst()) - timedelta(days=31)
    pd.to_pickle(payload, path)
    sd.load_sector_map(path=path, verbose=False)
    assert calls

    # 다시 받기 실패 → 이전 캐시 유지
    payload["fetched_at"] = pd.Timestamp(sd.now_kst()) - timedelta(days=40)
    pd.to_pickle(payload, path)

    def boom(url, **kw):
        raise RuntimeError("network down")
    monkeypatch.setattr(sd.http, "get", boom)
    stale = sd.load_sector_map(path=path, verbose=False)
    assert len(stale) == 6
    # 캐시도 없으면 빈 표
    assert sd.load_sector_map(path=tmp_path / "none.pkl", verbose=False).empty


def test_load_sector_map_keeps_cache_when_many_groups_fail(monkeypatch, tmp_path):
    path = tmp_path / "sector.pkl"
    monkeypatch.setattr(sd.http, "get", _fake_api(_GROUPS))
    sd.load_sector_map(path=path, verbose=False)
    monkeypatch.setattr(sd.http, "get", _fake_api({"industry": _GROUPS["industry"], "theme": _GROUPS["theme"]},
                                                  fail={1, 2, 11, 12}))
    df = sd.load_sector_map(refresh=True, path=path, verbose=False)
    assert len(df) == 6                                     # 성공률 1/5 → 이전 캐시


# ---------------------------------------------------------------- 그룹 강도 (합성 UniverseData)
N = 300


def _up(seed: int, last_jump: float | None = None, vol: float = 200_000) -> pd.DataFrame:
    """200일선 위 정배열 상승 + 최근 신고가."""
    df = make_ohlcv([(0, 10_000), (150, 14_000), (230, 17_000), (N - 1, 21_000)], n=N, seed=seed,
                    vol_base=vol)
    if last_jump:
        prev = float(df["close"].iloc[-2])
        df = set_bar(df, -1, open=prev, close=prev * (1 + last_jump), high=prev * (1 + last_jump) * 1.01,
                     volume=3_000_000)
    return df


def _down(seed: int) -> pd.DataFrame:
    return make_ohlcv([(0, 20_000), (150, 15_000), (N - 1, 10_000)], n=N, seed=seed, vol_base=300_000)


def _ud(frames: dict[str, pd.DataFrame], rs: dict[str, float], names: dict[str, str] | None = None) -> UniverseData:
    idx = next(iter(frames.values())).index
    uni = pd.DataFrame({
        "code": list(frames), "name": [(names or {}).get(c, f"종목{c}") for c in frames],
        "market": "KOSDAQ", "market_cap": 1e12, "value": np.nan, "traded_at": pd.NaT, "market_open": False,
    }).set_index("code", drop=False)
    rs_tab = pd.DataFrame({c: pd.Series(float(rs[c]), index=idx) for c in frames})
    return UniverseData(universe=uni, ohlcv=frames, index={}, market={}, rs=rs_tab, asof=idx[-1])


@pytest.fixture(scope="module")
def synth():
    frames = {
        "S1": _up(1, last_jump=0.08), "S2": _up(2), "S3": _up(3), "S4": _up(4),   # 강한 업종
        "W1": _down(11), "W2": _down(12), "W3": _down(13), "W4": _down(14),       # 약한 업종
        "T1": _up(21), "T2": _up(22),                                               # 2종목 업종 → 제외
        "ILLQ": _up(31, vol=100),                                                   # 거래대금 미달 → 제외
    }
    rs = {"S1": 97, "S2": 93, "S3": 95, "S4": 90, "W1": 8, "W2": 12, "W3": 20, "W4": 5,
          "T1": 80, "T2": 85, "ILLQ": 99}
    ud = _ud(frames, rs, names={"S1": "엑시콘", "S3": "티에스이"})
    sm = pd.DataFrame({
        "code": ["S1", "S2", "S3", "S4", "W1", "W2", "W3", "W4", "T1", "T2", "ILLQ", "ZZZ"],
        "sector": ["반도체"] * 4 + ["제약"] * 4 + ["소형", "소형", "반도체", None],
        "themes": [["HBM", "CXL"], ["HBM"], ["CXL"], ["HBM", "CXL"],
                   ["바이오", "CXL"], ["바이오"], ["바이오"], ["바이오", "HBM"],
                   ["소수테마"], ["소수테마"], ["HBM"], ["CXL"]],
    })
    return ud, sm


def test_stock_metrics_filters_and_flags(synth):
    ud, _ = synth
    m = stock_metrics(ud)
    assert "ILLQ" not in m.index                          # 유동성 필터
    assert set(m.index) == {"S1", "S2", "S3", "S4", "W1", "W2", "W3", "W4", "T1", "T2"}
    assert bool(m.loc["S1", "big_up_today"]) and not m.loc["S2", "big_up_today"]
    assert bool(m.loc["S1", "new_high_20d"]) and not m.loc["W1", "new_high_20d"]
    assert m.loc["S1", "chg_1d"] == pytest.approx(0.08)


def test_tt_pass_matches_trend_template_evaluate(synth):
    ud, _ = synth
    cases = [(ud.ohlcv[c], ud.rs[c].iloc[-1]) for c in ("S1", "S2", "W1", "T1")]
    cases += [(_up(5), 50.0), (_up(6).iloc[-215:], 95.0)]    # RS 미달 · 이력 부족
    for df, rs in cases:
        ev = evaluate(make_context(df, rs=rs))
        got = tt_pass(df["close"].to_numpy(), df["high"].to_numpy(), df["low"].to_numpy(), rs)
        assert got == (ev["passed"] == 8), ev["checks"]
    assert any(tt_pass(ud.ohlcv[c]["close"].to_numpy(), ud.ohlcv[c]["high"].to_numpy(),
                       ud.ohlcv[c]["low"].to_numpy(), 95) for c in ("S1", "S2", "S3", "S4"))


def test_group_strength_ranks_strong_group_first(synth):
    ud, sm = synth
    gs = group_strength(ud, sm)
    assert set(STRENGTH_COLUMNS) <= set(gs.columns)
    assert list(gs["score"]) == sorted(gs["score"], reverse=True)
    key = {(r.kind, r.group): r for r in gs.itertuples()}
    assert ("업종", "소형") not in key and ("테마", "소수테마") not in key       # 유동 3종목 미만
    semi, pharma = key[("업종", "반도체")], key[("업종", "제약")]
    assert semi.members == 4 and semi.total_members == 5                       # ILLQ 는 구성에만
    assert semi.rank_pct == 1.0 and pharma.rank_pct == 0.0
    assert semi.score > pharma.score
    assert semi.median_rs == 94 and pharma.median_rs == 10
    assert semi.big_value_today == 1 and pharma.big_value_today == 0
    assert semi.new_highs_20d >= 3 and pharma.new_highs_20d == 0
    assert 0 < semi.tt_pass_pct <= 1 and pharma.tt_pass_pct == 0
    assert semi.leaders[0] == ["S1", "엑시콘"] and semi.leaders[1] == ["S3", "티에스이"]
    assert all(isinstance(x, list) and len(x) == 2 for x in semi.leaders)
    themes = gs[gs.kind == "테마"]
    assert set(themes.group) == {"HBM", "CXL", "바이오"}
    assert themes["rank_pct"].between(0, 1).all()
    assert themes.iloc[0]["group"] in {"HBM", "CXL"} and key[("테마", "바이오")].rank_pct == 0.0


def test_group_strength_degrades_gracefully(synth):
    ud, sm = synth
    for bad in (None, sd.empty_frame()):
        out = group_strength(ud, bad)
        assert out.empty and list(out.columns) == STRENGTH_COLUMNS
    # 매핑 종목이 하나도 유동 종목이 아님
    out = group_strength(ud, pd.DataFrame({"code": ["ZZZ"], "sector": ["x"], "themes": [["y"]]}))
    assert out.empty


def test_group_strength_skips_stale_last_bar(synth):
    ud, sm = synth
    frames = dict(ud.ohlcv)
    frames["S2"] = frames["S2"].iloc[:-3]                 # 거래정지로 최근 봉 없음
    ud2 = UniverseData(universe=ud.universe, ohlcv=frames, index={}, market={}, rs=ud.rs, asof=ud.asof)
    gs = group_strength(ud2, sm)
    assert gs.set_index(["kind", "group"]).loc[("업종", "반도체"), "members"] == 3


def test_stock_groups(synth):
    ud, sm = synth
    gs = group_strength(ud, sm)
    g = stock_groups("S1", sm, gs)
    assert g["sector"] == "반도체" and g["sector_rank_pct"] == 1.0
    assert [t[0] for t in g["themes"]] in (["HBM", "CXL"], ["CXL", "HBM"])
    assert g["themes"][0][1] >= g["themes"][1][1]
    assert g["best_rank_pct"] == 1.0
    w = stock_groups("W4", sm, gs)
    assert w["themes"][0][0] == "HBM" and w["themes"][-1][0] == "바이오"      # 강한 테마 먼저
    t = stock_groups("T1", sm, gs)                         # 소형 업종·소수테마는 순위 없음
    assert t["sector"] == "소형" and t["sector_rank_pct"] is None
    assert t["themes"] == [] and t["themes_all"] == ["소수테마"] and t["best_rank_pct"] is None
    none = stock_groups("NOPE", sm, gs)
    assert none == {"sector": None, "sector_rank_pct": None, "themes": [], "themes_all": [],
                    "best_rank_pct": None}
    assert stock_groups("S1", None, None)["sector"] is None
    no_strength = stock_groups("S1", sm, None)
    assert no_strength["sector"] == "반도체" and no_strength["sector_rank_pct"] is None
    assert no_strength["themes_all"] == ["HBM", "CXL"]


def test_custom_config_min_members(synth):
    ud, sm = synth
    gs = group_strength(ud, sm, scfg=SectorConfig(min_members=2))
    assert ("업종", "소형") in set(zip(gs.kind, gs.group))


def test_group_url_from_mapping_attrs(synth):
    ud, sm = synth
    sm = sm.copy()
    sm.attrs["group_no"] = {"업종": {"반도체": 278}, "테마": {"HBM": 536}}
    gs = group_strength(ud, sm).set_index(["kind", "group"])
    assert gs.loc[("업종", "반도체"), "url"] == "https://stock.naver.com/market/stock/kr/industry/278"
    assert gs.loc[("테마", "HBM"), "url"] == "https://stock.naver.com/market/stock/kr/theme/536"
    assert gs.loc[("업종", "제약"), "url"] is None
