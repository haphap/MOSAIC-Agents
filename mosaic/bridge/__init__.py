"""MOSAIC JSON-RPC sidecar.

A Python process exposed over stdio so the TypeScript front-end (mosaic-ts) can
drive the Python codebase as a black box. The bridge does not modify any code
outside of ``mosaic/bridge/`` — it only re-exports the existing Python surface
as JSON-RPC methods.

Run as ``python -m mosaic.bridge``. Protocol details: see ``docs/bridge.md``
(to be written in Phase 9; the protocol mirrors ETFAgents' bridge).
"""

from __future__ import annotations

__all__ = ["serve"]


def serve() -> None:
    """Entry point used by ``__main__`` and integration tests."""
    # Imported lazily so simple ``import mosaic.bridge`` stays cheap
    # (LangChain/Pandas only loaded when the server actually starts).
    from .server import run_stdio_server

    run_stdio_server()
