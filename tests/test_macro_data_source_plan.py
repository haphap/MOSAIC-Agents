from __future__ import annotations

import os
import tempfile

import pytest

from mosaic.dataflows import opencli_news
from mosaic.dataflows.tushare_catalog import (
    REQUIRED_MACRO_CATEGORIES,
    catalog_by_endpoint,
    list_endpoint_catalog,
    refresh_catalog,
    validate_catalog_coverage,
)
from mosaic.scorecard.macro_path_labels import (
    PRIMARY_LABEL_CONFIGS,
    compute_basket_path_label,
    compute_drawdown_aware_path_label,
    compute_relative_path_label,
)
from mosaic.scorecard.store import MACRO_AGENTS, ScorecardStore


def test_tushare_catalog_schema_and_required_macro_categories(tmp_path):
    rows = list_endpoint_catalog()
    assert len(rows) >= 30
    categories = {row["category"] for row in rows}
    assert REQUIRED_MACRO_CATEGORIES <= categories
    for row in rows:
        assert row["endpoint_name"]
        assert row["doc_url"].startswith("https://tushare.pro/document/2")
        assert row["catalog_status"] in {
            "scoring_candidate",
            "evidence_candidate",
            "deferred_unverified",
            "not_macro_relevant",
        }
        assert row["point_in_time_rule"]
    assert validate_catalog_coverage()["ok"] is True
    out = tmp_path / "catalog.json"
    written = refresh_catalog(out)
    assert out.exists()
    assert len(written) == len(rows)


def test_tushare_catalog_contains_plan_endpoints():
    by_endpoint = catalog_by_endpoint()
    for endpoint in (
        "daily",
        "index_daily",
        "fund_daily",
        "fund_nav",
        "fut_daily",
        "fx_daily",
        "cb_daily",
        "cn_pmi",
        "cn_gdp",
        "cn_cpi",
        "cn_ppi",
        "shibor",
        "shibor_quote",
        "hibor",
        "yc_cb",
        "moneyflow",
        "moneyflow_ind_ths",
        "fund_share",
        "top_list",
        "ths_hot",
        "dc_hot",
        "margin_secs",
        "limit_list_ths",
        "news",
        "research_report",
    ):
        assert endpoint in by_endpoint


def test_macro_series_and_documents_are_point_in_time_stores():
    with tempfile.TemporaryDirectory() as d:
        store = ScorecardStore(db_path=os.path.join(d, "t.db"))
        store.append_macro_series(
            {
                "series_id": "fx:USDCNH",
                "source": "tushare",
                "endpoint_name": "fx_daily",
                "instrument": "USDCNH.FXCM",
                "date": "2024-01-02",
                "close": 7.1,
                "as_of_date": "2024-01-02",
                "metadata": {"field": "bid_close"},
            }
        )
        store.append_macro_series(
            {
                "series_id": "fx:USDCNH",
                "source": "tushare",
                "endpoint_name": "fx_daily",
                "instrument": "USDCNH.FXCM",
                "date": "2024-01-03",
                "close": 7.0,
                "as_of_date": "2024-01-03",
            }
        )
        rows = store.list_macro_series(
            "fx:USDCNH",
            start_date="2024-01-01",
            end_date="2024-01-03",
            as_of_date="2024-01-02",
        )
        assert [row["date"] for row in rows] == ["2024-01-02"]
        assert rows[0]["metadata_json"]

        store.append_macro_documents(
            {
                "document_id": "doc-1",
                "source": "opencli",
                "channel": "google_news",
                "query": "PBOC MLF",
                "title": "PBOC injects liquidity",
                "url": "https://example.com/a",
                "published_at": "2024-01-02T09:00:00+08:00",
                "discovered_at": "2024-01-02T10:00:00+08:00",
                "content_hash": "hash-1",
                "content_excerpt": "liquidity support",
                "agent_tags": ["central_bank"],
                "event_tags": ["liquidity"],
                "sentiment_score": 0.3,
                "quality_score": 0.8,
            }
        )
        assert store.list_macro_documents(agent="central_bank", discovered_at_lte="2024-01-02T10:00:00+08:00")
        assert not store.list_macro_documents(agent="central_bank", discovered_at_lte="2024-01-02T09:30:00+08:00")


def test_opencli_macro_document_collection_and_persistence(monkeypatch):
    calls = []

    def fake_safe_run(args):
        calls.append(args)
        return (
            [
                {
                    "title": "PBOC adds liquidity",
                    "url": "https://example.com/pboc",
                    "date": "2024-01-02",
                    "snippet": "central bank operation",
                },
                {
                    "title": "Future item",
                    "url": "https://example.com/future",
                    "date": "2024-01-20",
                    "snippet": "should be filtered",
                },
            ],
            None,
        )

    monkeypatch.setattr(opencli_news, "_safe_run_opencli", fake_safe_run)
    docs = opencli_news.collect_macro_documents(
        "2024-01-05",
        look_back_days=7,
        agents=["central_bank"],
        per_query_limit=2,
    )
    assert calls
    assert docs
    assert all(doc["source"] == "opencli" for doc in docs)
    assert all(doc["agent_tags"] == ["central_bank"] for doc in docs)
    assert all(doc["discovered_at"] == "2024-01-05T23:59:59+08:00" for doc in docs)
    assert "Future item" not in {doc["title"] for doc in docs}

    with tempfile.TemporaryDirectory() as d:
        store = ScorecardStore(db_path=os.path.join(d, "t.db"))
        n = opencli_news.persist_macro_documents(
            store,
            "2024-01-05",
            look_back_days=7,
            agents=["central_bank"],
            per_query_limit=2,
        )
        assert n == len(docs)
        persisted = store.list_macro_documents(agent="central_bank", discovered_at_lte="2024-01-05T23:59:59+08:00")
        assert len(persisted) == len(docs)


def test_macro_label_source_store_and_all_primary_configs():
    with tempfile.TemporaryDirectory() as d:
        store = ScorecardStore(db_path=os.path.join(d, "t.db"))
        store.upsert_macro_label_source(
            {
                "agent": "dollar",
                "label_type": "cny_pressure_path_5d",
                "primary_series_id": "fx:USDCNH",
                "proxy_series_ids": ["fx:USDCNH"],
                "orientation_rule": "risk_on = -USDCNH_return",
                "lookback_days": 5,
                "forward_horizon_trading_days": 5,
                "fallback_label": "benchmark_fallback_5d",
                "availability_status": "available",
                "implementation_status": "implemented",
            }
        )
        rows = store.list_macro_label_sources("dollar")
        assert rows[0]["primary_series_id"] == "fx:USDCNH"
        assert "USDCNH" in rows[0]["proxy_series_ids_json"]

    assert {cfg.agent for cfg in PRIMARY_LABEL_CONFIGS.values()} == set(MACRO_AGENTS)


def test_drawdown_aware_label_requires_two_points_and_penalises_path():
    with pytest.raises(ValueError):
        compute_drawdown_aware_path_label(
            label_type="x",
            closes=[100.0],
            vote=1,
            confidence=1.0,
            neutral_band=0.005,
            vol_scale=0.01,
            source_series_id="test",
        )
    smooth = compute_drawdown_aware_path_label(
        label_type="smooth",
        closes=[100.0, 101.0, 102.0],
        vote=1,
        confidence=1.0,
        neutral_band=0.005,
        vol_scale=0.01,
        source_series_id="smooth",
    )
    choppy = compute_drawdown_aware_path_label(
        label_type="choppy",
        closes=[100.0, 80.0, 102.0],
        vote=1,
        confidence=1.0,
        neutral_band=0.005,
        vol_scale=0.01,
        source_series_id="choppy",
    )
    assert smooth.max_drawdown_5d == pytest.approx(0.0)
    assert choppy.max_drawdown_5d < -0.1
    assert choppy.path_metric_5d < smooth.path_metric_5d


def test_relative_and_basket_path_helpers():
    relative = compute_relative_path_label([100.0, 104.0], [100.0, 101.0])
    assert relative == pytest.approx([1.0, 1.03])
    basket = compute_basket_path_label([[100.0, 110.0], [200.0, 190.0]])
    assert basket == pytest.approx([1.0, 1.025])


# ---------------------------------------------------------------------------
# P6: rollout gate (macro_full_label_sources_enabled) + integration
# ---------------------------------------------------------------------------

import datetime as _dt  # noqa: E402
from unittest.mock import patch  # noqa: E402

from mosaic.bridge.handlers.autoresearch import _select_agent  # noqa: E402
from mosaic.bridge.handlers.prompts import _LAYER_BY_AGENT  # noqa: E402
from mosaic.default_config import DEFAULT_CONFIG  # noqa: E402
from mosaic.scorecard.macro_labels import primary_label_for_agent  # noqa: E402
from mosaic.scorecard.scorer import MacroScorer  # noqa: E402


def _ntd(d: str, n: int) -> str:
    return (_dt.date.fromisoformat(d) + _dt.timedelta(days=n)).isoformat()


def _ptd(d: str, n: int) -> str:
    return (_dt.date.fromisoformat(d) - _dt.timedelta(days=n)).isoformat()


def _cal():
    return patch.multiple(
        "mosaic.dataflows.calendar", next_trading_day=_ntd, previous_trading_day=_ptd
    )


def _macro_state(outputs: dict, date: str = "2024-01-02") -> dict:
    return {
        "active_cohort": "cohort_default",
        "as_of_date": date,
        "layer1_outputs": outputs,
        "layer1_consensus": {"stance": "BULLISH", "confidence": 0.6},
    }


def test_full_label_sources_gate_controls_primary_labels():
    # Gate OFF: no agent's primary is a new proxy/path label; the two PR #73
    # agents still keep a (benchmark-derived) primary.
    for agent in MACRO_AGENTS:
        off = primary_label_for_agent(agent, full_label_sources_enabled=False)
        assert off is None or off.label_type not in PRIMARY_LABEL_CONFIGS
        assert primary_label_for_agent(agent, full_label_sources_enabled=True) is not None
    assert (
        primary_label_for_agent("volatility", full_label_sources_enabled=False).label_type
        == "max_drawdown_5d"
    )


def test_scorer_default_gate_off_keeps_proxy_agent_off_path_label(tmp_path):
    # dollar's primary is a proxy path label → gated off by default → must NOT be
    # recorded as cny_pressure_path_5d.
    store = ScorecardStore(db_path=os.path.join(tmp_path, "t.db"))
    d0 = "2024-01-02"
    store.append_macro_signals_from_state(
        _macro_state({"dollar": {"agent": "dollar", "dxy_trend": "WEAKENING", "confidence": 0.5}}, d0)
    )
    t5 = _ntd(d0, 5)
    with _cal(), \
         patch("mosaic.scorecard.scorer._fetch_close", lambda ts, date: {d0: 100.0, t5: 102.0}.get(date)), \
         patch("mosaic.scorecard.scorer._fetch_benchmark_series", lambda *a: [100, 101, 102]), \
         patch("mosaic.scorecard.scorer._fetch_instrument_series", lambda *a: [100, 101, 102]):
        MacroScorer(store, benchmark="000300.SH").score_pending("cohort_default", "2024-02-01")  # default flag
    with store._connect() as conn:
        row = conn.execute("SELECT label_type FROM macro_signals").fetchone()
    assert row["label_type"] != "cny_pressure_path_5d"  # rolled back to PR #73 behavior


def test_p6_integration_ingest_score_skill_select(tmp_path):
    store = ScorecardStore(db_path=os.path.join(tmp_path, "t.db"))
    d0 = "2024-01-02"
    outputs = {
        "central_bank": {"agent": "central_bank", "stance": "TIGHTENING", "confidence": 0.7},
        "china": {"agent": "china", "policy_direction": "PRO_GROWTH", "confidence": 0.6},
        "geopolitical": {"agent": "geopolitical", "escalation_level": 5, "confidence": 0.6},
        "dollar": {"agent": "dollar", "dxy_trend": "WEAKENING", "confidence": 0.5},
        "yield_curve": {"agent": "yield_curve", "recession_signal": "GREEN", "confidence": 0.5},
        "commodities": {"agent": "commodities", "china_demand_signal": "ACCELERATING", "confidence": 0.5},
        "volatility": {"agent": "volatility", "regime_filter": "RISK_ON", "confidence": 0.7},
        "emerging_markets": {"agent": "emerging_markets", "em_relative": "OUTPERFORMING", "confidence": 0.6},
        "news_sentiment": {"agent": "news_sentiment", "retail_sentiment_score": 0.5, "confidence": 0.6},
        "institutional_flow": {"agent": "institutional_flow", "sectors_in_out": [{"net_amount_cny": 1500}], "confidence": 0.6},
    }
    assert store.append_macro_signals_from_state(_macro_state(outputs, d0)) == 10
    t5 = _ntd(d0, 5)
    with _cal(), \
         patch("mosaic.scorecard.scorer._fetch_close", lambda ts, date: {d0: 100.0, t5: 102.0}.get(date)), \
         patch("mosaic.scorecard.scorer._fetch_benchmark_series", lambda *a: [100, 101, 102]), \
         patch("mosaic.scorecard.scorer._fetch_instrument_series", lambda *a: [100, 101, 102]):
        out = MacroScorer(store, benchmark="000300.SH", full_label_sources_enabled=True).score_pending(
            "cohort_default", "2024-02-01"
        )
    assert out["macro_scored"] == 10
    skill = {r["agent"]: r for r in store.list_macro_skill("cohort_default")}
    assert len(skill) == 10
    now = _dt.datetime(2024, 3, 1, tzinfo=_dt.timezone.utc)
    chosen = _select_agent(store, "cohort_default", None, DEFAULT_CONFIG, now)
    assert _LAYER_BY_AGENT[chosen] == "macro"  # selection picks a scored macro agent
