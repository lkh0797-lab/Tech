"""종목별 투자자(기관·외국인·개인) 일별 순매매 — 네이버 모바일 증권 API + 디스크 캐시.

CAN SLIM 의 I(기관 수요)를 실제 수급으로 보강하기 위한 자료다. 요청 수를 아끼기 위해
리포트 단계에서 '후보 종목'에만 호출한다 (전 종목 스캔에 쓰지 말 것).

    from chart_screener.data.investor import attach_investor, get_investor
    df = get_investor("005930", days=60)          # 캐시 우선, 필요 시 1~2회 요청
    attach_investor(ctx)                          # ctx.info["investor"] = df → patterns.canslim 의 I 점수에 반영

API: ``https://m.stock.naver.com/api/stock/{code}/trend?pageSize={n}[&bizdate=YYYYMMDD]``
  - 최신순 JSON 배열. pageSize 최대 60 (200 은 HTTP 400 확인). bizdate 를 주면 그 날짜 '이전' 자료.
  - 구 PC 페이지(finance.naver.com/item/frgn.naver)는 클라이언트 렌더링으로 바뀌어 HTML 에 표가 없다.
  - 당일 행은 장 마감 후 생긴다(장중에는 전일까지). 기관 수치는 저녁(약 18시)에 확정되므로
    18:10 이후 받은 캐시를 '확정'으로 본다.

반환 DataFrame (DatetimeIndex 오름차순, 수량 단위: 주)
    close, volume, inst_net(기관 순매매), foreign_net(외국인 순매매), indiv_net(개인 순매매),
    foreign_ratio(외국인 보유율 %)
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd

from ..config import CACHE_DIR
from . import http
from .ohlcv import KST, now_kst

URL = "https://m.stock.naver.com/api/stock/{code}/trend?pageSize={size}"
PAGE_MAX = 60
INVESTOR_FINAL = time(18, 10)       # 기관·외국인 수치 확정 시각(여유 포함)
COLUMNS = ["close", "volume", "inst_net", "foreign_net", "indiv_net", "foreign_ratio"]
_FIELDS = {   # API 키 → 컬럼
    "closePrice": "close",
    "accumulatedTradingVolume": "volume",
    "organPureBuyQuant": "inst_net",
    "foreignerPureBuyQuant": "foreign_net",
    "individualPureBuyQuant": "indiv_net",
    "foreignerHoldRatio": "foreign_ratio",
}


def _num(v) -> float:
    """'+1,273,618' / '-2,064,174' / '46.37%' / '0' → float. 실패 시 NaN."""
    if v is None:
        return float("nan")
    s = str(v).strip().replace(",", "").replace("%", "").replace("+", "")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def parse_trend(rows) -> pd.DataFrame:
    """trend API 응답(JSON 배열) → DataFrame. 형식이 맞지 않는 행은 건너뛴다."""
    recs = []
    for r in rows or []:
        if not isinstance(r, dict) or not r.get("bizdate"):
            continue
        try:
            d = pd.Timestamp(datetime.strptime(str(r["bizdate"]), "%Y%m%d"))
        except ValueError:
            continue
        recs.append({"date": d, **{col: _num(r.get(key)) for key, col in _FIELDS.items()}})
    if not recs:
        return pd.DataFrame(columns=COLUMNS, index=pd.DatetimeIndex([], name="date"))
    df = pd.DataFrame(recs).drop_duplicates("date").set_index("date").sort_index()
    return df[COLUMNS]


def fetch_investor(code: str, days: int = 60, before: str | None = None) -> pd.DataFrame:
    """네이버에서 최근 ``days`` 거래일(또는 ``before``(YYYYMMDD) 이전) 순매매를 받는다. 60일당 1회 요청."""
    frames: list[pd.DataFrame] = []
    got = 0
    cursor = before
    for _ in range(days // PAGE_MAX + 2):
        size = max(1, min(PAGE_MAX, days - got))
        url = URL.format(code=code, size=size) + (f"&bizdate={cursor}" if cursor else "")
        page = parse_trend(http.get(url).json())
        if page.empty:
            break
        frames.append(page)
        got += len(page)
        cursor = page.index[0].strftime("%Y%m%d")
        if got >= days or len(page) < size:
            break
    if not frames:
        return parse_trend([])
    df = pd.concat(frames)
    return df[~df.index.duplicated(keep="first")].sort_index().iloc[-days:]


def _last_final(at: datetime) -> datetime:
    """가장 최근 '확정' 시각 (평일 18:10, 공휴일은 무시 — 무해한 재요청만 발생)."""
    d = at
    if d.weekday() < 5 and d.time() >= INVESTOR_FINAL:
        return d.replace(hour=18, minute=10, second=0, microsecond=0)
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.replace(hour=18, minute=10, second=0, microsecond=0)


class InvestorCache:
    """종목별 pickle 캐시 (cache/investor/{code}.pkl). 새로 받은 행이 기존 행을 덮어쓰며 누적된다.

    신선도: 가장 최근 확정 시각(평일 18:10) 이후에 받은 캐시면 신선 — 그 전까지는 새 확정 행이
    생기지 않으므로 장중에도 재요청하지 않는다.
    """

    def __init__(self, root: Path | None = None):
        self.root = Path(root or CACHE_DIR / "investor")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, code: str) -> Path:
        return self.root / f"{code}.pkl"

    def is_fresh(self, code: str, at: datetime | None = None) -> bool:
        p = self._path(code)
        if not p.exists():
            return False
        at = at or now_kst()
        fetched = datetime.fromtimestamp(p.stat().st_mtime, KST)
        return fetched >= _last_final(at)

    def load(self, code: str) -> pd.DataFrame | None:
        p = self._path(code)
        if not p.exists():
            return None
        try:
            return pd.read_pickle(p)
        except Exception:
            return None

    def save(self, code: str, df: pd.DataFrame) -> None:
        df.to_pickle(self._path(code))


def get_investor(code: str, days: int = 60, cache: InvestorCache | None = None, refresh: bool = False,
                 offline: bool = False) -> pd.DataFrame | None:
    """캐시 우선 조회. 캐시가 신선하고 행이 충분하면 요청하지 않는다. offline 이면 캐시만 (없으면 None)."""
    cache = cache or InvestorCache()
    old = cache.load(code)
    if offline:
        return old.iloc[-days:] if old is not None else None
    if not refresh and old is not None and len(old) >= days and cache.is_fresh(code):
        return old.iloc[-days:]
    if old is not None and len(old) >= days and not refresh:
        # 최신 구간만 갱신(1회 요청): 마지막 저장일 이후 거래일 수 + 여유
        new = fetch_investor(code, min(PAGE_MAX, max(5, _bdays_since(old.index[-1]) + 3)))
        df = pd.concat([old, new])
        df = df[~df.index.duplicated(keep="last")].sort_index()
    else:
        df = fetch_investor(code, days)
    if not df.empty:
        cache.save(code, df)
    return df.iloc[-days:]


def _bdays_since(d: pd.Timestamp) -> int:
    return max(0, len(pd.bdate_range(d, now_kst().date())) - 1)


def attach_investor(ctx, days: int = 60, **kw) -> pd.DataFrame | None:
    """StockContext.info['investor'] 에 순매매 자료를 붙인다 (실패 시 None, 예외 전파 안 함)."""
    try:
        df = get_investor(ctx.code, days, **kw)
    except Exception:  # 네트워크 오류는 I 대용지표로 대체
        return None
    if df is not None and not df.empty:
        ctx.info["investor"] = df
    return df
