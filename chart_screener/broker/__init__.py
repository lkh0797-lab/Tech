"""증권사 연동 (조회 전용 — 주문 기능 없음).

현재는 한국투자증권(KIS) Open API 만 지원한다: 접근토큰·현재가(REST)·실시간 체결가(웹소켓).
설정은 ~/KIS/config/kis_devlp.yaml (공식 샘플 양식), 토큰 캐시는 그 옆 chart_screener_token.json.
"""
from .kis import (
    KISAuthError, KISConfig, KISConfigError, KISError, KISRateLimitError, KISRestClient, KISWebSocketClient,
    Quote, RateLimiter, Tick, TokenManager, issue_approval_key, parse_frame, parse_simple_yaml, redact,
    tick_from_record,
)

__all__ = [
    "KISAuthError", "KISConfig", "KISConfigError", "KISError", "KISRateLimitError", "KISRestClient",
    "KISWebSocketClient", "Quote", "RateLimiter", "Tick", "TokenManager", "issue_approval_key", "parse_frame",
    "parse_simple_yaml", "redact", "tick_from_record",
]
