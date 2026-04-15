from __future__ import annotations

import importlib
from typing import Any, Type

from services.strategy_runtime.bootstrap import ensure_repo_paths

ensure_repo_paths()

from trading_core.strategies import Strategy, StrategyContext


def _load_strategy_from_path(path: str) -> Type[Strategy]:
    module_name, _, class_name = path.rpartition(".")
    if not module_name or not class_name:
        raise ValueError("Strategy class path must be '<module>.<ClassName>'")

    module = importlib.import_module(module_name)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ValueError(f"Strategy class '{class_name}' was not found in module '{module_name}'")
    if not isinstance(cls, type) or not issubclass(cls, Strategy):
        raise ValueError(f"{path} is not a Strategy subclass")
    return cls


def _load_strategy_from_name(strategy_name: str) -> Type[Strategy]:
    module_name = f"services.strategy_runtime.strategies.{strategy_name}.strategy"
    module = importlib.import_module(module_name)
    cls = getattr(module, "StrategyImpl", None)
    if cls is None:
        raise ValueError(
            f"Strategy '{strategy_name}' does not expose StrategyImpl in {module_name}"
        )
    if not isinstance(cls, type) or not issubclass(cls, Strategy):
        raise ValueError(f"{module_name}.StrategyImpl is not a Strategy subclass")
    return cls


def load_strategy_params(strategy_name: str) -> dict[str, Any]:
    module_name = f"services.strategy_runtime.strategies.{strategy_name}.config"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return {}

    getter = getattr(module, "get_default_params", None)
    if getter is None:
        return {}
    params = getter()
    if not isinstance(params, dict):
        raise ValueError(f"{module_name}.get_default_params() must return a dict")
    return params


def load_strategy(ctx: StrategyContext, strategy_name: str, strategy_class_path: str = "") -> Strategy:
    if strategy_class_path:
        strategy_cls = _load_strategy_from_path(strategy_class_path)
        return strategy_cls(ctx)

    strategy_cls = _load_strategy_from_name(strategy_name)
    return strategy_cls(ctx)
