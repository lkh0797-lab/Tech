"""차트용 긴 일봉 이력 — 리포트 '5년 · 10년 · 전체' 기간을 상장 이후(1990년~)까지 그리기 위한 자료.

스캔 일봉(네이버, 최근 약 3년)은 패턴 판정용이라 그대로 두고, 그보다 앞 구간만 증권사(한국투자증권) 일봉 조회
(FHKST03010100, 수정주가)로 종목마다 한 번 받아 cache/kis/hist/<code>.json 에 둔다. 리포트를 쓴 뒤
리포트 옆 hist/<code>.json 에 '그 앞 긴 이력 + 스캔 일봉'을 이어 붙여 쓰고, 리포트는 종목을 열 때 이 파일을
불러와 차트를 늘린다(없거나 못 읽으면 리포트에 담긴 최근 이력만 — 파일로 직접 연 리포트 등).

    res = fill(client, [(code, ctx.df), ...], out_dir=out, budget=600)
    print(res.summary_line())

- 한 번에 100봉이라 오래 상장한 종목은 수십 번 부른다 (S-Oil 1987년~ 약 96회). 받은 앞 구간은 바뀌지 않으므로
  다시 묻지 않는다. 수정주가 조정(분할 · 증자)으로 겹치는 구간 종가가 어긋나면 받아 둔 앞 구간을 그 비율로 맞춰
  다시 저장한다(가격만 — 거래량은 스캔 일봉처럼 원래 주식 수). 거래정지일 등 가격 0 행은 빼되 쪽 넘김은 원래 행 수로 판단.
- 스캔마다 시간 한도(budget 초) 안에서 주어진 순서(리포트 순위)대로 채우고, 남은 종목은 다음 스캔에서.
- 증권사 연결이 없으면(client None) 이미 받아 둔 종목만 파일을 쓴다.
- 증권사 자료라 이 PC 의 본인 분석용이다(한국투자증권 Open API 약관: 시세는 본인 업무에만, 제3자 제공 금지).
"""
from __future__ import annotations

import json
import math
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

import pandas as pd

from .config import CACHE_DIR

PAGE = 100                       # KIS 일봉 1회 최대 봉 수
START = "19800101"               # 조회 시작일 (실제 자료는 1990년부터)
MAX_PAGES = 150                  # 한 종목 최대 호출 수 (약 15,000봉 — 무한 반복 방지)
OVERLAP_DAYS = 60                # 스캔 일봉과 겹쳐 받을 달력 일수 (수정주가 어긋남 확인용)
MISMATCH = 0.005                 # 겹치는 구간 종가 비율이 이만큼(0.5%) 넘게 어긋나면 수정주가 조정으로 본다
COLS = ("open", "high", "low", "close", "volume")
KEYS = ("o", "h", "l", "c", "v")


def _num(x):
    """JSON 용 숫자: 정수면 int, 아니면 소수 2자리. NaN · inf 는 None."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return int(f) if f.is_integer() else round(f, 2)


def _frame(js: dict) -> pd.DataFrame | None:
    """저장 형식 {t:[YYYYMMDD], o,h,l,c,v} → DatetimeIndex 'date' 일봉. 모양이 틀리면 None."""
    try:
        idx = pd.to_datetime([str(t) for t in js["t"]], format="%Y%m%d")
        df = pd.DataFrame({c: [float("nan") if v is None else float(v) for v in js[k]] for c, k in zip(COLS, KEYS)},
                          index=pd.DatetimeIndex(idx, name="date"))
    except (KeyError, TypeError, ValueError):
        return None
    return df if len(df) else None


def _js(df: pd.DataFrame) -> dict:
    return {"t": [int(f"{d:%Y%m%d}") for d in df.index],
            **{k: [_num(v) for v in df[c].to_numpy()] for c, k in zip(COLS, KEYS)}}


def _write(p: Path, data: dict, tries: int = 4) -> None:
    """원자적 쓰기. 뷰어가 같은 파일을 내주는 중이면(Windows 는 읽는 동안 바꿔치기 거부) 잠깐 뒤 다시, 끝내 못 하면 임시 파일을 지운다."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    try:
        for k in range(tries):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:
                if k == tries - 1:
                    raise
                time.sleep(0.1 * (k + 1))
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


CACHE_V = 2   # v1(2026-10-09 첫 판)은 거래정지 행이 낀 쪽에서 끊긴 채 '완료'로 저장됐을 수 있어 다시 받는다


class HistCache:
    """cache/kis/hist/<code>.json = {ver, code, at, until(받은 마지막 날 YYYYMMDD), complete(상장 첫날까지 받음), t, o, h, l, c, v}."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or CACHE_DIR / "kis" / "hist")

    def path(self, code: str) -> Path:
        return self.root / f"{code}.json"

    def load(self, code: str) -> tuple[pd.DataFrame | None, dict]:
        try:
            js = json.loads(self.path(code).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, {}
        if not isinstance(js, dict) or js.get("ver") != CACHE_V:      # "v" 는 거래량 열
            return None, {}
        meta = {k: js.get(k) for k in ("at", "until", "complete")}
        return (_frame(js) if js.get("t") else None), meta

    def save(self, code: str, df: pd.DataFrame | None, until: date, complete: bool) -> None:
        body = _js(df) if df is not None and len(df) else {"t": [], **{k: [] for k in KEYS}}
        _write(self.path(code), {"ver": CACHE_V, "code": code, "at": datetime.now().isoformat(timespec="seconds"),
                                 "until": f"{until:%Y%m%d}", "complete": bool(complete), **body})


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """종가 0 · 빈 행(상장 전 · 정지일 표시 행)은 빼고, 시가 · 고가 · 저가가 0 인 옛 행은 종가로 채운다(data.ohlcv.clean 과 같게).
    날짜순 · 중복 제거."""
    if df is None or not len(df):
        return pd.DataFrame(columns=list(COLS), index=pd.DatetimeIndex([], name="date"))
    df = df[[c for c in COLS if c in df.columns]].astype(float)
    df = df[df["close"] > 0].copy()
    for c in ("open", "high", "low"):
        bad = ~(df[c] > 0)
        df.loc[bad, c] = df.loc[bad, "close"]
    df["high"] = df[["open", "high", "low", "close"]].max(axis=1)
    df["low"] = df[["open", "high", "low", "close"]].min(axis=1)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    return df


def _page(client, code: str, start: str, end: date, tries: int = 3) -> pd.DataFrame:
    """일봉 한 쪽. 초당 한도 · 서버 오류 같은 일시 오류는 잠깐 쉬고 다시 (인증 등 치명 오류는 바로 던진다)."""
    from .data.kis_market import is_fatal

    for k in range(tries):
        try:
            return client.daily(code, start, end)
        except Exception as e:
            if is_fatal(e) or k == tries - 1:
                raise
            time.sleep(1.0 + k)
    return _clean(None)


def fetch_long(client, code: str, until: date, *, since: date | None = None, max_pages: int = MAX_PAGES,
               deadline: float | None = None) -> tuple[pd.DataFrame, bool, str | None]:
    """KIS 일봉을 until 부터 거꾸로 100봉씩 받는다 — since 가 있으면 그날까지, 없으면 상장 첫날까지.
    (일봉, 끝까지 닿았나 — since 또는 상장 첫날, 중간에 멈춘 오류). KIS 는 기간 안의 가장 최근 100봉을 준다.
    쪽 넘김은 정리 전 원래 행 수 · 가장 이른 날로 판단한다(거래정지일 등 0 행을 빼고 세면 마지막 쪽으로 착각).
    deadline(time.monotonic) 을 넘기거나 일시 오류가 계속되면 받은 데까지만 (닿음 False — 다음에 이어 받음).
    치명 오류(인증 등)는 던진다."""
    from .data.kis_market import is_fatal

    frames, end, reached, err = [], until, False, None
    start = f"{since:%Y%m%d}" if since else START
    for _ in range(max_pages):
        try:
            raw = _page(client, code, start, end)
        except Exception as e:
            if is_fatal(e):
                raise
            err = getattr(e, "message", None) or f"{type(e).__name__}: {e}"
            break
        if raw is None or not len(raw):
            reached = True
            break
        df = _clean(raw)
        if len(df):
            frames.append(df)
        if len(raw) < PAGE:
            reached = True
            break
        end = pd.Timestamp(raw.index.min()).date() - timedelta(days=1)
        if since is not None and end < since:
            reached = True
            break
        if deadline is not None and time.monotonic() > deadline:
            break
    out = _clean(pd.concat(frames)) if frames else _clean(None)
    return out, reached, err


def _ymd(x) -> date | None:
    try:
        return datetime.strptime(str(x), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _ratio(new: pd.DataFrame, old: pd.DataFrame) -> float | None:
    """겹치는 날 종가 비율 중앙값 new/old. 겹치는 날이 없으면 None."""
    if new is None or old is None or not len(new) or not len(old):
        return None
    common = new.index.intersection(old.index)
    if not len(common):
        return None
    r = (new.loc[common, "close"] / old.loc[common, "close"]).replace([float("inf")], float("nan")).dropna()
    return float(r.median()) if len(r) else None


def update_long(client, code: str, long: pd.DataFrame | None, meta: dict, first: date, today: date,
                deadline: float | None = None) -> tuple[pd.DataFrame | None, date | None, bool, bool, str | None]:
    """캐시된 앞 구간(long, meta)을 스캔 일봉 첫날(first)까지 이어지게 채운다. (long, until, complete, 받았나, 오류).
    - 처음: until(= first + 60일)부터 상장 첫날까지 전부.
    - 최근 쪽이 비면(지난번 until < first): 그 사이만(앞뒤 2주 겹치게). 새로 받은 쪽과 캐시가 겹치는 날 종가가
      어긋나면(그사이 분할 · 증자) 캐시를 그 비율로 맞춘다. 끝까지 닿았을 때만 until 을 올린다 — 시간 한도 · 오류로
      끊기면 지난 until 그대로 남겨 다음에 그 빈 구간을 다시 받는다.
    - 지난번에 끊겼으면(complete=False): 가장 이른 날 앞부터 이어서."""
    until_req = min(today, first + timedelta(days=OVERLAP_DAYS))
    have_until, complete = _ymd(meta.get("until")), bool(meta.get("complete"))
    if long is None or have_until is None:
        if long is None and complete and have_until is not None and have_until >= first:
            return None, have_until, True, False, None          # 앞 구간이 없는 종목(상장이 스캔 창 안)
        df, reached, err = fetch_long(client, code, until_req, deadline=deadline)
        if not len(df):
            return None, (until_req if reached else None), reached, True, err
        return df, until_req, reached, True, err
    pieces, fetched, err = [long], False, None
    if have_until < first:
        df, reached, err = fetch_long(client, code, until_req, since=have_until - timedelta(days=14), deadline=deadline)
        fetched = True
        r = _ratio(df, long)
        if r is not None and abs(r - 1) > MISMATCH:
            pieces = [_scaled(long, r)]                          # 그사이 수정주가 조정 — 캐시를 새 기준으로
        if len(df):
            pieces.append(df)
        if reached and err is None:
            have_until = until_req
    if err is None and not complete and (deadline is None or time.monotonic() <= deadline):
        df, complete, err = fetch_long(client, code, pieces[0].index[0].date() - timedelta(days=1), deadline=deadline)
        fetched = True
        if len(df):
            pieces.insert(0, df)
    out = _clean(pd.concat(pieces))
    return (out if len(out) else None), have_until, complete, fetched, err


def _needs(long: pd.DataFrame | None, meta: dict, first: date) -> bool:
    """증권사에서 더 받아야 하나 — 처음 · 지난번에 끊김 · 스캔 일봉 첫날과 이어지지 않음."""
    until = _ymd(meta.get("until"))
    return until is None or until < first or not meta.get("complete")


def merge(long: pd.DataFrame | None, recent: pd.DataFrame) -> tuple[pd.DataFrame, float | None]:
    """(긴 앞 구간 + 스캔 일봉, 겹치는 구간 종가 비율 중앙값 recent/long). 겹치는 날이 없으면 비율 None."""
    recent = _clean(recent)
    if long is None or not len(long) or not len(recent):
        return recent, None
    common = long.index.intersection(recent.index)
    ratio = None
    if len(common):
        r = (recent.loc[common, "close"] / long.loc[common, "close"]).dropna()
        ratio = float(r.median()) if len(r) else None
    older = long[long.index < recent.index[0]]
    return pd.concat([older, recent]), ratio


def _scaled(long: pd.DataFrame, ratio: float) -> pd.DataFrame:
    """가격만 비율로 맞춘다 — 거래량은 스캔 일봉(data.ohlcv)처럼 조정 전 주식 수 그대로."""
    out = long.copy()
    for c in ("open", "high", "low", "close"):
        out[c] = out[c] * ratio
    return out


@dataclass
class FillResult:
    written: int = 0                 # hist 파일을 쓴 종목 수
    fetched: int = 0                 # 이번에 증권사에서 받은 종목 수
    calls: int = 0                   # 증권사 일봉 호출 수
    scaled: int = 0                  # 수정주가 어긋남을 비율로 맞춘 종목 수
    pending: int = 0                 # 시간 한도 · 연결 없음으로 못 채운 종목 수 (다음 스캔에서)
    skipped: int = 0                 # 앞 구간이 없는 종목 (스캔 일봉이 상장 이후 전부 — 파일은 스캔 일봉만으로 씀)
    errors: dict = field(default_factory=dict)
    stopped: str | None = None       # 치명 오류로 멈춘 사유
    secs: float = 0.0

    def summary_line(self) -> str:
        s = (f"차트 긴 이력: 파일 {self.written} · 새로 받음 {self.fetched}종목({self.calls:,}회)"
             + (f" · 남음 {self.pending}(다음 스캔)" if self.pending else "")
             + (f" · 실패 {len(self.errors)}" if self.errors else "")
             + (f" · 수정주가 비율 보정 {self.scaled}" if self.scaled else "") + f" · {self.secs:.0f}초")
        return s + (f" — 중단: {self.stopped}" if self.stopped else "")


class _Counting:
    """client.daily 호출 수를 센다 (스레드 안전)."""

    def __init__(self, client):
        self.client, self.n, self._lock = client, 0, threading.Lock()

    def daily(self, *a, **k):
        with self._lock:
            self.n += 1
        return self.client.daily(*a, **k)


def fill(client, items: Iterable[tuple[str, pd.DataFrame]], *, out_dir: Path | str, cache: HistCache | None = None,
         budget: float = 600.0, workers: int = 2, today: date | None = None,
         progress: Callable[[int, int], None] | None = None) -> FillResult:
    """items = [(code, 스캔 일봉)] (리포트 순위대로). 필요한 종목은 증권사에서 앞 구간을 받고(시간 한도 안),
    out_dir/hist/<code>.json 에 이어 붙인 전체 이력을 쓴다. 증권사 오류는 종목별로 errors 에, 인증 등 치명 오류면 멈춘다."""
    from .data.kis_market import is_fatal

    t0 = time.monotonic()
    deadline = t0 + max(0.0, float(budget))
    cache = cache or HistCache()
    out = Path(out_dir) / "hist"
    today = today or date.today()
    res = FillResult()
    items = [(c, df) for c, df in dict(items).items() if df is not None and len(df)]
    counting = _Counting(client) if client is not None else None
    stop = threading.Event()
    lock = threading.Lock()

    def one(code: str, recent: pd.DataFrame) -> None:
        long, meta = cache.load(code)
        first = recent.index[0].date()
        fetched = False
        if _needs(long, meta, first):
            if counting is None or stop.is_set() or time.monotonic() > deadline:
                with lock:
                    res.pending += 1
                if _ymd(meta.get("until")) is None or _ymd(meta["until"]) < first:
                    return          # 스캔 일봉과 이어지지 않는 앞 구간은 쓰지 않는다 (빈 구간이 생긴다)
            else:
                long, until, complete, fetched, err = update_long(counting, code, long, meta, first, today, deadline)
                if fetched:
                    _save(code, long, until, complete)
                    with lock:
                        res.fetched += 1
                if err:
                    with lock:
                        res.errors[code] = err           # 받은 데까지는 저장 — 다음 스캔에서 이어 받는다
                meta = {"until": f"{until:%Y%m%d}" if until else None, "complete": complete}
                if until is None or until < first:
                    return
        merged, ratio = merge(long, recent)
        if ratio is not None and abs(ratio - 1) > MISMATCH and long is not None:
            # 수정주가 조정(분할 · 증자) 뒤이거나 증권사 · 네이버 조정 방식 차이 — 앞 구간을 겹치는 구간 비율로 맞추고
            # 맞춘 값으로 다시 저장한다(다음 스캔은 어긋나지 않아 다시 묻지 않는다)
            long = _scaled(long, ratio)
            merged, ratio = merge(long, recent)
            _save(code, long, _ymd(meta.get("until")), bool(meta.get("complete")))
            with lock:
                res.scaled += 1
        older = len(merged) - len(_clean(recent))
        if older <= 0:
            # 앞 구간이 없다(상장이 스캔 일봉 창 안) — 그래도 파일은 쓴다: 저평가 비후보 차트는 리포트에 최근 약 250봉만
            # 담기므로 스캔 일봉(상장 이후 전부)으로 늘려 그린다
            with lock:
                res.skipped += 1
        _write(out / f"{code}.json", {"ver": 1, "code": code, "from": f"{merged.index[0]:%Y-%m-%d}", "older": int(older),
                                      "complete": bool(meta.get("complete")),      # 상장 첫날까지 받았나 (아니면 다음 스캔에서 이어 받음)
                                      "src": "한국투자증권 일봉(수정주가) + 스캔 일봉", **_js(merged)})
        with lock:
            res.written += 1

    def _save(code, long, until, complete):
        if until is None and long is None:
            return
        try:
            cache.save(code, long, until or today, complete)
        except OSError:      # 드라이브 잠김 등 — 이번 파일은 그대로 쓰고 다음 스캔에서 다시
            pass

    def task(code, recent):
        if stop.is_set():
            return
        try:
            one(code, recent)
        except Exception as e:
            if is_fatal(e):
                stop.set()
                res.stopped = getattr(e, "message", None) or f"{type(e).__name__}: {e}"
            else:
                with lock:
                    res.errors[code] = getattr(e, "message", None) or f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
        futs = [ex.submit(task, c, df) for c, df in items]
        for i, f in enumerate(as_completed(futs), 1):
            f.result()
            if progress:
                progress(i, len(futs))
    res.calls = counting.n if counting is not None else 0
    res.secs = time.monotonic() - t0
    return res
