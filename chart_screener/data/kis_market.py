"""한국투자증권(KIS) 일일 데이터 허브 — 전 종목 상태·실제 거래대금 + 후보 종목 수급·투자의견·추정실적.

일일 스캔용 '조회 전용' 배치 수집기다. 클라이언트 하나(KISRestClient, 초당 15회 제한기 공유)를 여러 작업 스레드가
같이 쓰고, 결과는 cache/kis 아래 JSON 으로 캐시한다. 비밀값(앱키·시크릿·토큰)은 broker.kis 가 가린다.

    from chart_screener.data import kis_market as km
    res = km.refresh(codes_all, codes_focus, progress=lambda step, i, n: ...)
    print(res.summary())                 # 단계별 건수·시간, 치명 오류(인증 실패 등) 사유
    df = km.apply_turnover(df, res.turnover.get(code, {}))   # 추정 거래대금 → 실제 거래대금

단계 (refresh)
  1. 상태      전 종목 inquire-price (FHKST01010100) → Status (관리·경고·정지·증거금·시총·PER…)   status_YYYYMMDD.json
  2. 거래대금  전 종목 일봉 (FHKST03010100, 1회 100봉) → 실제 일별 거래대금(원)                  turnover/<code>.json
  3. 수급      후보 inquire-investor (FHKST01010900, 30일) → 외국인·기관·개인 순매수(억원)         flows_YYYYMMDD.json
  4. 투자의견  후보 invest-opinion (FHKST663300C0, 180일) → 목표가 상향·하향 건수, 평균 목표가    opinion_YYYYMMDD.json
  5. 추정실적  후보 estimate-perform (HHKST668300C0) → 연도별 매출·영업이익·EPS·ROE, 선행 EPS 증가율 estimate_YYYYMMDD.json
  날짜(YYYYMMDD)는 market_date(): 확정 종가가 있는 가장 최근 개장일 (평일 15:45 이후 개장일이면 오늘).
  종목 하나의 실패는 errors 에 적고 건너뛴다. 인증 실패(앱키·시크릿·토큰)는 그 자리에서 멈추고 사유를 돌려준다.

단위 (2026-10 실전 응답으로 확인)
  - inquire-price hts_avls = 시가총액(억원). iscd_stat_cls_code 51 관리 · 52 위험 · 53 경고 · 54 주의 · 55 정상
    · 57 증거금100% · 58 거래정지 · 59 단기과열. mrkt_warn_cls_code 00 없음 · 01 주의 · 02 경고 · 03 위험.
  - inquire-investor *_ntby_tr_pbmn = 백만원 (-26614 = -266억), *_ntby_qty = 주. 당일 행은 장 마감 후, 기관은 저녁 확정.
  - estimate-perform output2(6행) 매출·영업이익·순이익은 억원, 증감률은 ×0.1 %. output3(최대 8행) EBITDA 억원,
    EPS·EPS증감률·PER·EV/EBITDA·ROE·부채비율·이자보상배율은 ×0.1 (005930 EPS 2024 '49500' = 4,950원,
    PER '107' = 10.7배, 부채비율 '279' = 27.9% — 000660·035420 로도 확인). output3 행이 3개뿐인 종목도 있다.
    커버리지 없는 종목은 output4 가 비어 있다 → 추정 없음(None).
  - invest-opinion 은 직전 목표가가 없다 → 같은 증권사의 창 안 연속 행끼리 비교해 상향·하향을 판정한다.

스냅샷 JSON (write_snapshot, 기업추적 뷰어가 읽는다) — 비어 있는 값은 null (NaN 없음)
  {
    "v": 1, "at": "2026-10-09T16:20:11+09:00", "date": "20261008", "env": "prod",
    "steps": [{"step": "status", "n": 2500, "ok": 2498, "fail": 2, "secs": 171.2}, ...],
    "status":   {code: {"stat": "55", "tags": ["관리종목", ...], "ex": "관리종목"|null, "cap": 억원, "per", "pbr",
                        "frgn": 외국인소진율%, "hold": 외국인보유율%, "loan": 융자잔고율%, "marg": 증거금률%,
                        "sec": 업종명, "px": 현재가}},
    "flows":    {code: {"f20": 외국인20일 순매수(억원), "o20": 기관20일, "f5": 외국인5일, "o5": 기관5일}},
    "opinion":  {code: {"n30": 30일 리포트 수, "up30": 목표가 상향, "down30": 하향, "avg_tp": 90일 증권사별 최신
                        목표가 평균(원), "gap": 평균 목표가 대비 현재가 여력 %}},
    "estimate": {code: {"fwd_eps_g": 선행 EPS 증가율 %, "eps_e": 선행 연도 EPS(원), "years": ["2026.12E", "2027.12E"]}}
  }
"""
from __future__ import annotations

import json
import math
import os
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from ..broker.kis import (
    KST, PATH_DAILY, PATH_PRICE, TR_DAILY, TR_PRICE, KISAuthError, KISConfig, KISConfigError, KISError,
    KISRestClient, TokenManager,
)
from ..config import CACHE_DIR, OUTPUT_DIR

_Q = "/uapi/domestic-stock/v1/quotations/"
PATH_INVESTOR = _Q + "inquire-investor"
PATH_OPINION = _Q + "invest-opinion"
PATH_ESTIMATE = _Q + "estimate-perform"
TR_INVESTOR = "FHKST01010900"     # 종목별 투자자 (30일)
TR_OPINION = "FHKST663300C0"      # 종목 투자의견
TR_ESTIMATE = "HHKST668300C0"     # 종목 추정실적

DATA_FINAL = time(15, 45)         # 종가 확정(여유 포함) — data.ohlcv 와 같은 기준
FLOWS_FINAL = time(18, 10)        # 기관·외국인 수치 확정 — data.investor 와 같은 기준
VALUE_FINAL = time(18, 10)        # 거래대금 확정 — 시간외 종가(~16:00) · 시간외 단일가(~18:00)까지 더해진 뒤
STATUS_TTL = timedelta(hours=3)   # 종목 상태 캐시 재사용 한도 (같은 날 · 3시간 안 — 장중 지정 · 정지를 놓치지 않게)
# 다시 시도해도 소용없는 오류: 앱키·시크릿 오류, 재발급 후에도 토큰 거부, 토큰 발급 한도
FATAL_CODES = {"EGW00103", "EGW00105", "EGW00121", "EGW00123", "EGW00133", "CONFIG"}

Progress = Callable[[str, int, int], None]   # (단계, 완료 수, 전체 수)


@dataclass
class KISMarketConfig:
    cache_dir: Path = CACHE_DIR / "kis"                      # 일자별 JSON 캐시 (turnover/ 하위 폴더 포함)
    snapshot_path: Path | None = OUTPUT_DIR / "kis_market.json"   # 뷰어용 스냅샷 (None 이면 쓰지 않음)
    workers: int = 8                 # 작업 스레드 수 (호출 간격은 클라이언트 제한기가 지킨다)
    env: str = "prod"                # 'prod' 실전 | 'vps' 모의투자
    config_path: str | None = None   # kis_devlp.yaml 경로 (None = 기본 위치·환경변수)
    timeout: float = 10.0            # 요청 1건 제한 시간(초)
    retries: int = 2                 # 5xx·연결 오류 재시도 횟수
    turnover_days: int = 100         # 첫 수집 시 받을 거래일 수 (이후 매일 누적)
    flows_days: int = 30             # 수급 응답 길이 (API 고정 30일)
    opinion_days: int = 180          # 투자의견 조회 창 (직전 목표가 비교용으로 넉넉히)
    opinion_recent: int = 30         # 상향·하향 집계 창 (달력 일)
    target_days: int = 90            # 평균 목표가 창 (달력 일)
    keep_days: int = 7               # 일자별 캐시 파일 보관 개수 (종류별)


# ---------------------------------------------------------------- 공용 도우미
def _f(x, scale: float = 1.0) -> float | None:
    """'1,234.50' → 1234.5 × scale. 빈 값·숫자 아님·NaN 은 None (JSON 에 NaN 을 남기지 않는다)."""
    if x is None:
        return None
    try:
        v = float(str(x).replace(",", "").strip())
    except ValueError:
        return None
    if not math.isfinite(v):
        return None
    return v if scale == 1.0 else round(v * scale, 6)   # ×0.1 부동소수 잡음(36.800000000000004) 제거


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _now() -> datetime:
    return datetime.now(KST)


def is_fatal(e: BaseException) -> bool:
    """더 진행해도 소용없는 오류인지 (인증·설정 실패)."""
    return isinstance(e, (KISAuthError, KISConfigError)) or (
        isinstance(e, KISError) and str(e.code or "") in FATAL_CODES)


def _err_text(e: BaseException) -> str:
    return e.message if isinstance(e, KISError) else f"{type(e).__name__}: {e}"


def _rows(js: dict, key: str = "output") -> list[dict]:
    rows = js.get(key) if isinstance(js, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    return [r for r in rows or [] if isinstance(r, dict)]


# ---------------------------------------------------------------- 클라이언트·개장일
def client_or_none(cfg: KISMarketConfig | None = None, *, load: Callable | None = None,
                   tokens: Callable | None = None) -> tuple[KISRestClient | None, str]:
    """(클라이언트, '') 또는 (None, 한글 사유). 설정이 없거나 토큰 발급이 실패해도 예외를 던지지 않는다.
    load·tokens 는 시험용 주입 (기본: KISConfig.load, TokenManager)."""
    cfg = cfg or KISMarketConfig()
    try:
        kc = (load or KISConfig.load)(cfg.config_path, env=cfg.env)
    except KISConfigError as e:
        return None, "한국투자증권 설정 없음: " + e.message.splitlines()[0]
    except Exception as e:  # 설정 파일 읽기 오류 (권한 등)
        return None, f"한국투자증권 설정 읽기 실패 ({type(e).__name__})"
    errs = kc.diagnose()
    if errs:
        return None, "한국투자증권 설정 형식 문제: " + "; ".join(errs[:3])
    tm = (tokens or (lambda c: TokenManager(c, wait_on_limit=False)))(kc)
    try:
        tm.get()
    except KISError as e:
        return None, f"접근토큰 발급 실패: {e.message}"
    return KISRestClient(kc, tm, timeout=cfg.timeout, retries=cfg.retries), ""


def _cal_open(d: date) -> bool:
    """KRX 달력(주말 · 고정 휴장일 · 알려진 비정기 휴장일, live.krx_holiday)으로 본 개장일 여부."""
    from ..live import krx_holiday
    return d.weekday() < 5 and not krx_holiday(d)


def _open(client, d: date) -> bool:
    """개장일 여부. 주말은 False, KIS 휴장일 조회가 답하면 그 값, 모르면(None · 오류 · 모의투자) KRX 달력."""
    if d.weekday() >= 5:
        return False
    try:
        v = client.open_day(d) if client is not None else None
    except Exception:
        v = None
    return _cal_open(d) if v is None else bool(v)


def is_open_today(client, at: datetime | None = None) -> bool | None:
    """오늘이 KRX 개장일이면 True, 휴장일이면 False (KIS 국내휴장일조회, 결과는 파일 캐시).
    KIS 가 모르면(None · 오류 · 모의투자) KRX 달력으로 답한다 — 달력에도 없는 새 휴장일만 놓친다."""
    at = at or _now()
    if at.weekday() >= 5:
        return False
    try:
        v = client.open_day(at.date()) if client is not None else None
    except Exception:
        v = None
    return _cal_open(at.date()) if v is None else bool(v)


def market_date(client, at: datetime | None = None) -> date:
    """확정 종가가 있는 가장 최근 개장일 — 평일 15:45 이후이고 오늘 개장했으면 오늘, 아니면 그 이전 개장일."""
    at = at or _now()
    d = at.date()
    if at.time() >= DATA_FINAL and _open(client, d):
        return d
    for _ in range(20):
        d -= timedelta(days=1)
        if _open(client, d):
            return d
    return d


# ---------------------------------------------------------------- 캐시
class KISDayCache:
    """cache/kis 아래 JSON 캐시. 일자별 파일 {kind}_{YYYYMMDD}.json = {code: 항목}, 거래대금은 turnover/<code>.json."""

    def __init__(self, root: Path | str | None = None, keep_days: int = 7):
        self.root = Path(root or CACHE_DIR / "kis")
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError:      # 드라이브 동기화 잠김 등 — 쓰기는 save 에서 다시 시도하고, 실패해도 결과는 메모리에 남는다
            pass
        self.keep_days = keep_days

    def path(self, kind: str, day: date) -> Path:
        return self.root / f"{kind}_{_ymd(day)}.json"

    def turnover_path(self, code: str) -> Path:
        return self.root / "turnover" / f"{code}.json"

    def turnover_mtime(self, code: str) -> datetime | None:
        """turnover/<code>.json 을 마지막으로 쓴 시각 (KST). 없거나 못 읽으면 None."""
        try:
            return datetime.fromtimestamp(self.turnover_path(code).stat().st_mtime, KST)
        except OSError:
            return None

    @staticmethod
    def _read(p: Path) -> dict:
        try:
            js = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return js if isinstance(js, dict) else {}

    @staticmethod
    def _write(p: Path, data: dict) -> None:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        os.replace(tmp, p)

    def load(self, kind: str, day: date) -> dict:
        return self._read(self.path(kind, day))

    def save(self, kind: str, day: date, entries: dict) -> None:
        """기존 파일에 entries 를 덮어써 합친 뒤 저장하고, 오래된 같은 종류 파일을 정리한다."""
        if not entries:
            return
        data = self.load(kind, day)
        data.update(entries)
        self._write(self.path(kind, day), data)
        self.prune(kind)

    def prune(self, kind: str) -> None:
        files = sorted(self.root.glob(f"{kind}_*.json"))
        for p in files[:-self.keep_days] if self.keep_days > 0 else []:
            try:
                p.unlink()
            except OSError:
                pass

    def load_turnover(self, code: str) -> dict[str, float]:
        return {k: float(v) for k, v in self._read(self.turnover_path(code)).items()
                if isinstance(v, (int, float)) and len(k) == 8}

    def save_turnover(self, code: str, series: dict[str, float]) -> None:
        self._write(self.turnover_path(code), dict(sorted(series.items())))


# ---------------------------------------------------------------- 병렬 실행
def _run_many(codes: list[str], fn: Callable[[str], object], workers: int, step: str,
              progress: Progress | None = None, errors: dict | None = None) -> tuple[dict, BaseException | None]:
    """codes 마다 fn 을 스레드로 실행. 종목별 실패는 errors 에 적고, 치명 오류면 남은 작업을 취소하고 돌려준다."""
    out: dict = {}
    fatal: BaseException | None = None
    stop = threading.Event()

    def task(c):
        if stop.is_set():
            return None
        try:
            return fn(c)
        except Exception as e:
            if is_fatal(e):          # 다른 작업 스레드가 곧바로 멈추도록 여기서 신호
                stop.set()
            raise

    ex = ThreadPoolExecutor(max_workers=max(1, int(workers)))
    try:
        futs = {ex.submit(task, c): c for c in codes}
        for i, fut in enumerate(as_completed(futs), 1):
            c = futs[fut]
            try:
                v = fut.result()
                if v is not None:
                    out[c] = v
            except Exception as e:
                if is_fatal(e):
                    fatal = e
                    stop.set()
                    break
                if errors is not None:
                    errors[c] = _err_text(e)
            if progress:
                progress(step, i, len(codes))
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    return out, fatal


def _cached_run(kind: str, codes: Iterable[str], fetch_one: Callable[[str], object], *, cache: KISDayCache,
                day: date, to_json: Callable, from_json: Callable, reuse: Callable[[dict], bool] = lambda e: True,
                refresh: bool = False, workers: int = 8, progress: Progress | None = None,
                errors: dict | None = None, fallback: bool = False) -> dict:
    """일자별 캐시를 먼저 쓰고 나머지만 받는다. 받은 만큼은 (치명 오류로 멈춰도) 저장한 뒤 치명 오류를 다시 던진다.
    fallback: 다시 받다 실패한 종목은 reuse 를 통과 못 한(묵은) 캐시 항목이라도 대신 쓴다 — 실패는 errors 에 남아 재시도된다."""
    codes = list(dict.fromkeys(codes))
    stored = {} if refresh else cache.load(kind, day)
    out = {c: from_json(stored[c]) for c in codes if isinstance(stored.get(c), dict) and reuse(stored[c])}
    todo = [c for c in codes if c not in out]
    got, fatal = _run_many(todo, fetch_one, workers, kind, progress, errors)
    stamp = _now().isoformat(timespec="seconds")
    try:
        cache.save(kind, day, {c: {**to_json(v), "_at": stamp} for c, v in got.items()})
    except OSError:          # 드라이브 동기화 잠김 등 — 받은 자료는 메모리로 계속 쓴다(다음 실행에 다시 받음)
        pass
    out.update(got)
    if fallback:
        for c in todo:
            if c not in out and isinstance(stored.get(c), dict):
                try:
                    out[c] = from_json(stored[c])
                except Exception:
                    pass
    if fatal is not None:
        raise fatal
    return out


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


# ---------------------------------------------------------------- 1. 종목 상태
@dataclass
class Status:
    """inquire-price 의 종목 상태·밸류에이션 (억원·%·원). 빠진 숫자는 None."""
    stat: str = ""                 # iscd_stat_cls_code 원문 (55 정상 · 51 관리 · 58 정지 …)
    mang: bool = False             # 관리종목
    warn: str = "00"               # 시장경고 00 없음 · 01 투자주의 · 02 투자경고 · 03 투자위험
    halt: bool = False             # 거래정지 (temp_stop_yn 또는 stat 58)
    sltr: bool = False             # 정리매매
    short_over: bool = False       # 단기과열
    caution: bool = False          # 투자유의 (invt_caful_yn)
    marg: float | None = None      # 증거금률 %
    credit: bool = False           # 신용 가능
    cap_eok: float | None = None   # 시가총액(억원)
    per: float | None = None
    pbr: float | None = None
    eps: float | None = None
    bps: float | None = None
    frgn: float | None = None      # 외국인 소진율 % (보유 ÷ 외국인 한도 — 한도 있는 종목은 보유율보다 크다)
    hold: float | None = None      # 외국인 보유율 % (frgn_hldn_qty ÷ lstn_stcn)
    loan: float | None = None      # 융자잔고율 %
    sector: str = ""               # 업종명 (bstp_kor_isnm)
    price: float | None = None     # 현재가(원)


def parse_status(out: dict) -> Status:
    """inquire-price output → Status. 응답이 비었으면 KISError('EMPTY')."""
    if not isinstance(out, dict) or not (out.get("iscd_stat_cls_code") or out.get("stck_prpr")):
        raise KISError("종목 상태 응답이 비었습니다 — 종목코드를 확인하세요", "EMPTY")
    yes = lambda k: str(out.get(k) or "").strip().upper() == "Y"  # noqa: E731
    stat = str(out.get("iscd_stat_cls_code") or "").strip()
    held, listed = _f(out.get("frgn_hldn_qty")), _f(out.get("lstn_stcn"))
    return Status(
        stat=stat, mang=yes("mang_issu_cls_code") or stat == "51",
        warn=str(out.get("mrkt_warn_cls_code") or "00").strip() or "00",
        halt=yes("temp_stop_yn") or stat == "58", sltr=yes("sltr_yn"), short_over=yes("short_over_yn"),
        caution=yes("invt_caful_yn"), marg=_f(out.get("marg_rate")), credit=yes("crdt_able_yn"),
        cap_eok=_f(out.get("hts_avls")), per=_f(out.get("per")), pbr=_f(out.get("pbr")), eps=_f(out.get("eps")),
        bps=_f(out.get("bps")), frgn=_f(out.get("hts_frgn_ehrt")), loan=_f(out.get("whol_loan_rmnd_rate")),
        hold=round(held / listed * 100, 2) if held is not None and listed else None,
        sector=str(out.get("bstp_kor_isnm") or "").strip(), price=_f(out.get("stck_prpr")),
    )


_STATUS_KEYS = {f.name for f in fields(Status)}
_WARN_TAG = {"03": "투자위험", "02": "투자경고", "01": "투자주의"}
_STAT_WARN = {"52": "03", "53": "02", "54": "01"}   # iscd_stat_cls_code → 시장경고 코드


def _warn_level(s: Status) -> str:
    return max(s.warn if s.warn in _WARN_TAG else "00", _STAT_WARN.get(s.stat, "00"))


def status_tags(s: Status) -> list[str]:
    """짧은 한글 태그: 관리종목 · 거래정지 · 정리매매 · 투자위험/경고/주의 · 단기과열.
    증거금 100%(stat 57 · marg_rate 100)는 태그로 내지 않는다 — 증권사 자체 증거금 규칙이라 2026-10-08 전 종목의 68%(1,669/2,449)가
    해당해 경고 구실을 못 한다. 값은 Status.marg 에 남는다."""
    tags = []
    if s.mang:
        tags.append("관리종목")
    if s.halt:
        tags.append("거래정지")
    if s.sltr:
        tags.append("정리매매")
    w = _warn_level(s)
    if w in _WARN_TAG:
        tags.append(_WARN_TAG[w])
    if s.short_over or s.stat == "59":
        tags.append("단기과열")
    return tags


def status_exclude(s: Status) -> str | None:
    """스캔 제외 사유 (거래정지 · 정리매매 · 관리종목 · 투자위험) 또는 None."""
    if s.halt:
        return "거래정지"
    if s.sltr:
        return "정리매매"
    if s.mang:
        return "관리종목"
    if _warn_level(s) == "03":
        return "투자위험"
    return None


STATUS_OPEN = time(8, 0)          # 상태가 바뀌는 구간: 개장일 08:00(장 전 지정 · 해제 반영) ~ 15:45(종가 확정)


def _status_changed_between(at: datetime, now: datetime) -> bool:
    """at 과 now 사이에 상태가 바뀔 수 있는 경계(개장일 08:00 · 15:45, KRX 달력)가 있었는지. 30일 넘게 묵었으면 True."""
    if now - at > timedelta(days=30):
        return True
    d = at.date()
    while d <= now.date():
        if _cal_open(d):
            for t in (STATUS_OPEN, DATA_FINAL):
                if at < datetime.combine(d, t, KST) <= now:
                    return True
        d += timedelta(days=1)
    return False


def _status_fresh(entry: dict, now: datetime | None = None) -> bool:
    """캐시된 상태를 다시 써도 되는지. 장중(개장일 08:00~15:45)이면 오늘 STATUS_TTL 안에 받은 것만 — 장중 정지 ·
    지정을 놓치지 않게. 장 밖이면 받은 뒤 개장일 08:00 · 15:45 경계를 지나지 않았으면 그대로 쓴다(그사이 상태가
    바뀌지 않는다 — 저녁 · 휴장일 재실행이 전 종목 상태를 다시 받지 않게: 2026-10-09 실측 2,449건 11분).
    상태 파일은 market_date(장중엔 전 거래일)로 묶이므로 장중 스캔이 전날 저녁 상태를 쓰는 것도 막는다."""
    now = now or _now()
    if not _STATUS_KEYS <= set(entry):           # 예전 모양 캐시(새 필드 없음 — 예: 외국인 보유율 hold) → 다시 받는다
        return False
    try:
        at = datetime.fromisoformat(str(entry.get("_at")))
    except ValueError:
        return False
    if at.tzinfo is None:
        at = at.replace(tzinfo=KST)
    at, now = at.astimezone(KST), now.astimezone(KST)
    if at > now:
        return False
    if _cal_open(now.date()) and STATUS_OPEN <= now.time() < DATA_FINAL:
        return at.date() == now.date() and now - at < STATUS_TTL
    return not _status_changed_between(at, now)


def fetch_status(client, codes: Iterable[str], cache: KISDayCache | None = None, *, day: date | None = None,
                 refresh: bool = False, workers: int = 8, progress: Progress | None = None,
                 errors: dict | None = None) -> dict[str, Status]:
    """전 종목 상태 {code: Status}. 거래일별 캐시(status_YYYYMMDD.json) — 오늘 3시간 안에 받은 것만 재사용, 1종목 1회 요청."""
    cache = cache or KISDayCache()
    day = day or market_date(client)
    now = _now()

    def one(code: str) -> Status:
        js = client.get(PATH_PRICE, TR_PRICE, {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code})
        return parse_status(js.get("output") or {})

    # 다시 받다 실패하면 묵은 상태라도 쓴다 — 관리 · 정지 종목이 상태 없음으로 후보에 들어가는 것보다 낫다
    return _cached_run("status", codes, one, cache=cache, day=day, to_json=asdict,
                       from_json=lambda e: Status(**{k: v for k, v in e.items() if k in _STATUS_KEYS}),
                       reuse=lambda e: _status_fresh(e, now), refresh=refresh, workers=workers, progress=progress,
                       errors=errors, fallback=True)


# ---------------------------------------------------------------- 2. 실제 거래대금
def parse_turnover(rows: list[dict], until: str) -> dict[str, float]:
    """일봉 output2 → {YYYYMMDD: 거래대금(원)}. until 이후(장중 미확정)·0원(거래정지) 행은 뺀다."""
    out = {}
    for r in rows:
        d = str(r.get("stck_bsop_date") or "")
        v = _f(r.get("acml_tr_pbmn"))
        if len(d) == 8 and d.isdigit() and d <= until and v is not None and v > 0:
            out[d] = v
    return out


def fetch_turnover(client, codes: Iterable[str], cache: KISDayCache | None = None, days: int = 100, *,
                   day: date | None = None, workers: int = 8, progress: Progress | None = None,
                   errors: dict | None = None) -> dict[str, dict[str, float]]:
    """종목별 실제 일별 거래대금을 turnover/<code>.json 에 합쳐 쌓는다 (과거 날짜는 지우지 않음).

    캐시에 이미 기준일(day)이 있으면 요청하지 않는다 — 단, 기준일 18:10(VALUE_FINAL, 시간외 거래까지 더해진 값)이
    지났는데 캐시를 그 전에 썼으면 기준일 값이 장 마감 직후의 덜 쌓인 값이므로 다시 받는다.
    처음이면 최근 days 거래일(1회 최대 100봉), 이후에는 캐시 마지막 날짜부터 기준일까지만 받는다.
    반환: {code: {YYYYMMDD: 원}} (캐시 포함 전체)."""
    cache = cache or KISDayCache()
    day = day or market_date(client)
    until = _ymd(day)
    codes = list(dict.fromkeys(codes))
    have = {c: cache.load_turnover(c) for c in codes}
    final_at = datetime.combine(day, VALUE_FINAL, KST)
    settled = _now() >= final_at

    def done(code: str, s: dict) -> bool:
        if until not in s:
            return False
        if not settled:
            return True
        at = cache.turnover_mtime(code)
        return at is None or at >= final_at

    out = {c: s for c, s in have.items() if done(c, s)}

    def one(code: str) -> dict[str, float]:
        old = have.get(code) or {}
        start = day - timedelta(days=int(days * 1.5) + 7)
        if old:
            start = max(start, datetime.strptime(max(old), "%Y%m%d").date())
        js = client.get(PATH_DAILY, TR_DAILY, {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code, "FID_INPUT_DATE_1": _ymd(start),
            "FID_INPUT_DATE_2": until, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"})
        merged = {**old, **parse_turnover(_rows(js, "output2"), until)}
        if merged != old or (settled and until in merged):     # 확정 뒤 받은 것은 같은 값이어도 시각을 남긴다
            try:
                cache.save_turnover(code, merged)
            except OSError:      # 드라이브 동기화 잠김 등 — 받은 자료는 메모리로 계속 쓴다(다음 실행에 다시 받음)
                pass
        return merged

    got, fatal = _run_many([c for c in codes if c not in out], one, workers, "turnover", progress, errors)
    out.update(got)
    # 받다 실패한 종목은 이미 쌓인 실제 거래대금(기준일 값은 없거나 덜 쌓였어도)이라도 쓴다 — 실패는 errors 에 남아 재시도된다
    out.update({c: s for c, s in have.items() if c not in out and s})
    if fatal is not None:
        raise fatal
    return out


def apply_turnover(df: pd.DataFrame, series: dict[str, float] | pd.Series | None) -> pd.DataFrame:
    """OHLCV(DatetimeIndex 'date', data.ohlcv 형식)의 'value'(추정 (H+L+C)/3×거래량)를 같은 날짜의 실제 거래대금으로 덮어쓴다.

    열은 늘리지 않는다 (소비자 호환). 실제 값으로 바뀐 행 수·첫 날짜는 attrs['value_real_n'] ·
    attrs['value_real_from'] 에 적는다. 원본은 바꾸지 않고 사본을 돌려준다."""
    if df is None or df.empty or "value" not in df.columns or series is None or len(series) == 0:
        return df
    s = series.copy() if isinstance(series, pd.Series) else pd.Series(series, dtype=float)
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index.astype(str), format="%Y%m%d", errors="coerce")
    s = s[s.index.notna() & (s > 0)]
    s = s[~s.index.duplicated(keep="last")]
    common = df.index.intersection(s.index)
    out = df.copy()
    if len(common):
        out.loc[common, "value"] = s.loc[common].to_numpy(dtype=float)
        out.attrs["value_real_n"] = int(len(common))
        out.attrs["value_real_from"] = f"{common.min():%Y-%m-%d}"
    return out


# ---------------------------------------------------------------- 3. 수급 (외국인·기관·개인)
@dataclass
class Flows:
    """최근 30거래일 순매수 (날짜 오름차순). 금액은 억원, 수량은 주. f5·o20 등은 최근 n일 합(억원)."""
    dates: list[str] = field(default_factory=list)
    close: list = field(default_factory=list)
    frgn: list = field(default_factory=list)
    orgn: list = field(default_factory=list)
    prsn: list = field(default_factory=list)
    frgn_qty: list = field(default_factory=list)
    orgn_qty: list = field(default_factory=list)
    prsn_qty: list = field(default_factory=list)
    f5: float = 0.0
    o5: float = 0.0
    p5: float = 0.0
    f20: float = 0.0
    o20: float = 0.0
    p20: float = 0.0


def _tail_sum(xs: list, n: int) -> float:
    return round(sum(x for x in xs[-n:] if x is not None), 2)


def parse_flows(rows: list[dict]) -> Flows:
    """inquire-investor output(최신순) → Flows. 금액이 빈 행(당일 집계 전)은 건너뛴다. 백만원 → 억원(÷100)."""
    recs = []
    for r in rows:
        d = str(r.get("stck_bsop_date") or "")
        amt = [_f(r.get(k), 0.01) for k in ("frgn_ntby_tr_pbmn", "orgn_ntby_tr_pbmn", "prsn_ntby_tr_pbmn")]
        if len(d) != 8 or any(a is None for a in amt):
            continue
        qty = [_f(r.get(k)) for k in ("frgn_ntby_qty", "orgn_ntby_qty", "prsn_ntby_qty")]
        recs.append((d, _f(r.get("stck_clpr")), *amt, *qty))
    recs = sorted({r[0]: r for r in recs}.values())
    cols = list(zip(*recs)) if recs else [[]] * 8
    fl = Flows(*[list(c) for c in cols])
    for name, xs in (("f", fl.frgn), ("o", fl.orgn), ("p", fl.prsn)):
        setattr(fl, f"{name}5", _tail_sum(xs, 5))
        setattr(fl, f"{name}20", _tail_sum(xs, 20))
    return fl


def _flows_final(entry: dict, day: date) -> bool:
    """캐시된 수급이 기준일 18:10(기관 확정) 이후에 받은 것인지."""
    try:
        at = datetime.fromisoformat(str(entry.get("_at")))
    except ValueError:
        return False
    return at >= datetime.combine(day, FLOWS_FINAL, KST)


def fetch_flows(client, codes: Iterable[str], cache: KISDayCache | None = None, *, day: date | None = None,
                refresh: bool = False, workers: int = 8, progress: Progress | None = None,
                errors: dict | None = None) -> dict[str, Flows]:
    """후보 종목 수급 {code: Flows}. 거래일별 캐시(flows_YYYYMMDD.json) — 기준일 18:10 이후에 받은 것만 재사용."""
    cache = cache or KISDayCache()
    day = day or market_date(client)

    def one(code: str) -> Flows:
        js = client.get(PATH_INVESTOR, TR_INVESTOR, {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code})
        return parse_flows(_rows(js))

    return _cached_run("flows", codes, one, cache=cache, day=day, to_json=asdict,
                       from_json=lambda e: Flows(**_strip(e)), reuse=lambda e: _flows_final(e, day),
                       refresh=refresh, workers=workers, progress=progress, errors=errors)


def flows_frame(fl: Flows, foreign_ratio: float | None = None) -> pd.DataFrame:
    """Flows → data.investor 와 같은 모양의 DataFrame (scanner·CAN SLIM I 가 그대로 쓴다).

    DatetimeIndex 'date' 오름차순, 열 = investor.COLUMNS:
      close(종가) · volume(NaN — 이 API 에 없음) · inst_net(기관 순매매, 주) · foreign_net(외국인, 주)
      · indiv_net(개인, 주) · foreign_ratio(%, 마지막 행만 foreign_ratio 인자 — KIS 외국인 소진율, 나머지 NaN)
    """
    from .investor import COLUMNS

    nan = float("nan")
    num = lambda xs: [nan if x is None else float(x) for x in xs]  # noqa: E731
    idx = pd.DatetimeIndex(pd.to_datetime(fl.dates, format="%Y%m%d"), name="date")
    df = pd.DataFrame({
        "close": num(fl.close), "volume": [nan] * len(idx), "inst_net": num(fl.orgn_qty),
        "foreign_net": num(fl.frgn_qty), "indiv_net": num(fl.prsn_qty), "foreign_ratio": [nan] * len(idx),
    }, index=idx)
    if len(df) and foreign_ratio is not None:
        df.iloc[-1, df.columns.get_loc("foreign_ratio")] = float(foreign_ratio)
    return df[COLUMNS]


def attach_flows(ctx, fl: Flows | None, foreign_ratio: float | None = None) -> pd.DataFrame | None:
    """data.investor.attach_investor 대신 KIS 수급을 ctx.info['investor'] 에 붙인다 (자료 없으면 None)."""
    if fl is None or not fl.dates:
        return None
    df = flows_frame(fl, foreign_ratio)
    ctx.info["investor"] = df
    return df


# ---------------------------------------------------------------- 4. 투자의견·목표가
@dataclass
class Opinions:
    """rows = [(YYYYMMDD, 증권사, 의견, 직전 의견, 목표가)] 최신순. up30·down30 = 최근 30일 같은 증권사 목표가 상향·하향 수.
    avg_target_90d = 90일 안 증권사별 최신 목표가 평균(원), gap_pct = 그 평균 대비 현재가 여력 %."""
    rows: list = field(default_factory=list)
    n30: int = 0
    up30: int = 0
    down30: int = 0
    avg_target_90d: float | None = None
    gap_pct: float | None = None
    price: float | None = None


def parse_opinions(raw: list[dict], asof: date, price: float | None = None, recent: int = 30,
                   target_days: int = 90) -> Opinions:
    """invest-opinion output(최신순) → Opinions. 직전 목표가는 같은 증권사의 바로 앞 행(창 안)에서 찾는다."""
    rows = []
    for r in raw:
        d = str(r.get("stck_bsop_date") or "")
        if len(d) == 8 and d.isdigit():
            tp = _f(r.get("hts_goal_prc"))
            rows.append((d, str(r.get("mbcr_name") or "").strip(), str(r.get("invt_opnn") or "").strip(),
                         str(r.get("rgbf_invt_opnn") or "").strip(), tp if tp and tp > 0 else None))
    rows = list(reversed(rows))                    # 오래된 순 (같은 날은 응답 역순)
    rows.sort(key=lambda x: x[0])
    d30, d90 = _ymd(asof - timedelta(days=recent)), _ymd(asof - timedelta(days=target_days))
    last: dict[str, float] = {}
    latest90: dict[str, float] = {}
    op = Opinions()
    for d, broker, _, _, tp in rows:
        prev = last.get(broker)
        if d > d30:
            op.n30 += 1
            if tp is not None and prev is not None:
                op.up30 += tp > prev
                op.down30 += tp < prev
        if tp is not None:
            last[broker] = tp
            if d > d90:
                latest90[broker] = tp
    op.rows = list(reversed(rows))
    op.price = price          # 현재가가 없으면 여력도 없음 — 리포트 행의 전일 종가는 그 리포트 날짜 기준이라 묵은 값
    if latest90:
        op.avg_target_90d = round(sum(latest90.values()) / len(latest90), 1)
        if price and price > 0:
            op.gap_pct = round((op.avg_target_90d / price - 1) * 100, 2)
    return op


def fetch_opinions(client, codes: Iterable[str], cache: KISDayCache | None = None, days: int = 180, *,
                   day: date | None = None, prices: dict[str, float] | None = None, recent: int = 30,
                   target_days: int = 90, refresh: bool = False, workers: int = 8,
                   progress: Progress | None = None, errors: dict | None = None) -> dict[str, Opinions]:
    """후보 종목 투자의견 {code: Opinions}. 거래일별 캐시(opinion_YYYYMMDD.json). prices = 현재가(Status.price)."""
    cache = cache or KISDayCache()
    day = day or market_date(client)
    prices = prices or {}
    start = day - timedelta(days=days)

    def one(code: str) -> Opinions:
        js = client.get(PATH_OPINION, TR_OPINION, {
            "FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "16633", "FID_INPUT_ISCD": code,
            "FID_INPUT_DATE_1": "00" + _ymd(start), "FID_INPUT_DATE_2": "00" + _ymd(day)})
        return parse_opinions(_rows(js), day, prices.get(code), recent, target_days)

    def load(e: dict) -> Opinions:
        op = Opinions(**_strip(e))
        op.rows = [tuple(r) for r in op.rows]
        return op

    return _cached_run("opinion", codes, one, cache=cache, day=day, to_json=asdict, from_json=load,
                       refresh=refresh, workers=workers, progress=progress, errors=errors)


# ---------------------------------------------------------------- 5. 추정실적
@dataclass
class Estimate:
    """연도별 실적·추정 (years 의 'E' = 추정). 금액 억원, EPS 원, 증감률·ROE·부채비율 %, PER·EV/EBITDA 배.
    fwd_eps_g = 다음 해 추정 EPS / 올해 추정 EPS - 1 (추정이 하나뿐이면 마지막 실적 대비), %."""
    years: list = field(default_factory=list)
    rev: list = field(default_factory=list)
    rev_g: list = field(default_factory=list)
    op: list = field(default_factory=list)
    op_g: list = field(default_factory=list)
    ni: list = field(default_factory=list)
    ni_g: list = field(default_factory=list)
    ebitda: list = field(default_factory=list)
    eps: list = field(default_factory=list)
    eps_g: list = field(default_factory=list)
    per: list = field(default_factory=list)
    ev_ebitda: list = field(default_factory=list)
    roe: list = field(default_factory=list)
    debt: list = field(default_factory=list)
    icr: list = field(default_factory=list)
    fwd_eps_g: float | None = None
    fwd_years: list = field(default_factory=list)   # [기준 연도, 선행 연도] 라벨
    estdate: str = ""


# (필드, 배율) — output2 6행, output3 최대 8행 (2026-10 실전 응답으로 배율 확인)
_EST_ROWS2 = [("rev", 1.0), ("rev_g", 0.1), ("op", 1.0), ("op_g", 0.1), ("ni", 1.0), ("ni_g", 0.1)]
_EST_ROWS3 = [("ebitda", 1.0), ("eps", 0.1), ("eps_g", 0.1), ("per", 0.1), ("ev_ebitda", 0.1), ("roe", 0.1),
              ("debt", 0.1), ("icr", 0.1)]


def _fwd_growth(years: list[str], eps: list) -> tuple[float | None, list[str]]:
    est = [i for i, y in enumerate(years) if str(y).upper().endswith("E")]
    if not est:
        return None, []
    if len(est) >= 2:
        b, n = est[0], est[1]
    elif est[0] > 0:
        b, n = est[0] - 1, est[0]
    else:
        return None, []
    base, nxt = eps[b], eps[n]
    if base is None or nxt is None or base <= 0:
        return None, [years[b], years[n]]
    return round((nxt / base - 1) * 100, 2), [years[b], years[n]]


def parse_estimate(js: dict) -> Estimate | None:
    """estimate-perform 응답 → Estimate. 커버리지 없으면(연도 없음·EPS 전부 0/없음) None."""
    years = [str(r.get("dt") or "").strip() for r in _rows(js, "output4")]
    years = [y for y in years if y]
    if not years:
        return None
    n = len(years)
    est = Estimate(years=years, estdate=str((js.get("output1") or {}).get("estdate") or "").strip()
                   if isinstance(js.get("output1"), dict) else "")
    for key, specs in (("output2", _EST_ROWS2), ("output3", _EST_ROWS3)):
        rows = _rows(js, key)
        for i, (name, scale) in enumerate(specs):
            r = rows[i] if i < len(rows) else {}
            setattr(est, name, [_f(r.get(f"data{j + 1}"), scale) for j in range(n)])
    if not any(v for v in est.eps) and not any(v for v in est.rev):
        return None
    est.fwd_eps_g, est.fwd_years = _fwd_growth(est.years, est.eps)
    return est


def fetch_estimates(client, codes: Iterable[str], cache: KISDayCache | None = None, *, day: date | None = None,
                    refresh: bool = False, workers: int = 8, progress: Progress | None = None,
                    errors: dict | None = None) -> dict[str, Estimate]:
    """후보 종목 추정실적 {code: Estimate} (커버리지 없는 종목은 빠진다). 거래일별 캐시(estimate_YYYYMMDD.json).
    커버리지 없음도 캐시에 {"none": true} 로 남겨 같은 날 다시 묻지 않는다."""
    cache = cache or KISDayCache()
    day = day or market_date(client)

    def one(code: str) -> Estimate | dict:
        return parse_estimate(client.get(PATH_ESTIMATE, TR_ESTIMATE, {"SHT_CD": code})) or {"none": True}

    got = _cached_run("estimate", codes, one, cache=cache, day=day,
                      to_json=lambda v: v if isinstance(v, dict) else asdict(v),
                      from_json=lambda e: {"none": True} if e.get("none") else Estimate(**_strip(e)),
                      refresh=refresh, workers=workers, progress=progress, errors=errors)
    return {c: v for c, v in got.items() if isinstance(v, Estimate)}


# ---------------------------------------------------------------- 스냅샷
def _r(x, nd: int = 2):
    return None if x is None else round(float(x), nd)


def _snap_status(s: Status) -> dict:
    return {"stat": s.stat, "tags": status_tags(s), "ex": status_exclude(s), "cap": _r(s.cap_eok, 0),
            "per": _r(s.per), "pbr": _r(s.pbr), "frgn": _r(s.frgn), "hold": _r(getattr(s, "hold", None)),
            "loan": _r(s.loan), "marg": _r(s.marg, 0),
            "sec": s.sector, "px": _r(s.price, 0)}


def _snap_estimate(e: Estimate) -> dict:
    eps_e = None
    if e.fwd_years and e.fwd_years[-1] in e.years:
        eps_e = e.eps[e.years.index(e.fwd_years[-1])]
    return {"fwd_eps_g": e.fwd_eps_g, "eps_e": _r(eps_e, 0), "years": list(e.fwd_years)}


def write_snapshot(path: Path | str, status: dict[str, Status], flows: dict[str, Flows],
                   opinions: dict[str, Opinions], estimates: dict[str, Estimate], meta: dict | None = None) -> Path:
    """뷰어용 스냅샷 JSON 을 원자적으로 쓴다 (스키마는 모듈 설명 참고). meta: date(YYYYMMDD)·env·steps."""
    meta = meta or {}
    js = {
        "v": 1, "at": _now().isoformat(timespec="seconds"), "date": meta.get("date"), "env": meta.get("env"),
        "steps": meta.get("steps") or [],
        "status": {c: _snap_status(s) for c, s in sorted(status.items())},
        "flows": {c: {"f20": f.f20, "o20": f.o20, "f5": f.f5, "o5": f.o5} for c, f in sorted(flows.items())},
        "opinion": {c: {"n30": o.n30, "up30": o.up30, "down30": o.down30, "avg_tp": _r(o.avg_target_90d, 0),
                        "gap": o.gap_pct} for c, o in sorted(opinions.items())},
        "estimate": {c: _snap_estimate(e) for c, e in sorted(estimates.items())},
    }
    p = Path(path)
    KISDayCache._write(p, js)
    return p


# ---------------------------------------------------------------- 일괄 갱신
@dataclass
class RefreshResult:
    """refresh() 결과. fatal 이 있으면 그 단계에서 멈춘 것 (이전 단계 결과는 남아 있다)."""
    day: date | None = None
    status: dict = field(default_factory=dict)
    turnover: dict = field(default_factory=dict)
    flows: dict = field(default_factory=dict)
    opinions: dict = field(default_factory=dict)
    estimates: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)       # {단계: {code: 사유}}
    steps: list = field(default_factory=list)        # [{step, n, ok, fail, secs}]
    fatal: str | None = None
    snapshot: Path | None = None

    @property
    def ok(self) -> bool:
        return self.fatal is None

    def summary(self) -> str:
        names = {"status": "상태", "turnover": "거래대금", "flows": "수급", "opinion": "투자의견", "estimate": "추정실적"}
        lines = [f"KIS 데이터 기준일 {self.day:%Y-%m-%d}" if self.day else "KIS 데이터"]
        for st in self.steps:
            lines.append(f"  {names.get(st['step'], st['step'])}: {st['ok']}/{st['n']} "
                         f"(실패 {st['fail']}) {st['secs']:.1f}초")
        if self.fatal:
            lines.append(f"  ✘ 중단: {self.fatal}")
        return "\n".join(lines)


def _step(res: RefreshResult, name: str, codes: list[str], run: Callable[[list, dict], dict]) -> dict:
    errs = res.errors.setdefault(name, {})
    t0 = _time.perf_counter()
    got = None
    try:
        got = run(codes, errs)
    finally:
        st = {"step": name, "n": len(codes), "ok": len(codes) - len(errs) if got is not None else 0,
              "fail": len(errs), "secs": round(_time.perf_counter() - t0, 1)}
        if got is None:          # 치명 오류 등으로 멈춤 — 취소된 종목을 성공으로 세지 않는다
            st["stop"] = True
        res.steps.append(st)
    return got


def refresh(codes_all: Iterable[str], codes_focus: Iterable[str], *, client=None,
            cfg: KISMarketConfig | None = None, cache: KISDayCache | None = None, day: date | None = None,
            progress: Progress | None = None, refresh: bool = False) -> RefreshResult:
    """클라이언트 하나로 전 종목 상태·거래대금, 후보 종목 수급·투자의견·추정실적을 차례로 받는다.

    종목별 실패는 res.errors 에 남기고 건너뛴다. 인증 실패 등 치명 오류는 그 단계에서 멈추고 res.fatal 에 사유.
    cfg.snapshot_path 가 있고 치명 오류가 없으면 스냅샷 JSON 을 쓴다."""
    cfg = cfg or KISMarketConfig()
    res = RefreshResult()
    if client is None:
        client, why = client_or_none(cfg)
        if client is None:
            res.fatal = why
            return res
    cache = cache or KISDayCache(cfg.cache_dir, cfg.keep_days)
    res.day = day = day or market_date(client)
    codes_all = list(dict.fromkeys(codes_all))
    focus = list(dict.fromkeys(codes_focus))
    kw = dict(cache=cache, day=day, workers=cfg.workers, progress=progress)
    # 거래정지 종목은 기준일 거래대금이 생기지 않아 매번 다시 묻게 되므로 거래대금 단계에서 뺀다
    active = lambda: [c for c in codes_all if not getattr(res.status.get(c), "halt", False)]  # noqa: E731
    plan = [
        ("status", lambda: codes_all, lambda cs, e: fetch_status(client, cs, refresh=refresh, errors=e, **kw)),
        ("turnover", active, lambda cs, e: fetch_turnover(client, cs, days=cfg.turnover_days, errors=e, **kw)),
        ("flows", lambda: focus, lambda cs, e: fetch_flows(client, cs, refresh=refresh, errors=e, **kw)),
        ("opinion", lambda: focus, lambda cs, e: fetch_opinions(
            client, cs, days=cfg.opinion_days, prices={c: s.price for c, s in res.status.items() if s.price},
            recent=cfg.opinion_recent, target_days=cfg.target_days, refresh=refresh, errors=e, **kw)),
        ("estimate", lambda: focus, lambda cs, e: fetch_estimates(client, cs, refresh=refresh, errors=e, **kw)),
    ]
    attr = {"status": "status", "turnover": "turnover", "flows": "flows", "opinion": "opinions",
            "estimate": "estimates"}
    for name, codes_of, run in plan:
        codes = codes_of()
        if not codes:
            continue
        try:
            setattr(res, attr[name], _step(res, name, codes, run))
        except KISError as e:
            if not is_fatal(e):
                raise
            res.fatal = f"{e.message} ({name} 단계에서 중단)"
            return res
    if cfg.snapshot_path:
        res.snapshot = write_snapshot(cfg.snapshot_path, res.status, res.flows, res.opinions, res.estimates,
                                      {"date": _ymd(day), "env": getattr(getattr(client, "cfg", None), "env", None),
                                       "steps": res.steps})
    return res
