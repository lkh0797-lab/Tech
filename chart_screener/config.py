"""스크리너 전역 설정.

모든 임계값은 여기서 조정한다. 패턴별 세부 임계값은 각 패턴 모듈의
``*Config`` 데이터클래스에 있고, ``Config.patterns`` 딕셔너리로 덮어쓸 수 있다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUT_DIR = PROJECT_ROOT / "output"

EOK = 100_000_000  # 1억 원


YEAR_BARS = 250  # 한국 시장 1년 ≈ 250 거래일


def bars_for_years(years: float) -> int:
    """n년치 일봉 요청 수 (휴장일 여유 포함). 네이버는 10년(약 2,600봉)까지 한 번에 내려준다."""
    return int(round(years * YEAR_BARS)) + 10


@dataclass
class DataConfig:
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    history_days: int = 760          # 약 3년치 일봉. 더 길게: CLI --years N (예: 10) 또는 이 값을 bars_for_years(N) 로
    max_workers: int = 8             # 동시 요청 수 (네이버 서버 배려)
    request_delay: float = 0.05      # 요청 간 최소 간격(초)
    exclude_spac: bool = True        # 스팩 제외
    exclude_reits: bool = True       # 리츠 제외
    exclude_preferred: bool = True   # 우선주 제외
    min_history_days: int = 120      # 이 미만 상장 종목은 분석 제외


@dataclass
class UniverseFilter:
    """스캔 전 기본 유동성 필터 (패턴 판정과 별개)."""
    min_price: float = 1_000                 # 동전주 제외
    min_avg_value_20d: float = 10 * EOK      # 20일 평균 거래대금 10억 이상
    min_market_cap: float = 500 * EOK        # 시가총액 500억 이상


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    universe: UniverseFilter = field(default_factory=UniverseFilter)
    # 대량 거래대금 기준 (사용자 요구: 일 300억 돌파)
    big_value_threshold: float = 300 * EOK
    # RS 레이팅 기준
    rs_min: float = 70.0
    # ---- 포지션 계획 (scanner.position_plan)
    account_size: float = 100_000_000   # 계좌 규모(원), 기본 1억
    risk_per_trade: float = 0.01        # 1회 거래 최대 손실 = 계좌 × 1%
    max_position_pct: float = 0.20      # 한 종목 최대 투입 = 계좌 × 20%
    max_entry_risk: float = 0.10        # 진입 손절폭이 이보다 크면 '눌림 대기' (수량 0)
    max_liquidity_pct: float = 0.02     # 투입금액 ≤ 20일 평균 거래대금 × 2% (슬리피지·유동성 한도)
    # ---- 300억 장대양봉 레이더 (ScanResult.radar)
    radar_days: int = 10                # 최근 이 거래일 안의
    radar_min_change: float = 0.07      # +7% 이상 & 거래대금 big_value_threshold 이상 양봉
    # 패턴별 설정 덮어쓰기: {"vcp": VCPConfig(...), ...}
    patterns: dict = field(default_factory=dict)

    def pattern_cfg(self, name: str, default_factory):
        cfg = self.patterns.get(name)
        return cfg if cfg is not None else default_factory()
