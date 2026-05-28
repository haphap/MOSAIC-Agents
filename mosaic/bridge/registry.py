"""Method registry for the JSON-RPC sidecar.

Handlers register themselves with ``@method("namespace.name")``. The server
imports ``mosaic.bridge.handlers`` once at startup; that subpackage's
``__init__`` is responsible for importing every handler module so their
``@method`` decorators run.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

Handler = Callable[[Dict[str, Any]], Any]

_REGISTRY: Dict[str, Handler] = {}


def method(name: str) -> Callable[[Handler], Handler]:
    """Decorator: register ``func`` as JSON-RPC method ``name``.

    The handler receives ``params`` (always a dict, possibly empty) and may
    return any JSON-serialisable value, which becomes ``result`` in the
    response. Raise ``RpcError`` for protocol-level errors; any other
    exception is mapped to ``INTERNAL_ERROR`` by the server.
    """
    if not name or "." not in name:
        raise ValueError(f"RPC method name must be 'namespace.action', got {name!r}")

    def decorator(func: Handler) -> Handler:
        if name in _REGISTRY:
            raise RuntimeError(f"RPC method {name!r} is already registered")
        _REGISTRY[name] = func
        return func

    return decorator


def get_handler(name: str) -> Handler | None:
    return _REGISTRY.get(name)


def all_methods() -> list[str]:
    return sorted(_REGISTRY)


def reset_for_tests() -> None:
    """Test helper. Not used at runtime."""
    _REGISTRY.clear()
