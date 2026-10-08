"""보컬(김형준) 눌림목 깔때기 — 전 시장 단면 계산 (patterns/vocal.py 가 종목마다 결과를 읽는다).

    from chart_screener.vocal import prepare
    res = prepare(ud, sector_map)        # {code: 깔때기 결과 dict} — scanner.run_scan 이 ctx.info["vocal"] 로 넣는다

① 거래대금 상위(최근 30거래일 안 하루라도 150위 안) → ② 강한 테마(테마 점유율이 앞 20일 평균의 2배↑ · 풀 안 멤버 3곳↑,
점유율 배수 · 멤버 5일 수익 · 60일 신고가 멤버 수 순위 합 상위 10) → ③ 대장주(테마 시작일부터 거래대금 합 1·2위이면서
수익률도 테마 안 2위 안) → ④ 큰 상승(최근 40봉 고점이 그 앞 60봉 바닥보다 +30%↑, 바닥 → 고점 20봉 안, 상승 중 순위 안 2일↑)
→ ⑤ 눌림(고점 뒤 2~15봉, 종가 −8~−35%, 상승 폭 80% 넘게 되돌리면 끝) → ⑥ 지지선(5·10·20일선 · 전고점 · 급등봉 시가 ·
급등봉 중간 · 50% 되돌림)에 ±2% 닿음 + 거래량 감소(앞 3봉 평균 ≤ 급등 최대봉의 40% · 상승 구간 평균의 70%)
→ ⑦ 재유입(거래대금이 앞 3봉 평균의 1.5배↑) + 양봉(몸통 1%↑, 종가 ≥ 전일) + 지지 지킴(저가 ≥ 지지선 −3%) + 5일선 위.
⑧ 진입 = 다음 날 시가, 손절 = 눌림 저점, 목표 = 직전 고점, 손익비 1.5↑.

규칙과 숫자는 기업추적 `보컬.py`(눌림목 모드)와 같다. 차이 — 거래대금은 Tech 일봉의 value 열(과거는 (고+저+종)/3 × 거래량
추정, 당일은 실제 집계), 테마는 Tech 의 네이버 테마 분류표(오늘 것). 그래서 숫자가 조금 다를 수 있다.
같게 맞춘 것 — 패널은 60봉 이상 종목(스캔 대상 120봉보다 짧은 신규 상장도 순위 · 테마 · 대장에 들어간다), 장중 미완성 봉은 빼고
어제까지로 잰다, 잡주 거르기(네이버 분기 재무: 부채비율 200%↑ · 큰 적자, 공시 위험 파일이 있으면 작전주 꼴 · 상폐 절차 ·
자금조달 잦음 · 관리종목 등)로 걸린 종목은 깔때기에서 뺀다(원본 보컬 탭의 기본 표시와 같게).

과거 검증(기업추적 도구/보컬_백테스트.py, 2013~2026 매 거래일, ⑦ 신호 · 대장 · 손익비 1.5↑ → 다음 날 시가 진입 · 규칙 청산):
신호 400건 중 보유 겹침 54건을 뺀 346거래 · 승률 31% · 거래당 평균 −2.4% · 20일 초과수익 −4.8%p — **손실**.
그래서 이 결과는 종합 점수 · 매수 계획 · 실시간 감시에 넣지 않고 후보 목록의 칩(관찰)으로만 쓴다.
"""
from __future__ import annotations

import json
import os
import statistics as st
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import CACHE_DIR


@dataclass
class VocalConfig:
    top: int = 150              # ① 거래대금 순위 (눌림목 모드)
    pool_days: int = 30         # ① 최근 이 거래일 안 하루라도 순위 안
    gain: float = 0.30          # ④ 바닥 → 고점 +30%↑
    rally_win: int = 40         # ④ 고점을 찾는 창
    base_win: int = 60          # ④ 고점 앞 바닥을 찾는 창
    rise_max: int = 20          # ④ 바닥 마지막 터치 → 고점 봉 수
    pull_lo: float = 0.08       # ⑤ 눌림 깊이(종가 기준) 하한
    pull_hi: float = 0.35       # ⑤ 상한
    days_lo: int = 2            # ⑤ 고점 뒤 봉 수 하한
    days_hi: int = 15           # ⑤ 상한
    retrace_max: float = 0.80   # ⑤ 상승 폭의 80% 넘게 되돌리면 끝
    touch: float = 0.02         # ⑥ 눌림 저점이 지지선 ±2% 안
    dry_peak: float = 0.40      # ⑥ 앞 3봉 평균 거래량 ≤ 급등 최대봉의 40%
    dry_rally: float = 0.70     # ⑥ … 이면서 상승 구간 평균의 70%
    reflow: float = 1.5         # ⑦ 거래대금이 앞 3봉 평균의 1.5배↑
    body: float = 0.01          # ⑦ 양봉 몸통 1%↑
    hold_below: float = 0.03    # ⑦ 신호봉 저가 ≥ 닿은 지지선 −3%
    rr_min: float = 1.5         # ⑧ 손익비
    theme_ratio: float = 2.0    # ② 테마 점유율 ÷ 앞 20일 평균
    theme_min: int = 3          # ② 풀 안 멤버 수
    theme_top: int = 10         # ② 강한 테마 = 순위 합 상위 10
    theme_cool: float = 1.2     # ② 테마 시작일 — 배수가 이 밑으로 식으면 끊긴 것
    ratio_days: int = 20        # ② 점유율 기준 일수
    tail: int = 200             # 단면 계산에 쓰는 최근 거래일 수 (속도)
    min_bars: int = 60          # 패널에 넣는 최소 봉 수 (원본 bars_from 의 min_n)
    debt_max: float = 200.0     # 잡주 — 부채비율 200%↑
    loss_roe: float = -10.0     # 잡주 — 최근 4분기 순손실이면서 ROE −10%↓
    fund_min: int = 2           # 잡주 — 24개월 안 CB · BW · 유상증자 · 제3자배정이 서로 다른 날 2번↑
    risk_path: str | None = None  # 공시 위험 파일(기업추적 .cache/공시목록/공시위험.json). 없으면 환경변수 CHART_SCREENER_RISK_JSON


# ---------------------------------------------------------------- 패널
class Panel:
    """전 종목 최근 tail 거래일. dates = 거래일(전 종목 합집합), codes 순서는 고정.
    V = 거래대금 행렬(날짜 × 종목, 봉 없으면 NaN), R = 그날 거래대금 순위(1..), 봉 없으면 큰 수."""

    def __init__(self, ohlcv: dict[str, pd.DataFrame], themes: dict[str, list[str]], tail: int = 200,
                 value_override: dict[str, tuple[pd.Timestamp, float]] | None = None):
        frames = {c: d for c, d in ohlcv.items() if d is not None and len(d)}
        idx = sorted(set().union(*[d.index[-tail:] for d in frames.values()])) if frames else []
        self.dates = pd.DatetimeIndex(idx)[-tail:]
        self.codes = list(frames)
        self.col = {c: k for k, c in enumerate(self.codes)}
        V = pd.DataFrame({c: d["value"].astype(float) for c, d in frames.items()}).reindex(self.dates)
        for c, (day, val) in (value_override or {}).items():
            if c in V.columns and day in V.index and val and val > 0:
                V.at[day, c] = float(val)
        self.V = V.to_numpy(dtype=float)
        vz = np.where(np.isfinite(self.V), self.V, -1.0)
        order = np.argsort(-vz, axis=1, kind="stable")
        R = np.empty_like(order)
        R[np.arange(order.shape[0])[:, None], order] = np.arange(1, order.shape[1] + 1)[None, :]
        self.R = np.where(np.isfinite(self.V), R, 10 ** 6)
        self.tot = np.nansum(self.V, axis=1)
        self.ohlcv = frames
        # 테마 → 패널 안 멤버
        self.theme_of: dict[str, list[str]] = {}
        self.members: dict[str, list[str]] = {}
        for code, ths in themes.items():
            if code in self.col and ths:
                self.theme_of[code] = list(ths)
                for t in ths:
                    self.members.setdefault(t, []).append(code)
        self.themes = list(self.members)
        if self.themes:
            M = np.zeros((len(self.codes), len(self.themes)))
            for ti, t in enumerate(self.themes):
                for m in self.members[t]:
                    M[self.col[m], ti] = 1.0
            Vz = np.nan_to_num(self.V)
            with np.errstate(divide="ignore", invalid="ignore"):
                self.share = (Vz @ M) / self.tot[:, None]            # 날짜 × 테마 점유율
        else:
            self.share = np.zeros((len(self.dates), 0))
        self.tpos = {t: k for k, t in enumerate(self.themes)}
        self._arr: dict[str, dict] = {}

    def ratio(self, ti: int, gi: int, n: int) -> float | None:
        """점유율 배수 — 오늘 ÷ 앞 n일 평균. 앞 n일이 없으면 None."""
        if gi < n:
            return None
        base = float(np.nanmean(self.share[gi - n:gi, ti]))
        return float(self.share[gi, ti]) / base if base > 0 else None

    def pool(self, gi: int, top: int, days: int) -> dict[str, int]:
        """최근 days 거래일 안 하루라도 top 안 → {code: 든 날 수}."""
        win = self.R[max(0, gi - days + 1):gi + 1] <= top
        cnt = win.sum(axis=0)
        return {self.codes[k]: int(cnt[k]) for k in np.nonzero(cnt)[0]}

    def in_rank(self, code: str, date, top: int) -> bool:
        gi = self.dates.get_indexer([date])[0]
        return bool(gi >= 0 and self.R[gi, self.col[code]] <= top)

    def arrays(self, code: str) -> dict:
        """종목 일봉 배열(그 종목 전체 이력) — o h l c v tv d."""
        if code not in self._arr:
            d = self.ohlcv[code]
            tv = d["value"].astype(float).to_numpy().copy()
            self._arr[code] = {"o": d["open"].to_numpy(float), "h": d["high"].to_numpy(float), "l": d["low"].to_numpy(float),
                               "c": d["close"].to_numpy(float), "v": d["volume"].to_numpy(float), "tv": tv, "d": d.index}
        return self._arr[code]

    def loc(self, code: str, gi: int) -> int | None:
        """패널 날짜 번호 gi → 그 종목의 봉 번호(그날 봉이 없으면 None)."""
        a = self.arrays(code)
        j = a["d"].searchsorted(self.dates[gi])
        return int(j) if j < len(a["d"]) and a["d"][j] == self.dates[gi] else None


# ---------------------------------------------------------------- ② 강한 테마 · ③ 대장주
def theme_strength(P: Panel, gi: int, cfg: VocalConfig, pool: dict | None = None) -> list[dict]:
    """강한 테마(순위 합 상위 theme_top) — [{theme, ratio, r5, nh, n, n_pool, score, start}]."""
    if gi < cfg.ratio_days:
        return []
    pool = pool if pool is not None else P.pool(gi, cfg.top, cfg.pool_days)
    cand = []
    for t in P.themes:
        ms = P.members[t]
        if len(ms) < 2:
            continue
        ratio = P.ratio(P.tpos[t], gi, cfg.ratio_days)
        if ratio is None:
            continue
        n_pool = sum(1 for m in ms if m in pool)
        if not (ratio >= cfg.theme_ratio and n_pool >= cfg.theme_min):
            continue
        r5, nh, n = [], 0, 0
        for m in ms:
            j = P.loc(m, gi)
            if j is None or j < 60:
                continue
            a = P.arrays(m)
            n += 1
            if a["c"][j - 5] > 0:
                r5.append(a["c"][j] / a["c"][j - 5] - 1)
            if a["c"][j] >= a["h"][j - 59:j].max():
                nh += 1
        if n < 2:
            continue
        cand.append({"theme": t, "ratio": ratio, "n_pool": n_pool, "n": n, "share": float(P.share[gi, P.tpos[t]] * 100),
                     "r5": st.median(r5) * 100 if r5 else None, "nh": nh})
    for key in ("ratio", "r5", "nh"):                 # 순위(큰 쪽이 1위, 같은 값은 같은 순위)
        order = sorted((r for r in cand if r.get(key) is not None), key=lambda r: -r[key])
        rank, prev = 0, None
        for k, r in enumerate(order):
            if r[key] != prev:
                rank, prev = k + 1, r[key]
            r["_" + key] = rank
    for r in cand:
        r["score"] = sum(r.get("_" + k, len(cand)) for k in ("ratio", "r5", "nh"))
    strong = sorted(cand, key=lambda r: r["score"])[:cfg.theme_top]
    for r in strong:
        r["start"] = theme_start(P, P.tpos[r["theme"]], gi, cfg)
    return strong


def theme_start(P: Panel, ti: int, gi: int, cfg: VocalConfig) -> int:
    """테마가 움직이기 시작한 날 — 오늘부터 거슬러 배수가 theme_cool 밑으로 식지 않은 구간 안에서 theme_ratio 를 처음 넘은 날."""
    start = gi
    for k in range(gi, max(0, gi - cfg.pool_days) - 1, -1):
        r = P.ratio(ti, k, cfg.ratio_days)
        if r is None or r < cfg.theme_cool:
            break
        if r >= cfg.theme_ratio:
            start = k
    return start


def leaders(P: Panel, theme: str, start: int, gi: int) -> list[dict]:
    """테마 시작일부터 거래대금 합 1·2위 가운데 수익률도 테마 안 2위 안 → [대장, 부대장] (없으면 짧게)."""
    rows = []
    d0 = P.dates[start]
    for m in P.members.get(theme, []):
        j = P.loc(m, gi)
        if j is None:
            continue
        a = P.arrays(m)
        s = int(a["d"].searchsorted(d0))
        if s >= len(a["d"]) or s > j:
            continue
        j0 = max(0, s - 1)
        tvs = float(np.nansum(a["tv"][s:j + 1]))
        ret = (a["c"][j] / a["c"][j0] - 1) * 100 if a["c"][j0] else None
        rows.append({"code": m, "tv_sum": tvs, "ret": ret})
    if not rows:
        return []
    by_ret = sorted((r for r in rows if r["ret"] is not None), key=lambda r: -r["ret"])
    rank_ret = {r["code"]: k + 1 for k, r in enumerate(by_ret)}
    out = []
    for r in sorted(rows, key=lambda r: -r["tv_sum"])[:2]:     # 돈이 안 몰린 종목은 수익률이 높아도 대장이 아니다
        r["ret_rank"] = rank_ret.get(r["code"])
        if r["ret_rank"] is not None and r["ret_rank"] <= 2:
            r["role"] = "대장" if not out else "부대장"
            out.append(r)
    return out


class LeadHistory:
    """날짜별 대장주 · 강한 테마 — 눌림 중엔 테마가 식어 '오늘 대장'일 수 없으니 급등 구간(바닥~오늘)에 대장이었나로 본다."""

    def __init__(self, P: Panel, cfg: VocalConfig):
        self.P, self.cfg, self.cache = P, cfg, {}

    def at(self, gi: int):
        if gi not in self.cache:
            strong = theme_strength(self.P, gi, self.cfg)
            lead_of: dict[str, list[tuple[str, str]]] = {}
            for t in strong:
                for r in leaders(self.P, t["theme"], t["start"], gi):
                    lead_of.setdefault(r["code"], []).append((t["theme"], r["role"]))
            self.cache[gi] = (lead_of, {t["theme"] for t in strong}, strong)
        return self.cache[gi]

    def during(self, code: str, d0, d1, themes: list[str]):
        """d0~d1 사이 — [(theme, role, date)] 대장이었던 날들, 강한 테마 멤버였던 날 수."""
        g0 = self.P.dates.searchsorted(d0)
        g1 = self.P.dates.get_indexer([d1])[0]
        if g1 < 0:
            return [], 0
        lead, n_theme = [], 0
        for k in range(max(0, g0), g1 + 1):
            lead_of, strong_set, _ = self.at(k)
            for t, role in lead_of.get(code, ()):
                lead.append((t, role, f"{self.P.dates[k]:%Y-%m-%d}"))
            if any(t in strong_set for t in themes):
                n_theme += 1
        return lead, n_theme


# ---------------------------------------------------------------- ④~⑧ 종목 깔때기
def _mean(a) -> float | None:
    a = [x for x in a if x == x]
    return sum(a) / len(a) if a else None


def _ma(c: np.ndarray, j: int, n: int) -> float | None:
    return float(c[j - n + 1:j + 1].mean()) if j + 1 >= n else None


def funnel(a: dict, j: int, in_rank, cfg: VocalConfig) -> dict | None:
    """j 번째 봉까지로 본 한 종목의 단계. in_rank(date)→bool 은 그날 거래대금 순위 안이었나(④).
    stage: 0 해당 없음 · 4 큰 상승 뒤 · 5 눌림 중 · 6 지지선 닿고 거래량 마름 · 7 신호(재유입 + 양봉). 나머지는 근거 숫자."""
    if j < cfg.base_win + 5:
        return None
    o, h, l, c, v, tv, d = a["o"], a["h"], a["l"], a["c"], a["v"], a["tv"], a["d"]
    ds = lambda k: f"{d[k]:%Y-%m-%d}"
    w0 = max(0, j - cfg.rally_win + 1)
    seg = h[w0:j + 1]
    H = float(seg.max())
    hk = w0 + len(seg) - 1 - int(np.argmax(seg[::-1]))       # 고점이 여럿이면 가장 최근
    if hk < cfg.base_win or H <= 0:                           # 고점 앞 60봉이 다 있어야 바닥을 잴 수 있다
        return None
    b0 = max(0, hk - cfg.base_win)
    base_lo = float(l[b0:hk].min()) if hk > b0 else None
    if not base_lo or base_lo <= 0:
        return None
    gain = H / base_lo - 1
    lk = max(k for k in range(b0, hk) if l[k] <= base_lo * 1.05)
    rise = hk - lk
    n_rank = sum(1 for k in range(lk, hk + 1) if in_rank(d[k]))
    out = {"H": H, "hk": ds(hk), "base_lo": base_lo, "lk": ds(lk), "gain": gain * 100, "rise": rise, "n_rank": n_rank,
           "stage": 0, "why": None}
    if gain < cfg.gain:
        out["why"] = "상승 %.0f%% < %.0f%%" % (gain * 100, cfg.gain * 100)
        return out
    if rise > cfg.rise_max:
        out["why"] = "상승에 %d봉 — 급등 아님" % rise
        return out
    if n_rank < 2:
        out["why"] = "상승 중 거래대금 %d위 안 %d일" % (cfg.top, n_rank)
        return out
    bk = lk + int(np.argmax(v[lk:hk + 1]))
    out.update(bk=ds(bk), v_peak=float(v[bk]), v_rally=_mean(v[lk:hk + 1]), stage=4)
    # ⑤ 눌림
    days = j - hk
    depth = 1 - c[j] / H
    depth_min = 1 - float(c[hk + 1:j + 1].min()) / H if j > hk else None
    pl = float(l[hk + 1:j + 1].min()) if j > hk else None
    plk = hk + 1 + int(np.argmin(l[hk + 1:j + 1])) if pl is not None else None
    retrace = (H - pl) / (H - base_lo) if pl is not None and H > base_lo else None
    out.update(days=days, depth=depth * 100, depth_min=depth_min * 100 if depth_min is not None else None, pl=pl,
               pl_d=ds(plk) if plk is not None else None, retrace=retrace * 100 if retrace is not None else None)
    if days == 0:
        out["why"] = "오늘이 고점"
        return out
    if days > cfg.days_hi:
        out["stage"], out["why"] = 0, "고점 뒤 %d봉 — 눌림 기간 지남" % days
        return out
    if retrace is not None and retrace > cfg.retrace_max:
        out["stage"], out["why"] = 0, "상승 폭의 %.0f%% 되돌림 — 끝난 상승" % (retrace * 100)
        return out
    if depth > cfg.pull_hi:
        out["stage"], out["why"] = 0, "고점 대비 −%.0f%% — 눌림 넘어 하락" % (depth * 100)
        return out
    if days < cfg.days_lo or depth_min < cfg.pull_lo:
        out["why"] = "눌림 기다리는 중(%d봉 · −%.1f%%)" % (days, depth_min * 100)
        return out
    out["stage"] = 5
    # ⑥ 지지선 · 거래량 감소
    ma5, ma10, ma20 = _ma(c, j, 5), _ma(c, j, 10), _ma(c, j, 20)
    box_hi = float(h[max(0, lk - cfg.base_win):lk].max()) if lk > 0 else None
    static = [("전고점", box_hi if box_hi and box_hi < H * 0.97 and box_hi > base_lo else None),
              ("급등봉 시가", float(o[bk])), ("급등봉 중간", float((o[bk] + c[bk]) / 2)), ("50% 되돌림", H - 0.5 * (H - base_lo))]
    levels = [("5일선", ma5), ("10일선", ma10), ("20일선", ma20)] + static
    levels = [(nm, lv) for nm, lv in levels if lv and lv > 0 and lv < H * 0.99]
    # '닿음'은 눌림 저점이 생긴 날의 선과 견준다 · '지킴'(⑦)은 오늘 선과
    at_pl = [("5일선", _ma(c, plk, 5)), ("10일선", _ma(c, plk, 10)), ("20일선", _ma(c, plk, 20))] + static
    touched = [(nm, lv) for nm, lv in at_pl if lv and lv > 0 and lv < H * 0.99 and abs(pl / lv - 1) <= cfg.touch]
    tnames = {t for t, _ in touched}
    hold_lv = [lv for nm, lv in levels if nm in tnames and lv]
    prev3, now3 = v[j - 3:j], v[j - 2:j + 1]
    dry = lambda s: len(s) > 0 and _mean(s) <= cfg.dry_peak * v[bk] and _mean(s) <= cfg.dry_rally * out["v_rally"]
    dry_prev, dry_now = bool(dry(prev3)), bool(dry(now3))
    out.update(levels=[(nm, lv, (pl / lv - 1) * 100) for nm, lv in levels], touched=[nm for nm, _ in touched],
               touched_lv=[(nm, lv) for nm, lv in touched], v_prev3=_mean(prev3), v_now3=_mean(now3),
               dry_prev=dry_prev, dry_now=dry_now,
               v_ratio_peak=(_mean(now3) / v[bk]) if v[bk] else None,
               v_ratio_rally=(_mean(now3) / out["v_rally"]) if out["v_rally"] else None)
    if touched and (dry_now or dry_prev):
        out["stage"] = 6
    # ⑦ 재유입 + 양봉
    tv_prev = _mean(tv[j - 3:j])
    reflow = tv_prev is not None and tv_prev > 0 and tv[j] >= cfg.reflow * tv_prev
    bull = bool(c[j] > o[j] and (c[j] - o[j]) / o[j] >= cfg.body and c[j] >= c[j - 1])
    hold = any(l[j] >= lv * (1 - cfg.hold_below) for lv in hold_lv)
    above5 = ma5 is not None and c[j] > ma5
    out.update(reflow=bool(reflow), reflow_x=(tv[j] / tv_prev) if tv_prev else None, bull=bull, hold=bool(hold), above5=bool(above5))
    if out["stage"] >= 5 and touched and reflow and bull and hold and above5 and dry_prev:
        out["stage"] = 7
    # ⑧ 진입 · 손절 · 목표
    entry = float(c[j])
    out.update(entry=entry, stop=pl, target=H, rr=((H - entry) / (entry - pl)) if pl and entry > pl else None,
               stop_pct=(pl / entry - 1) * 100 if pl else None, target_pct=(H / entry - 1) * 100)
    if out["stage"] == 5:
        out["why"] = "지지선 " + ("닿음 · 거래량 아직" if touched else "아직 안 닿음")
    elif out["stage"] == 6:
        miss = [k for k, ok in (("재유입", reflow), ("양봉", bull), ("지지 지킴", hold), ("5일선 위", above5), ("앞 3봉 마름", dry_prev)) if not ok]
        out["why"] = "신호 대기 — 아직: " + " · ".join(miss) if miss else "신호 대기"
    elif out["stage"] == 7:
        out["why"] = "신호 — %s 지지 · 거래대금 %.1f배" % (", ".join(out["touched"]), out["reflow_x"] or 0)
    return out


# ---------------------------------------------------------------- 잡주 거르기 (원본 보컬.junk_flags 와 같은 규칙)
FIN_DIR = CACHE_DIR / "fin"
NAVER_FIN = "https://m.stock.naver.com/api/stock/{code}/finance/quarter"
RISK_RED = ("상폐 절차", "보고서 없음", "작전주 꼴", "자금조달 잦음")
JUNK_REF = {"회생절차": "회생절차", "파산신청": "파산신청", "감사의견비적정": "감사의견 비적정", "관리종목_사유": "관리종목 지정 사유",
            "관리종목_우려": "관리종목 우려", "실질심사": "상장적격성 실질심사", "상폐우려": "상장폐지 우려", "자본잠식": "자본잠식"}
WARN_REF = {"횡령배임": "횡령 · 배임 혐의", "불성실_지정": "불성실공시", "보고서지연": "보고서 지연", "투자주의환기": "투자주의 환기"}
FUND_CATS = {"CB발행": "CB 발행", "BW발행": "BW 발행", "유상증자": "유상증자", "제3자배정": "제3자배정"}


def _num(x):
    try:
        return float(str(x).replace(",", ""))
    except (TypeError, ValueError):
        return None


def fetch_fin(code: str, offline: bool = False, max_age: float = 7 * 86400) -> dict | None:
    """네이버 분기 재무 요약 → {q, roe(%), debt(부채비율 %), ni4(최근 4분기 순이익 합, 억원)}. 7일 캐시. 못 받으면 None."""
    p = FIN_DIR / f"{code}.json"
    try:
        if p.exists() and (offline or time.time() - p.stat().st_mtime < max_age):
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    if offline:
        return None
    try:
        from .data import http
        fi = (http.get(NAVER_FIN.format(code=code), min_interval=0.1).json() or {}).get("financeInfo") or {}
    except Exception:
        return None
    keys = [t["key"] for t in (fi.get("trTitleList") or []) if t.get("key") and t.get("isConsensus") != "Y"]
    rows = {(row.get("title") or "").strip(): row.get("columns") or {} for row in (fi.get("rowList") or [])}

    def col(title, k):
        return _num(((rows.get(title) or {}).get(k) or {}).get("value"))
    last = next((k for k in reversed(keys) if col("당기순이익", k) is not None or col("ROE", k) is not None), None)
    out = {"q": None, "roe": None, "debt": None, "ni4": None, "at": time.time()}
    if last:
        i = keys.index(last)
        qs = keys[max(0, i - 3):i + 1]
        ni = [col("당기순이익", k) for k in qs]
        out.update(q=last[:4] + "." + last[4:], roe=col("ROE", last), debt=col("부채비율", last),
                   ni4=sum(ni) if len(qs) == 4 and all(x is not None for x in ni) else None)
    try:
        FIN_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


def load_risk(cfg: VocalConfig) -> dict:
    """공시 위험 {code: {...}} — 파일이 없으면 {} (공시 쪽 잡주 거르기는 건너뛴다)."""
    path = cfg.risk_path or os.environ.get("CHART_SCREENER_RISK_JSON")
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("codes") or {}
    except Exception:
        return {}


def junk_flags(fin: dict | None, risk: dict | None, cfg: VocalConfig) -> tuple[list[str], list[str]]:
    """(제외 사유, 참고 표시) — 원본 보컬.junk_flags 와 같은 규칙."""
    junk, warn = [], []
    rk = risk or {}
    if rk.get("level") in RISK_RED:
        junk.append("공시 위험: " + rk["level"])
    fund = [(FUND_CATS[h["cat"]], h["days"]) for h in (rk.get("hits") or [])
            if h.get("cat") in FUND_CATS and (h.get("days") or 0) >= cfg.fund_min]
    if fund and not any(j.startswith("공시 위험") for j in junk):
        junk.append("자금조달 잦음: " + " · ".join("%s %d번" % kv for kv in fund))
    for r in rk.get("ref") or []:
        c = r.get("cat")
        if c in JUNK_REF:
            junk.append(JUNK_REF[c])
        elif c in WARN_REF:
            warn.append(WARN_REF[c])
    f = fin or {}
    if f.get("debt") is not None and f["debt"] >= cfg.debt_max:
        junk.append("부채비율 %.0f%%" % f["debt"])
    if f.get("debt") is not None and f["debt"] < 0:
        junk.append("자본잠식(부채비율 음수)")
    if f.get("ni4") is not None and f["ni4"] < 0:
        if f.get("roe") is not None and f["roe"] <= cfg.loss_roe:
            junk.append("큰 적자: 4분기 순이익 %s억 · ROE %.1f%%" % (format(int(round(f["ni4"])), ","), f["roe"]))
        else:
            warn.append("적자: 4분기 순이익 %s억" % format(int(round(f["ni4"])), ","))
    if not f:
        warn.append("재무 요약 없음")
    return junk, warn


# ---------------------------------------------------------------- 전 시장 한 번
def _themes(sector_map) -> dict[str, list[str]]:
    if sector_map is None or len(sector_map) == 0 or "themes" not in sector_map:
        return {}
    out = {}
    for c, t in zip(sector_map["code"], sector_map["themes"]):
        if isinstance(t, (list, tuple, np.ndarray)) and len(t):
            out[str(c)] = [str(x) for x in t]
    return out


def prepare(ud, sector_map, cfg: VocalConfig | None = None, *, offline: bool = True,
            extra_ohlcv: dict | None = None) -> dict[str, dict]:
    """오늘(패널 마지막 완성 봉) 기준 — 풀 종목마다 깔때기 결과 + 대장 이력 + 잡주 표시. {code: dict}.
    extra_ohlcv = 스캔 대상(120봉↑)보다 짧은 종목(60봉↑) — 순위 · 테마 · 대장에만 쓴다. 테마 분류표가 없으면 {}.
    풀 안이지만 ④~⑤에서 빠진 종목은 {stage: 0, why} 로 남겨 '왜 아닌지'를 보인다."""
    cfg = cfg or VocalConfig()
    themes = _themes(sector_map)
    if not themes or not ud.ohlcv:
        return {}
    over = {}
    uni = getattr(ud, "universe", None)
    if uni is not None and "value" in uni and "traded_at" in uni:
        for c, val, ts in zip(uni.index, uni["value"], uni["traded_at"]):
            if c in ud.ohlcv and val == val and ts == ts and ts is not None:
                over[c] = (pd.Timestamp(ts).normalize().tz_localize(None) if pd.Timestamp(ts).tzinfo else pd.Timestamp(ts).normalize(), val)
    bars = {c: d for c, d in {**(extra_ohlcv or {}), **ud.ohlcv}.items() if d is not None and len(d) >= cfg.min_bars}
    P = Panel(bars, themes, cfg.tail, over)
    if not len(P.dates):
        return {}
    gi = len(P.dates) - 1
    # 장중 미완성 봉은 빼고 어제까지로 잰다(원본 서버가 15:40 전엔 오늘 반쪽 봉을 뺀다 — 거래량 마름 · 재유입이 틀어진다)
    try:
        from .universe_data import partial_bar
        if gi > 0 and partial_bar(P.dates[gi], getattr(ud, "fetched_at", None))[0]:
            gi -= 1
    except Exception:
        pass
    pool = P.pool(gi, cfg.top, cfg.pool_days)
    hist = LeadHistory(P, cfg)
    lead_of_now, _, strong_now = hist.at(gi)
    risk = load_risk(cfg)
    out = {}
    for code in pool:
        j = P.loc(code, gi)
        if j is None:
            continue
        a = P.arrays(code)
        f = funnel(a, j, lambda dd, code=code: P.in_rank(code, dd, cfg.top), cfg)
        if not f or f["stage"] < 4:
            out[code] = {"stage": 0, "why": (f or {}).get("why") or "봉이 모자라 ④ 큰 상승을 잴 수 없다",
                         "gain": (f or {}).get("gain"), "pool_days": pool[code], "asof": f"{P.dates[gi]:%Y-%m-%d}"}
            continue
        ths = P.theme_of.get(code, [])
        lead, n_theme = hist.during(code, pd.Timestamp(f["lk"]), P.dates[gi], ths)
        seen, lead_u = set(), []
        for t, role, dd in lead:                     # 테마마다 처음 대장이 된 날 하나씩
            if (t, role) not in seen:
                seen.add((t, role))
                lead_u.append([t, role, dd])
        rank = int(P.R[gi, P.col[code]])
        fin = fetch_fin(code, offline=offline)
        junk, warn_j = junk_flags(fin, risk.get(code), cfg)
        f.update(code=code, rank=rank if rank < 10 ** 6 else None, pool_days=pool[code], themes=ths, lead=lead_u,
                 lead_now=[list(x) for x in lead_of_now.get(code, [])], n_theme_days=n_theme,
                 asof=f"{P.dates[gi]:%Y-%m-%d}", junk=junk, warn_j=warn_j, risk_checked=bool(risk),
                 fin={k: (fin or {}).get(k) for k in ("q", "roe", "debt", "ni4")} if fin else None)
        out[code] = f
    return out


def strong_themes_now(ud, sector_map, cfg: VocalConfig | None = None) -> list[dict]:
    """오늘의 강한 테마(표시용)."""
    cfg = cfg or VocalConfig()
    themes = _themes(sector_map)
    if not themes or not ud.ohlcv:
        return []
    P = Panel(ud.ohlcv, themes, cfg.tail)
    return theme_strength(P, len(P.dates) - 1, cfg) if len(P.dates) else []
