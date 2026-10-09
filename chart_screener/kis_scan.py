"""일일 스캔 ↔ 증권사(한국투자증권, KIS) 자료 연결 — data.kis_market 을 scan 명령에 붙인다.

    hub = open_hub("auto")                                        # 클라이언트가 없으면 hub.on = False, hub.reason = 한글 사유
    ud = load_universe_data(cfg, prepare=hub.load_universe)       # ① 전 종목 상태 ② 실제 거래대금 → 일봉 'value' 덮어쓰기
    scan = run_scan(ud, cfg, kis=hub)                             # 상태 제외(거래정지·정리매매·관리종목·투자위험) · 태그
    hub.enrich(scan)                                              # ③ 후보 수급 ④ 투자의견 ⑤ 추정실적 → CAN SLIM I · s.kis
    hub.write_snapshots(out_dir)                                  # out/kis_snapshot.json + cache/kis/snapshot.json

순서가 중요하다: 실제 거래대금은 패턴 · 시장 폭 · 업종 강도 · 300억 레이더 · 보컬 단면보다 먼저 들어가야 하므로
load_universe_data 의 prepare 단계(시장 폭 계산 전)에서 덮어쓴다. 후보는 패턴을 돌려야 정해지므로 ③~⑤는 스캔 뒤에 받는다.

단계별 시간 · 건수는 hub.res.steps (data.kis_market.RefreshResult 와 같은 모양). 인증 실패 같은 치명 오류가 나면
그 자리에서 KIS 를 끄고(hub.res.fatal) 나머지는 네이버 자료로 계속한다. 비밀값은 broker.kis 가 가린다.

리포트 종목 자료 StockScan.kis (후보만, 자료가 있을 때)
    {"tp_n30": 30일 리포트 수, "tp_up30": 목표가 상향 수, "tp_down30": 하향 수, "tp_avg": 90일 증권사별 최신 목표가 평균(원),
     "tp_gap": 평균 목표가 대비 종가 여력(%), "opinions": [{"date", "broker", "opinion", "target"}] 최근 3건,
     "fwd_eps_g": 선행 EPS 증가율(%), "eps_e": [[연도, EPS(원)], ...] 추정(E) 연도 앞 두 해}
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from .broker.kis import RateLimiter
from .data import kis_market as km

# 스캔용 호출 한도(초/회). 클라이언트 기본 15회로 8스레드를 돌리면 2026-10-09 실측에서 전 종목 상태 2,449건 중 237건이
# EGW00201(초당 한도)로 재시도 끝에 실패했다(실효 초당 5.4건). 조금 낮춰 한도 오류를 줄이고, 실패분은 한 번 더 천천히 받는다.
SCAN_PER_SEC = 12.0
RETRY_WORKERS = 2                          # 실패 종목 재시도 스레드 수 (0 이면 재시도 안 함)
STEP_NAMES = {"status": "상태", "turnover": "실거래대금", "flows": "수급", "opinion": "의견", "estimate": "실적"}
SNAPSHOT_NAME = "kis_snapshot.json"        # 스캔 출력 폴더
STABLE_SNAPSHOT = "snapshot.json"          # cache/kis/ 아래 고정 경로 (기업추적 뷰어가 읽는다)


def _secs(t: float) -> str:
    t = int(round(t))
    return f"{t // 60}분 {t % 60}초" if t >= 60 else f"{t}초"


@dataclass
class KISScan:
    """스캔 한 번 동안 쓰는 KIS 자료 묶음. client 가 None 이면 꺼진 상태(reason = 한글 사유)."""
    mode: str = "off"                                   # 'auto' | 'on' | 'off'
    client: object | None = None
    reason: str = ""                                    # 꺼진 이유 (켜져 있으면 빈 문자열)
    cfg: km.KISMarketConfig = field(default_factory=km.KISMarketConfig)
    cache: km.KISDayCache | None = None
    day: date | None = None                             # 자료 기준일 (market_date)
    res: km.RefreshResult = field(default_factory=km.RefreshResult)
    progress: km.Progress | None = None
    snapshots: list = field(default_factory=list)       # 쓴 스냅샷 경로
    retry_workers: int = RETRY_WORKERS                  # 실패 종목 재시도 스레드 수
    retried: dict = field(default_factory=dict)         # {단계: 재시도한 종목 수}

    @property
    def on(self) -> bool:
        """지금 KIS 를 쓰는가 (치명 오류가 나면 꺼진다)."""
        return self.client is not None and self.res.fatal is None

    @property
    def used(self) -> bool:
        """한 단계라도 KIS 자료를 받았는가."""
        return bool(self.res.steps)

    # ------------------------------------------------------------ 공용
    def _cache(self) -> km.KISDayCache:
        if self.cache is None:
            self.cache = km.KISDayCache(self.cfg.cache_dir, self.cfg.keep_days)
        return self.cache

    def _day(self) -> date:
        if self.day is None:
            self.day = km.market_date(self.client)
            self.res.day = self.day
        return self.day

    def _run(self, name: str, codes: list[str], fetch: Callable[[list, dict, int], dict]) -> dict:
        """한 단계 실행 (시간 · 건수 기록). fetch(codes, errors, workers). 실패 종목(초당 한도 등)은 스레드를 줄여
        한 번 더 받는다 (캐시에 있는 종목은 다시 묻지 않음). 치명 오류면 KIS 를 끄고 빈 결과."""
        if not self.on or not codes:
            return {}

        def run(cs: list, errs: dict) -> dict:
            got = dict(fetch(cs, errs, self.cfg.workers) or {})
            again = [c for c in cs if c in errs]          # 캐시로 대신한 종목도 한 번 더 받아 본다
            if again and self.retry_workers > 0:
                for c in again:
                    errs.pop(c, None)
                self.retried[name] = len(again)
                got.update(fetch(again, errs, self.retry_workers) or {})
            return got

        try:
            return km._step(self.res, name, codes, run) or {}
        except Exception as e:   # 치명 KIS 오류 · 캐시 쓰기 실패(드라이브 잠김) 등 — 스캔은 네이버 자료로 계속
            why = e.message if isinstance(e, km.KISError) else f"{type(e).__name__}: {e}"
            self.res.fatal = f"{why} ({STEP_NAMES.get(name, name)} 단계에서 중단)"
            return {}

    def _kw(self, workers: int) -> dict:
        return dict(cache=self._cache(), day=self._day(), workers=workers, progress=self.progress)

    # ------------------------------------------------------------ ①② 전 종목
    def load_universe(self, universe: pd.DataFrame, data: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """load_universe_data 의 prepare 단계: 전 종목 상태 · 실제 거래대금을 받아 일봉 'value' 를 덮어쓴다."""
        if not self.on:
            return data
        try:
            codes = list(dict.fromkeys([str(c) for c in universe.index] + list(data)))
            self.res.status = self._run("status", codes, lambda cs, e, w: km.fetch_status(
                self.client, cs, errors=e, **self._kw(w)))
            active = [c for c in codes if not getattr(self.res.status.get(c), "halt", False)]
            self.res.turnover = self._run("turnover", active, lambda cs, e, w: km.fetch_turnover(
                self.client, cs, days=self.cfg.turnover_days, errors=e, **self._kw(w)))
            return apply_turnover_all(data, self.res.turnover)
        except Exception as e:   # 기준일 계산 · 덮어쓰기 실패 — 추정 거래대금 그대로 계속
            self.res.fatal = self.res.fatal or f"{type(e).__name__}: {e} (전 종목 단계에서 중단)"
            return data

    def turnover_for(self, frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
        """이미 받은 실제 거래대금을 다른 일봉 묶음(보컬 단면의 신규 상장 60~119봉 등)에도 덮어쓴다."""
        return apply_turnover_all(frames, self.res.turnover) if self.res.turnover else frames

    def tags(self, code: str) -> list[str]:
        st = self.res.status.get(code)
        return km.status_tags(st) if st is not None else []

    def exclude(self, code: str) -> str | None:
        st = self.res.status.get(code)
        return km.status_exclude(st) if st is not None else None

    # ------------------------------------------------------------ ③④⑤ 후보
    def enrich(self, scan, verbose: bool = False) -> dict:
        """후보 전부에 KIS 수급(CAN SLIM I 재계산) · 투자의견 · 추정실적을 붙인다. 반환 {단계: 붙인 종목 수}.
        저평가 목록 종목(scan.value_scans, 후보 아님)도 같은 단계로 함께 받는다(리포트 '저평가 종목' 탭) — 그때만
        반환에 'value'(함께 받은 비후보 목록 종목 수)가 붙고, 단계별 수는 후보 + 목록 종목 합이다."""
        from .scanner import recalc_canslim

        targets = [s for s in scan.stocks if s.ctx is not None]
        extra = value_targets(scan, targets)
        targets += extra
        codes = [s.code for s in targets]
        out = {"flows": 0, "opinion": 0, "estimate": 0}
        if extra:
            out["value"] = len(extra)
        if not self.on or not codes:
            return out
        self.res.flows = self._run("flows", codes, lambda cs, e, w: km.fetch_flows(
            self.client, cs, errors=e, **self._kw(w)))
        for s in targets:
            fl = self.res.flows.get(s.code)
            st = self.res.status.get(s.code)
            # 외국인 '보유율'(보유 ÷ 상장주식) — 소진율(보유 ÷ 외국인 한도)은 한도 있는 종목(통신 · 방송 · 항공 등)에서 훨씬 크다
            if km.attach_flows(s.ctx, fl, getattr(st, "hold", None) if st is not None else None) is not None:
                s.ctx.info["kis_flows"] = fl
                out["flows"] += 1
                recalc_canslim(s)
        # 목표가 여력 기준가: 증권사 현재가, 상태 조회에 실패한 종목은 스캔 종가
        prices = {s.code: s.close for s in targets if s.close and s.close > 0}
        prices.update({c: st.price for c, st in self.res.status.items() if st.price})
        self.res.opinions = self._run("opinion", codes, lambda cs, e, w: km.fetch_opinions(
            self.client, cs, days=self.cfg.opinion_days, prices=prices, recent=self.cfg.opinion_recent,
            target_days=self.cfg.target_days, errors=e, **self._kw(w)))
        self.res.estimates = self._run("estimate", codes, lambda cs, e, w: km.fetch_estimates(
            self.client, cs, errors=e, **self._kw(w)))
        for s in targets:
            s.kis = stock_kis(self.res.opinions.get(s.code), self.res.estimates.get(s.code), s.close)
            out["opinion"] += self.res.opinions.get(s.code) is not None
            out["estimate"] += self.res.estimates.get(s.code) is not None
        scan.stocks.sort(key=lambda s: -s.score.composite)
        return out

    # ------------------------------------------------------------ 출력
    def write_snapshots(self, out_dir: Path | str | None) -> list[Path]:
        """스캔 출력 폴더의 kis_snapshot.json 과 cache/kis/snapshot.json. 치명 오류로 멈췄거나 받은 게 없으면 쓰지 않는다."""
        if not self.used or self.res.fatal or not self.res.status:
            return []
        meta = {"date": km._ymd(self.day) if self.day else None, "steps": self.res.steps,
                "env": getattr(getattr(self.client, "cfg", None), "env", None) or self.cfg.env}
        paths = ([Path(out_dir) / SNAPSHOT_NAME] if out_dir else []) + [self._cache().root / STABLE_SNAPSHOT]
        r = self.res
        self.snapshots = [km.write_snapshot(p, r.status, r.flows, r.opinions, r.estimates, meta) for p in paths]
        return self.snapshots

    def total_secs(self) -> float:
        return sum(float(st.get("secs") or 0) for st in self.res.steps)

    def summary_line(self) -> str:
        """리포트 헤더 한 줄: '증권사 자료: 상태 2,449 · 실거래대금 2,449 · … · 4분 12초' 또는 꺼진 이유."""
        if not self.used:
            why = self.reason or self.res.fatal or "꺼짐"
            return f"증권사 자료 없음 — 네이버 ({why})"
        parts = [f"{STEP_NAMES.get(st['step'], st['step'])} {st['ok']:,}" + (f"(실패 {st['fail']:,})" if st["fail"] else "")
                 + (" 중단" if st.get("stop") else "") for st in self.res.steps]
        line = "증권사 자료: " + " · ".join(parts) + f" · {_secs(self.total_secs())}"
        if self.res.fatal:
            line += f" — 중단: {self.res.fatal}, 나머지는 네이버"
        return line

    def timing_lines(self) -> list[str]:
        """콘솔용 단계별 시간 요약."""
        if not self.used:
            return [self.summary_line()]
        lines = [f"증권사(KIS) 자료 기준일 {self.day:%Y-%m-%d}" if self.day else "증권사(KIS) 자료"]
        for st in self.res.steps:
            name = st["step"]
            line = (f"  {STEP_NAMES.get(name, name):<6} {st['ok']:>5,}/{st['n']:<5,} "
                    f"실패 {st['fail']:>3} · {st['secs']:6.1f}초" + (" · 중단" if st.get("stop") else ""))
            if self.retried.get(name):
                line += f" · 재시도 {self.retried[name]:,}"
            why = error_reasons(self.res.errors.get(name))
            lines.append(line + (f" · 실패 사유: {why}" if why else ""))
        lines.append(f"  합계 {_secs(self.total_secs())}")
        if self.res.fatal:
            lines.append(f"  ✘ 중단: {self.res.fatal}")
        return lines

    def report_info(self) -> dict:
        """ScanResult.kis — 리포트 헤더용 {on, line, reason, day, steps}."""
        return {"on": self.used and not self.res.fatal, "line": self.summary_line(),
                "reason": self.reason or self.res.fatal or None,
                "day": f"{self.day:%Y-%m-%d}" if self.day else None, "steps": list(self.res.steps),
                "real_value": any(bool(v) for v in self.res.turnover.values())}


def value_targets(scan, cands: list) -> list:
    """후보가 아닌 저평가 목록 종목 중 ctx 가 남은 것 (enrich 대상에 더한다)."""
    have = {s.code for s in cands}
    return [s for c, s in (getattr(scan, "value_scans", None) or {}).items()
            if c not in have and s.ctx is not None]


# ---------------------------------------------------------------- 만들기
def open_hub(mode: str = "auto", *, offline: bool = False, cfg: km.KISMarketConfig | None = None,
             connect: Callable | None = None, verbose: bool = False, per_sec: float | None = SCAN_PER_SEC) -> KISScan:
    """--kis 값으로 KISScan 을 만든다. off · (auto 이면서 offline) 이면 연결하지 않는다.
    connect 는 시험용 주입 (기본 data.kis_market.client_or_none). 실패해도 예외 없이 reason 에 사유.
    per_sec: 스캔 중 호출 한도(초당, 기본 SCAN_PER_SEC) — 실제 KISRestClient 의 제한기만 바꾼다."""
    cfg = cfg or km.KISMarketConfig(snapshot_path=None)
    hub = KISScan(mode=mode, cfg=cfg)
    if verbose:
        hub.progress = _progress
    if mode == "off":
        hub.reason = "--kis off"
        return hub
    if offline and mode == "auto":
        hub.reason = "오프라인 실행"
        return hub
    client, why = (connect or km.client_or_none)(cfg)
    hub.client, hub.reason = client, ("" if client is not None else why or "클라이언트 없음")
    if client is not None and isinstance(getattr(client, "limiter", None), RateLimiter) and per_sec:
        client.limiter = RateLimiter(per_sec)
    return hub


def error_reasons(errors: dict | None, top: int = 2) -> str:
    """종목별 실패 사유 → '초당 호출 한도… 12 · 서버 오류 3' (많은 순 top 개)."""
    if not errors:
        return ""
    from collections import Counter
    return " · ".join(f"{msg[:40]} {n}" for msg, n in Counter(errors.values()).most_common(top))


def _progress(step: str, done: int, total: int) -> None:
    if done == total or done % 100 == 0:
        print(f"\r  증권사 {STEP_NAMES.get(step, step)} {done}/{total}", end="" if done < total else "\n",
              file=sys.stderr, flush=True)


# ---------------------------------------------------------------- 변환
def apply_turnover_all(data: dict[str, pd.DataFrame], turnover: dict[str, dict]) -> dict[str, pd.DataFrame]:
    """종목별 일봉의 추정 거래대금을 KIS 실제 거래대금으로 덮어쓴 새 dict (자료 없는 종목은 그대로)."""
    if not turnover:
        return data
    return {c: km.apply_turnover(df, turnover.get(c)) if turnover.get(c) else df for c, df in data.items()}


def _ymd_dash(d: str) -> str:
    d = str(d)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d


def stock_kis(op: km.Opinions | None, est: km.Estimate | None, close: float | None) -> dict | None:
    """후보 한 종목의 리포트용 KIS 요약 (모듈 설명의 StockScan.kis). 둘 다 없으면 None."""
    if op is None and est is None:
        return None
    out: dict = {"tp_n30": None, "tp_up30": None, "tp_down30": None, "tp_avg": None, "tp_gap": None,
                 "opinions": [], "fwd_eps_g": None, "eps_e": []}
    if op is not None:
        avg = op.avg_target_90d
        out.update(tp_n30=op.n30, tp_up30=op.up30, tp_down30=op.down30, tp_avg=avg,
                   tp_gap=round((avg / close - 1) * 100, 2) if avg and close and close > 0 else None,
                   opinions=[{"date": _ymd_dash(r[0]), "broker": r[1], "opinion": r[2], "target": r[4]}
                             for r in list(op.rows)[:3]])
    if est is not None:
        e_years = [(y, est.eps[i] if i < len(est.eps) else None) for i, y in enumerate(est.years)
                   if str(y).upper().endswith("E")]
        out.update(fwd_eps_g=est.fwd_eps_g, eps_e=[[y, v] for y, v in e_years[:2]])
    return out


# ---------------------------------------------------------------- 휴장일 건너뛰기
def _prev_open(d: date, is_open: Callable[[date], bool]) -> date:
    for _ in range(20):
        d -= timedelta(days=1)
        if is_open(d):
            return d
    return d


def holiday_skip(client=None, *, now: datetime | None = None, last_bar: date | None = None,
                 cached_last_bar: Callable[[], date | None] | None = None) -> tuple[bool, str]:
    """(건너뛸지, 사유). 오늘이 휴장일이고 캐시 최신 봉이 이미 직전 개장일이면 True.

    휴장 판정은 KIS 국내휴장일조회(client), 없으면 주말 · KRX 고정 휴장일 달력(live.krx_holiday).
    캐시 최신 봉은 KOSPI 지수 일봉 캐시의 마지막 날짜."""
    from .live import krx_holiday

    now = now or km._now()
    today = now.date()
    cal_open = lambda d: d.weekday() < 5 and not krx_holiday(d)  # noqa: E731
    open_today = km.is_open_today(client, now) if client is not None else None
    if open_today is None:                      # KIS 없음 · 모름(모의투자 · 조회 실패) → KRX 달력
        open_today = cal_open(today)
    if open_today is not False:
        return False, "개장일"
    try:
        last_open = km.market_date(client, now) if client is not None else _prev_open(today, cal_open)
    except Exception:
        last_open = _prev_open(today, cal_open)
    if last_bar is None:
        last_bar = (cached_last_bar or _cached_index_last)()
    if last_bar is None:
        return False, "휴장일이지만 일봉 캐시가 없음"
    if last_bar >= last_open:
        return True, f"휴장일 — 캐시 최신 봉 {last_bar:%Y-%m-%d} = 직전 개장일"
    return False, f"휴장일이지만 캐시 최신 봉 {last_bar:%Y-%m-%d} < 직전 개장일 {last_open:%Y-%m-%d}"


def _cached_index_last() -> date | None:
    """KOSPI 지수 일봉 캐시의 마지막 '확정' 봉 날짜. 그 봉 날짜 15:45(종가 확정) 전에 받은 캐시면 마지막 봉은 장중
    미확정이라 바로 앞 봉 날짜를 돌려준다 — 그래야 휴장일 실행이 확정 종가를 받으러 스캔한다."""
    from .data import OHLCVCache
    try:
        cache = OHLCVCache()
        df = cache.load("KOSPI")
        if df is None or not len(df):
            return None
        fetched = datetime.fromtimestamp(cache._path("KOSPI").stat().st_mtime, km.KST)
    except Exception:
        return None
    last = df.index[-1].date()
    if fetched < datetime.combine(last, km.DATA_FINAL, km.KST):
        return df.index[-2].date() if len(df) > 1 else None
    return last
