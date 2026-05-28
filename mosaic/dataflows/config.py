import copy
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Mapping

import mosaic.default_config as default_config

_DEFAULT_CONFIG = copy.deepcopy(default_config.DEFAULT_CONFIG)
_config_var: ContextVar[Dict[str, Any]] = ContextVar(
    "mosaic_config",
    default=copy.deepcopy(_DEFAULT_CONFIG),
)


@dataclass(frozen=True)
class BacktestContext:
    mode: str = "live"
    as_of_date: str | None = None


@dataclass
class BacktestHealthState:
    clamp_hits: int = 0
    blocked_calls: int = 0


_backtest_context_var: ContextVar[BacktestContext] = ContextVar(
    "mosaic_backtest_context",
    default=BacktestContext(),
)
_backtest_health_var: ContextVar[BacktestHealthState | None] = ContextVar(
    "mosaic_backtest_health",
    default=None,
)


def _merged_config(config: Mapping[str, Any] | None = None) -> Dict[str, Any]:
    merged = copy.deepcopy(_DEFAULT_CONFIG)
    if config:
        for key, value in config.items():
            merged[key] = copy.deepcopy(value)
    return merged


def initialize_config() -> None:
    """Initialize the current execution context with default values."""
    _config_var.set(_merged_config())


def set_config(config: Mapping[str, Any] | None) -> None:
    """Set the configuration for the current execution context."""
    _config_var.set(_merged_config(config))


def get_config() -> Dict[str, Any]:
    """Return a deep-copied configuration for the current execution context."""
    return copy.deepcopy(_config_var.get())


def get_backtest_context() -> BacktestContext:
    """Return the current backtest/runtime date context for this execution context."""
    return _backtest_context_var.get()


def set_backtest_context(as_of_date: str | None, mode: str = "backtest") -> None:
    """Set the backtest/runtime date context for the current execution context."""
    _backtest_context_var.set(
        BacktestContext(
            mode=(mode or "backtest").strip().lower(),
            as_of_date=copy.deepcopy(as_of_date),
        )
    )


def clear_backtest_context() -> None:
    """Clear the backtest/runtime date context for the current execution context."""
    _backtest_context_var.set(BacktestContext())


def get_backtest_health_state() -> BacktestHealthState:
    state = _backtest_health_var.get()
    if state is None:
        return BacktestHealthState()
    return copy.deepcopy(state)


def increment_backtest_health(*, clamp_hit: bool = False, blocked_call: bool = False) -> None:
    state = _backtest_health_var.get()
    if state is None:
        return
    if clamp_hit:
        state.clamp_hits += 1
    if blocked_call:
        state.blocked_calls += 1


@contextmanager
def backtest_health_context():
    token = _backtest_health_var.set(BacktestHealthState())
    try:
        yield _backtest_health_var.get()
    finally:
        _backtest_health_var.reset(token)


@contextmanager
def backtest_context(as_of_date: str | None, mode: str = "backtest"):
    """Temporarily set a backtest/runtime date context for nested tool routing."""
    token = _backtest_context_var.set(
        BacktestContext(
            mode=(mode or "backtest").strip().lower(),
            as_of_date=copy.deepcopy(as_of_date),
        )
    )
    try:
        yield _backtest_context_var.get()
    finally:
        _backtest_context_var.reset(token)


initialize_config()
