"""
Data Agent — pulls live trading data and financials.

Sources:
  - yfinance: price, market cap, EV, margins, growth, analyst ratings (no key)
  - FMP /stable/profile: company metadata, CIK, exchange details (free key)
  - FMP deeper endpoints require paid plan — skipped

Usage:
    python3 agents/data_agent.py SNOW
    python3 agents/data_agent.py SNOW DDOG ESTC MDB   # includes comps

Setup:
    pip3 install yfinance requests
    export FMP_API_KEY="your_key"   # get free at financialmodelingprep.com
"""

import sys
import os
import json
import datetime
import requests
from concurrent.futures import ThreadPoolExecutor

# yfinance is required for live quotes, but importing this module must NEVER kill the
# process: deliverable_agent imports live_quote inside try/except guards, and a bare
# sys.exit() here (SystemExit is not an Exception) would punch straight through them and
# abort the whole brief render on any environment without yfinance (e.g. the ephemeral
# cloud runner). Degrade gracefully instead — live_quote returns {'error': ...} and the
# __main__ entrypoint below reports the missing dependency.
try:
    import yfinance as yf
except ImportError:
    yf = None
    _YF_IMPORT_ERROR = "yfinance not installed. Run: pip3 install yfinance"
else:
    _YF_IMPORT_ERROR = None

FMP_KEY  = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"

# SEC EDGAR is free / no key, but REQUIRES a descriptive User-Agent with a contact.
# Override via SEC_USER_AGENT env if you want your own contact on the requests.
SEC_UA = os.environ.get("SEC_USER_AGENT", "Atlas Research (your-email@example.com)")
_SEC_TICKER_CACHE: dict = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def fmp_get(endpoint: str, params: dict | None = None) -> list | dict | None:
    if not FMP_KEY:
        return None
    try:
        r = requests.get(
            f"{FMP_BASE}/{endpoint}",
            params={"apikey": FMP_KEY, **(params or {})},
            timeout=8,
        )
        if r.ok and r.text.strip().startswith(("[", "{")):
            return r.json()
    except Exception:
        pass
    return None


def _b(val, decimals=1) -> str | None:
    if val is None or val != val:                  # None or NaN — no honest value to print
        return None
    val = float(val)
    if abs(val) >= 1e12:
        return f"${val/1e12:.{decimals}f}T"
    if abs(val) >= 1e9:
        return f"${val/1e9:.{decimals}f}B"
    if abs(val) >= 1e6:
        return f"${val/1e6:.0f}M"
    return f"${val:,.0f}"


def _pct(val) -> str | None:
    if val is None or val != val:
        return None
    return f"{float(val)*100:.1f}%"


def _x(val) -> str | None:
    if val is None or val != val:
        return None
    return f"{float(val):.1f}x"


# ── Last market close: the single dated anchor for every multiple ─────────────

def last_close(stock) -> tuple:
    """
    Return (close_price, close_date_iso) from the most recently COMPLETED trading
    session — the date a banker would label a multiple "as of".

    Critically, an in-progress session is NOT a close: if the US market is open today
    (or pre-open) and has not yet reached the 16:00 ET bell, today's partial bar is
    skipped and we use the prior completed session (e.g. on a Monday morning we use
    Friday's close). On weekends/holidays the latest bar is already the prior close.
    """
    try:
        try:
            from zoneinfo import ZoneInfo
            now_et = datetime.datetime.now(ZoneInfo("America/New_York"))
        except Exception:
            now_et = datetime.datetime.utcnow() - datetime.timedelta(hours=4)  # EDT approx
        today_et = now_et.date()
        market_closed_today = now_et.hour >= 16          # regular session ends 16:00 ET

        hist = stock.history(period="7d", interval="1d")
        if hist is None or hist.empty:
            return None, None
        for i in range(len(hist) - 1, -1, -1):
            bar_date = hist.index[i].date()
            if bar_date > today_et:
                continue                                  # never use a future-dated bar
            if bar_date == today_et and not market_closed_today:
                continue                                  # today's session still open — not a close
            close_val = hist["Close"].iloc[i]
            if close_val != close_val:                    # NaN bar (Yahoo sometimes ships the
                continue                                  # latest session unpopulated) — skip it,
            return float(close_val), bar_date.isoformat() # or every multiple becomes "nanx"
    except Exception:
        pass
    return None, None


# One quote pull per ticker per process: the subject's quote is needed by the hero
# stats, the comps enrichment, and get_yf in the same render, and each uncached call
# costs two slow Yahoo round-trips (info + price history). Errors are never cached.
_QUOTE_CACHE: dict = {}


def live_quote(ticker: str, stock=None, info=None) -> dict:
    """
    Single source of truth for a ticker's trading multiples, anchored to the
    actual last market close. EV/Revenue is RECOMPUTED from the close price
    (close × shares + net debt) rather than read from Yahoo's pre-computed
    enterpriseValue, so the multiple is internally consistent, dated, and
    defensible. Every field carries its source. Returns {'error': ...} on failure.

    Used by both data_agent and deliverable_agent so the brief and the comps
    table can never diverge or fall back to model-memory numbers. Pass an already-
    constructed `stock`/`info` to reuse a fetch the caller has done anyway.
    """
    if yf is None:
        return {"ticker": ticker, "error": _YF_IMPORT_ERROR}
    ticker = ticker.upper().strip()
    cached = _QUOTE_CACHE.get(ticker)
    if cached is not None:
        return dict(cached)
    try:
        stock = stock or yf.Ticker(ticker)
        info = info or stock.info
    except Exception as e:
        return {"ticker": ticker, "error": f"yfinance lookup failed: {e}"}

    close, close_date = last_close(stock)
    shares = info.get("sharesOutstanding")
    debt   = info.get("totalDebt") or 0
    cash   = info.get("totalCash") or 0
    rev    = info.get("totalRevenue")

    # Vendor fallback: everything above hangs off Yahoo's unofficial feed, which has
    # already shipped NaN bars and can rate-limit. If the primary pull came up empty
    # AND an FMP key is configured, backstop price/shares from FMP /stable/quote —
    # honestly labeled, since FMP's quote is "latest", not a stamped close.
    if (not close or not shares) and FMP_KEY:
        fq = fmp_get("quote", {"symbol": ticker})
        fq = fq[0] if isinstance(fq, list) and fq else (fq if isinstance(fq, dict) else None)
        if isinstance(fq, dict):
            if not close and fq.get("price"):
                close = float(fq["price"])
                close_date = close_date or datetime.date.today().isoformat()
            shares = shares or fq.get("sharesOutstanding")

    # Market cap & EV anchored to the stamped close, recomputed when inputs exist
    if close and shares:
        market_cap = close * shares
        ev = market_cap + debt - cash
        ev_basis = "recomputed: last close × shares + net debt"
    else:
        market_cap = info.get("marketCap")
        ev = info.get("enterpriseValue")
        ev_basis = "Yahoo-reported (close × shares unavailable)"

    ev_rev = (ev / rev) if (ev and rev) else None

    # FCF margin + Rule of 40 (growth + FCF margin): the comp-quality screen an MD
    # reads the comps table for. Computed from the same live pull so they tie.
    fcf = info.get("freeCashflow")
    fcf_margin = (fcf / rev) if (fcf and rev) else None
    growth = info.get("revenueGrowth")
    rule40 = None
    if fcf_margin is not None and growth is not None and fcf_margin == fcf_margin and growth == growth:
        rule40 = round((growth + fcf_margin) * 100)

    # Street + balance-sheet context, all from the same info fetch (free): consensus
    # target/upside, forward P/E, short interest, net cash. The 52-week EV/Rev band
    # holds today's shares, net debt, and LTM revenue constant (price effect only) —
    # an honest approximation, labeled as such where rendered.
    target = info.get("targetMeanPrice")
    upside = (target / close - 1) if (target and close) else None
    net_cash = (cash - debt) if (cash or debt) else None
    hi, lo = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")
    ev_rev_range = None
    if hi and lo and shares and rev:
        ev_lo = (lo * shares + debt - cash) / rev
        ev_hi = (hi * shares + debt - cash) / rev
        if ev_lo == ev_lo and ev_hi == ev_hi:
            ev_rev_range = f"{ev_lo:.1f}x–{ev_hi:.1f}x"
    fwd_pe = info.get("forwardPE")

    out = {
        "ticker":            ticker,
        "name":              info.get("shortName", ticker),
        "priceAsOf":         close_date,                       # actual close the multiple reflects
        "closePrice":        round(close, 2) if close else None,
        "marketCap":         _b(market_cap),
        "enterpriseValue":   _b(ev),
        "totalRevenueLTM":   _b(rev),
        "totalRevenueNum":   rev,
        "evRevenueLTM":      _x(ev_rev),
        "evRevenueNum":      round(ev_rev, 2) if (ev_rev and ev_rev == ev_rev) else None,
        "evRevRange52w":     ev_rev_range,
        "revenueGrowthYoY":  _pct(growth),
        "grossMargin":       _pct(info.get("grossMargins")),
        "fcfMarginLTM":      _pct(fcf_margin),
        "ruleOf40":          rule40,
        "analystRating":     info.get("recommendationKey"),
        "analystTarget":     f"${target:,.2f}" if target else None,
        "analystUpside":     _pct(upside),
        "numberOfAnalysts":  info.get("numberOfAnalystOpinions"),
        "forwardPE":         round(fwd_pe, 1) if (fwd_pe and fwd_pe == fwd_pe) else None,
        "shortPctFloat":     _pct(info.get("shortPercentOfFloat")),
        "netCash":           (f"-{_b(abs(net_cash))}" if net_cash < 0 else _b(net_cash)) if net_cash is not None else None,
        "evBasis":           ev_basis,
        "source":            "yfinance / Yahoo Finance",
        "sourceUrl":         f"https://finance.yahoo.com/quote/{ticker}",
    }
    _QUOTE_CACHE[ticker] = out
    return dict(out)


def sbc_pct_revenue(ticker: str, total_revenue=None) -> str | None:
    """Stock-based comp as % of LTM revenue (the dilution screen) from the last four
    quarterly cash-flow statements. Returns a formatted % or None, never raises."""
    if yf is None:
        return None
    try:
        t = yf.Ticker(ticker.upper().strip())
        cf = t.quarterly_cashflow
        if cf is None or getattr(cf, "empty", True):
            return None
        if "Stock Based Compensation" not in cf.index:
            return None
        vals = [float(v) for v in cf.loc["Stock Based Compensation"].iloc[:4]
                if v is not None and v == v]
        rev = total_revenue or t.info.get("totalRevenue")
        if not vals or not rev:
            return None
        return _pct(sum(vals) / rev)
    except Exception:
        return None


def relative_performance(ticker: str, bench: str = "QQQ") -> dict:
    """1M / YTD / 1Y price change vs a benchmark, with the spread in percentage points —
    the 'is this working?' row. Returns {} quietly on any failure."""
    if yf is None:
        return {}
    try:
        hs = yf.Ticker(ticker.upper().strip()).history(period="1y")["Close"].dropna()
        hb = yf.Ticker(bench).history(period="1y")["Close"].dropna()
        if hs.empty or hb.empty:
            return {}
        def _chg(h, days=None, ytd=False):
            if ytd:
                sub = h[h.index.year == h.index[-1].year]
                start = sub.iloc[0] if len(sub) else h.iloc[0]
            else:
                start = h.iloc[-min(days, len(h))]
            return float(h.iloc[-1] / start - 1)
        periods = {}
        for label, kw in (("1M", {"days": 21}), ("YTD", {"ytd": True}), ("1Y", {"days": len(hs)})):
            a, b = _chg(hs, **kw), _chg(hb, **kw)
            periods[label] = {"stock": _pct(a), "bench": _pct(b), "spreadPp": round((a - b) * 100, 1)}
        return {"benchmark": bench, "periods": periods, "asOf": hs.index[-1].date().isoformat(),
                "source": "yfinance / Yahoo Finance"}
    except Exception:
        return {}


def get_xbrl_facts(ticker: str) -> dict:
    """As-reported revenue and net income from SEC XBRL companyfacts — primary-of-record
    figures straight from the filings, the highest-trust source for revenueHistory.
    Returns {} on any failure (non-US filers, no CIK, network)."""
    cik = _sec_ticker_to_cik(ticker)
    if not cik:
        return {}
    try:
        r = requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                         headers={"User-Agent": SEC_UA}, timeout=25)
        if not r.ok:
            return {}
        gaap = (r.json().get("facts") or {}).get("us-gaap") or {}
        def _series(concepts, form):
            for con in concepts:
                rows = ((gaap.get(con) or {}).get("units") or {}).get("USD") or []
                picked = {}
                for e in rows:
                    if e.get("form") != form or not e.get("end") or e.get("val") is None:
                        continue
                    # keep annual spans for 10-K (~12mo), quarterly spans for 10-Q (~3mo)
                    if e.get("start"):
                        span = (datetime.date.fromisoformat(e["end"])
                                - datetime.date.fromisoformat(e["start"])).days
                        if form == "10-K" and not 300 < span < 400:
                            continue
                        if form == "10-Q" and not 60 < span < 120:
                            continue
                    picked[e["end"]] = {"end": e["end"], "value": e["val"],
                                        "valueFormatted": _b(e["val"]), "fy": e.get("fy"),
                                        "fp": e.get("fp"), "filed": e.get("filed"), "concept": con}
                if picked:
                    return sorted(picked.values(), key=lambda x: x["end"])
            return []
        rev_concepts = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues",
                        "SalesRevenueNet")
        facts = {
            "annualRevenue":    _series(rev_concepts, "10-K")[-4:],
            "quarterlyRevenue": _series(rev_concepts, "10-Q")[-5:],
            "annualNetIncome":  _series(("NetIncomeLoss",), "10-K")[-4:],
        }
        if not any(facts.values()):
            return {}
        facts.update({"cik": cik, "source": "SEC EDGAR XBRL companyfacts (as reported)",
                      "sourceUrl": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K"})
        return facts
    except Exception:
        return {}


def next_earnings_date(ticker: str) -> str | None:
    """Next scheduled earnings date (ISO) from yfinance's calendar — the one catalyst
    every reader asks for. Returns None quietly on any failure or for private names."""
    if yf is None:
        return None
    try:
        cal = yf.Ticker(ticker.upper().strip()).calendar or {}
        dates = cal.get("Earnings Date") or []
        today = datetime.date.today()
        future = sorted(d for d in dates if isinstance(d, datetime.date) and d >= today)
        return future[0].isoformat() if future else None
    except Exception:
        return None


# ── yfinance: full trading + financials snapshot ──────────────────────────────

def get_yf(ticker: str) -> dict:
    if yf is None:
        return {"error": _YF_IMPORT_ERROR}
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info

        # Core multiples anchored to the actual last close (single source of truth);
        # hand over the Ticker/info just fetched so the quote doesn't re-pull them.
        q = live_quote(ticker, stock=stock, info=info)
        close = q.get("closePrice")

        return {
            "priceAsOf":           q.get("priceAsOf"),       # date the price/multiples reflect
            "stockPrice":          _b(close, 2) if close else _b(info.get("currentPrice") or info.get("regularMarketPrice"), 2),
            "marketCap":           q.get("marketCap"),
            "enterpriseValue":     q.get("enterpriseValue"),
            "totalRevenueLTM":     q.get("totalRevenueLTM"),
            "revenueGrowthYoY":    q.get("revenueGrowthYoY"),
            "grossMargin":         q.get("grossMargin"),
            "operatingMarginGAAP": _pct(info.get("operatingMargins")),
            "ebitdaMargin":        _pct(info.get("ebitdaMargins")),
            "fcfPerShare":         info.get("freeCashflow"),
            "totalDebt":           _b(info.get("totalDebt")),
            "totalCash":           _b(info.get("totalCash")),
            "evRevenueLTM":        q.get("evRevenueLTM"),
            "evBasis":             q.get("evBasis"),
            "forwardPE":           round(info.get("forwardPE"), 1) if info.get("forwardPE") else None,
            "priceToSalesLTM":     round(info.get("priceToSalesTrailing12Months"), 1) if info.get("priceToSalesTrailing12Months") else None,
            "52wHigh":             info.get("fiftyTwoWeekHigh"),
            "52wLow":              info.get("fiftyTwoWeekLow"),
            "dayChange":           _pct(info.get("regularMarketChangePercent", 0) / 100) if info.get("regularMarketChangePercent") else None,
            "volume":              info.get("regularMarketVolume"),
            "avgVolume":           info.get("averageVolume"),
            "analystTargetPrice":  info.get("targetMeanPrice"),
            "analystTargetHigh":   info.get("targetHighPrice"),
            "analystTargetLow":    info.get("targetLowPrice"),
            "analystRating":       info.get("recommendationKey"),
            "numberOfAnalysts":    info.get("numberOfAnalystOpinions"),
            "shortName":           info.get("shortName"),
            "sector":              info.get("sector"),
            "industry":            info.get("industry"),
            "sharesOutstanding":   info.get("sharesOutstanding"),
        }
    except Exception as e:
        return {"error": f"yfinance failed: {e}"}


# ── FMP: company profile (free) ───────────────────────────────────────────────

def get_fmp_profile(ticker: str) -> dict:
    data = fmp_get("profile", {"symbol": ticker})
    if not data:
        return {}
    p = data[0] if isinstance(data, list) else data
    if isinstance(p, str) or "Premium" in str(p):
        return {}
    return {
        "cik":          p.get("cik"),
        "exchange":     p.get("exchangeFullName"),
        "isin":         p.get("isin"),
        "beta":         p.get("beta"),
        "lastDividend": p.get("lastDividend"),
    }


# ── SEC EDGAR: primary-source filings (free, no key) ──────────────────────────

def _sec_ticker_to_cik(ticker: str) -> str | None:
    """Map a ticker to its zero-padded 10-digit CIK via SEC's official mapping."""
    if not _SEC_TICKER_CACHE:
        try:
            r = requests.get("https://www.sec.gov/files/company_tickers.json",
                             headers={"User-Agent": SEC_UA}, timeout=10)
            if r.ok:
                for row in r.json().values():
                    _SEC_TICKER_CACHE[row["ticker"].upper()] = str(row["cik_str"]).zfill(10)
        except Exception:
            return None
    return _SEC_TICKER_CACHE.get(ticker.upper())


def get_sec_filings(ticker: str, forms=("10-K", "10-Q", "8-K"), per_form: int = 2) -> dict:
    """
    Pull the most recent primary-source filings from SEC EDGAR so the brief can
    cite the company's own 10-K/10-Q/8-K (with filing dates and direct links)
    rather than secondary coverage. No API key required. Returns {} on any failure
    so it never breaks a run. This is primary-of-record data: the highest tier.
    """
    cik = _sec_ticker_to_cik(ticker)
    if not cik:
        return {}
    try:
        r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",
                         headers={"User-Agent": SEC_UA}, timeout=10)
        if not r.ok:
            return {}
        j = r.json()
        recent = j.get("filings", {}).get("recent", {})
        form_l = recent.get("form", [])
        fdate  = recent.get("filingDate", [])
        rdate  = recent.get("reportDate", [])
        accn   = recent.get("accessionNumber", [])
        pdoc   = recent.get("primaryDocument", [])
        cik_int = str(int(cik))
        wanted = {f: 0 for f in forms}
        filings = []
        for i, form in enumerate(form_l):
            if form in wanted and wanted[form] < per_form:
                acc = accn[i].replace("-", "") if i < len(accn) else ""
                doc = pdoc[i] if i < len(pdoc) else ""
                url = (f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{doc}"
                       if acc and doc else
                       f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}")
                filings.append({
                    "form":       form,
                    "filingDate": fdate[i] if i < len(fdate) else "",
                    "reportDate": rdate[i] if i < len(rdate) else "",
                    "url":        url,
                    "source":     "SEC EDGAR (primary filing)",
                })
                wanted[form] += 1
            if all(v >= per_form for v in wanted.values()):
                break
        if not filings:
            return {}
        return {
            "company":       j.get("name"),
            "cik":           cik,
            "fiscalYearEnd": j.get("fiscalYearEnd"),
            "filings":       filings,
            "source":        "SEC EDGAR",
            "sourceUrl":     f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=&dateb=&owner=include&count=40",
        }
    except Exception:
        return {}


# ── Quarterly trend: last N quarters, live & dated ────────────────────────────

def quarterly_trend(ticker: str, n: int = 5) -> dict:
    """
    The last `n` reported quarters of revenue and gross margin, pulled LIVE from
    yfinance's quarterly income statement and stamped with each quarter's fiscal
    period-end date, so a brief can show trajectory (is growth accelerating? is
    gross margin inflecting toward positive?) rather than a single-quarter snapshot.

    A single quarter never tells the story an MD wants; four do. Every figure is a
    live pull (never model memory): revenue and gross profit come straight from the
    statement, gross margin is recomputed as gross profit / revenue, QoQ growth is
    vs. the immediately prior quarter, and YoY is vs. the same quarter a year earlier
    when that quarter is still in the returned window. Returns {} on any failure so
    it never breaks a run.

    Quarters are labelled by the CALENDAR quarter their fiscal period-end falls in
    (e.g. a 2026-03-31 period-end -> "1Q26"), which is the apples-to-apples basis for
    comparing companies with different fiscal-year ends; the exact period-end date
    travels alongside so nothing is ambiguous.
    """
    if yf is None:
        return {}
    ticker = ticker.upper().strip()
    try:
        stmt = yf.Ticker(ticker).quarterly_income_stmt
    except Exception:
        return {}
    if stmt is None or getattr(stmt, "empty", True):
        return {}

    def _row(*names):
        for nm in names:
            if nm in stmt.index:
                return nm
        return None

    rev_row = _row("Total Revenue", "TotalRevenue", "Operating Revenue")
    gp_row  = _row("Gross Profit")
    if not rev_row:
        return {}

    # Newest-first columns; pull a clean (period-end -> revenue) map for YoY lookups.
    cols = list(stmt.columns)
    def _rev(col):
        v = stmt.loc[rev_row, col]
        return float(v) if v == v and v is not None else None      # v==v screens NaN

    quarters = []
    for i, col in enumerate(cols[:n]):
        d = col.date()
        rev = _rev(col)
        if rev is None:
            continue
        cal_q = (d.month - 1) // 3 + 1                              # calendar quarter of the period-end
        gm = None
        if gp_row is not None:
            gp = stmt.loc[gp_row, col]
            if gp == gp and gp is not None and rev:
                gm = float(gp) / rev
        qoq = None
        if i + 1 < len(cols):
            prev = _rev(cols[i + 1])
            if prev:
                qoq = (rev - prev) / abs(prev)
        yoy = None
        if i + 4 < len(cols):                                      # same quarter a year earlier
            ago = _rev(cols[i + 4])
            if ago:
                yoy = (rev - ago) / abs(ago)
        quarters.append({
            "periodEnd":     d.isoformat(),
            "label":         f"{cal_q}Q{d.year % 100:02d}",
            "revenue":       _b(rev),
            "revenueNum":    rev,
            "grossMargin":   _pct(gm),
            "qoqGrowth":     _pct(qoq),
            "yoyGrowth":     _pct(yoy),
        })

    if not quarters:
        return {}
    return {
        "ticker":    ticker,
        "quarters":  quarters,                                     # newest first
        "basis":     "calendar-quarter labels on fiscal period-ends; gross margin = gross profit / revenue",
        "source":    "yfinance / Yahoo Finance (quarterly income statement)",
        "sourceUrl": f"https://finance.yahoo.com/quote/{ticker}/financials",
    }


# ── Ramp Data MCP: B2B demand signals ─────────────────────────────────────────
# These tools are available to Claude Code via the ramp-data MCP server
# (.claude/settings.json). They are NOT callable from this Python script directly;
# the Data Agent subagent calls them and merges results into data.json at run time.
#
# Available MCP tools:
#   ramp-data: ai_index_get_adoption        — AI vendor adoption history + breakdown
#   ramp-data: ai_index_get_adoption_by_sector  — sector-level spend trends
#   ramp-data: ai_index_get_adoption_by_size    — by company size (SMB / mid / enterprise)
#   ramp-data: ramp_rate_get_vendor         — vendor growth, switching, share-of-spend
#
# Best for: SaaS, AI-native, and cloud companies where corporate card spend is a
# leading demand indicator (e.g. Snowflake, Anthropic, Cursor, Databricks).
# Less signal for semis, hardware, or non-software companies.
#
# Data is free, sourced from 50k+ businesses, and citable as "Ramp Data (ramp.com/data)".

RAMP_DATA_TOOLS = [
    "ai_index_get_adoption",
    "ai_index_get_adoption_by_sector",
    "ai_index_get_adoption_by_size",
    "ramp_rate_get_vendor",
]

RAMP_DEMAND_SIGNAL_SCHEMA = {
    "available":        bool,    # True if MCP call succeeded
    "vendorName":       str,     # as Ramp recognises it
    "adoptionTrend":    str,     # e.g. "growing", "declining", "flat"
    "adoptionGrowthYoY": str,    # e.g. "+38% YoY"
    "shareOfSpend":     str,     # share of corporate card spend in category
    "switchRate":       str,     # % of businesses switching away per year
    "sectorBreakdown":  list,    # [{sector, adoptionPct}, ...]
    "sizeBreakdown":    list,    # [{size, adoptionPct}, ...]
    "note":             str,     # any caveats (e.g. SMB-skewed dataset)
    "source":           str,     # "Ramp Data"
    "sourceUrl":        str,     # "https://ramp.com/data"
    "asOf":             str,     # date of latest Ramp Data index
}


# ── Comps table ───────────────────────────────────────────────────────────────

def get_comps(tickers: list[str]) -> list:
    """Every comp pulled in the same run via the shared live_quote helper, so
    all multiples share one consistent last-close anchor (or visibly flag if
    a ticker's data is stale relative to the rest). Quotes are fetched in
    parallel — each is ~2 slow Yahoo round-trips, so a 6-name comp set would
    otherwise dominate the run time."""
    if not tickers:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(tickers))) as pool:
        quotes = list(pool.map(live_quote, tickers))
    out = []
    for t, q in zip(tickers, quotes):
        if "error" in q:
            out.append({"ticker": t.upper(), "error": q["error"]})
            continue
        out.append({
            "ticker":        q["ticker"],
            "name":          q["name"],
            "priceAsOf":     q["priceAsOf"],
            "marketCap":     q["marketCap"],
            "evRevenueLTM":  q["evRevenueLTM"],
            "revenueGrowth": q["revenueGrowthYoY"],
            "grossMargin":   q["grossMargin"],
            "analystRating": q["analystRating"],
            "source":        q["source"],
            "sourceUrl":     q["sourceUrl"],
        })
    return out


# ── Main ─────────────────────────────────────────────────────────────────────

def run(ticker: str, comps_tickers: list[str] | None = None, ramp_demand_signal: dict | None = None) -> dict:
    ticker = ticker.upper().strip()
    yf_data      = get_yf(ticker)
    fmp_profile  = get_fmp_profile(ticker)
    comps        = get_comps(comps_tickers) if comps_tickers else []
    sec_filings  = get_sec_filings(ticker)
    qtrend       = quarterly_trend(ticker)
    sec_facts    = get_xbrl_facts(ticker)          # as-reported, primary-of-record
    rel_perf     = relative_performance(ticker)

    # Freshness audit: gather every close date used, surface the anchor, and flag
    # any ticker whose last close lags the rest (halt, holiday, delisting, stale feed).
    close_dates = [yf_data.get("priceAsOf")] + [c.get("priceAsOf") for c in comps]
    close_dates = [d for d in close_dates if d]
    market_close = max(close_dates) if close_dates else None
    stale = sorted({d for d in close_dates if market_close and d != market_close})

    sources = ["yfinance / Yahoo Finance", "FMP /stable/profile", "SEC EDGAR"]
    if ramp_demand_signal and ramp_demand_signal.get("available"):
        sources.append("Ramp Data (ramp.com/data)")

    return {
        "ticker":            ticker,
        "runDate":           datetime.date.today().isoformat(),
        "marketCloseAsOf":   market_close,
        "freshnessNote":  (
            f"All multiples reflect the {market_close} market close."
            if not stale else
            f"Primary multiples reflect the {market_close} close; "
            f"these tickers lag and must not be compared at face value: {', '.join(stale)}."
        ) if market_close else "No live close date available — do not present multiples as current.",
        "sources":           sources,
        "trading":           yf_data,
        "quarterlyTrend":    qtrend,
        "profile":           fmp_profile,
        "comps":             comps,
        "secFilings":        sec_filings,
        # As-reported XBRL figures: prefer these over Yahoo aggregates when writing
        # revenueHistory for US filers — they are the company's own filed numbers.
        "secFacts":          sec_facts,
        "relativePerformance": rel_perf,
        # Populated by the Data Agent subagent via ramp-data MCP tools (Claude Code only).
        # See RAMP_DATA_TOOLS and RAMP_DEMAND_SIGNAL_SCHEMA above for expected shape.
        "rampDemandSignal":  ramp_demand_signal,
    }


if __name__ == "__main__":
    if yf is None:
        print(json.dumps({"error": _YF_IMPORT_ERROR}))
        sys.exit(1)
    if len(sys.argv) < 2:
        print("Usage: python3 agents/data_agent.py TICKER [COMP1 COMP2 ...]")
        sys.exit(1)

    ticker = sys.argv[1]
    comps  = sys.argv[2:] if len(sys.argv) > 2 else []
    result = run(ticker, comps)
    print(json.dumps(result, indent=2))
