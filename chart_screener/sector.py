"""업종·테마(그룹) 상대강도 — 주도 업종·테마와 그 대장주.

    from chart_screener.data.sector import load_sector_map
    sm = load_sector_map(offline=True)
    gs = group_strength(ud, sm)                  # 그룹별 강도 표 (점수 내림차순)
    stock_groups("092870", sm, gs)               # {'sector': '반도체와반도체장비', 'sector_rank_pct': 0.97, ...}

    python -m chart_screener.sector --top 15    # 오늘의 강한 업종·테마 출력

구성 종목은 스캔과 같은 유동성 필터(주가 1,000원·20일 평균 거래대금 10억·시총 500억 이상,
``passes_universe_filter``)를 통과하고 마지막 봉이 기준일(ud.asof)인 종목만 센다.
유동 종목이 ``min_members``(3) 미만인 그룹은 통계가 무의미해 제외한다.

그룹 지표 (유동 구성 종목 기준)
    median_rs       RS 레이팅 중앙값 (1~99)
    tt_pass_pct     미너비니 트렌드 템플릿 8개 기준 모두 충족 비율 (patterns.trend_template 과 같은 규칙,
                    이동평균은 마지막 봉에서만 numpy 로 계산해 빠르게)
    new_highs_20d   최근 20봉 안에 52주(252봉) 신고가를 낸 종목 수
    big_value_today 오늘 거래대금 300억↑ 이면서 +3%↑ 상승 마감한 종목 수 (자금 유입)
    ret_20d         20일 수익률 중앙값 (점수의 '단기 시세' 항목)
그룹 점수 (0~100, 가중치는 SectorConfig)
    소규모 그룹의 우연한 극단값을 누르기 위해 각 지표를 '유동 전 종목 평균(중앙값)'으로 ``prior_members``(5)
    종목만큼 끌어당긴(베이지안 수축) 뒤 가중 합산한다.
      35 × (RS중앙값-1)/98 + 20 × 템플릿 충족 비율 + 20 × min(1, 신고가 비율/0.3)
      + 15 × (20일 수익률 중앙값의 전 종목 백분위) + 10 × min(1, 300억↑ 상승 비율/0.2)
    단기 시세 항목은 V자 반등 중인 그룹(템플릿 미충족이 많음)의 순환매를 놓치지 않기 위해 넣었다
    (2026-10-07: 반도체 장비 그룹은 RS 91·20일 +27% 인데 52주 고점 -25% 밖 종목이 많아 템플릿 충족 17%).
    rank_pct = 같은 종류(업종/테마) 안에서의 점수 백분위 (0~1, 1 = 가장 강함, 꼴찌 = 0).
대장주(leaders): RS 레이팅 → 20일 수익률 순 상위 5개 [코드, 종목명].
부가 컬럼: total_members(매핑상 전체 구성 수), tt_pass(템플릿 충족 수), chg_1d(당일 등락률 중앙값),
           ret_20d, url(네이버 그룹 페이지, 매핑에 그룹 번호가 있을 때).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import Config
from .patterns.trend_template import TrendTemplateConfig
from .universe_data import build_context, passes_universe_filter

KIND_SECTOR, KIND_THEME = "업종", "테마"
STRENGTH_COLUMNS = ["group", "kind", "members", "median_rs", "tt_pass_pct", "new_highs_20d",
                    "big_value_today", "score", "rank_pct", "leaders",
                    # 부가 정보
                    "total_members", "tt_pass", "chg_1d", "ret_20d", "url"]
_NAVER_GROUP_URL = "https://stock.naver.com/market/stock/kr/{kind}/{no}"
_URL_KIND = {KIND_SECTOR: "industry", KIND_THEME: "theme"}


@dataclass
class SectorConfig:
    min_members: int = 3              # 유동 구성 종목이 이 미만인 그룹은 제외
    prior_members: float = 5.0        # 수축 강도: 전 종목 평균을 이 종목 수만큼 섞음
    high_window: int = 252            # 52주 신고가 기준 봉 수
    new_high_window: int = 20         # 최근 이 봉 수 안의 신고가를 센다
    big_change_min: float = 0.03      # 300억↑ 거래 종목 중 이 이상 상승 마감만 '자금 유입'으로 센다
    w_rs: float = 35.0                # 점수 가중치: RS 중앙값
    w_tt: float = 20.0                #   트렌드 템플릿 충족 비율
    w_nh: float = 20.0                #   신고가 비율
    w_mom: float = 15.0               #   20일 수익률 중앙값의 전 종목 백분위 (그룹 단기 시세)
    w_big: float = 10.0               #   300억↑ 상승 비율 (당일 자금 유입)
    nh_full: float = 0.3              # 신고가 비율이 이 이상이면 만점
    big_full: float = 0.2             # 300억↑ 상승 비율이 이 이상이면 만점
    leaders: int = 5                  # 대장주 표시 수


def empty_strength() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype=object) for c in STRENGTH_COLUMNS})


# ---------------------------------------------------------------- 종목별 지표
def tt_pass(close: np.ndarray, high: np.ndarray, low: np.ndarray, rs: float | None,
            cfg: TrendTemplateConfig | None = None) -> bool:
    """마지막 봉 기준 트렌드 템플릿 8개 기준 모두 충족 여부 (trend_template.evaluate 와 같은 규칙)."""
    cfg = cfg or TrendTemplateConfig()
    d = cfg.sma200_rising_days
    if len(close) < 200 + d or rs is None or not rs >= cfg.rs_min:
        return False
    c = float(close[-1])
    s50, s150, s200 = close[-50:].mean(), close[-150:].mean(), close[-200:].mean()
    s200_prev = close[-200 - d:-d].mean()
    hi52, lo52 = float(np.max(high[-252:])), float(np.min(low[-252:]))
    return bool(c > s150 and c > s200 and s150 > s200 and s200 > s200_prev and s50 > s150 and s50 > s200
                and c > s50 and c >= lo52 * (1 + cfg.above_52w_low) and c >= hi52 * (1 - cfg.within_52w_high))


def stock_metrics(ud, cfg: Config | None = None, scfg: SectorConfig | None = None) -> pd.DataFrame:
    """유동성 필터를 통과한 종목별 지표 표 (index=code).

    컬럼: name, market, rs, tt_pass, new_high_20d, big_up_today, chg_1d, ret_20d, value_today"""
    cfg = cfg or Config()
    scfg = scfg or SectorConfig()
    tt_cfg = cfg.pattern_cfg("trend_template", TrendTemplateConfig)
    big = cfg.big_value_threshold
    asof = getattr(ud, "asof", None)
    rows = {}
    for code in ud.ohlcv:
        ctx = build_context(code, ud, cfg)
        if ctx is None or ctx.n < 2:
            continue
        if asof is not None and ctx.df.index[-1] != asof:
            continue   # 거래정지 등으로 오늘 봉이 없는 종목
        if not passes_universe_filter(ctx)[0]:
            continue
        c = ctx.close.to_numpy(dtype=float)
        h = ctx.high.to_numpy(dtype=float)
        lo = ctx.low.to_numpy(dtype=float)
        chg = c[-1] / c[-2] - 1 if c[-2] > 0 else np.nan
        value = float(ctx.value.iloc[-1])
        hw = h[-scfg.high_window:]
        rows[code] = {
            "name": ctx.name, "market": ctx.market, "rs": ctx.rs_rating,
            "tt_pass": tt_pass(c, h, lo, ctx.rs_rating, tt_cfg),
            "new_high_20d": bool(len(hw) and np.max(hw[-scfg.new_high_window:]) >= np.max(hw)),
            "big_up_today": bool(value >= big and chg >= scfg.big_change_min),
            "chg_1d": chg,
            "ret_20d": c[-1] / c[-21] - 1 if len(c) > 20 and c[-21] > 0 else np.nan,
            "value_today": value,
        }
    df = pd.DataFrame.from_dict(rows, orient="index")
    if df.empty:
        return pd.DataFrame(columns=["name", "market", "rs", "tt_pass", "new_high_20d", "big_up_today",
                                     "chg_1d", "ret_20d", "value_today"])
    df["rs"] = pd.to_numeric(df["rs"], errors="coerce")
    df.index.name = "code"
    return df


# ---------------------------------------------------------------- 그룹 강도
def _memberships(sector_map: pd.DataFrame) -> pd.DataFrame:
    """sector_map → (code, kind, group) 긴 표."""
    if sector_map is None or len(sector_map) == 0:
        return pd.DataFrame(columns=["code", "kind", "group"])
    recs = []
    for code, sec, themes in zip(sector_map["code"], sector_map["sector"], sector_map["themes"]):
        if isinstance(sec, str) and sec:
            recs.append((code, KIND_SECTOR, sec))
        if isinstance(themes, (list, tuple, np.ndarray)):
            for t in dict.fromkeys(themes):
                if isinstance(t, str) and t:
                    recs.append((code, KIND_THEME, t))
    return pd.DataFrame(recs, columns=["code", "kind", "group"])


def _rank_pct(scores: pd.Series) -> pd.Series:
    """점수 백분위 0~1 (1 = 최고, 꼴찌 = 0, 동점은 평균 순위). 그룹이 하나면 1."""
    n = len(scores)
    if n <= 1:
        return pd.Series(1.0, index=scores.index)
    return (scores.rank(method="average") - 1) / (n - 1)


def group_strength(ud, sector_map: pd.DataFrame | None, cfg: Config | None = None,
                   scfg: SectorConfig | None = None, metrics: pd.DataFrame | None = None) -> pd.DataFrame:
    """업종·테마별 강도 표 (점수 내림차순, 그룹당 한 행). 컬럼은 ``STRENGTH_COLUMNS``.

    metrics 를 주면(stock_metrics 결과) 종목별 계산을 건너뛴다."""
    scfg = scfg or SectorConfig()
    mem = _memberships(sector_map)
    if mem.empty:
        return empty_strength()
    m = metrics if metrics is not None else stock_metrics(ud, cfg, scfg)
    if m.empty:
        return empty_strength()
    total = mem.groupby(["kind", "group"]).size()
    j = mem.join(m, on="code", how="inner")
    if j.empty:
        return empty_strength()

    # 수축용 사전값: 유동 전 종목의 평균(RS·수익률은 중앙값)
    k = scfg.prior_members
    rs_all = m["rs"].dropna()
    ret_all = np.sort(m["ret_20d"].dropna().to_numpy(dtype=float))
    prior = {
        "rs": float(rs_all.median()) if len(rs_all) else 50.0,
        "ret": float(np.median(ret_all)) if len(ret_all) else 0.0,
        "tt": float(m["tt_pass"].mean()),
        "nh": float(m["new_high_20d"].mean()),
        "big": float(m["big_up_today"].mean()),
    }

    def shrink(x: float, n: int, p: float) -> float:
        return (n * (x if x == x else p) + k * p) / (n + k)

    group_no = (sector_map.attrs.get("group_no") or {}) if sector_map is not None else {}
    j = j.sort_values(["rs", "ret_20d"], ascending=False, na_position="last")
    recs = []
    for (kind, group), g in j.groupby(["kind", "group"], sort=False):
        n = len(g)
        if n < scfg.min_members:
            continue
        rs_med = float(g["rs"].median()) if g["rs"].notna().any() else np.nan
        ret_med = float(g["ret_20d"].median()) if g["ret_20d"].notna().any() else np.nan
        tt, nh, big = int(g["tt_pass"].sum()), int(g["new_high_20d"].sum()), int(g["big_up_today"].sum())
        rs_s = shrink(rs_med, n, prior["rs"])
        ret_s = shrink(ret_med, n, prior["ret"])
        mom = float(np.searchsorted(ret_all, ret_s, side="right") / len(ret_all)) if len(ret_all) else 0.5
        score = (scfg.w_rs * (rs_s - 1) / 98
                 + scfg.w_tt * shrink(tt / n, n, prior["tt"])
                 + scfg.w_nh * min(1.0, shrink(nh / n, n, prior["nh"]) / scfg.nh_full)
                 + scfg.w_mom * mom
                 + scfg.w_big * min(1.0, shrink(big / n, n, prior["big"]) / scfg.big_full))
        recs.append({
            "group": group, "kind": kind, "members": n,
            "median_rs": rs_med, "tt_pass_pct": tt / n, "new_highs_20d": nh, "big_value_today": big,
            "score": round(float(score), 2), "rank_pct": np.nan,
            "leaders": [[c, str(nm)] for c, nm in zip(g["code"].iloc[:scfg.leaders], g["name"].iloc[:scfg.leaders])],
            "total_members": int(total.get((kind, group), n)), "tt_pass": tt,
            "chg_1d": float(g["chg_1d"].median()), "ret_20d": ret_med,
            "url": (_NAVER_GROUP_URL.format(kind=_URL_KIND[kind], no=group_no[kind][group])
                    if group in group_no.get(kind, {}) else None),
        })
    if not recs:
        return empty_strength()
    out = pd.DataFrame(recs, columns=STRENGTH_COLUMNS)
    out["rank_pct"] = out.groupby("kind")["score"].transform(_rank_pct).astype(float)
    out = out.sort_values(["score", "members"], ascending=[False, False]).reset_index(drop=True)
    return out


# ---------------------------------------------------------------- 종목 → 그룹
def stock_groups(code: str, sector_map: pd.DataFrame | None, strength: pd.DataFrame | None) -> dict:
    """한 종목의 업종·테마와 각 그룹의 강도 백분위.

    반환: {'sector': 업종|None, 'sector_rank_pct': float|None,
           'themes': [[테마, rank_pct], ...] (강한 순, 순위가 있는 테마만),
           'themes_all': [테마, ...] (소속 테마 전체), 'best_rank_pct': float|None}"""
    out = {"sector": None, "sector_rank_pct": None, "themes": [], "themes_all": [], "best_rank_pct": None}
    if sector_map is None or len(sector_map) == 0:
        return out
    row = sector_map[sector_map["code"] == code]
    if row.empty:
        return out
    sec = row["sector"].iloc[0]
    themes = row["themes"].iloc[0]
    out["sector"] = sec if isinstance(sec, str) and sec else None
    out["themes_all"] = [t for t in themes if isinstance(t, str)] if isinstance(themes, (list, tuple, np.ndarray)) else []

    rank: dict[tuple[str, str], float] = {}
    if strength is not None and len(strength):
        rank = {(k, g): float(r) for k, g, r in zip(strength["kind"], strength["group"], strength["rank_pct"])
                if r == r}
    if out["sector"] is not None:
        out["sector_rank_pct"] = rank.get((KIND_SECTOR, out["sector"]))
    ranked = [[t, rank[(KIND_THEME, t)]] for t in out["themes_all"] if (KIND_THEME, t) in rank]
    ranked.sort(key=lambda x: -x[1])
    out["themes"] = ranked
    cands = [r for r in [out["sector_rank_pct"], *(t[1] for t in ranked)] if r is not None]
    out["best_rank_pct"] = max(cands) if cands else None
    return out


# ---------------------------------------------------------------- CLI
def _fmt_row(i: int, r) -> str:
    leaders = ", ".join(nm for _, nm in r["leaders"])
    return (f"{i:>3}. {r['group'][:20]:<20} {r['members']:>3}종목  RS {r['median_rs']:>3.0f}  "
            f"템플릿 {r['tt_pass_pct']:>4.0%}  신고가 {r['new_highs_20d']:>2}  300억↑ {r['big_value_today']:>2}  "
            f"20일 {r['ret_20d']:>+6.1%}  점수 {r['score']:>5.1f}  | {leaders}")


def main(argv: list[str] | None = None) -> None:
    from .data.sector import load_sector_map
    from .universe_data import load_universe_data

    ap = argparse.ArgumentParser(prog="python -m chart_screener.sector", description="강한 업종·테마 순위")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--offline", action="store_true", help="캐시만 사용")
    ap.add_argument("--refresh", action="store_true", help="업종·테마 구성을 새로 받음")
    a = ap.parse_args(argv)
    sm = load_sector_map(refresh=a.refresh, offline=a.offline)
    if sm.empty:
        print("업종·테마 매핑이 없습니다. 온라인으로 한 번 실행하세요.", file=sys.stderr)
        return
    ud = load_universe_data(offline=a.offline)
    gs = group_strength(ud, sm)
    fetched = sm.attrs.get("fetched_at")
    print(f"기준일 {ud.asof:%Y-%m-%d} · 업종·테마 구성 {pd.Timestamp(fetched):%Y-%m-%d} 기준"
          if fetched is not None else f"기준일 {ud.asof:%Y-%m-%d}")
    for kind in (KIND_SECTOR, KIND_THEME):
        g = gs[gs["kind"] == kind].reset_index(drop=True)
        print(f"\n[{kind}] 상위 {min(a.top, len(g))} / {len(g)}개 그룹")
        for i, r in g.head(a.top).iterrows():
            print(_fmt_row(i + 1, r))


if __name__ == "__main__":
    main()
