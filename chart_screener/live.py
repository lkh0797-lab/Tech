"""실시간 감시 — 스캔 후보 × 증권사(한국투자증권)·네이버 시세 → 돌파·눌림·손절 알림 + 대시보드.

    python -m chart_screener live                  # 자동: KIS 설정·토큰이 되면 KIS 실시간, 아니면 네이버
    python -m chart_screener live --source naver   # 네이버 시세 (10초 간격 조회)
    python -m chart_screener live --check          # KIS 연결 점검만 (설정 형식·토큰·현재가·개장일·웹소켓)

조회 전용: 주문을 내지 않는다. 증권사 API 는 시세 조회·실시간 체결가만 쓰며 매수·매도 기능이 없다.

흐름
  1. 감시 목록: 스캔(장 마감 후 받은 캐시가 있으면 오프라인)을 돌려 최대 --top(40)종목을 고른다.
     우선순위: 단계 돌파·피벗 근접·300억 눌림목 매수 구간 → 장기횡보 돌파 전 관찰·눌림 대기 →
     진입 계획이 '피벗 X 돌파 매수'(역지정가)인 형성 중 종목. 돌파 실패·손절가 이탈(관망)은 제외.
     종목마다 피벗·손절가·눌림 매수 구간(50%선 ~ 구간 상단)·50일 평균 거래량(오늘 제외)·대표 패턴·종합점수.
  2. 시세: kis = 실시간 체결가 웹소켓(H0STCNT0, 통합은 H0UNCNT0; 연속 실패하면 REST 현재가 조회로 대체하고
                 5분마다 웹소켓 재시도),
           naver = 네이버 실시간 조회 API (계속 실패하면 전 종목 목록 API 를 1분 간격으로, 3분마다 원래 방식 재시도).
  3. 알림 — 종목·종류별 하루 1회. output/live_alerts_YYYYMMDD.csv 에 기록해 다시 실행해도 반복하지 않는다
     (파일이 엑셀 등에 열려 있어 못 쓰면 live_alerts_YYYYMMDD.pending.csv 에 대신 쓴다).
       피벗 근접   피벗 -1% 이내 (돌파 알림 뒤에는 생략)
       피벗 돌파   현재가 > 피벗. 전일 종가가 피벗 이하였거나 장중에 피벗 아래로 내려갔다 다시 넘을 때만
                   (이미 피벗 위에 있던 종목은 되밀렸다 재돌파할 때). 하루 예상 거래량 = 누적 ÷ 장중 경과 비율
                   (data.ohlcv.session_fraction, U자형) 을 50일 평균과 비교 → '거래량 1.8배 예상 ✓'.
       눌림 구간   300억 장대양봉 눌림목: 50%선 ≤ 현재가 ≤ 매수 구간 상단
       손절가 이탈 현재가 ≤ 손절가 (전일 종가가 이미 손절가 아래였던 종목은 장중에 위로 올라왔다 다시 내려갈 때만).
                   손절가를 깬 종목(전일 종가가 손절가 이하 포함)은 그날 근접·돌파·눌림 알림을 더 내지 않는다.
     장중 신호는 '잠정'이다. 돌파는 종가가 피벗 위인지, 눌림목 손절은 종가 기준으로 확인할 것.
     오늘 정규장 체결이 아닌 시세(지난 거래일 시세·09:00 전·누적 거래량 0)는 표시만 하고 알림에 쓰지 않는다.
  4. 대시보드 output/live.html (몇 초마다 자동 새로고침, 원자적 쓰기) · 콘솔 · 윈도우 알림(토스트).
  5. 09:00 전에는 기다리고, 15:30 장 마감 뒤 종료 (--after-hours 면 계속). Ctrl+C 로 언제든 종료.
     주말·KRX 휴장일(달력, KIS 연결 시 국내휴장일조회)은 바로 끝내고, 달력에 없는 휴장일은 10:15 까지 오늘 체결이
     하나도 없으면(지난 거래일 시세만 오면) 휴장일로 보고 끝낸다.
"""
from __future__ import annotations

import asyncio
import base64
import csv
import html
import math
import os
import shutil
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import AsyncIterator, Callable, Iterable

import pandas as pd

from . import scoring
from .broker.kis import (
    KST, TR_CCNL_KRX, TR_CCNL_TOTAL, KISConfig, KISConfigError, KISError, KISRestClient, KISWebSocketClient, Tick,
    TokenManager,
)
from .config import OUTPUT_DIR
from .data.ohlcv import SESSION_CLOSE, SESSION_OPEN, now_kst, session_fraction
from .patterns.base import BREAKOUT, FAILED, FORMING, NEAR_PIVOT, STAGE_LABELS
from .patterns.three_weeks_tight import FIXED_HOLIDAYS, KRX_EXTRA_HOLIDAYS

NEAR, BREAKOUT_HIT, PULLBACK, STOP = "near", "breakout", "pullback", "stop"
KIND_LABELS = {NEAR: "피벗 근접", BREAKOUT_HIT: "피벗 돌파", PULLBACK: "눌림 구간 진입", STOP: "손절가 이탈"}
KIND_TAGS = {NEAR: "근접", BREAKOUT_HIT: "돌파", PULLBACK: "눌림", STOP: "손절"}
ALERT_COLUMNS = ["date", "time", "code", "name", "kind", "label", "price", "pivot", "stop", "vol_ratio", "source",
                 "text"]
NAVER_POLL_URL = "https://polling.finance.naver.com/api/realtime/domestic/stock/{codes}"
DASHBOARD_NAME = "live.html"
CLOSE_GRACE = timedelta(seconds=60)   # 15:30 종가 단일가 체결이 들어올 여유
MIN_FRAC = 0.02                       # 장 시작 직후(약 3분)에는 거래량 환산을 하지 않음
EARLY_MINUTES = 15                    # 이 전의 환산은 '장 초반 추정' 표시
QUIET_WARN = timedelta(minutes=5)     # 09:05 이 지나도 오늘 체결이 없으면 안내
HOLIDAY_STOP = dtime(10, 15)          # 이때까지 지난 거래일 시세만 오면 휴장일로 보고 종료 (수능일·새해 첫날은 10:00 개장)
_EXTRA_HOLIDAYS = frozenset(KRX_EXTRA_HOLIDAYS)


def krx_holiday(d: date) -> bool:
    """KRX 휴장일(평일)인가 — 고정 휴장일 + 알려진 비정기 휴장일 (patterns.three_weeks_tight 의 달력).
    달력에 없는 새 휴장일은 모른다 (그때는 시세가 지난 거래일 것이라 알림이 나가지 않고 10:15 에 종료)."""
    return d.strftime("%m-%d") in FIXED_HOLIDAYS or d.strftime("%Y-%m-%d") in _EXTRA_HOLIDAYS


# ---------------------------------------------------------------- 감시 목록
@dataclass
class WatchItem:
    code: str
    name: str
    market: str
    pattern: str                        # 패턴 키 (vcp, big_value_pullback, ...)
    label: str                          # 패턴 한글명
    stage: str | None
    pivot: float
    stop: float | None
    reason: str                         # 감시 사유: 돌파 · 피벗 근접 · 눌림 구간 · 눌림 대기 · 돌파 전 관찰 · 돌파 매수 대기 · 지정 종목
    composite: float
    ref_close: float                    # 마지막 확정 종가 (오늘 장중 봉 제외)
    avg_vol_50: float | None = None     # 50일 평균 거래량 (오늘 제외)
    support: float | None = None        # 눌림목 50%선 (지정가)
    zone_top: float | None = None       # 눌림 매수 구간 상단
    plan: str = ""                      # 스캔의 진입 계획 문구
    breakout_date: str | None = None

    @property
    def is_pullback(self) -> bool:
        return self.support is not None and self.zone_top is not None

    @property
    def stage_label(self) -> str:
        return STAGE_LABELS.get(self.stage or "", "-")


_PRIORITY = {"지정 종목": -1, "돌파": 0, "피벗 근접": 0, "눌림 구간": 0, "돌파 전 관찰": 1, "눌림 대기": 1,
             "돌파 매수 대기": 2}


def _pos(x) -> float | None:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0 else None


def watch_reason(s, r) -> str | None:
    """감시 사유. 대상이 아니면 None. r = 대표 결과(s.lead())."""
    if r is None or _pos(r.pivot) is None or r.stage == FAILED:
        return None
    plan = (s.position or {}).get("plan", "") if r is s.lead() else ""
    if "관망" in plan:
        return None
    if scoring.pullback_limit(r) is not None:
        return {NEAR_PIVOT: "눌림 구간", FORMING: "눌림 대기"}.get(r.stage)
    if r.name == "long_base_breakout" and (r.metrics or {}).get("pre_breakout"):
        return "돌파 전 관찰"
    if r.stage == BREAKOUT:
        return "돌파"
    if r.stage == NEAR_PIVOT:
        return "피벗 근접"
    if plan.startswith("피벗") and "돌파 매수" in plan:
        # 역지정가 대기라도 이미 손절가 아래면 지금 감시할 이유가 없다 (돌파까지 손절폭 이상 올라야 함)
        stop = _pos(r.stop)
        return "돌파 매수 대기" if stop is None or s.close > stop else None
    return None


def _before(df: pd.DataFrame, today: date) -> pd.DataFrame:
    return df[df.index < pd.Timestamp(today)]


def avg_volume(df: pd.DataFrame | None, today: date, n: int = 50) -> float | None:
    """오늘 이전 n봉 평균 거래량 (장중 미완성 봉 제외). 자료가 10봉 미만이면 None."""
    if df is None or "volume" not in df or not len(df):
        return None
    v = _before(df, today)["volume"].astype(float).iloc[-n:]
    v = v[v > 0]
    return float(v.mean()) if len(v) >= min(10, n) else None


def last_close(df: pd.DataFrame | None, today: date, fallback: float) -> float:
    if df is None or "close" not in df or not len(df):
        return float(fallback)
    past = _before(df, today)
    return float(past["close"].iloc[-1]) if len(past) else float(fallback)


def _make_item(s, r, reason: str, today: date) -> WatchItem:
    support = scoring.pullback_limit(r)
    zone_top = scoring.pullback_zone_top(r) if support is not None else None
    df = s.ctx.df if s.ctx is not None else None
    return WatchItem(
        code=s.code, name=s.name, market=s.market, pattern=r.name, label=r.label, stage=r.stage,
        pivot=float(r.pivot), stop=_pos(r.stop), reason=reason, composite=float(s.score.composite),
        ref_close=last_close(df, today, s.close), avg_vol_50=avg_volume(df, today), support=support,
        zone_top=zone_top, plan=(s.position or {}).get("plan", "") if r is s.lead() else "",
        breakout_date=r.breakout_date,
    )


def select_watchlist(scan, top: int = 40, *, today: date | None = None,
                     codes: Iterable[str] | None = None) -> list[WatchItem]:
    """ScanResult → 감시 목록 (우선순위·종합점수 순, 최대 top). codes 는 후보이고 피벗이 있으면 맨 앞에 넣는다
    (감시 조건에 맞으면 원래 사유, 아니면 '지정 종목')."""
    today = today or now_kst().date()
    extra = {str(c).strip() for c in (codes or ()) if str(c).strip()}
    picked = []
    for s in scan.stocks:
        r = s.lead()
        reason = watch_reason(s, r)
        if reason is None:
            lb = s.results.get("long_base_breakout")
            if lb is not None and lb.detected and (lb.metrics or {}).get("pre_breakout") \
                    and _pos(lb.pivot) and lb.stage != FAILED:
                r, reason = lb, "돌파 전 관찰"
        forced = s.code in extra and r is not None and _pos(r.pivot) is not None
        if reason is None and forced:
            reason = "지정 종목"
        if reason is None:
            continue
        picked.append((s, r, reason, forced))
    picked.sort(key=lambda x: (not x[3], _PRIORITY.get(x[2], 3), -float(x[0].score.composite)))
    return [_make_item(s, r, reason, today) for s, r, reason, _ in picked[:max(0, int(top))]]


# ---------------------------------------------------------------- 거래량 환산
def projected_volume(cum_volume: float | None, at: datetime) -> float | None:
    """누적 거래량 ÷ 장중 경과 비율 = 하루 예상 거래량. 장 시작 직후(경과 비율 2% 미만)는 None."""
    if cum_volume is None or not cum_volume == cum_volume or cum_volume <= 0:
        return None
    frac = session_fraction(at)
    if frac < MIN_FRAC:
        return None
    return float(cum_volume) / frac


def volume_ratio(cum_volume: float | None, avg50: float | None, at: datetime) -> float | None:
    proj = projected_volume(cum_volume, at)
    return proj / avg50 if proj is not None and avg50 else None


def _minutes_since_open(at: datetime) -> float:
    return (at - at.replace(hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute, second=0, microsecond=0)
            ).total_seconds() / 60


def volume_note(ratio: float | None, vol_mult: float, at: datetime) -> str:
    if ratio is None:
        return "거래량 추정 불가(장 초반·자료 없음)"
    early = " (장 초반 추정)" if _minutes_since_open(at) < EARLY_MINUTES else ""
    if ratio >= vol_mult:
        return f"거래량 {ratio:.1f}배 예상 ✓{early}"
    return f"거래량 부족(장중 추정) ✘ {ratio:.1f}배{early}"


# ---------------------------------------------------------------- 알림
@dataclass
class Alert:
    code: str
    name: str
    kind: str
    price: float
    at: datetime
    text: str
    pivot: float | None = None
    stop: float | None = None
    vol_ratio: float | None = None
    source: str = ""

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    @property
    def title(self) -> str:
        return f"[{KIND_TAGS.get(self.kind, self.kind)}] {self.name}"

    @property
    def body(self) -> str:
        head = f"[{KIND_TAGS.get(self.kind, self.kind)}] {self.name} "
        return self.text[len(head):] if self.text.startswith(head) else self.text


def pre_entry(it: WatchItem) -> bool:
    """아직 매수 전(진입 계획 대기)인가. 스캔 진입 계획이 있으면 그 문구로('돌파 확인 — 현재가 … 매수' 만 진입),
    없으면 돌파 이력이 없고 전일 종가가 피벗 이하일 때."""
    if it.plan:
        return not it.plan.startswith("돌파 확인")
    return not it.breakout_date and it.ref_close <= it.pivot


def alert_text(it: WatchItem, kind: str, price: float, ratio: float | None, vol_mult: float, at: datetime) -> str:
    px = f"{price:,.0f}"
    if kind == BREAKOUT_HIT:
        return (f"[돌파] {it.name} {px} (피벗 {it.pivot:,.0f}) · {volume_note(ratio, vol_mult, at)} · "
                f"잠정 — 종가가 피벗 위인지 확인")
    if kind == NEAR:
        return f"[근접] {it.name} {px} · 피벗 {it.pivot:,.0f}까지 {it.pivot / price - 1:+.1%} — 돌파 대기 · 잠정"
    if kind == PULLBACK:
        stop = f" · 손절: 종가 {it.stop:,.0f} 이탈" if it.stop else ""
        return (f"[눌림] {it.name} {px} · 50%선 매수 구간 {it.support:,.0f}~{it.zone_top:,.0f} 진입{stop} · "
                f"잠정 — 종가 확인")
    if kind == STOP:
        if it.is_pullback:
            what = "눌림목 손절은 종가 기준 — 종가 확인"
        elif pre_entry(it):
            what = "돌파 전 — 매수 계획 보류, 종가 확인"
        else:
            what = "손절 검토 — 종가 확인"
        return f"[손절] {it.name} {px} (손절가 {it.stop:,.0f}) · 장중 이탈 · {what} · 잠정"
    return f"[{KIND_TAGS.get(kind, kind)}] {it.name} {px}"


class AlertStore:
    """오늘 낸 알림 (output/live_alerts_YYYYMMDD.csv). 종목·종류별 하루 1회 — 재실행해도 반복하지 않는다.

    기록 파일이 엑셀 등에 열려 있어 쓸 수 없으면 live_alerts_YYYYMMDD.pending.csv 에 대신 쓰고(notice 로 한 번 안내),
    읽을 때는 두 파일을 함께 읽는다. 날짜는 앞으로만 넘어간다 (지난 날짜 시세가 와도 오늘 기록은 그대로).
    """

    def __init__(self, out_dir: str | Path = OUTPUT_DIR, day: date | None = None, *,
                 notice: Callable[[str], None] | None = None):
        self.out_dir = Path(out_dir)
        self.day = day or now_kst().date()
        self._notice = notice or (lambda msg: None)
        self._warned = False
        self._fired: set[tuple[str, str]] = set()
        self.rows: list[dict] = []
        self._load()

    @property
    def path(self) -> Path:
        return self.out_dir / f"live_alerts_{self.day:%Y%m%d}.csv"

    @property
    def pending_path(self) -> Path:
        return self.out_dir / f"live_alerts_{self.day:%Y%m%d}.pending.csv"

    def _load(self) -> None:
        self._fired.clear()
        self.rows = []
        for p in (self.path, self.pending_path):
            if not p.exists():
                continue
            try:
                with open(p, encoding="utf-8-sig", newline="") as f:
                    for row in csv.DictReader(f):
                        code = str(row.get("code") or "").strip()
                        if code.isdigit() and len(code) < 6:
                            code = code.zfill(6)  # 엑셀로 열었다 저장해 앞자리 0 이 빠진 경우
                        row["code"] = code
                        self.rows.append(row)
                        self._fired.add((code, str(row.get("kind") or "")))
            except (OSError, csv.Error):
                pass
        self.rows.sort(key=lambda r: str(r.get("time") or ""))

    def roll(self, day: date) -> None:
        """다음 날로 넘긴다 (자정을 넘겨 실행할 때). 지난 날짜로는 돌아가지 않는다."""
        if day > self.day:
            self.day = day
            self._warned = False
            self._load()

    def has(self, code: str, kind: str) -> bool:
        return (code, kind) in self._fired

    def _append(self, path: Path, row: dict) -> bool:
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            new = not path.exists()
            with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=ALERT_COLUMNS)
                if new:
                    w.writeheader()
                w.writerow(row)
            return True
        except OSError:
            return False

    def add(self, al: Alert) -> bool:
        if al.at.date() > self.day:
            self.roll(al.at.date())
        if self.has(al.code, al.kind):
            return False
        row = {"date": f"{al.at:%Y-%m-%d}", "time": f"{al.at:%H:%M:%S}", "code": al.code, "name": al.name,
               "kind": al.kind, "label": al.label, "price": f"{al.price:.0f}",
               "pivot": "" if al.pivot is None else f"{al.pivot:.0f}",
               "stop": "" if al.stop is None else f"{al.stop:.0f}",
               "vol_ratio": "" if al.vol_ratio is None else f"{al.vol_ratio:.2f}", "source": al.source, "text": al.text}
        self._fired.add((al.code, al.kind))
        self.rows.append(row)
        if not self._append(self.path, row):
            side = self._append(self.pending_path, row)
            if not self._warned:
                self._warned = True
                how = (f"{self.pending_path.name} 에 대신 기록합니다" if side
                       else "이번 실행 안에서만 중복을 막습니다 (다시 실행하면 같은 알림이 또 날 수 있음)")
                try:
                    self._notice(f"알림 기록 파일 {self.path.name} 을 쓸 수 없습니다 — 엑셀 등에서 열려 있으면 닫으세요. {how}")
                except Exception:
                    pass
        return True


@dataclass
class ItemState:
    price: float | None = None
    change_pct: float | None = None
    cum_volume: float | None = None
    vol_ratio: float | None = None
    updated_at: datetime | None = None
    last_alert: str = ""
    last_alert_at: str = ""
    was_below: bool = True              # 피벗 아래(이하)에 있었는가 — 돌파 알림 조건
    was_above_stop: bool = True         # 손절가 위에 있었는가 — 손절 알림 조건 (이미 아래였던 종목은 알리지 않음)
    stopped: bool = False               # 오늘 손절가를 깼는가(전일 종가가 손절가 이하 포함) — 그러면 매수 쪽 알림 생략
    stale: bool = False                 # 표시 중인 시세가 오늘 정규장 체결이 아님 (지난 거래일·체결 전)


class TriggerEngine:
    """Tick → 알림. 근접·돌파·눌림·손절 각각 종목별 하루 1회 (AlertStore 로 재실행 간에도 유지).

    store.day 가 '오늘'이다. 그날 09:00 이후의 체결(누적 거래량 0 이 아닌 시세)만 알림 판단에 쓰고, 지난 거래일 시세
    (휴장일·첫 체결 전 네이버 시세의 localTradedAt)는 화면 표시만 한다 (stale_ticks 로 셈). 다음 날짜 시세가 오면
    (자정을 넘겨 실행) 기록 파일을 새 날짜로 넘긴다. 손절 알림이 난 종목은 그날 근접·돌파·눌림 알림을 내지 않는다.
    """

    def __init__(self, items: Iterable[WatchItem], store: AlertStore, *, near_pct: float = 0.01,
                 vol_mult: float = 1.4, clock: Callable[[], datetime] = now_kst):
        self.items = {it.code: it for it in items}
        self.store = store
        self.near_pct = near_pct
        self.vol_mult = vol_mult
        self.clock = clock
        self.fresh_ticks = 0
        self.stale_ticks = 0
        self.state = {c: self._initial_state(it, it.ref_close) for c, it in self.items.items()}
        self._apply_store_rows()

    @staticmethod
    def _initial_state(it: WatchItem, ref: float) -> ItemState:
        below_stop = bool(it.stop) and ref <= it.stop
        return ItemState(was_below=not ref > it.pivot, was_above_stop=not below_stop, stopped=below_stop)

    def _apply_store_rows(self) -> None:
        for row in self.store.rows:   # 재실행: 오늘 이미 낸 알림을 '마지막 알림' 칸에, 손절 알림은 상태에도
            st = self.state.get(row.get("code", ""))
            if st is not None:
                st.last_alert, st.last_alert_at = row.get("text", ""), row.get("time", "")
                if row.get("kind") == STOP:
                    st.stopped = True

    def _new_day(self, day: date) -> None:
        """자정을 넘겨 계속 실행할 때(--after-hours): 새 날짜 기록으로 넘기고 하루 단위 상태를 다시 잡는다."""
        self.store.roll(day)
        for c, it in self.items.items():
            old = self.state[c]
            st = self._initial_state(it, old.price if old.price is not None else it.ref_close)
            st.price, st.change_pct, st.updated_at, st.stale = old.price, old.change_pct, old.updated_at, True
            self.state[c] = st
        self._apply_store_rows()

    def is_fresh(self, t: Tick, now: datetime) -> bool:
        """오늘(store.day) 09:00 이후 체결인가. 지난 거래일 시세·장 시작 전·누적 거래량 0(아직 체결 없음)은 False."""
        if now.tzinfo is not None:
            now = now.astimezone(KST)
        if now.date() != self.store.day or now.time() < SESSION_OPEN:
            return False
        v = t.cum_volume
        return not (v is not None and v == v and v <= 0)

    def on_tick(self, t: Tick) -> list[Alert]:
        it = self.items.get(t.code)
        if it is None or not (t.price and t.price == t.price and t.price > 0):
            return []
        now = t.time or self.clock()
        day = (now.astimezone(KST) if now.tzinfo is not None else now).date()
        if day > self.store.day:
            self._new_day(day)
        st = self.state[t.code]
        if not self.is_fresh(t, now):
            # 표시만: 오늘 체결을 받기 전까지 지난 시세를 보여 주고, 알림·거래량 환산에는 쓰지 않는다
            self.stale_ticks += 1
            if st.updated_at is None or st.stale:
                st.price, st.updated_at, st.stale = float(t.price), now, True
                if t.change_pct == t.change_pct:
                    st.change_pct = float(t.change_pct)
            return []
        self.fresh_ticks += 1
        st.price, st.updated_at, st.stale = float(t.price), now, False
        if t.change_pct == t.change_pct:
            st.change_pct = float(t.change_pct)
        if t.cum_volume == t.cum_volume and t.cum_volume and t.cum_volume > 0:
            st.cum_volume = float(t.cum_volume)
        st.vol_ratio = volume_ratio(st.cum_volume, it.avg_vol_50, now)
        p = float(t.price)
        out: list[Alert] = []
        if it.stop:
            if p > it.stop:
                st.was_above_stop = True
            else:
                if st.was_above_stop:
                    out += self._fire(it, STOP, t, now)
                st.was_above_stop = False
                st.stopped = True
        if st.stopped:
            return out   # 손절가를 깬 날에는 근접·돌파·눌림(매수 쪽) 알림을 내지 않는다
        if it.is_pullback:
            if it.support <= p <= it.zone_top:
                out += self._fire(it, PULLBACK, t, now)
        elif p > it.pivot:
            if st.was_below:
                out += self._fire(it, BREAKOUT_HIT, t, now)
        else:
            st.was_below = True
            if p >= it.pivot * (1 - self.near_pct) and not self.store.has(it.code, BREAKOUT_HIT):
                out += self._fire(it, NEAR, t, now)
        return out

    def _fire(self, it: WatchItem, kind: str, t: Tick, now: datetime) -> list[Alert]:
        if self.store.has(it.code, kind):
            return []
        st = self.state[it.code]
        al = Alert(code=it.code, name=it.name, kind=kind, price=float(t.price), at=now,
                   text=alert_text(it, kind, float(t.price), st.vol_ratio, self.vol_mult, now),
                   pivot=it.pivot, stop=it.stop, vol_ratio=st.vol_ratio, source=t.source)
        if not self.store.add(al):
            return []
        st.last_alert, st.last_alert_at = al.text, f"{now:%H:%M:%S}"
        return [al]


# ---------------------------------------------------------------- 알림 출력 (콘솔·토스트·소리)
TOAST_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
_TOAST_PS = """$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml('<toast><visual><binding template="ToastGeneric"><text>__TITLE__</text><text>__BODY__</text></binding></visual></toast>')
$toast = New-Object Windows.UI.Notifications.ToastNotification $xml
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('__APP__').Show($toast)
"""


def _xml_ps(text: str) -> str:
    """토스트 XML 안 문자열: XML 이스케이프 + PowerShell 작은따옴표 문자열 이스케이프."""
    s = html.escape(str(text), quote=True)
    return s.replace("'", "''")


def toast_script(title: str, body: str, app_id: str = TOAST_APP_ID) -> str:
    return (_TOAST_PS.replace("__TITLE__", _xml_ps(title)).replace("__BODY__", _xml_ps(body))
            .replace("__APP__", app_id.replace("'", "''")))


def toast_command(title: str, body: str) -> list[str]:
    """Windows PowerShell 5.1 내장 Windows.UI.Notifications 로 토스트를 띄우는 명령 (추가 모듈 없음)."""
    enc = base64.b64encode(toast_script(title, body).encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
            "-EncodedCommand", enc]


def toast_available() -> bool:
    return sys.platform == "win32" and shutil.which("powershell") is not None


def show_toast(title: str, body: str, popen: Callable = subprocess.Popen) -> bool:
    """토스트를 띄운다 (기다리지 않음). 실패해도 예외를 내지 않고 False."""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        popen(toast_command(title, body), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL, creationflags=flags)
        return True
    except Exception:
        return False


def _beep() -> None:
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass


class Notifier:
    def __init__(self, *, toast: bool = True, beep: bool = False, out: Callable[[str], None] | None = None,
                 toast_fn: Callable[[str, str], bool] | None = None):
        self.toast = bool(toast) and (toast_fn is not None or toast_available())
        self.beep = beep
        self.out = out or (lambda s: print(s, flush=True))
        self._toast_fn = toast_fn or show_toast
        self.sent = 0

    def notify(self, al: Alert) -> None:
        self.sent += 1
        try:
            self.out(f"{al.at:%H:%M:%S} {al.text}")
        except Exception:
            pass
        if self.toast:
            try:
                if not self._toast_fn(al.title, al.body):
                    self.toast = False
            except Exception:
                self.toast = False
        if self.beep:
            _beep()


# ---------------------------------------------------------------- 대시보드
@dataclass
class LiveStatus:
    source: str = "-"
    message: str = ""
    ticks: int = 0
    alerts: int = 0
    last_tick_at: datetime | None = None
    started_at: datetime = field(default_factory=now_kst)
    close_at: datetime | None = None

    def set(self, msg: str) -> None:
        self.message = msg


def _dist(it: WatchItem, price: float | None) -> tuple[float | None, str]:
    """(정렬용 거리, 표시 문구). 눌림목은 매수 구간까지, 그 밖은 피벗까지."""
    if price is None:
        return None, "-"
    if it.is_pullback:
        if it.support <= price <= it.zone_top:
            return 0.0, "구간 안"
        if price < it.support:
            return abs(price / it.support - 1), f"50%선 {price / it.support - 1:+.1%}"
        return abs(price / it.zone_top - 1), f"구간까지 {it.zone_top / price - 1:+.1%}"
    d = it.pivot / price - 1
    return abs(d), (f"{d:+.1%}" if d >= 0 else f"돌파 {-d:+.1%}")


def _fmt_px(x: float | None) -> str:
    return "-" if x is None or not x == x else f"{x:,.0f}"


def dashboard_rows(engine: TriggerEngine) -> list[dict]:
    rows = []
    for code, it in engine.items.items():
        st = engine.state[code]
        price = st.price if st.price is not None else None
        key, dist = _dist(it, price)
        rows.append({"item": it, "state": st, "dist": dist, "key": key})
    rows.sort(key=lambda r: (r["state"].last_alert == "", r["key"] is None, r["key"] or 0.0))
    return rows


_DASH_CSS = """
:root { --bg:#f3f5f7; --surface:#fff; --sunken:#eef1f4; --ink:#151a21; --muted:#5a6472; --line:#dbe0e6;
  --accent:#0a746f; --up:#d22c43; --down:#1d5ccc; --good:#13835a; --warn:#a86d12;
  --font-body:"IBM Plex Sans KR","Malgun Gothic","Apple SD Gothic Neo",sans-serif;
  --font-data:"IBM Plex Mono",ui-monospace,"Consolas",monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#0e1217; --surface:#151b22; --sunken:#1b222b; --ink:#e5eaf0; --muted:#8d98a7; --line:#273140;
  --accent:#35b5aa; --up:#ff5a6e; --down:#4b8cff; --good:#3cc489; --warn:#e2a64a; color-scheme: dark; } }
:root[data-theme="dark"] { --bg:#0e1217; --surface:#151b22; --sunken:#1b222b; --ink:#e5eaf0; --muted:#8d98a7;
  --line:#273140; --accent:#35b5aa; --up:#ff5a6e; --down:#4b8cff; --good:#3cc489; --warn:#e2a64a; color-scheme: dark; }
* { box-sizing: border-box; }
html { overflow-x: hidden; }
body { margin: 0; background: var(--bg); color: var(--ink); font: 14px/1.5 var(--font-body); }
header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 16px; padding: 12px 16px;
  background: var(--surface); border-bottom: 1px solid var(--line); }
h1 { margin: 0; font-size: 17px; }
.meta { color: var(--muted); font-size: 12.5px; }
.status { margin-left: auto; font-size: 12.5px; color: var(--accent); }
.note { margin: 12px 16px 0; font-size: 12.5px; color: var(--muted); }
.note b { color: var(--warn); font-weight: 600; }
.wrap { margin: 12px 16px; overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
table { border-collapse: collapse; width: 100%; min-width: 860px; }
th, td { padding: 7px 10px; border-bottom: 1px solid var(--line); text-align: left; white-space: nowrap; }
th { font-size: 12px; color: var(--muted); font-weight: 500; background: var(--sunken); position: sticky; top: 0; }
td.n { text-align: right; font-family: var(--font-data); font-variant-numeric: tabular-nums; }
td .sub { display: block; color: var(--muted); font-size: 11.5px; }
td.alert { white-space: normal; min-width: 240px; font-size: 12.5px; }
tr.hit td { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.up { color: var(--up); } .down { color: var(--down); } .ok { color: var(--good); } .muted { color: var(--muted); }
section { margin: 0 16px 24px; }
section h2 { font-size: 14px; margin: 16px 0 6px; }
section ol { margin: 0; padding-left: 20px; font-size: 12.5px; }
"""


def _cls(x: float | None) -> str:
    if x is None or not x == x or x == 0:
        return ""
    return "up" if x > 0 else "down"


def render_dashboard(engine: TriggerEngine, status: LiveStatus, *, now: datetime | None = None,
                     refresh: int = 5) -> str:
    """대시보드 HTML (자동 새로고침, 밝은·어두운 테마 토큰, 빨강=상승 파랑=하락)."""
    now = now or now_kst()
    e = html.escape
    body = []
    for r in dashboard_rows(engine):
        it: WatchItem = r["item"]
        st: ItemState = r["state"]
        chg = st.change_pct
        zone = (f"<span class='sub'>구간 {_fmt_px(it.support)}~{_fmt_px(it.zone_top)}</span>"
                if it.is_pullback else "")
        if st.vol_ratio is None:
            vol = "-"
        else:
            mark = " ✓" if st.vol_ratio >= engine.vol_mult else ""
            vol = f"{st.vol_ratio:.1f}배{mark}"
        stopped = "<span class='sub down'>손절 이탈 — 매수 알림 끔</span>" if st.stopped else ""
        if st.updated_at is None:
            upd = "-"
        elif st.stale:
            upd = f"{st.updated_at:%m-%d %H:%M}<span class='sub'>지난 시세</span>"
        else:
            upd = f"{st.updated_at:%H:%M:%S}"
        body.append(
            f"<tr class='{'hit' if st.last_alert else ''}'>"
            f"<td>{e(it.name)}<span class='sub'>{e(it.code)} · {e(it.market)}</span></td>"
            f"<td class='n {_cls(chg)}'>{_fmt_px(st.price)}</td>"
            f"<td class='n {_cls(chg)}'>{'-' if chg is None else f'{chg:+.2f}%'}</td>"
            f"<td>{e(it.label)} · {e(it.stage_label)}<span class='sub'>{e(it.reason)} · 점수 {it.composite:.0f}</span></td>"
            f"<td class='n'>{e(r['dist'])}<span class='sub'>피벗 {_fmt_px(it.pivot)}</span>{zone}</td>"
            f"<td class='n'>{_fmt_px(it.stop)}{stopped}</td>"
            f"<td class='n'>{e(vol)}</td>"
            f"<td class='alert'>{e(st.last_alert) or '<span class=muted>-</span>'}"
            f"{f'<span class=sub>{e(st.last_alert_at)}</span>' if st.last_alert_at else ''}</td>"
            f"<td class='n muted'>{upd}</td></tr>")
    recent = list(reversed(engine.store.rows[-20:]))
    alerts = "".join(f"<li><span class='muted'>{e(str(r.get('time', '')))}</span> {e(str(r.get('text', '')))}</li>"
                     for r in recent) or "<li class='muted'>아직 없음</li>"
    close = f" · 종료 {status.close_at:%H:%M}" if status.close_at else ""
    return (
        "<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<meta http-equiv=\"refresh\" content=\"{int(refresh)}\">\n<title>실시간 감시</title>\n"
        f"<style>{_DASH_CSS}</style>\n</head>\n<body>\n"
        f"<header><h1>실시간 감시</h1><span class='meta'>{e(status.source)} · 갱신 {now:%H:%M:%S}{close} · "
        f"{len(engine.items)}종목 · 수신 {status.ticks:,}건"
        f"{f' (지난 시세 {engine.stale_ticks:,}건 — 알림 제외)' if engine.stale_ticks else ''} · "
        f"알림 {len(engine.store.rows)}건</span>"
        f"<span class='status'>{e(status.message)}</span></header>\n"
        "<p class='note'><b>조회 전용 — 주문 기능 없음.</b> 장중 신호는 <b>잠정</b>입니다: 돌파는 종가가 피벗 위인지, "
        "눌림목 손절은 종가로 확인하세요. 거래량 예상배수 = 누적 거래량 ÷ 장중 경과 비율(U자형 추정) ÷ 50일 평균 "
        f"(✓ = {engine.vol_mult:.1f}배 이상). '지난 시세'(오늘 체결 전)는 알림에 쓰지 않고, 손절가를 깬 종목은 그날 "
        "매수 쪽 알림을 끕니다.</p>\n"
        "<div class='wrap'><table><thead><tr><th>종목</th><th>현재가</th><th>등락률</th><th>패턴/단계</th>"
        "<th>피벗까지 %</th><th>손절가</th><th>거래량 예상배수</th><th>마지막 알림</th><th>갱신 시각</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table></div>\n"
        f"<section><h2>오늘 알림</h2><ol reversed>{alerts}</ol></section>\n</body>\n</html>\n")


def write_atomic(path: Path, text: str, retries: int = 3) -> bool:
    """임시 파일에 쓴 뒤 교체 (브라우저가 반쯤 쓴 파일을 읽지 않게). 실패하면 False."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    for i in range(retries):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, path)
            return True
        except OSError:
            time.sleep(0.05 * (i + 1))
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    return False


class Dashboard:
    def __init__(self, path: Path, engine: TriggerEngine, status: LiveStatus, refresh: int = 5):
        self.path = Path(path)
        self.engine, self.status, self.refresh = engine, status, refresh

    def write(self) -> bool:
        try:
            return write_atomic(self.path, render_dashboard(self.engine, self.status, refresh=self.refresh))
        except Exception:
            return False


# ---------------------------------------------------------------- 시세 출처
def _num(x) -> float:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return float("nan")


def _iso(s) -> datetime | None:
    if not s:
        return None
    try:
        ts = pd.Timestamp(str(s))
    except (ValueError, TypeError):
        return None
    if ts is pd.NaT:
        return None
    ts = ts.tz_localize(KST) if ts.tzinfo is None else ts.tz_convert(KST)
    return ts.to_pydatetime()


def parse_naver_polling(js: dict, now: datetime | None = None) -> list[Tick]:
    """네이버 실시간 조회 API(api/realtime/domestic/stock/{코드,코드}) 응답 → Tick 목록."""
    out = []
    for d in (js or {}).get("datas") or []:
        if not isinstance(d, dict):
            continue
        code = str(d.get("itemCode") or d.get("symbolCode") or "").strip()
        price = _num(d.get("closePriceRaw", d.get("closePrice")))
        if not code or not price > 0:
            continue
        out.append(Tick(
            code=code, time=_iso(d.get("localTradedAt")) or now or now_kst(), price=price,
            change_pct=_num(d.get("fluctuationsRatioRaw", d.get("fluctuationsRatio"))),
            cum_volume=_num(d.get("accumulatedTradingVolumeRaw", d.get("accumulatedTradingVolume"))),
            cum_value=_num(d.get("accumulatedTradingValueRaw")),
            high=_num(d.get("highPriceRaw", d.get("highPrice"))), low=_num(d.get("lowPriceRaw", d.get("lowPrice"))),
            open=_num(d.get("openPriceRaw", d.get("openPrice"))),
            change=_num(d.get("compareToPreviousClosePriceRaw", d.get("compareToPreviousClosePrice"))),
            source="naver"))
    return out


def _naver_json(url: str) -> dict:
    """한 번만 짧게 시도 (실패하면 다음 회차에 다시 — Ctrl+C 가 오래 걸리지 않게)."""
    from .data import http
    return http.get(url, min_interval=0.2, retries=1, timeout=5).json()


def _naver_snapshot(codes: list[str]) -> list[Tick]:
    """전 종목 목록 API (data.universe) 로 받은 스냅샷에서 감시 종목만 (시가·고가·저가 없음)."""
    from .config import DataConfig
    from .data.universe import fetch_universe
    uni = fetch_universe(DataConfig())
    now = now_kst()
    want = set(codes)
    out = []
    for r in uni.itertuples(index=False):
        if r.code in want and r.close > 0:
            out.append(Tick(code=r.code, time=now, price=float(r.close), change_pct=float(r.change_pct),
                            cum_volume=float(r.volume), cum_value=float(r.value), high=float("nan"),
                            low=float("nan"), open=float("nan"), source="naver"))
    return out


class NaverSource:
    """네이버 시세를 interval 초마다 조회 (20종목씩 묶어 요청 — 40종목이면 2회). 3회 연속 실패하면
    전 종목 목록 API 를 60초 이상 간격으로 쓰는 방식으로 바꾸고, probe_every 초(기본 3분)마다 실시간 조회를 다시
    시도해 되면 원래 방식으로 돌아온다 (잠깐의 네트워크 장애로 하루 종일 느려지지 않게)."""

    def __init__(self, codes: Iterable[str], interval: float = 10.0, *, fetch_json: Callable[[str], dict] | None = None,
                 snapshot: Callable[[list[str]], list[Tick]] | None = None, sleep: Callable | None = None,
                 on_status: Callable[[str], None] | None = None, chunk: int = 20, probe_every: float = 180.0,
                 clock: Callable[[], float] = time.monotonic):
        self.codes = list(dict.fromkeys(str(c) for c in codes))
        self.interval = max(5.0, float(interval))
        self._fetch = fetch_json or _naver_json
        self._snapshot = snapshot or _naver_snapshot
        self._sleep = sleep or asyncio.sleep
        self._status = on_status or (lambda m: None)
        self._clock = clock
        self.chunk = max(1, chunk)
        self.probe_every = float(probe_every)
        self.mode = "polling"
        self._poll_label = f"네이버 시세 ({self.interval:.0f}초 간격)"
        self.label = self._poll_label

    async def _poll(self) -> list[Tick]:
        out: list[Tick] = []
        for i in range(0, len(self.codes), self.chunk):
            url = NAVER_POLL_URL.format(codes=",".join(self.codes[i:i + self.chunk]))
            try:
                js = await asyncio.to_thread(self._fetch, url)
                out += parse_naver_polling(js)
            except Exception as e:
                self._status(f"네이버 시세 조회 실패 ({type(e).__name__})")
        return out

    async def stream(self) -> AsyncIterator[Tick]:
        fails = 0
        probe_at = 0.0
        while True:
            if self.mode == "polling" or self._clock() >= probe_at:
                ticks = await self._poll()
                if ticks:
                    fails = 0
                    if self.mode != "polling":
                        self.mode, self.label = "polling", self._poll_label
                        self._status(f"네이버 실시간 조회 복구 — 다시 {self.interval:.0f}초 간격으로 조회합니다")
                    for t in ticks:
                        yield t
                    await self._sleep(self.interval)
                    continue
                fails += 1
                if self.mode == "polling":
                    if fails < 3:
                        await self._sleep(self.interval)
                        continue
                    self.mode, self.label = "snapshot", "네이버 전 종목 목록 (60초 간격)"
                    self._status(f"네이버 실시간 조회가 계속 실패 — 전 종목 목록 API(60초 간격)로 바꾸고 "
                                 f"{self.probe_every / 60:.0f}분마다 다시 시도합니다")
                probe_at = self._clock() + self.probe_every
            try:
                ticks = await asyncio.to_thread(self._snapshot, self.codes)
            except Exception as e:
                self._status(f"네이버 전 종목 목록 조회 실패 ({type(e).__name__})")
                ticks = []
            for t in ticks:
                yield t
            await self._sleep(max(60.0, self.interval))


class KISRestSource:
    """KIS REST 현재가(FHKST01010100)를 interval 초마다 종목별로 조회 (초당 15회, 모의투자 2회 이하).
    stream(until=…) 이면 그 시각(clock 기준)이 지나면 끝난다 — KISSource 가 웹소켓을 다시 시도할 수 있게."""

    def __init__(self, client: KISRestClient, codes: Iterable[str], interval: float = 15.0, *, market: str = "J",
                 sleep: Callable | None = None, on_status: Callable[[str], None] | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self.client = client
        self.codes = list(dict.fromkeys(str(c) for c in codes))
        self.interval = max(3.0, float(interval))
        self.market = market
        self._sleep = sleep or asyncio.sleep
        self._status = on_status or (lambda m: None)
        self._clock = clock
        self.label = f"한국투자증권 REST 현재가 ({self.interval:.0f}초 간격)"

    async def stream(self, until: float | None = None) -> AsyncIterator[Tick]:
        while True:
            for code in self.codes:
                if until is not None and self._clock() >= until:
                    return
                try:
                    q = await asyncio.to_thread(self.client.quote, code, self.market)
                except KISError as e:
                    if e.code in ("EGW00103", "EGW00105"):
                        raise
                    self._status(f"현재가 조회 실패 {code}: {e.message}")
                    continue
                yield q.to_tick()
            wait = self.interval
            if until is not None:
                wait = min(wait, until - self._clock())
                if wait <= 0:
                    return
            await self._sleep(wait)


class KISSource:
    """KIS 실시간 체결가 웹소켓. 연속 실패(기본 5회)하면 REST 현재가 조회로 바꾸고, rest_window 초(기본 5분)마다
    웹소켓을 다시 시도한다 (websockets 패키지가 없으면 REST 만). 앱키·시크릿 오류(EGW00103·EGW00105)는 그대로 올린다."""

    def __init__(self, cfg: KISConfig, codes: Iterable[str], *, tokens: TokenManager | None = None,
                 venue: str = "krx", interval: float = 15.0, on_status: Callable[[str], None] | None = None,
                 ws_factory: Callable[[], KISWebSocketClient] | None = None,
                 rest_factory: Callable[[], KISRestSource] | None = None, ws_max_failures: int = 5,
                 rest_window: float = 300.0, clock: Callable[[], float] = time.monotonic,
                 quote_client_factory: Callable[[], KISRestClient] | None = None,
                 sleep: Callable | None = None, prime: bool = True):
        self.cfg = cfg
        self.codes = list(dict.fromkeys(str(c) for c in codes))
        self.tokens = tokens
        self.venue = venue
        self.interval = interval
        self._status = on_status or (lambda m: None)
        self.ws_max_failures = ws_max_failures
        self.rest_window = float(rest_window)
        self._clock = clock
        tr = TR_CCNL_TOTAL if venue == "total" else TR_CCNL_KRX
        self._ws_factory = ws_factory or (lambda: KISWebSocketClient(
            cfg, self.codes, tr_id=tr, max_failures=ws_max_failures, on_status=self._status))
        # 장중 REST 는 짧게: 실패한 종목은 다음 회차에 다시 (Ctrl+C 가 오래 걸리지 않게)
        self._rest_factory = rest_factory or (lambda: KISRestSource(
            KISRestClient(cfg, tokens, timeout=5.0, retries=2), self.codes, interval,
            market="UN" if venue == "total" else "J", on_status=self._status))
        # 웹소켓이 받아 주지 않은 종목(구독 한도 초과·40종목 상한 밖)을 보충 조회할 REST 클라이언트
        self._quote_client_factory = quote_client_factory or (lambda: KISRestClient(cfg, tokens, timeout=5.0, retries=2))
        self._market = "UN" if venue == "total" else "J"
        self._sleep = sleep or asyncio.sleep
        self.overflow_codes: list[str] = []
        self.prime = prime
        self._ws_label = f"한국투자증권 실시간 체결 ({'KRX+NXT 통합' if venue == 'total' else 'KRX'}, 웹소켓)"
        self.label = self._ws_label
        self.mode = "ws"
        self.ws_attempts = 0

    async def stream(self) -> AsyncIterator[Tick]:
        ws_usable = True
        key = None
        while True:
            if ws_usable:
                ws = self._ws_factory()
                self.ws_attempts += 1
                if key and getattr(ws, "_key", "") is None:
                    ws._key = key   # 직전 접속키 재사용 (거부된 키는 클라이언트가 이미 버렸다)
                self.mode, self.label = "ws", self._ws_label
                queue: asyncio.Queue = asyncio.Queue()

                async def pump(ws=ws, queue=queue):
                    try:
                        async for t in ws.ticks():
                            await queue.put(("tick", t))
                        await queue.put(("end", None))
                    except Exception as e:  # 소비 쪽에서 같은 예외 처리 경로를 타도록 전달
                        await queue.put(("err", e))

                tasks = [asyncio.create_task(pump()), asyncio.create_task(self._poll_overflow(ws, queue))]
                try:
                    while True:
                        kind, val = await queue.get()
                        if kind == "tick":
                            yield val
                        elif kind == "end":
                            return
                        else:
                            raise val
                except KISError as e:
                    if e.code in ("EGW00103", "EGW00105"):
                        raise
                    key = getattr(ws, "_key", None)
                    if e.code == "WS_LIB":
                        ws_usable = False
                        self._status(f"웹소켓 사용 불가 ({e.message}) — REST 현재가 조회로 바꿉니다")
                    else:
                        self._status(f"웹소켓 사용 불가 ({e.message}) — REST 현재가 조회로 바꾸고 "
                                     f"{self.rest_window / 60:.0f}분 뒤 웹소켓을 다시 시도합니다")
                finally:
                    for tk in tasks:
                        tk.cancel()
                    self.overflow_codes = []
            rest = self._rest_factory()
            self.mode, self.label = "rest", rest.label
            until = self._clock() + self.rest_window if ws_usable else None
            async for t in rest.stream(until=until):
                yield t
            self._status("웹소켓 재연결을 시도합니다")


    def _overflow(self, ws) -> list[str]:
        """웹소켓이 받아 주지 않은 감시 종목: 서버 거부(MAX SUBSCRIBE OVER) + 상한(40) 밖, 단 구독된 것은 제외."""
        over = set(getattr(ws, "overflow", ()) or ()) | set(getattr(ws, "dropped", ()) or ())
        over -= set(getattr(ws, "subscribed", ()) or ())
        return [c for c in self.codes if c in over]

    async def _poll_overflow(self, ws, queue: asyncio.Queue) -> None:
        """웹소켓과 나란히 돌며, 구독되지 못한 종목만 interval 초마다 REST 현재가로 조회해 같은 큐에 넣는다.
        시작할 때는 감시 종목 전체를 한 번 조회해 둔다 — 체결이 뜸한 종목도 대시보드에 처음부터 가격이 보이게."""
        client = None
        announced = -1
        if self.prime and self.codes:
            await self._sleep(1.0)   # 웹소켓 구독 응답을 먼저 받는다
            try:
                client = self._quote_client_factory()
            except Exception as e:   # 보충 조회를 못 해도 웹소켓 시세는 계속 받는다
                self._status(f"REST 현재가 조회 준비 실패 ({type(e).__name__}) — 실시간 체결만 사용합니다")
                return
            for code in self.codes:
                try:
                    q = await asyncio.to_thread(client.quote, code, self._market)
                except KISError as e:
                    if e.code in ("EGW00103", "EGW00105"):
                        await queue.put(("err", e))
                        return
                    continue
                except Exception:
                    continue
                await queue.put(("tick", q.to_tick()))
        while True:
            codes = self._overflow(ws)
            self.overflow_codes = codes
            if len(codes) != announced:
                announced = len(codes)
                if codes:
                    self._status(f"실시간 구독 한도로 {len(codes)}종목은 REST 현재가 조회"
                                 f"({self.interval:.0f}초 간격)로 받습니다")
            if codes:
                try:
                    client = client or self._quote_client_factory()
                except Exception as e:
                    self._status(f"REST 현재가 조회 준비 실패 ({type(e).__name__}) — 실시간 체결만 사용합니다")
                    return
                for code in codes:
                    try:
                        q = await asyncio.to_thread(client.quote, code, self._market)
                    except KISError as e:
                        if e.code in ("EGW00103", "EGW00105"):
                            await queue.put(("err", e))
                            return
                        self._status(f"현재가 조회 실패 {code}: {e.message}")
                        continue
                    except Exception as e:   # 네트워크 등 예기치 못한 오류: 다음 회차에 다시
                        self._status(f"현재가 조회 실패 {code}: {type(e).__name__}")
                        continue
                    await queue.put(("tick", q.to_tick()))
            await self._sleep(self.interval if codes else 2.0)


# ---------------------------------------------------------------- 출처 선택·연결 점검
def resolve_source(mode: str, *, config_path: str | None = None, paper: bool = False,
                   out: Callable[[str], None] = print, token_factory: Callable | None = None
                   ) -> tuple[str | None, KISConfig | None, TokenManager | None]:
    """('kis'|'naver'|None, 설정, 토큰 관리자). auto 는 KIS 설정 형식·접근토큰이 모두 되면 kis, 아니면 이유를 알리고 naver.
    kis 를 지정했는데 안 되면 이유를 출력하고 (None, None, None)."""
    if mode == "naver":
        return "naver", None, None

    def fail(why: str):
        if mode == "kis":
            out(f"✘ 한국투자증권 연결 불가: {why}")
            out("  → 설정을 고친 뒤 'python -m chart_screener live --check' 로 점검하세요.")
            return None, None, None
        out(f"[알림] 한국투자증권 연결 안 함 — {why}")
        out("       네이버 시세(10초 간격 조회, 수 초 지연)로 감시합니다. 점검: python -m chart_screener live --check")
        return "naver", None, None

    try:
        cfg = KISConfig.load(config_path, env="vps" if paper else "prod")
    except KISConfigError as e:
        return fail(e.message.splitlines()[0])
    errs = cfg.diagnose()
    if errs:
        return fail("설정 형식 문제: " + "; ".join(errs[:3]) + (f" 외 {len(errs) - 3}건" if len(errs) > 3 else ""))
    tm = (token_factory or (lambda c: TokenManager(c, notice=out)))(cfg)
    try:
        tm.get()
    except KISError as e:
        return fail(f"접근토큰 발급 실패: {e.message}")
    return "kis", cfg, tm


async def probe_websocket(cfg: KISConfig, code: str = "005930", *, tr_id: str = TR_CCNL_KRX, timeout: float = 8.0,
                          connect: Callable | None = None, approval: Callable | None = None) -> tuple[bool, str]:
    """웹소켓 접속·구독을 잠깐 시험. 장중이면 첫 체결까지, 장 밖이면 구독 응답까지 확인."""
    client = KISWebSocketClient(cfg, [code], tr_id=tr_id, max_failures=1, connect=connect, approval=approval,
                                send_interval=0)
    agen = client.ticks()
    try:
        t = await asyncio.wait_for(agen.__anext__(), timeout)
        return True, f"실시간 체결 수신 {t.code} {t.price:,.0f}원 ({t.time:%H:%M:%S})"
    except asyncio.TimeoutError:
        if client.subscribed:
            return True, "구독 성공 (장 시간이 아니면 체결이 오지 않는 것이 정상)"
        if client.connects:
            return False, "접속은 됐지만 구독 응답이 없습니다"
        return False, client.last_error or "응답 없음"
    except KISError as e:
        return False, e.message
    except StopAsyncIteration:
        return False, client.last_error or "연결 종료"
    finally:
        client.stop()
        try:
            await agen.aclose()
        except Exception:
            pass


def check_connection(config_path: str | None = None, *, paper: bool = False, code: str = "005930",
                     venue: str = "krx", out: Callable[[str], None] = print, session=None,
                     ws_probe: bool = True, today: date | None = None) -> int:
    """한국투자증권 연결 점검 (조회 전용): 설정 형식 → 접근토큰 → 현재가 → 개장일 → 웹소켓. 비밀값은 출력하지 않는다."""
    out("한국투자증권 연결 점검 (조회 전용 — 주문 기능 없음)")
    try:
        cfg = KISConfig.load(config_path, env="vps" if paper else "prod")
    except KISConfigError as e:
        out(f"✘ 설정: {e.message}")
        return 1
    out(f"  설정 파일: {cfg.path}")
    out(f"  {cfg.summary()}")
    for w in cfg.warnings():
        out(f"  ! {w}")
    errs = cfg.diagnose()
    if errs:
        for m in errs:
            out(f"  ✘ {m}")
        out("→ 설정 파일을 고친 뒤 다시 실행하세요 (값은 KIS Developers > 앱 관리에서 복사).")
        return 1
    out("✔ 설정 형식")
    tm = TokenManager(cfg, session=session, notice=lambda m: out(f"  {m}"))
    try:
        tm.get()
    except KISError as e:
        out(f"✘ 접근토큰: {e}")
        return 1
    how = {"cache": "저장된 토큰 재사용", "memory": "저장된 토큰 재사용", "issued": "새로 발급"}.get(tm.source or "", "")
    exp = f", 만료 {tm.expires_at:%m-%d %H:%M}" if tm.expires_at else ""
    out(f"✔ 접근토큰 ({how}{exp}) — 캐시: {tm.cache_path}")
    client = KISRestClient(cfg, tm, session=session)
    try:
        q = client.quote(code, "UN" if venue == "total" else "J")
        out(f"✔ 현재가 {code}: {q.price:,.0f}원 ({q.change_pct:+.2f}%) · 누적 거래량 {q.volume:,.0f}주")
    except KISError as e:
        out(f"✘ 현재가 조회: {e}")
        return 1
    today = (today or now_kst().date())
    try:
        opened = client.open_day(today)
    except Exception:
        opened = None
    if opened is None:
        out("  · 개장일 조회 안 됨 — 건너뜀 (달력·시세로 판단)" + (" · 모의투자는 지원 안 함" if paper else ""))
    else:
        out(f"✔ 개장일 조회: {today:%m-%d} {'개장' if opened else '휴장 — 오늘은 실시간 체결이 없습니다'} "
            f"(캐시: {cfg.holiday_cache_path.name})")
    if ws_probe:
        tr = TR_CCNL_TOTAL if venue == "total" else TR_CCNL_KRX
        try:
            ok, msg = asyncio.run(probe_websocket(cfg, code, tr_id=tr))
        except Exception as e:
            ok, msg = False, f"{type(e).__name__}"
        out(f"{'✔' if ok else '✘'} 웹소켓: {msg}")
        if not ok:
            out("  (웹소켓이 안 되면 live 는 REST 현재가 조회로 대신합니다)")
    out("점검 끝 — 'python -m chart_screener live' 로 실시간 감시를 시작하세요.")
    return 0


# ---------------------------------------------------------------- 실행
def session_phase(now: datetime) -> str:
    """'weekend' | 'holiday'(KRX 휴장일 달력) | 'pre'(09:00 전) | 'open' | 'closed'(15:30 이후).
    달력에 없는 휴장일은 'pre'/'open' 으로 나오지만, 그날 시세는 지난 거래일 것이라 알림이 나가지 않는다."""
    if now.weekday() >= 5:
        return "weekend"
    if krx_holiday(now.date()):
        return "holiday"
    t = now.time()
    if t < SESSION_OPEN:
        return "pre"
    if t < SESSION_CLOSE:
        return "open"
    return "closed"


def scan_cache_fresh(now: datetime | None = None) -> bool:
    """종목목록 캐시가 가장 최근 확정 종가(15:45) 이후에 받은 것이면 True (오프라인 스캔으로 충분)."""
    from .data.ohlcv import _last_final_close
    from .universe_data import UNIVERSE_CACHE
    if not UNIVERSE_CACHE.exists():
        return False
    fetched = datetime.fromtimestamp(UNIVERSE_CACHE.stat().st_mtime, KST)
    return fetched >= _last_final_close(now or now_kst())


def build_watchlist(*, top: int = 40, codes: Iterable[str] | None = None, offline: bool | None = None,
                    refresh: bool = False, verbose: bool = True, today: date | None = None,
                    out: Callable[[str], None] = print):
    """스캔(run_scan)을 돌려 감시 목록을 만든다. offline=None 이면 캐시가 신선할 때만 오프라인."""
    from .config import Config
    from .scanner import run_scan
    from .universe_data import load_universe_data

    cfg = Config()
    if offline is None:
        offline = (not refresh) and scan_cache_fresh()
    out("감시 목록: 스캔 " + ("(캐시 사용)" if offline else "(데이터 받는 중 — 처음이면 2~3분)"))
    try:
        ud = load_universe_data(cfg, refresh=refresh, offline=offline, verbose=verbose)
    except RuntimeError:
        if not offline:
            raise
        out("  캐시가 없어 온라인으로 받습니다")
        ud = load_universe_data(cfg, refresh=refresh, offline=False, verbose=verbose)
    if ud.asof is None or not ud.ohlcv:
        raise RuntimeError("분석할 일봉 데이터가 없습니다 (캐시가 비었거나 수집 실패)")
    scan = run_scan(ud, cfg, verbose=verbose, offline=bool(offline))
    return scan, select_watchlist(scan, top, today=today, codes=codes)


def print_watchlist(items: list[WatchItem], out: Callable[[str], None] = print) -> None:
    out(f"감시 목록 {len(items)}종목")
    for it in items:
        zone = (f"구간 {it.support:,.0f}~{it.zone_top:,.0f}" if it.is_pullback else f"피벗 {it.pivot:,.0f}")
        stop = f"손절 {it.stop:,.0f}" if it.stop else "손절 -"
        vol = f"50일 평균 {it.avg_vol_50 / 1e4:,.0f}만주" if it.avg_vol_50 else "50일 평균 -"
        out(f"  {it.code} {it.name:<10} {it.reason:<8} {it.label} · {it.stage_label} · {zone} · {stop} · {vol} · "
            f"점수 {it.composite:.0f}")


async def live_loop(source, engine: TriggerEngine, notifier: Notifier, dash: Dashboard, status: LiveStatus, *,
                    close_at: datetime | None, every: float = 3.0, clock: Callable[[], datetime] = now_kst,
                    out: Callable[[str], None] = print, holiday_check: bool = False,
                    watch_every: float = 15.0) -> int:
    """시세를 받아 알림·대시보드를 갱신. close_at 이 지나거나 출처가 끝나면 종료. 반환: 0 정상, 1 출처 오류.

    holiday_check 이면 09:05 이 지나도 오늘 체결이 없을 때 안내하고, 10:15 까지 지난 거래일 시세만 왔으면
    (달력에 없는 휴장일) 종료한다."""
    async def consume():
        async for t in source.stream():
            status.ticks += 1
            status.last_tick_at = t.time
            status.source = getattr(source, "label", status.source)
            for al in engine.on_tick(t):
                status.alerts += 1
                notifier.notify(al)

    async def refresher():
        while True:
            status.source = getattr(source, "label", status.source)
            dash.write()
            await asyncio.sleep(every)

    async def closer():
        while True:
            rem = (close_at - clock()).total_seconds()
            if rem <= 0:
                return
            await asyncio.sleep(min(rem, 30.0))

    async def watchdog():
        """오늘 체결이 없는지 지켜본다. 휴장일로 판단되면 끝난다 (그 밖에는 계속 돈다)."""
        day = engine.store.day
        warn_at = datetime.combine(day, SESSION_OPEN, KST) + QUIET_WARN
        stop_at = datetime.combine(day, HOLIDAY_STOP, KST)
        warned = False
        while True:
            await asyncio.sleep(watch_every)
            if engine.fresh_ticks:
                continue
            now = clock()
            if now >= stop_at and engine.stale_ticks:
                return
            if now >= warn_at and not warned:
                warned = True
                msg = ("아직 오늘 체결이 없습니다 — 지난 거래일 시세는 알림에 쓰지 않습니다 (늦은 개장·휴장일일 수 있음)"
                       if engine.stale_ticks else "아직 시세 수신이 없습니다 — 휴장일이거나 연결 문제일 수 있습니다")
                status.set(msg)
                out(f"  · {msg}")

    feed = asyncio.create_task(consume())
    tasks = [feed, asyncio.create_task(refresher())]
    stopper = asyncio.create_task(closer()) if close_at is not None else None
    if stopper is not None:
        tasks.append(stopper)
    holiday = asyncio.create_task(watchdog()) if holiday_check else None
    if holiday is not None:
        tasks.append(holiday)
    rc = 0
    try:
        done, _ = await asyncio.wait([t for t in (feed, stopper, holiday) if t is not None],
                                     return_when=asyncio.FIRST_COMPLETED)
        if feed in done and feed.exception() is not None:
            e = feed.exception()
            out(f"시세 수신 중단: {e}")
            status.set(f"시세 수신 중단: {getattr(e, 'message', type(e).__name__)}")
            rc = 1
        elif stopper is not None and stopper in done:
            out("15:30 장 마감 — 감시를 마칩니다. 장중 신호는 종가로 다시 확인하세요.")
            status.set("장 마감 — 종료")
        elif holiday is not None and holiday in done:
            out(f"{HOLIDAY_STOP:%H:%M} 까지 오늘 체결이 하나도 없습니다 (받은 시세가 모두 지난 거래일 것) — "
                "휴장일로 보고 감시를 마칩니다.")
            status.set("오늘 체결 없음 — 휴장일로 보고 종료")
        else:
            status.set("시세 수신 종료")
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        dash.write()
    return rc


def _wait_until_open(status: LiveStatus, dash: Dashboard, out: Callable[[str], None] = print) -> None:
    """09:00 까지 카운트다운 (Ctrl+C 로 중단)."""
    tty = sys.stdout.isatty()
    last_print = 0.0
    while True:
        now = now_kst()
        start = now.replace(hour=SESSION_OPEN.hour, minute=SESSION_OPEN.minute, second=0, microsecond=0)
        rem = (start - now).total_seconds()
        if rem <= 0:
            if tty:
                out("")
            return
        h, m, s = int(rem // 3600), int(rem % 3600 // 60), int(rem % 60)
        msg = f"장 시작(09:00)까지 {h:02d}:{m:02d}:{s:02d}"
        status.set(msg)
        if tty:
            print(f"\r{msg}  (Ctrl+C 종료)", end="", flush=True)
        elif time.monotonic() - last_print >= 300 or last_print == 0.0:
            out(msg)
            last_print = time.monotonic()
        if int(rem) % 15 == 0:
            dash.write()
        time.sleep(min(1.0, rem))


def make_source(kind: str, cfg: KISConfig | None, tokens: TokenManager | None, codes: list[str], *, venue: str,
                interval: float | None, status: LiveStatus, out: Callable[[str], None] = print):
    last = {"msg": None, "at": 0.0}

    def on_status(msg: str) -> None:
        status.set(msg)
        # 같은 문구가 반복되면(네트워크 장애 등) 1분에 한 번만 출력
        if msg == last["msg"] and time.monotonic() - last["at"] < 60:
            return
        last["msg"], last["at"] = msg, time.monotonic()
        out(f"  · {msg}")

    if kind == "kis" and cfg is not None:
        return KISSource(cfg, codes, tokens=tokens, venue=venue, interval=interval or 15.0, on_status=on_status)
    return NaverSource(codes, interval or 10.0, on_status=on_status)


def run(a) -> int:
    """CLI 'live' 진입점 (조회 전용 — 주문 없음). 준비 단계(토큰 대기·스캔)에서 Ctrl+C 를 눌러도 깔끔히 끝낸다."""
    try:
        return _run(a)
    except KeyboardInterrupt:
        print("\nCtrl+C — 감시를 종료합니다.")
        return 0


def _run(a) -> int:
    out_dir = Path(getattr(a, "out", "") or OUTPUT_DIR)
    if getattr(a, "check", False):
        return check_connection(a.config or None, paper=a.paper, code=a.check_code, venue=a.venue)

    now = now_kst()
    phase = session_phase(now)
    if not a.after_hours and phase == "weekend":
        print("주말에는 장이 열리지 않습니다 (강제 실행: --after-hours).")
        return 0
    if not a.after_hours and phase == "holiday":
        print(f"오늘({now:%m-%d})은 KRX 휴장일입니다 (강제 실행: --after-hours).")
        return 0
    if not a.after_hours and phase == "closed":
        print("오늘 정규장이 끝났습니다 (15:30). 내일 09:00 전에 다시 실행하세요 (강제 실행: --after-hours).")
        return 0
    if a.top < 1:
        print("--top 은 1 이상이어야 합니다.", file=sys.stderr)
        return 2
    print("실시간 감시 — 조회 전용 (주문 기능 없음)")

    kind, cfg, tokens = resolve_source(a.source, config_path=a.config or None, paper=a.paper)
    if kind is None:
        return 2
    if kind == "kis" and not a.after_hours:
        # 달력에 없는 휴장일 확인 (KIS 국내휴장일조회 — 결과를 캐시해 하루 1회만 부른다)
        try:
            opened = KISRestClient(cfg, tokens, timeout=5.0, retries=1).open_day(now.date())
        except Exception:
            opened = None
        if opened is False:
            print(f"오늘({now:%m-%d})은 휴장일입니다 (한국투자증권 국내휴장일조회). 강제 실행: --after-hours")
            return 0
    top = a.top
    if kind == "kis" and top > 40:
        print("KIS 실시간 구독은 세션당 40종목까지라 --top 을 40 으로 줄입니다.")
        top = 40
    codes = [c.strip() for c in (a.codes or "").split(",") if c.strip()]
    try:
        scan, items = build_watchlist(top=top, codes=codes, offline=True if a.offline else None,
                                      refresh=a.refresh_scan, verbose=sys.stderr.isatty(), today=now.date())
    except Exception as e:
        print(f"감시 목록을 만들지 못했습니다: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    missing = [c for c in codes if c not in {it.code for it in items}]
    if missing:
        print(f"  지정 종목 중 스캔 후보가 아니거나 피벗이 없어 제외: {', '.join(missing)}")
    if not items:
        print("감시할 종목이 없습니다 (돌파·피벗 근접·눌림목·돌파 매수 대기 후보 없음).")
        return 0
    asof = f"{scan.asof:%Y-%m-%d}" if scan.asof is not None else "-"
    print(f"스캔 기준일 {asof} · 후보 {len(scan.stocks)}종목 중")
    print_watchlist(items)

    store = AlertStore(out_dir, now.date(), notice=lambda m: print(f"  ! {m}", flush=True))
    engine = TriggerEngine(items, store, near_pct=a.near / 100, vol_mult=a.vol_mult)
    close_at = None if a.after_hours else datetime.combine(now.date(), SESSION_CLOSE, KST) + CLOSE_GRACE
    status = LiveStatus(close_at=close_at)
    source = make_source(kind, cfg, tokens, [it.code for it in items], venue=a.venue, interval=a.interval,
                         status=status)
    status.source = source.label
    dash = Dashboard(out_dir / DASHBOARD_NAME, engine, status, refresh=max(2, int(round(a.dash_every))))
    status.set("시작")
    dash.write()
    print(f"대시보드: {dash.path}")
    if store.rows:
        print(f"오늘 이미 낸 알림 {len(store.rows)}건은 다시 알리지 않습니다 ({store.path.name}).")
    if not a.no_open:
        try:
            webbrowser.open(dash.path.resolve().as_uri())
        except Exception:
            pass
    notifier = Notifier(toast=not a.no_toast, beep=a.beep)
    rc = 0
    try:
        if phase == "pre" and not a.after_hours:
            _wait_until_open(status, dash)
        status.set("시세 수신 중")
        print(f"시세: {source.label} — Ctrl+C 로 종료")
        rc = asyncio.run(live_loop(source, engine, notifier, dash, status, close_at=close_at,
                                   every=max(1.0, float(a.dash_every)), holiday_check=not a.after_hours))
    except KeyboardInterrupt:
        print("\nCtrl+C — 감시를 종료합니다.")
        status.set("사용자 종료")
    finally:
        dash.write()
        print(f"오늘 알림 {len(store.rows)}건 · 기록 {store.path} · 대시보드 {dash.path}")
    return rc
