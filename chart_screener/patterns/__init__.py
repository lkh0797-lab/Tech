"""패턴 모듈 자동 로드: 이 패키지의 모든 모듈을 import 해 @register 를 실행한다."""
import importlib
import pkgutil

from .base import REGISTRY, PatternResult, StockContext, run_all

for _m in pkgutil.iter_modules(__path__):
    if _m.name != "base" and not _m.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_m.name}")

__all__ = ["REGISTRY", "PatternResult", "StockContext", "run_all"]
