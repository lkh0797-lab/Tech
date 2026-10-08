"""네이버 금융 요청용 공용 HTTP 세션 (재시도 + 최소 간격)."""
from __future__ import annotations

import threading
import time

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
)

_local = threading.local()
_lock = threading.Lock()
_last_request = [0.0]


def session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = _UA
        _local.session = s
    return s


def get(url: str, *, min_interval: float = 0.05, retries: int = 3, timeout: float = 15) -> requests.Response:
    """GET with global rate limit and exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        with _lock:
            wait = _last_request[0] + min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_request[0] = time.monotonic()
        try:
            r = session().get(url, timeout=timeout)
            if r.status_code == 200:
                return r
            last_exc = RuntimeError(f"HTTP {r.status_code}: {url}")
        except requests.RequestException as e:  # 네트워크 일시 오류
            last_exc = e
        time.sleep(0.5 * (2 ** attempt))
    raise RuntimeError(f"요청 실패: {url}") from last_exc
