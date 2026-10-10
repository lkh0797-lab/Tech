"""종목 뉴스 제목 — 한국투자증권 '종합 시황/공시(제목)' 조회(FHKST01011800, 조회 전용)로 종목마다 받아
cache/kis/news/<code>.json 에 쌓는다. 기업추적 뷰어의 '내러티브' 탭이 이 파일을 직접 읽어 분류 · 표시한다.

    res = run(client, ["010170", "005930"], pages=60, budget=120)
    print(res.summary_line())

- 한 쪽 40행, 쪽 안에서 cntt_usiq_srno(19자리, 앞 14자리 = 등록 시각) 내림차순. 다음(더 오래된) 쪽 커서는 마지막 행
  srno 로 ('00'+srno[:8], srno[8:14], srno) — data_tm 으로 주면 수정된 기사 때문에 뒤로 밀린다. 커서 행부터 오므로 쪽끼리
  보통 1행 겹친다. 중복은 srno 로 지운다(겹침 수를 가정하지 않는다).
- 갱신(update): 머리(커서 없이 최신부터, 받아 둔 가장 새 행에 닿을 때까지) → 빈 구간(지난번 머리가 한도로 끊긴 곳)
  → 꼬리(complete 가 아니면 가장 오래된 행 앞부터). 꼬리는 행 40 미만 · 새 행 0 · 쪽 마지막 날짜 < floor ·
  쪽 전체가 공시 제공사(F · G · I)이고 그 쪽이 오늘 − DISC_DAYS(330)일보다 앞이면 끝(complete) — 기사 보관 1년 안쪽의
  공시만 쪽(긴 거래정지 · 기사 없는 소형주)은 넘어가 그 뒤 기사를 받는다. 쪽 수 · 시간 한도에 걸리면 capped — 받은 데까지
  저장하고 다음 실행에서 이어 받는다. 시간 한도는 재시도 사이에도 본다(한도 뒤로는 진행 중인 호출 하나만 넘긴다).
- 언론 기사는 KIS 가 약 1년만 보관한다(그 앞은 거래소 · 코스닥 공시 제목뿐). 행을 지우지 않으므로 이 캐시가 보관소다.
  분류는 하지 않는다(원자료 그대로 — 기업추적이 읽을 때 매긴다).
- 이 TR 은 실효 초당 1회 안팎(2026-10-10 실측: 0.28초 간격이면 두 번에 한 번 EGW00201). 클라이언트 제한기(client.limiter)는
  그대로 두고 따로 RateLimiter(NEWS_PER_SEC) 로 매 호출 앞에서 기다린다. 작업자 1명(병렬 이득 없음).
- 기사 제목은 언론사 저작물이고 증권사 계정으로 받은 자료라 이 PC 의 본인 분석용이다(유료 상품에 넣지 않는다 · 본문은 받지 않는다).

캐시 JSON (원자적 쓰기 — chart_history._write)
  {"v": 1, "code": "010170", "at": "2026-10-11T09:00:00+09:00", "newest": srno, "oldest": srno,
   "complete": 꼬리 끝까지 받음, "capped": 이번 실행이 한도로 끊김, "floor": "YYYYMMDD"(꼬리 하한), "pages": 받은 쪽 수 누계,
   "gaps": [[위 srno, 아래 srno], ...]   ← 머리가 끊겨 빈 구간이 남았을 때만 (최신 구간 먼저)
   "rows": [{"id": srno, "d": data_dt, "t": data_tm, "src": dorg(출처 이름), "pc": 제공사 1글자, "lc": 제공사별 분류,
             "title": 제목, "c1": 대표 종목 코드, "n1": 대표 종목 이름}, ...]}   ← id 내림차순 · 유일
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable

from ..broker.kis import KST, RateLimiter
from ..chart_history import _write
from ..config import CACHE_DIR
from .kis_market import _rows, is_fatal

PATH_NEWS = "/uapi/domestic-stock/v1/quotations/news-title"
TR_NEWS = "FHKST01011800"        # 종합 시황/공시(제목)
PAGE = 40                        # 한 쪽 행 수
NEWS_PER_SEC = 1.0               # 이 TR 의 호출 간격 (초당)
FIRST_PAGES = 60                 # 한 실행 한 종목 최대 쪽 수 (중소형주는 1년치 뉴스가 약 44쪽, 005930 은 60쪽이 2~3주치)
NEWS_DAYS = 400                  # 꼬리를 받을 달력 일수 (floor = 오늘 − 이만큼)
DISC_DAYS = 330                  # 공시만 쪽에서 꼬리를 끝내는 건 이보다 오래된 쪽만 (기사 보관 약 1년 안쪽은 계속)
CACHE_V = 1
DISC_PC = frozenset("FGI")       # 공시 제공사: F 거래소 공시 · G 코스닥 공시 · I 파생 시장조치


def _now() -> datetime:
    return datetime.now(KST)


def _sid(x) -> bool:
    return isinstance(x, str) and len(x) == 19 and x.isdigit()


def _row(r: dict) -> dict | None:
    """응답 한 행 → 저장 꼴. 늘 비어 있는 iscd2..10 · kor_isnm2..10 은 버린다. srno 가 19자리 숫자가 아니면 None."""
    sid = str(r.get("cntt_usiq_srno") or "").strip()
    if not _sid(sid):
        return None

    def s(k):
        return str(r.get(k) or "").strip()

    return {"id": sid, "d": s("data_dt") or sid[:8], "t": s("data_tm") or sid[8:14], "src": s("dorg"),
            "pc": s("news_ofer_entp_code"), "lc": s("news_lrdv_code"), "title": s("hts_pbnt_titl_cntt"),
            "c1": s("iscd1"), "n1": s("kor_isnm1")}


def _cursor(sid: str) -> tuple[str, str, str]:
    """그 행 자신부터 더 오래된 40행을 받는 커서 (DATE_1, HOUR_1, SRNO)."""
    return "00" + sid[:8], sid[8:14], sid


def _page(client, code: str, cursor: tuple[str, str, str] | None, limiter: RateLimiter | None = None,
          tries: int = 3, deadline: float | None = None) -> tuple[list[dict], int]:
    """뉴스 제목 한 쪽 → (저장 꼴 행, 원래 행 수). 초당 한도 · 서버 오류 같은 일시 오류는 1+k 초 쉬고 다시(3번까지),
    인증 등 치명 오류는 바로 던진다. 쉬고 나면 deadline(time.monotonic)을 넘는 재시도는 하지 않고 그 오류를 던진다."""
    d, h, s = cursor or ("", "", "")
    params = {"FID_NEWS_OFER_ENTP_CODE": "", "FID_COND_MRKT_CLS_CODE": "", "FID_INPUT_ISCD": code,
              "FID_TITL_CNTT": "", "FID_INPUT_DATE_1": d, "FID_INPUT_HOUR_1": h,
              "FID_RANK_SORT_CLS_CODE": "", "FID_INPUT_SRNO": s}
    raw: list[dict] = []
    for k in range(tries):
        try:
            if limiter is not None:
                limiter.wait()
            raw = _rows(client.get(PATH_NEWS, TR_NEWS, params))
            break
        except Exception as e:
            if is_fatal(e) or k == tries - 1 or (deadline is not None and time.monotonic() + 1.0 + k > deadline):
                raise
            time.sleep(1.0 + k)
    rows = [x for x in map(_row, raw) if x]
    if raw and not rows:
        raise ValueError("뉴스 제목 응답 모양이 다름 (cntt_usiq_srno 없음)")
    return rows, len(raw)


class NewsCache:
    """cache/kis/news/<code>.json (형식은 맨 위 설명). 행을 지우지 않는 보관소라 깨진 파일은 덮어쓰지 않고
    옆(<code>.json.bad, 이미 있으면 .bad1 · .bad2 …)으로 치운 뒤 새로 시작한다. 치운 이름은 moved[code] 에."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or CACHE_DIR / "kis" / "news")
        self.moved: dict[str, str] = {}

    def path(self, code: str) -> Path:
        return self.root / f"{code}.json"

    def load(self, code: str) -> dict:
        """저장된 문서 또는 {}. 판(v)이 다르면 머리 정보는 버리고 행만 살린다(머리 · 꼬리를 다시 받는다).
        읽기 오류(잠김 등)는 던진다 — 못 읽은 보관소를 덮어쓰지 않게. 깨진 파일을 못 치워도(뷰어가 읽는 중 등) 던진다."""
        p = self.path(code)
        try:
            js = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except ValueError:
            js = None
        if not isinstance(js, dict):
            bad, k = p.with_name(p.name + ".bad"), 1
            while bad.exists():                  # 앞서 치운 것을 덮지 않는다 (KIS 가 지운 옛 행이 그것뿐일 수 있음)
                bad, k = p.with_name(f"{p.name}.bad{k}"), k + 1
            os.replace(p, bad)
            self.moved[code] = bad.name
            return {}
        rows = [r for r in js.get("rows") or [] if isinstance(r, dict) and _sid(r.get("id"))]
        return {**js, "rows": rows} if js.get("v") == CACHE_V else {"rows": rows}

    def save(self, code: str, doc: dict) -> None:
        _write(self.path(code), doc)


@dataclass
class CodeNews:
    code: str
    rows: int = 0                    # 캐시 행 수
    added: int = 0                   # 이번에 새로 들어온 행
    pages: int = 0                   # 이번에 받은 쪽 수
    oldest: str | None = None        # 가장 오래된 행 날짜 (YYYYMMDD, 공시 포함)
    news_from: str | None = None     # 가장 오래된 기사(공시 제공사 아님) 날짜
    complete: bool = False
    capped: bool = False
    gaps: int = 0                    # 남은 빈 구간 수
    odd: int = 0                     # 이어 받은 쪽 중 겹침이 1행이 아닌 쪽 수 (커서 감시용)
    moved: str | None = None         # 깨진 캐시를 치운 이름 (<code>.json.bad…) — 이번에 새로 시작함
    err: str | None = None

    def line(self) -> str:
        def dot(d):
            return f"{d[:4]}.{d[4:6]}.{d[6:8]}"

        span = (f"{dot(self.oldest)}~" + (f", 기사 {dot(self.news_from)}~" if self.news_from else "")) if self.oldest \
            else "자료 없음"
        return (f"  {self.code}: {self.rows:,}행 ({span}) · 새 {self.added:,} · {self.pages}쪽 · "
                + ("끝까지 받음" if self.complete else "꼬리 남음") + (" · 한도에 걸림" if self.capped else "")
                + (f" · 빈 구간 {self.gaps}" if self.gaps else "") + (f" · 겹침 1행 아닌 쪽 {self.odd}" if self.odd else "")
                + (f" · 깨진 캐시 → {self.moved} (새로 시작)" if self.moved else "")
                + (f" · 오류: {self.err}" if self.err else ""))


class _Capped(Exception):
    """쪽 수 · 시간 한도 — 받은 데까지 저장하고 다음 실행에서 이어 받는다."""


def update(client, code: str, cache: NewsCache, *, pages: int = FIRST_PAGES, floor: str | None = None,
           deadline: float | None = None, limiter: RateLimiter | None = None, disc_edge: str | None = None) -> CodeNews:
    """한 종목 갱신: 머리 → 빈 구간 → 꼬리 (맨 위 설명). floor = 꼬리 하한 YYYYMMDD, deadline = time.monotonic 한도,
    disc_edge = 공시만 쪽에서 꼬리를 끝내는 날짜 YYYYMMDD(그 쪽 마지막 날짜가 이보다 앞일 때만, None 이면 늘).
    받은 데까지는 늘 저장한다(한 쪽도 못 받았으면 파일을 건드리지 않는다). 일시 오류가 계속되면 err 에 적고 이 종목을 멈춘다
    (다음 실행에서 이어 받음). 치명 오류(인증 등)는 저장한 뒤 던진다. 캐시를 못 읽으면(잠김 등) 아무것도 받지 않고 던진다."""
    doc = cache.load(code)
    have = {r["id"]: r for r in doc.get("rows", [])}
    newest = doc.get("newest") if _sid(doc.get("newest")) else None
    oldest = doc.get("oldest") if _sid(doc.get("oldest")) else None
    if not have:
        newest = oldest = None
    elif newest is None or oldest is None:
        newest, oldest = max(have), min(have)    # 머리 정보 없는 행(판이 다름) — 이어진 구간으로 보고 머리 · 꼬리를 잇는다
    gaps = [[a, b] for a, b in (g for g in doc.get("gaps") or [] if isinstance(g, list) and len(g) == 2)
            if _sid(a) and _sid(b) and a > b] if newest else []
    kept_floor = doc.get("floor") if isinstance(doc.get("floor"), str) else None
    complete = bool(doc.get("complete")) and newest is not None
    if complete and floor and kept_floor and floor < kept_floor:
        complete = False                         # 더 앞까지 받기로 함 (--days 를 늘림)
    was_complete = complete
    out = CodeNews(code, moved=cache.moved.pop(code, None))
    fatal: BaseException | None = None

    def get(cursor):
        if out.pages >= pages or (deadline is not None and time.monotonic() > deadline):
            raise _Capped
        rows, n = _page(client, code, cursor, limiter, deadline=deadline)
        out.pages += 1
        new = sum(1 for r in rows if r["id"] not in have)
        for r in rows:
            have[r["id"]] = r                    # 있으면 덮어씀 (수정된 제목)
        out.added += new
        return rows, n, new, min((r["id"] for r in rows), default=None)

    def moved(lo, cur):
        if lo >= cur:
            raise ValueError(f"뉴스 쪽 넘김이 멈춤 (커서 {cur})")

    head_lo, reached = None, False
    try:
        # 1. 머리 — 받아 둔 가장 새 행(newest)에 닿거나 마지막 쪽까지. 처음이면 한 쪽만(그 앞은 꼬리가)
        cur = None
        while True:
            rows, n, new, lo = get(_cursor(cur) if cur else None)
            if lo is None:
                reached, complete = True, complete or newest is None
                break
            head_lo = lo if head_lo is None else min(head_lo, lo)
            if newest is None:
                oldest, reached = lo, True
                complete = n < PAGE               # 한 쪽에 다 들어옴
                break
            if lo <= newest or n < PAGE:
                reached = True
                break
            if cur:
                moved(lo, cur)
            cur = lo
        # 2. 빈 구간 — 지난번 머리가 끊긴 곳 [위, 아래] 를 위에서부터
        while gaps:
            g = gaps[0]
            rows, n, new, lo = get(_cursor(g[0]))
            if lo is None or lo <= g[1] or n < PAGE:
                gaps.pop(0)
                continue
            moved(lo, g[0])
            out.odd += (len(rows) - new) != 1
            g[0] = lo
        # 3. 꼬리 — 가장 오래된 행 앞부터
        while not complete and oldest:
            rows, n, new, lo = get(_cursor(oldest))
            if (lo is None or n < PAGE or new == 0 or (floor and lo[:8] < floor)
                    or ((disc_edge is None or lo[:8] < disc_edge) and all(r["pc"] in DISC_PC for r in rows))):
                oldest = min(oldest, lo) if lo else oldest
                complete = True
                break
            moved(lo, oldest)
            out.odd += (len(rows) - new) != 1
            oldest = lo
    except _Capped:
        out.capped = True
    except Exception as e:
        if is_fatal(e):
            fatal = e
        else:
            out.err = getattr(e, "message", None) or f"{type(e).__name__}: {e}"
    if newest is not None and head_lo is not None and not reached:
        gaps.insert(0, [head_lo, newest])        # 머리가 지난번 가장 새 행에 못 닿음 — 그 사이는 다음 실행에서

    rows = sorted(have.values(), key=lambda r: r["id"], reverse=True)
    out.rows, out.complete, out.gaps = len(rows), complete, len(gaps)
    out.oldest = rows[-1]["d"] if rows else None
    out.news_from = next((r["d"] for r in reversed(rows) if r["pc"] not in DISC_PC), None)
    if out.pages:
        body = {"v": CACHE_V, "code": code, "at": _now().isoformat(timespec="seconds"),
                "newest": rows[0]["id"] if rows else None, "oldest": oldest if rows else None,
                "complete": complete, "capped": out.capped,
                "floor": kept_floor if (was_complete and complete and kept_floor) else (floor or kept_floor),
                "pages": int(doc.get("pages") or 0) + out.pages}
        if gaps:
            body["gaps"] = gaps
        body["rows"] = rows
        cache.save(code, body)
    if fatal is not None:
        raise fatal
    return out


@dataclass
class NewsResult:
    codes: int = 0                   # 받으려 한 종목 수
    added: int = 0                   # 새로 들어온 행
    calls: int = 0                   # 증권사 호출 수 (재시도 포함, 클라이언트 안쪽 EGW00201 재시도는 빼고)
    pages: int = 0                   # 받은 쪽 수
    left: int = 0                    # 이어 받기 남은 종목 (꼬리 · 빈 구간 · 한도)
    pending: int = 0                 # 시간 한도로 시작도 못 한 종목
    moved: int = 0                   # 깨진 캐시를 치우고 새로 시작한 종목
    items: list = field(default_factory=list)    # 종목별 CodeNews
    errors: dict = field(default_factory=dict)
    stopped: str | None = None       # 치명 오류로 멈춘 사유
    secs: float = 0.0

    def summary_line(self) -> str:
        s = (f"뉴스 제목: {self.codes}종목 · 새 {self.added:,}건 · 호출 {self.calls:,} · {self.secs:.1f}초"
             + (f" · 이어 받기 남음 {self.left}" if self.left else "")
             + (f" · 못 받음 {self.pending}(시간 한도)" if self.pending else "")
             + (f" · 깨진 캐시 치움 {self.moved}" if self.moved else "")
             + (f" · 실패 {len(self.errors)}" if self.errors else ""))
        return s + (f" — 중단: {self.stopped}" if self.stopped else "")


class _Counting:
    """client.get 호출 수를 센다."""

    def __init__(self, client):
        self.client, self.n = client, 0

    def get(self, *a, **k):
        self.n += 1
        return self.client.get(*a, **k)


def run(client, codes: Iterable[str], *, cache: NewsCache | None = None, pages: int = FIRST_PAGES,
        days: int = NEWS_DAYS, budget: float = 120.0, per_sec: float = NEWS_PER_SEC, today: date | None = None,
        limiter: RateLimiter | None = None, progress: Callable[[int, int], None] | None = None) -> NewsResult:
    """codes 를 차례로 갱신한다(종목마다 pages 쪽까지, 시간 한도 budget 초는 전체에). 종목별 일시 오류는 errors 에,
    인증 등 치명 오류면 멈춘다."""
    t0 = time.monotonic()
    deadline = t0 + max(0.0, float(budget))
    cache = cache or NewsCache()
    today = today or _now().date()
    floor = f"{today - timedelta(days=int(days)):%Y%m%d}"
    edge = f"{today - timedelta(days=DISC_DAYS):%Y%m%d}"
    limiter = limiter or RateLimiter(per_sec)
    counting = _Counting(client)
    codes = list(dict.fromkeys(codes))
    res = NewsResult(codes=len(codes))
    for i, code in enumerate(codes, 1):
        if time.monotonic() >= deadline:
            res.pending += 1
        else:
            try:
                u = update(counting, code, cache, pages=pages, floor=floor, deadline=deadline, limiter=limiter,
                           disc_edge=edge)
            except Exception as e:
                msg = getattr(e, "message", None) or f"{type(e).__name__}: {e}"
                if is_fatal(e):
                    res.stopped = msg
                    break
                res.errors[code] = msg
            else:
                res.items.append(u)
                res.added += u.added
                res.moved += bool(u.moved)
                res.pages += u.pages
                if u.err:
                    res.errors[code] = u.err
                if u.capped or u.gaps or not u.complete:
                    res.left += 1
        if progress:
            progress(i, len(codes))
    res.calls = counting.n
    res.secs = time.monotonic() - t0
    return res
