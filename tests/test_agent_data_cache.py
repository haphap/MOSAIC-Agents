from __future__ import annotations

import sqlite3

import pytest

from mosaic.cache_manager import CacheManager
from mosaic.dataflows import interface
from mosaic.dataflows.agent_data_cache import AgentDataCache
from mosaic.dataflows.config import backtest_context, get_config, set_config
from mosaic.dataflows.exceptions import DataVendorUnavailable


@pytest.fixture(autouse=True)
def isolated_config(tmp_path):
    set_config(
        {
            "data_cache_dir": str(tmp_path / "cache"),
            "tool_vendors": {
                "get_fred_series": "fred",
                "get_stock_data": "bad,good",
            },
            "agent_data_cache": {"enabled": True},
        }
    )
    try:
        yield
    finally:
        set_config({})


def _cache() -> AgentDataCache:
    cache = AgentDataCache.from_config(get_config())
    assert cache is not None
    return cache


def test_route_to_vendor_reads_from_permanent_cache_before_vendor(monkeypatch):
    calls = []

    def fake_fred(series_id, start_date, end_date):
        calls.append((series_id, start_date, end_date))
        return f"payload-{len(calls)}"

    monkeypatch.setitem(interface.VENDOR_METHODS, "get_fred_series", {"fred": fake_fred})

    first = interface.route_to_vendor("get_fred_series", "FEDFUNDS", "2024-01-01", "2024-01-31")
    second = interface.route_to_vendor("get_fred_series", "FEDFUNDS", "2024-01-01", "2024-01-31")

    assert first == "payload-1"
    assert second == "payload-1"
    assert calls == [("FEDFUNDS", "2024-01-01", "2024-01-31")]
    stats = _cache().stats()
    assert stats["entries"] == 1
    assert stats["by_method"] == {"get_fred_series": 1}


def test_route_to_vendor_writes_successful_fallback_result(monkeypatch):
    calls = []

    def bad_vendor(*args):
        calls.append(("bad", args))
        raise DataVendorUnavailable("bad unavailable")

    def good_vendor(*args):
        calls.append(("good", args))
        return "good payload"

    monkeypatch.setitem(interface.VENDOR_METHODS, "get_stock_data", {"bad": bad_vendor, "good": good_vendor})

    first = interface.route_to_vendor("get_stock_data", "AAPL.US", "2024-01-01", "2024-01-31")
    second = interface.route_to_vendor("get_stock_data", "AAPL.US", "2024-01-01", "2024-01-31")

    assert first == "good payload"
    assert second == "good payload"
    assert calls == [
        ("bad", ("AAPL.US", "2024-01-01", "2024-01-31")),
        ("good", ("AAPL.US", "2024-01-01", "2024-01-31")),
    ]
    with sqlite3.connect(_cache().db_path) as conn:
        row = conn.execute(
            "SELECT vendor, vendor_chain_json FROM agent_data_cache WHERE method='get_stock_data'"
        ).fetchone()
    assert row[0] == "good"
    assert row[1] == '["bad", "good"]'


def test_vendor_chain_is_part_of_cache_key(monkeypatch):
    calls = []

    def first_vendor(*args):
        calls.append(("first", args))
        return "first payload"

    def second_vendor(*args):
        calls.append(("second", args))
        return "second payload"

    monkeypatch.setitem(
        interface.VENDOR_METHODS,
        "get_stock_data",
        {"first": first_vendor, "second": second_vendor},
    )
    set_config(
        {
            "data_cache_dir": get_config()["data_cache_dir"],
            "tool_vendors": {"get_stock_data": "first"},
            "agent_data_cache": {"enabled": True},
        }
    )
    assert interface.route_to_vendor("get_stock_data", "AAPL.US", "2024-01-01", "2024-01-31") == "first payload"

    set_config(
        {
            "data_cache_dir": get_config()["data_cache_dir"],
            "tool_vendors": {"get_stock_data": "second"},
            "agent_data_cache": {"enabled": True},
        }
    )
    assert interface.route_to_vendor("get_stock_data", "AAPL.US", "2024-01-01", "2024-01-31") == "second payload"

    set_config(
        {
            "data_cache_dir": get_config()["data_cache_dir"],
            "tool_vendors": {"get_stock_data": "first"},
            "agent_data_cache": {"enabled": True},
        }
    )
    assert interface.route_to_vendor("get_stock_data", "AAPL.US", "2024-01-01", "2024-01-31") == "first payload"
    assert calls == [
        ("first", ("AAPL.US", "2024-01-01", "2024-01-31")),
        ("second", ("AAPL.US", "2024-01-01", "2024-01-31")),
    ]
    assert _cache().stats()["entries"] == 2


def test_backtest_clamped_arguments_define_cache_key(monkeypatch):
    calls = []

    def fake_fred(series_id, start_date, end_date):
        calls.append((series_id, start_date, end_date))
        return f"{series_id}:{start_date}:{end_date}"

    monkeypatch.setitem(interface.VENDOR_METHODS, "get_fred_series", {"fred": fake_fred})

    with backtest_context("2024-06-15"):
        first = interface.route_to_vendor("get_fred_series", "DGS10", "2024-06-01", "2024-06-30")
    with backtest_context("2024-06-15"):
        second = interface.route_to_vendor("get_fred_series", "DGS10", "2024-06-01", "2024-06-15")

    assert first == "DGS10:2024-06-01:2024-06-15"
    assert second == first
    assert calls == [("DGS10", "2024-06-01", "2024-06-15")]


def test_stale_cache_entry_is_refetched(monkeypatch):
    set_config(
        {
            "data_cache_dir": get_config()["data_cache_dir"],
            "tool_vendors": {"get_fred_series": "fred"},
            "agent_data_cache": {"enabled": True, "read_ttl_seconds": 1},
        }
    )
    calls = []

    def fake_fred(*args):
        calls.append(args)
        return f"payload-{len(calls)}"

    monkeypatch.setitem(interface.VENDOR_METHODS, "get_fred_series", {"fred": fake_fred})

    assert interface.route_to_vendor("get_fred_series", "DFF", "2024-01-01", "2024-01-31") == "payload-1"
    with sqlite3.connect(_cache().db_path) as conn:
        conn.execute(
            "UPDATE agent_data_cache SET updated_at = '2000-01-01T00:00:00+00:00'"
        )

    assert interface.route_to_vendor("get_fred_series", "DFF", "2024-01-01", "2024-01-31") == "payload-2"
    assert calls == [
        ("DFF", "2024-01-01", "2024-01-31"),
        ("DFF", "2024-01-01", "2024-01-31"),
    ]


def test_max_entries_prunes_least_recently_used_entries(monkeypatch):
    set_config(
        {
            "data_cache_dir": get_config()["data_cache_dir"],
            "tool_vendors": {"get_fred_series": "fred"},
            "agent_data_cache": {"enabled": True, "max_entries": 2},
        }
    )
    calls = []

    def fake_fred(series_id, *args):
        calls.append(series_id)
        return f"{series_id}-payload-{len(calls)}"

    monkeypatch.setitem(interface.VENDOR_METHODS, "get_fred_series", {"fred": fake_fred})

    assert interface.route_to_vendor("get_fred_series", "A", "2024-01-01", "2024-01-31") == "A-payload-1"
    assert interface.route_to_vendor("get_fred_series", "B", "2024-01-01", "2024-01-31") == "B-payload-2"
    assert interface.route_to_vendor("get_fred_series", "A", "2024-01-01", "2024-01-31") == "A-payload-1"
    assert interface.route_to_vendor("get_fred_series", "C", "2024-01-01", "2024-01-31") == "C-payload-3"
    assert _cache().stats()["entries"] == 2

    assert interface.route_to_vendor("get_fred_series", "A", "2024-01-01", "2024-01-31") == "A-payload-1"
    assert interface.route_to_vendor("get_fred_series", "B", "2024-01-01", "2024-01-31") == "B-payload-4"
    assert calls == ["A", "B", "C", "B"]
    assert _cache().stats()["entries"] == 2


def test_agent_data_cache_can_be_disabled(monkeypatch):
    set_config(
        {
            "data_cache_dir": get_config()["data_cache_dir"],
            "tool_vendors": {"get_fred_series": "fred"},
            "agent_data_cache": {"enabled": False},
        }
    )
    calls = []

    def fake_fred(*args):
        calls.append(args)
        return f"payload-{len(calls)}"

    monkeypatch.setitem(interface.VENDOR_METHODS, "get_fred_series", {"fred": fake_fred})

    assert interface.route_to_vendor("get_fred_series", "DGS2", "2024-01-01", "2024-01-31") == "payload-1"
    assert interface.route_to_vendor("get_fred_series", "DGS2", "2024-01-01", "2024-01-31") == "payload-2"


def test_cache_manager_exposes_agent_data_category(monkeypatch):
    monkeypatch.setitem(interface.VENDOR_METHODS, "get_fred_series", {"fred": lambda *args: "payload"})
    interface.route_to_vendor("get_fred_series", "DFF", "2024-01-01", "2024-01-31")

    manager = CacheManager(get_config())
    stats = manager.stats()
    assert stats["agent_data"]["entries"] == 1
    assert stats["agent_data"]["by_method"] == {"get_fred_series": 1}
    details = manager.details("agent_data")
    assert details["total"] == 1
    assert details["entries"][0]["path"].startswith("agent_data:get_fred_series:")
    cleared = manager.clear("agent_data")
    assert cleared["deleted_files"] == 1
    assert manager.stats()["agent_data"]["entries"] == 0
