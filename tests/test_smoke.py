"""
Offline smoke tests for the Atlas QA layer — the checks that make a brief trustworthy.

Each test plants a defect this codebase has actually shipped (or nearly shipped) and
asserts the auditors catch it: a number that doesn't tie, a NaN multiple, a stale
EV/Rev in prose, a segment revenue misread as a contradiction. No network: live
quotes are injected through data_agent's per-process cache.

Run: python3 -m pytest tests/ -q
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))

import data_agent
from metric_audit import audit_metrics
from source_audit import _is_shallow, _domain_ok
import deliverable_agent as da


def _profile(metrics=None, bullets=None, swot=None, comps=None):
    return {
        "name": "TestCo", "ticker": "TST", "stage": "Public",
        "shortDescription": "TestCo sells testing software to enterprises.",
        "explainer": {"plain": ["Sells testing software"], "technical": ["Multi-tenant SaaS"],
                      "simple": ["A robot proofreader for code"]},
        "brief": {
            "runDate": "2026-01-15",
            "businessOverview": ["TestCo builds testing tools."],
            "earningsTakeaways": {"quarter": "Q1 2026 (ended March 31, 2026)",
                                  "reportDate": "2026-05-01",
                                  "keyMetrics": metrics or {}},
            "slideBullets": bullets or [],
            "swot": swot or {},
            "comps": comps or [],
        },
    }


# ── metric_audit: contradictions, collisions, segments ─────────────────────────

def test_contradiction_blocks():
    """Grid $200M vs slide-bullet $210M, same period — must be flagged (prose → warn)."""
    p = _profile(metrics={"revenue": "$200M (+20% YoY)"},
                 bullets=["Q1 2026 revenue of $210M shows momentum"])
    issues, _ = audit_metrics(p)
    assert any("doesn't tie" in m for _, m in issues), issues
    # structured-vs-structured stays a BLOCKING error
    p2 = _profile(metrics={"revenue": "$200M", "totalRevenue": "$230M"})
    issues2, _ = audit_metrics(p2)
    assert any(lvl == "error" and "doesn't tie" in m for lvl, m in issues2), issues2


def test_matching_figures_pass():
    p = _profile(metrics={"revenue": "$200M (+20% YoY)"},
                 bullets=["Q1 2026 revenue of $200M shows momentum"])
    issues, _ = audit_metrics(p)
    assert not any(lvl == "error" for lvl, _ in issues), issues


def test_segment_revenue_is_not_a_contradiction():
    """US-commercial $595M vs total $1.63B is a segment, not a conflict (PLTR run)."""
    p = _profile(metrics={"revenue": "$1.63B (+85% YoY)",
                          "usCommercialRevenue": "$595M (+133% YoY)",
                          "usRevenue": "$1.28B (+104% YoY)"})
    issues, _ = audit_metrics(p)
    assert not any(lvl == "error" for lvl, _ in issues), issues


def test_product_segment_revenue_is_not_a_contradiction():
    """'iPhone revenue' vs total revenue (AAPL run) — any qualifier keys its own concept,
    not just the ones an allowlist happened to anticipate."""
    p = _profile(metrics={"revenue": "$94.9B (+8% YoY)",
                          "iPhoneRevenue": "$44.6B (+5% YoY)",
                          "servicesRevenue": "$27.4B (+12% YoY)"})
    issues, _ = audit_metrics(p)
    assert not any(lvl == "error" for lvl, _ in issues), issues
    # ...while a pure period qualifier still maps to total revenue and still ties
    p2 = _profile(metrics={"revenue": "$200M", "quarterlyRevenue": "$230M"})
    issues2, _ = audit_metrics(p2)
    assert any(lvl == "error" and "doesn't tie" in m for lvl, m in issues2), issues2


def test_quarter_equals_annual_collision_warns():
    p = _profile(metrics={"revenue": "$200M"},
                 bullets=["Full-year FY2025 revenue was $200M"])
    issues, _ = audit_metrics(p)
    assert any("QUARTER" in m and "YEAR" in m for _, m in issues), issues


# ── data_agent: NaN guards ─────────────────────────────────────────────────────

def test_formatters_never_print_nan():
    assert data_agent._b(float("nan")) is None
    assert data_agent._pct(float("nan")) is None
    assert data_agent._x(float("nan")) is None
    assert data_agent._b(1.5e9) == "$1.5B"


# ── source_audit: trust + shallow-link heuristics ──────────────────────────────

def test_source_trust_and_shallow_rules():
    ok, tier = _domain_ok("ramp.com", set())
    assert ok and tier == 2                      # registry keyed by domain, not domain/path
    assert not _is_shallow("https://ramp.com/data")          # spec-blessed citation
    assert _is_shallow("https://bloomberg.com/")             # bare homepage
    assert not _is_shallow("https://wsj.com/articles/some-deep-link-123")
    assert not _domain_ok("randomblog.example", set())[0]


# ── deliverable_agent: live reconciliation + drift QA ──────────────────────────

_FAKE_QUOTE = {
    "ticker": "TST", "name": "TestCo", "priceAsOf": "2026-01-14", "closePrice": 50.0,
    "marketCap": "$10.0B", "enterpriseValue": "$11.0B", "totalRevenueLTM": "$2.5B",
    "totalRevenueNum": 2.5e9, "evRevenueLTM": "4.4x", "evRevenueNum": 4.4,
    "evRevRange52w": "3.0x–6.0x", "revenueGrowthYoY": "20.0%", "grossMargin": "75.0%",
    "fcfMarginLTM": "25.0%", "ruleOf40": 45, "analystRating": "buy",
    "analystTarget": "$60.00", "analystUpside": "20.0%", "numberOfAnalysts": 30,
    "forwardPE": 40.0, "shortPctFloat": "3.0%", "netCash": "$1.0B",
    "evBasis": "recomputed", "source": "yfinance / Yahoo Finance",
    "sourceUrl": "https://finance.yahoo.com/quote/TST",
}


def test_render_reconciles_stored_multiple_to_live(monkeypatch):
    """A stale EV/Rev stored in keyMetrics must be overwritten by the live pull."""
    monkeypatch.setitem(data_agent._QUOTE_CACHE, "TST", dict(_FAKE_QUOTE))
    p = _profile(metrics={"revenue": "$700M", "evRevenue": "9.9x"})
    html = da.build_html(p)
    assert "9.9x" not in html
    assert "4.4x" in html and "2026-01-14" in html
    assert "nanx" not in html and "$nan" not in html


def test_drift_qa_flags_stale_prose_multiple(monkeypatch):
    monkeypatch.setitem(data_agent._QUOTE_CACHE, "TST", dict(_FAKE_QUOTE))
    p = _profile(bullets=["Cheap at 9.9x EV/Rev versus peers"])
    p["_liveQuote"] = dict(_FAKE_QUOTE)
    issues = da._audit_multiple_drift(p)
    assert any("9.9x" in m and "4.4x" in m for _, m in issues), issues
    # ...but a forward multiple right next to its marker is excused
    p2 = _profile(bullets=["Trades at ~12x forward EV/Rev estimates"])
    p2["_liveQuote"] = dict(_FAKE_QUOTE)
    assert not da._audit_multiple_drift(p2)


def test_dict_shaped_key_risks_render(monkeypatch):
    """The research schema sometimes emits keyRisks as {risk, detail, source} dicts —
    the renderer must flatten them to 'Label: detail', not TypeError in clean()."""
    monkeypatch.setitem(data_agent._QUOTE_CACHE, "TST", dict(_FAKE_QUOTE))
    p = _profile()
    p["brief"]["keyRisks"] = [
        {"risk": "Concentration", "detail": "Top customer is 30% of revenue.",
         "source": "10-K"},
        "Churn: SMB cohort retention is slipping.",
    ]
    html = da.build_html(p)
    assert "Concentration:" in html and "Top customer is 30% of revenue." in html
    assert "Churn:" in html


def test_subject_injected_into_comps_and_scatter(monkeypatch):
    """A comps list that only names peers must still show the subject — pinned row in
    the table and the crimson dot on the growth-vs-multiple scatter (AAPL bug)."""
    peer_q = dict(_FAKE_QUOTE, ticker="PEER", name="PeerCo", evRevenueLTM="6.0x",
                  evRevenueNum=6.0, revenueGrowthYoY="10.0%",
                  sourceUrl="https://finance.yahoo.com/quote/PEER")
    peer2_q = dict(peer_q, ticker="PEEB", name="PeerBCo", evRevenueLTM="8.0x",
                   evRevenueNum=8.0, revenueGrowthYoY="15.0%")
    monkeypatch.setitem(data_agent._QUOTE_CACHE, "TST", dict(_FAKE_QUOTE))
    monkeypatch.setitem(data_agent._QUOTE_CACHE, "PEER", peer_q)
    monkeypatch.setitem(data_agent._QUOTE_CACHE, "PEEB", peer2_q)
    p = _profile(comps=[{"name": "PeerCo", "ticker": "PEER", "note": "closest peer"},
                        {"name": "PeerBCo", "ticker": "PEEB", "note": "scaled peer"}])
    html = da.build_html(p)
    assert 'class="subj"' in html                      # subject row pinned in the table
    assert "GROWTH VS MULTIPLE" in html                # scatter rendered (needs 3+ points)
    assert html.count(">TST<") >= 1                    # subject labeled on the scatter


def test_missing_explainer_blocks():
    p = _profile()
    del p["explainer"]
    issues = da._audit_completeness(p)
    assert any(lvl == "error" and "explainer" in m for lvl, m in issues), issues
