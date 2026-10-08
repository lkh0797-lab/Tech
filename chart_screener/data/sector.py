"""종목 → 업종·테마 매핑 (네이버 모바일 증권 API) + 디스크 캐시.

    from chart_screener.data.sector import load_sector_map
    sm = load_sector_map()              # 캐시 우선, 30일 지나면 다시 받음
    sm = load_sector_map(offline=True)  # 캐시만 (없으면 빈 표)

반환 DataFrame 컬럼
    code    종목코드
    sector  업종명 (네이버 업종 분류, 종목당 하나. 없으면 None)
    themes  테마명 목록 (list[str], 없으면 [])
  attrs["fetched_at"]  받은 시각 (KST, tz-aware Timestamp)
  attrs["group_no"]    {"업종": {이름: 번호}, "테마": {이름: 번호}} — 네이버 그룹 페이지 링크용

출처 (2026-10 확인)
  - PC 페이지 finance.naver.com/sise/sise_group(_detail).naver 는 stock.naver.com(Next.js, 클라이언트
    렌더링)으로 리다이렉트되어 HTML 에 종목 표가 없다 → 모바일 JSON API 를 쓴다.
  - 그룹 목록: m.stock.naver.com/api/stocks/{industry|theme}?page=N&pageSize=100
      → {"groups": [{"no", "name", "totalCount", ...}], "totalCount"}
  - 그룹 구성: m.stock.naver.com/api/stocks/{industry|theme}/{no}?page=N&pageSize=100
      → {"stocks": [{"itemCode", "stockName", "stockEndType", ...}], "groupInfo", "totalCount"}
  - pageSize 최대 100 (200 은 HTTP 400). 업종 약 80개 + 테마 약 260개 → 요청 약 370회,
    30일에 한 번만 받는다.
"""
from __future__ import annotations

import math
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pandas as pd

from ..config import CACHE_DIR
from . import http
from .ohlcv import KST, now_kst

SECTOR_CACHE = CACHE_DIR / "sector.pkl"
MAX_AGE_DAYS = 30                       # 캐시 유효 기간
PAGE_SIZE = 100                         # API 최대 pageSize
WORKERS = 4                             # 동시 요청 수 (http.get 이 전역 간격을 지킴)
MIN_OK_RATIO = 0.9                      # 그룹 구성 요청 성공률이 이 미만이면 기존 캐시 유지
COLUMNS = ["code", "sector", "themes"]
KINDS = {"업종": "industry", "테마": "theme"}   # 표시명 → API 경로

_LIST_URL = "https://m.stock.naver.com/api/stocks/{kind}?page={page}&pageSize={size}"
_DETAIL_URL = "https://m.stock.naver.com/api/stocks/{kind}/{no}?page={page}&pageSize={size}"


def empty_frame() -> pd.DataFrame:
    return pd.DataFrame({"code": pd.Series(dtype=object), "sector": pd.Series(dtype=object),
                         "themes": pd.Series(dtype=object)})


# ---------------------------------------------------------------- 파서 (네트워크 없음)
def _pages(total, size: int | None = None) -> int:
    try:
        return max(1, math.ceil(int(total) / (size or PAGE_SIZE)))
    except (TypeError, ValueError):
        return 1


def parse_group_list(js) -> tuple[list[dict], int]:
    """그룹 목록 응답 → ([{no, name, count}], 전체 그룹 수). 형식이 맞지 않는 항목은 건너뛴다."""
    if not isinstance(js, dict):
        return [], 0
    out = []
    for g in js.get("groups") or []:
        if not isinstance(g, dict) or g.get("no") is None or not g.get("name"):
            continue
        try:
            no = int(g["no"])
        except (TypeError, ValueError):
            continue
        try:
            count = int(g.get("totalCount") or 0)
        except (TypeError, ValueError):
            count = 0
        out.append({"no": no, "name": str(g["name"]).strip(), "count": count})
    try:
        total = int(js.get("totalCount") or len(out))
    except (TypeError, ValueError):
        total = len(out)
    return out, total


def parse_group_members(js) -> tuple[list[tuple[str, str]], int]:
    """그룹 구성 응답 → ([(코드, 종목명)], 전체 종목 수). ETF 등 주식이 아닌 항목은 제외."""
    if not isinstance(js, dict):
        return [], 0
    out = []
    for s in js.get("stocks") or []:
        if not isinstance(s, dict):
            continue
        code = str(s.get("itemCode") or "").strip()
        end_type = s.get("stockEndType")
        if len(code) != 6 or (end_type is not None and end_type != "stock"):
            continue
        out.append((code, str(s.get("stockName") or "").strip()))
    try:
        total = int(js.get("totalCount") or len(out))
    except (TypeError, ValueError):
        total = len(out)
    return out, total


def build_map(industries: dict[str, list[str]], themes: dict[str, list[str]]) -> pd.DataFrame:
    """{업종명: [코드]}, {테마명: [코드]} → code/sector/themes 표 (코드순).

    한 종목이 여러 업종에 나오면(드묾) 구성 종목 수가 적은(더 구체적인) 업종을 택한다."""
    sector: dict[str, str] = {}
    size: dict[str, int] = {}
    for name, codes in industries.items():
        n = len(set(codes))
        for c in codes:
            if c not in sector or n < size[c]:
                sector[c], size[c] = name, n
    th: dict[str, list[str]] = {}
    for name, codes in themes.items():
        for c in dict.fromkeys(codes):
            th.setdefault(c, []).append(name)
    codes = sorted(set(sector) | set(th))
    if not codes:
        return empty_frame()
    return pd.DataFrame({
        "code": codes,
        "sector": [sector.get(c) for c in codes],
        "themes": [sorted(th.get(c, [])) for c in codes],
    })


# ---------------------------------------------------------------- 수집
def _progress(msg: str, done: bool = False) -> None:
    print(f"\r  {msg}", end="\n" if done else "", file=sys.stderr, flush=True)


def fetch_groups(kind: str) -> list[dict]:
    """kind: 'industry' | 'theme' → 그룹 목록 전체 (페이지 순회)."""
    groups, page, pages = [], 1, 1
    while page <= pages:
        part, total = parse_group_list(http.get(_LIST_URL.format(kind=kind, page=page, size=PAGE_SIZE)).json())
        groups.extend(part)
        pages = _pages(total)
        if not part:
            break
        page += 1
    seen, out = set(), []
    for g in groups:
        if g["no"] not in seen:
            seen.add(g["no"])
            out.append(g)
    return out


def fetch_members(kind: str, no: int) -> list[tuple[str, str]]:
    members, page, pages = [], 1, 1
    while page <= pages:
        part, total = parse_group_members(
            http.get(_DETAIL_URL.format(kind=kind, no=no, page=page, size=PAGE_SIZE)).json())
        members.extend(part)
        pages = _pages(total)
        if not part:
            break
        page += 1
    return members


def fetch_sector_map(verbose: bool = True, workers: int = WORKERS) -> pd.DataFrame:
    """업종·테마 전체를 네이버에서 받아 code/sector/themes 표로 만든다.

    목록 요청이 실패하면 예외. 개별 그룹 실패는 건너뛰고 attrs["failed"] 에 남긴다."""
    lists = {label: fetch_groups(kind) for label, kind in KINDS.items()}
    jobs = [(label, g) for label, gs in lists.items() for g in gs]
    result: dict[str, dict[str, list[str]]] = {label: {} for label in KINDS}
    failed: list[str] = []

    def one(job):
        label, g = job
        return label, g, fetch_members(KINDS[label], g["no"])

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futs = [ex.submit(one, j) for j in jobs]
        for k, (job, fut) in enumerate(zip(jobs, futs), 1):
            try:
                label, g, members = fut.result()
                result[label][g["name"]] = [c for c, _ in members]
            except Exception as e:  # 한 그룹 실패로 전체를 버리지 않는다
                failed.append(f"{job[0]}:{job[1]['name']} ({type(e).__name__})")
            if verbose and (k % 20 == 0 or k == len(jobs)):
                _progress(f"업종·테마 구성 수집 {k}/{len(jobs)}", done=k == len(jobs))
    df = build_map(result["업종"], result["테마"])
    df.attrs["fetched_at"] = pd.Timestamp(now_kst())
    df.attrs["group_no"] = {label: {g["name"]: g["no"] for g in gs} for label, gs in lists.items()}
    df.attrs["failed"] = failed
    df.attrs["requested"] = len(jobs)
    return df


# ---------------------------------------------------------------- 캐시
def _save(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = df[COLUMNS].reset_index(drop=True).copy()
    frame.attrs = {}
    payload = {"fetched_at": df.attrs.get("fetched_at"), "group_no": df.attrs.get("group_no", {}),
               "frame": frame}
    tmp = path.with_suffix(".tmp")
    pd.to_pickle(payload, tmp)
    tmp.replace(path)


def _load(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    try:
        payload = pd.read_pickle(path)
        df = payload["frame"].copy()
        df.attrs["fetched_at"] = payload.get("fetched_at")
        df.attrs["group_no"] = payload.get("group_no") or {}
        return df
    except Exception as e:  # 손상된 캐시 → 없는 것으로 취급
        print(f"  업종·테마 캐시를 읽지 못했습니다 ({type(e).__name__}: {e})", file=sys.stderr)
        return None


def _age(df: pd.DataFrame, now=None) -> timedelta | None:
    ts = df.attrs.get("fetched_at")
    if ts is None:
        return None
    ts = pd.Timestamp(ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(KST)
    now = pd.Timestamp(now or now_kst())
    return now - ts


def load_sector_map(refresh: bool = False, offline: bool = False, *, path: Path | None = None,
                    max_age_days: int = MAX_AGE_DAYS, verbose: bool = True) -> pd.DataFrame:
    """캐시 우선으로 업종·테마 매핑을 돌려준다.

    - offline: 캐시만 사용 (나이 무관). 캐시가 없으면 빈 표.
    - 캐시가 없거나 ``max_age_days`` 보다 오래됐거나 refresh 면 새로 받는다.
    - 새로 받기가 실패(또는 그룹 요청 성공률 < 90%)하면 기존 캐시를, 그것도 없으면 빈 표를 돌려준다.
    """
    path = path or SECTOR_CACHE
    cached = _load(path)
    if offline:
        return cached if cached is not None else empty_frame()
    if cached is not None and not refresh:
        age = _age(cached)
        if age is not None and age <= timedelta(days=max_age_days):
            return cached
    try:
        df = fetch_sector_map(verbose=verbose)
    except Exception as e:
        print(f"  업종·테마 수집 실패 ({type(e).__name__}: {e}) → "
              f"{'이전 캐시 사용' if cached is not None else '업종·테마 없이 진행'}", file=sys.stderr)
        return cached if cached is not None else empty_frame()
    failed, requested = df.attrs.get("failed", []), df.attrs.get("requested", 0)
    if failed and verbose:
        print(f"  업종·테마 그룹 {len(failed)}개 수집 실패: {', '.join(failed[:5])}", file=sys.stderr)
    if requested and (requested - len(failed)) / requested < MIN_OK_RATIO and cached is not None:
        print("  수집 성공률이 낮아 이전 캐시를 유지합니다.", file=sys.stderr)
        return cached
    if df.empty:
        return cached if cached is not None else df
    _save(df, path)
    loaded = _load(path)
    return loaded if loaded is not None else df
