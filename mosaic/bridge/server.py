"""Newline-delimited JSON-RPC 2.0 server over stdio.

Loop:
    line = stdin.readline()
    request = json.loads(line)
    response = dispatch(request)
    stdout.write(json.dumps(response) + "\n"); stdout.flush()

The server runs single-threaded — JSON-RPC dispatch is serial, which keeps
underlying state (config ContextVars, SQLite connections) simple. If we ever
need concurrent tool calls, a thread pool can be added without changing the
wire protocol.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from typing import Any, IO

from .protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    RpcError,
    make_error_payload,
)
from .registry import get_handler

logger = logging.getLogger("mosaic.bridge")


def _configure_logging() -> None:
    """All logs go to stderr — stdout is reserved for the protocol."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stderr for h in root.handlers):
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def _load_handlers() -> None:
    """Import the handlers package so each module registers its methods."""
    from . import handlers  # noqa: F401  (import side-effect: register methods)


def _build_response(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _build_error(req_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": make_error_payload(code, message, data),
    }


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    """Process one parsed JSON-RPC request, return a response envelope."""
    req_id = request.get("id")

    if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
        return _build_error(req_id, INVALID_REQUEST, "Request must be JSON-RPC 2.0")

    method_name = request.get("method")
    if not isinstance(method_name, str):
        return _build_error(req_id, INVALID_REQUEST, "Missing 'method' string")

    params = request.get("params", {})
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _build_error(req_id, INVALID_PARAMS, "'params' must be an object")

    handler = get_handler(method_name)
    if handler is None:
        return _build_error(req_id, METHOD_NOT_FOUND, f"Unknown method {method_name!r}")

    try:
        result = handler(params)
    except RpcError as exc:
        return _build_error(req_id, exc.code, exc.message, exc.data)
    except Exception as exc:
        logger.exception("Unhandled error in %s", method_name)
        return _build_error(
            req_id,
            INTERNAL_ERROR,
            f"{type(exc).__name__}: {exc}",
            {"traceback": traceback.format_exc()},
        )

    return _build_response(req_id, result)


def _serve_streams(stdin: IO[str], stdout: IO[str]) -> None:
    """Drive dispatch off two text streams. Public for tests."""
    for raw in stdin:
        line = raw.rstrip("\r\n")
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response = _build_error(None, PARSE_ERROR, f"Invalid JSON: {exc}")
        else:
            response = dispatch(request)
        stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        stdout.flush()


def run_stdio_server() -> None:
    """Main entry. Blocks until stdin closes."""
    _configure_logging()
    _load_handlers()
    logger.info("MOSAIC bridge ready (methods: %d)", len(_handler_count()))
    _serve_streams(sys.stdin, sys.stdout)


def _handler_count() -> list[str]:
    from .registry import all_methods

    return all_methods()
