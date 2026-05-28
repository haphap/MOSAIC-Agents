"""MOSAIC: A-share self-improving multi-agent trading framework."""

from __future__ import annotations

import os
import warnings

os.environ.setdefault("PYTHONUTF8", "1")

# Suppress noisy LangChain pending deprecation warning when langchain is installed.
try:
    from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

    warnings.filterwarnings(
        "ignore",
        message=r"The default value of `allowed_objects` will change in a future version\..*",
        category=LangChainPendingDeprecationWarning,
    )
except ImportError:
    pass

# Best-effort .env loading (no-op if python-dotenv missing).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
