import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # 프로젝트 루트
"""《차트의 기술》 6기법 기준 성적(base rate) — 우리 캐시(약 3년)로 잰 과거 신호 성과. 확률 · 추천이 아니다.

    python scripts/bt_techniques.py [--out DIR] [--patterns a,b] [--workers N] [--reuse]

- 신호: backtest.run_backtest 그대로(미래 참조 없음 — 날짜 t 까지 자른 자료로 detect, 신호일 = 판정이 처음 알려지는 봉
  backtest.event_date, t 시점 유동성 필터). 10% 주도주만 stage 모드(near_pivot = 신호 봉, step 1).
- 진입 두 가지를 모두 잰다: 'close' = 신호 봉 종가, 'open' = 다음 봉 시가(백테스트 기본). 기법이 정한 쪽을 '주' 로 보인다(PLAN).
- 수익 = 신호 봉 t 뒤 h 봉(종목 자기 봉) 종가 / 진입 − 1. MFE · MAE = t+1 … t+h 고가 최고 · 저가 최저 / 진입 − 1.
- 초과 = 수익 − 같은 날 유동성 필터(주가 ≥ 1,000 · 20일 평균 거래대금 ≥ 10억 · 이력 ≥ 260봉)를 통과한 전 종목의
  같은 구간(시장 달력 t → t+h, 진입 방식 같음) 수익 중앙값.
- 임계값은 바꾸지 않는다 — 이 결과로 규칙을 고치지 않는다(데이터 스누핑 금지). 거래비용 · 슬리피지 미반영, 현재 상장 종목만(생존 편향).
"""
import argparse
import json
import math
import time
import warnings

import numpy as np
import pandas as pd

from chart_screener import technique_panel
from chart_screener.backtest import BacktestConfig, run_backtest
from chart_screener.config import OUTPUT_DIR, Config
from chart_screener.universe_data import load_universe_data

HZ = (5, 20, 60)
# 패턴: (모드, stages, 주 진입, 주 진입 근거)
PLAN = {
    "red_three_monthly": ("breakout_day", ("breakout",), "open",
                          "기법에 진입 규칙 없음 — 백테스트 기본(확정 봉 = 다음 달 첫 거래일, 그다음 날 시가)"),
    "fib_pullback": ("breakout_day", ("breakout",), "close", "신호 봉 종가 (영상 [27:00, 51:00] 종가 매수)"),
    "trendline_break": ("breakout_day", ("breakout",), "close",
                        "안착 확인 봉 종가 (패턴 체크리스트 · 청산 계획의 진입가 — 확인 전엔 사지 않음)"),
    "trendline_fib": ("breakout_day", ("breakout",), "close", "신호 봉 종가 (영상 [27:00, 51:00] 종가 매수)"),
    "day_leader": ("stage", ("near_pivot",), "open",
                   "다음 날(관찰일) 시가 — 영상의 3분봉 진입이 아님(분봉 자료 없음), 일봉 대용"),
    "ma60_supply": ("breakout_day", ("breakout",), "close",
                    "기법에 진입 규칙 없음 — 패턴 체크리스트의 진입가(돌파 봉 종가)"),
}
LABEL = {"red_three_monthly": "월봉 적삼병", "fib_pullback": "피보나치 눌림 반등", "trendline_break": "빗각 추세선 돌파",
         "trendline_fib": "빗각 돌파 + 피보 눌림", "day_leader": "10% 주도주 (단타 관찰)", "ma60_supply": "60일선 수급 돌파"}


def _upto(df: pd.DataFrame, until) -> pd.DataFrame:
    return df.loc[:pd.Timestamp(until)] if until else df


def panels(ud, cfg: Config, min_bars: int, until=None):
    """시장 달력(전 종목 날짜 합집합) × 종목 종가 · 시가 · 유동성 통과 여부. until 뒤 봉(장중 미완성 등)은 뺀다."""
    C, O, E = {}, {}, {}
    for code, df in ud.ohlcv.items():
        df = _upto(df, until)
        if df.empty:
            continue
        c = df["close"].astype(float)
        v20 = df["value"].rolling(20).mean()
        pos = pd.Series(np.arange(len(df)), index=df.index)
        C[code], O[code] = c, df["open"].astype(float)
        E[code] = (c >= cfg.universe.min_price) & (v20 >= cfg.universe.min_avg_value_20d) & (pos >= min_bars)
    C, O = pd.concat(C, axis=1).sort_index(), pd.concat(O, axis=1).sort_index()
    E = pd.concat(E, axis=1).reindex(C.index).eq(True)       # 거래 없는 날(NaN) = 통과 아님
    return C, O, E


def bench(C: pd.DataFrame, O: pd.DataFrame, E: pd.DataFrame) -> dict:
    """{(진입, h): (중앙값 Series, 평균 Series, 종목 수 Series, 전체 표본 1차원 배열)} — 날짜 = 신호일 t."""
    out = {}
    o1 = O.shift(-1)
    for h in HZ:
        ch = C.shift(-h)
        for kind, base in (("close", C), ("open", o1.where(o1 > 0))):
            R = (ch / base - 1).where(E)
            a = R.to_numpy()
            with warnings.catch_warnings():          # 끝 h 봉은 미래가 없어 전부 NaN — 그 날은 기준 없음
                warnings.simplefilter("ignore", RuntimeWarning)
                med = pd.Series(np.nanmedian(np.where(np.isfinite(a), a, np.nan), axis=1), index=R.index)
            out[(kind, h)] = (med, R.mean(axis=1), R.notna().sum(axis=1), R)
    return out


def enrich(ev: pd.DataFrame, ud, B: dict, until=None) -> pd.DataFrame:
    rows = []
    for _, e in ev.iterrows():
        df = _upto(ud.ohlcv[e["code"]], until)
        d = pd.Timestamp(e["date"])
        t = df.index.get_loc(d)
        o, h, l, c = (df[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        n = len(df)
        ent = {"close": c[t], "open": float(e["entry"])}
        r = {"code": e["code"], "date": e["date"], "stage": e["stage"], "outcome": e.get("outcome"),
             "has_stop": e.get("has_stop"), "entry_close": ent["close"], "entry_open": ent["open"]}
        for hz in HZ:
            j = t + hz
            for kind, x in ent.items():
                k = f"{kind}_{hz}"
                if j < n and x > 0:
                    r[f"ret_{k}"] = c[j] / x - 1
                    r[f"mfe_{k}"] = h[t + 1:j + 1].max() / x - 1
                    r[f"mae_{k}"] = l[t + 1:j + 1].min() / x - 1
                    bm = B[(kind, hz)][0].get(d, np.nan)
                    r[f"bm_{k}"] = bm
                    r[f"xs_{k}"] = r[f"ret_{k}"] - bm if np.isfinite(bm) else np.nan
                else:
                    for p in ("ret", "mfe", "mae", "bm", "xs"):
                        r[f"{p}_{k}"] = np.nan
            # 인프라 수익(다음 봉 시가 진입)과 같은지 — 같은 자료 · 같은 식
            if "ret_" + str(hz) in e and np.isfinite(e[f"ret_{hz}"]) and np.isfinite(r[f"ret_open_{hz}"]):
                assert abs(e[f"ret_{hz}"] - r[f"ret_open_{hz}"]) < 1e-9, (e["code"], e["date"], hz)
        rows.append(r)
    return pd.DataFrame(rows)


def _r(x, k=2):
    return None if x is None or not np.isfinite(x) else round(float(x) * 100, k)


def summary(en: pd.DataFrame, kind: str) -> list[dict]:
    out = []
    for hz in HZ:
        k = f"{kind}_{hz}"
        m = en[f"ret_{k}"].notna() & en[f"xs_{k}"].notna()
        x = en.loc[m]
        if not len(x):
            out.append({"h": hz, "n": 0})
            continue
        ret, xs = x[f"ret_{k}"], x[f"xs_{k}"]
        # 날짜 묶음: 같은 날 신호끼리 평균 → 날짜 평균 · 대략 95% 구간(날짜 사이 독립 가정 — 겹치는 보유기간 때문에 실제보다 좁다)
        dm = xs.groupby(x["date"]).mean()
        se = dm.std(ddof=1) / math.sqrt(len(dm)) if len(dm) > 1 else np.nan
        out.append({
            "h": hz, "n": int(len(x)), "dates": int(x["date"].nunique()), "codes": int(x["code"].nunique()),
            "mean": _r(ret.mean()), "median": _r(ret.median()), "win": _r((ret > 0).mean(), 1),
            "xs_mean": _r(xs.mean()), "xs_median": _r(xs.median()), "xs_win": _r((xs > 0).mean(), 1),
            "xs_date_mean": _r(dm.mean()), "xs_date_ci": [_r(dm.mean() - 1.96 * se), _r(dm.mean() + 1.96 * se)],
            "mfe_median": _r(x[f"mfe_{k}"].median()), "mae_median": _r(x[f"mae_{k}"].median()),
            "mfe_mean": _r(x[f"mfe_{k}"].mean()), "mae_mean": _r(x[f"mae_{k}"].mean()),
        })
    return out


def by_year(en: pd.DataFrame, kind: str, hz: int = 20) -> dict:
    k = f"{kind}_{hz}"
    x = en[en[f"xs_{k}"].notna()]
    g = x.groupby(x["date"].str[:4])
    return {y: {"n": int(len(v)), "xs_median": _r(v[f"xs_{k}"].median()), "xs_mean": _r(v[f"xs_{k}"].mean())}
            for y, v in g}


def baseline(B: dict, since: pd.Timestamp, last_sig: pd.Timestamp) -> dict:
    out = {}
    for (kind, hz), (_, _, _, R) in B.items():
        a = R.loc[(R.index >= since) & (R.index <= last_sig)].to_numpy().ravel()
        a = a[np.isfinite(a)]
        out[f"{kind}_{hz}"] = {"n": int(len(a)), "mean": _r(a.mean()), "median": _r(np.median(a)),
                               "win": _r((a > 0).mean(), 1)}
    return out


def _read_events(path: pathlib.Path) -> pd.DataFrame:
    """이벤트 CSV → 표. 신호 0건으로 쓴 파일(빈 줄뿐 — 열 없음)은 빈 표."""
    try:
        return pd.read_csv(path, dtype={"code": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUTPUT_DIR / "bt_techniques"))
    ap.add_argument("--patterns", default=",".join(PLAN))
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--reuse", action="store_true", help="이미 있는 이벤트 CSV 를 다시 쓴다(신호 재계산 안 함)")
    ap.add_argument("--codes", default="", help="시험용 종목 제한 (쉼표 구분)")
    ap.add_argument("--until", default="", help="이 날짜(포함)까지의 봉만 (기본: 캐시의 마지막 완성 봉 — 장중 미완성 봉 뺌)")
    a = ap.parse_args()
    codes = [c for c in a.codes.split(",") if c] or None
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    pats = [p for p in a.patterns.split(",") if p]
    cfg = Config()
    ud = load_universe_data(cfg, offline=True, verbose=False)
    eod = technique_panel.eod_asof(ud)
    until = a.until or (f"{eod:%Y-%m-%d}" if eod is not None else None)
    print(f"캐시 마지막 봉 {ud.asof:%Y-%m-%d} · 완성 봉 기준 until = {until}", flush=True)
    events = {}
    for p in pats:
        path = out / f"events_{p}.csv"
        mode, stages, _, _ = PLAN[p]
        if a.reuse and path.exists():
            events[p] = _read_events(path)
            print(f"[{p}] 재사용 {len(events[p])}건")
            continue
        t0 = time.time()
        bt = BacktestConfig(pattern=p, mode=mode, step=1, horizons=HZ, stages=stages, until=until)
        ev = run_backtest(bt, workers=a.workers, codes=codes)
        ev.to_csv(path, index=False, encoding="utf-8-sig")
        # 신호 0건이면 to_csv 가 빈 줄만 써서 read_csv 가 EmptyDataError — 빈 표는 그대로 둔다(다른 패턴 요약은 계속)
        events[p] = _read_events(path) if not ev.empty else ev
        print(f"[{p}] 신호 {len(ev)}건 · {time.time() - t0:.0f}초", flush=True)

    min_bars = BacktestConfig(pattern="x").min_bars
    C, O, E = panels(ud, cfg, min_bars, until)
    B = bench(C, O, E)
    first = min(d.index[0] for d in ud.ohlcv.values())
    since = pd.Timestamp((first + pd.tseries.offsets.BDay(min_bars)).date())
    res = {"asof": str(ud.asof.date()), "until": until, "data_first": str(first.date()), "since": str(since.date()),
           "stocks": len(ud.ohlcv), "patterns": {}}
    for p in pats:
        ev = events[p]
        if ev.empty:
            res["patterns"][p] = {"n_events": 0}
            continue
        en = enrich(ev, ud, B, until)
        en.to_csv(out / f"enriched_{p}.csv", index=False, encoding="utf-8-sig")
        prim = PLAN[p][2]
        alt = "open" if prim == "close" else "close"
        st = en[en["has_stop"].astype(bool)] if "has_stop" in en else en.iloc[:0]
        res["patterns"][p] = {
            "label": LABEL[p], "n_events": int(len(en)), "first": en["date"].min(), "last": en["date"].max(),
            "codes": int(en["code"].nunique()), "dates": int(en["date"].nunique()),
            "stages": {str(k): int(v) for k, v in en["stage"].value_counts().items()},
            "entry": prim, "entry_why": PLAN[p][3], "primary": summary(en, prim), "alt": summary(en, alt),
            "by_year_20": by_year(en, prim),
            "stop": ({"n": int(len(st)), "stop": _r((st["outcome"] == "stop").mean(), 1),
                      "target": _r((st["outcome"] == "target").mean(), 1)} if len(st) else None),
        }
    last_sig = pd.Timestamp(max((str(v["last"]) for v in res["patterns"].values() if v.get("last")), default=None)
                            or ud.asof)
    res["baseline"] = baseline(B, since, last_sig)
    (out / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, default=str)[:4000])
    print(f"요약: {out / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
