from __future__ import annotations

import pandas as pd

from .exceptions import DataVendorUnavailable

_PROFILE_LABELS = {
    "所属行业",
    "证券代码",
    "证券简称",
    "公司名称",
    "英文名称",
    "上市日期",
}


def _normalize_hk_symbol(symbol: str) -> str:
    raw = str(symbol or "").strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    if not raw.isdigit():
        raise DataVendorUnavailable(f"AkShare HK profile requires a numeric HK symbol, got '{symbol}'.")
    return raw.zfill(5)


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null"}:
        return ""
    return text


def _looks_like_industry_name(value: str) -> bool:
    text = _clean_text(value)
    if not 2 <= len(text) <= 30:
        return False
    if text in _PROFILE_LABELS:
        return False
    if text.isdigit() or "." in text or "://" in text:
        return False
    if any(token in text for token in ("代码", "简称", "名称", "公司", "有限", "日期")):
        return False
    return True


def get_hk_security_profile(symbol: str) -> pd.DataFrame:
    """Return AkShare Eastmoney HK security profile for a 5-digit HK symbol."""
    hk_symbol = _normalize_hk_symbol(symbol)
    try:
        # Keep AkShare lazy-loaded so non-HK workflows can import the package
        # even if optional data dependencies are not initialized yet.
        import akshare as ak
    except ImportError as exc:
        raise DataVendorUnavailable(
            "akshare package is not installed. Install it to enable HK security profiles."
        ) from exc

    try:
        data = ak.stock_hk_security_profile_em(symbol=hk_symbol)
    except Exception as exc:
        raise DataVendorUnavailable(
            f"AkShare HK security profile query failed for '{hk_symbol}': {exc}"
        ) from exc
    if data is None:
        return pd.DataFrame()
    return data


def get_hk_security_industry(symbol: str) -> str:
    """Return current AkShare '所属行业' for a 5-digit HK symbol, or ''.

    AkShare does not expose a point-in-time industry profile here, so historical
    backtests should treat this as current metadata rather than dated evidence.
    """
    try:
        profile = get_hk_security_profile(symbol)
    except DataVendorUnavailable:
        return ""
    if profile is None or profile.empty:
        return ""

    if "所属行业" in profile.columns:
        for value in profile["所属行业"]:
            industry = _clean_text(value)
            if _looks_like_industry_name(industry):
                return industry

    for _, row in profile.iterrows():
        row_values = [_clean_text(value) for value in row.tolist()]
        for idx, value in enumerate(row_values):
            if value == "所属行业":
                for candidate in row_values[idx + 1 :]:
                    if _looks_like_industry_name(candidate):
                        return candidate

    return ""
