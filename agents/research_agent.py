"""
Research Agent — handles both public and private companies.

All searches MUST use sources from agents/sources.py.
Do not cite random blogs, aggregators, Reddit, or unverified Substack posts.

Tier hierarchy:
  Tier 1: WSJ, Bloomberg, FT, Reuters, NYT, Axios
  Tier 2: TechCrunch, The Information, Stratechery, Sacra, Semafor, Not Boring
  Tier 3: acceptable for context only; flag clearly

X/Twitter: only curated accounts in sources.X_ACCOUNTS. No anonymous sources.

This module documents the search strategy and prompt templates used by
the Claude orchestrator when running Wave 1 research.
"""

import datetime

from agents.sources import (
    NEWS_SITE_QUERY,
    FUNDING_SITE_QUERY,
    EARNINGS_SITE_QUERY,
    ANALYSIS_SITE_QUERY,
    SITE_QUERY_T1,
    SITE_QUERY_T1_T2,
    x_query,
)

# ── Dynamic recency anchors ─────────────────────────────────────────────────────
# Years are computed at run time so searches always target the CURRENT period.
# Never hardcode a year in a query — a stale year silently filters out fresh results
# and breaks the Data Freshness Mandate (see CLAUDE.md).
_CUR_YEAR  = datetime.date.today().year
_PREV_YEAR = _CUR_YEAR - 1
_YEARS     = f"{_PREV_YEAR} {_CUR_YEAR}"        # e.g. "2025 2026"
_YEARS_OR  = f"{_PREV_YEAR} OR {_CUR_YEAR}"     # e.g. "2025 OR 2026"


# ── Search query templates ─────────────────────────────────────────────────────

def public_queries(company: str, ticker: str, competitors: str = "") -> list[str]:
    return [
        f'"{company}" {ticker} business model product revenue segments {_YEARS} ({SITE_QUERY_T1_T2})',
        f'"{company}" investor presentation annual report earnings call transcript {_CUR_YEAR}',
        f'"{company}" competitive positioning vs {competitors} ({SITE_QUERY_T1_T2})' if competitors else f'"{company}" competitive analysis market share {_CUR_YEAR} ({SITE_QUERY_T1})',
        f'"{company}" {ticker} strategy product launch AI {_CUR_YEAR} ({ANALYSIS_SITE_QUERY})',
        f'"{company}" CEO CFO CRO executive leadership team {_YEARS} site:{company.lower().replace(" ","")+".com"} OR ({SITE_QUERY_T1_T2})',
    ]

def private_queries(company: str) -> list[str]:
    return [
        f'"{company}" funding round valuation raised ({FUNDING_SITE_QUERY})',
        f'"{company}" series valuation investors raised million billion ({SITE_QUERY_T1_T2})',
        f'"{company}" ({ANALYSIS_SITE_QUERY})',
        f'"{company}" SEC Form D filing private placement',
        f'"{company}" CEO CFO CRO executive leadership team {_YEARS} ({SITE_QUERY_T1_T2})',
        x_query(company, ["danprimack", "ericnewcomer", "benedictevans", "packyM", "ttunguz", "jasonlk"]),
    ]

def news_queries(company: str) -> list[str]:
    return [
        f'"{company}" news M&A funding earnings announcement {_CUR_YEAR} ({NEWS_SITE_QUERY})',
        f'"{company}" ({NEWS_SITE_QUERY}) {_CUR_YEAR}',
        f'"{company}" analysis strategy ({ANALYSIS_SITE_QUERY})',
        x_query(company, ["danprimack", "ericnewcomer", "karaswisher", "benedictevans", "packyM"]),
    ]

def earnings_queries(company: str, ticker: str = "") -> list[str]:
    return [
        f'"{company}" {ticker} earnings call transcript latest quarter {_YEARS_OR} guidance ({EARNINGS_SITE_QUERY})',
        f'"{company}" {ticker} earnings results revenue guidance {_CUR_YEAR} ({SITE_QUERY_T1})',
        f'"{company}" CEO interview outlook {_CUR_YEAR} ({ANALYSIS_SITE_QUERY})',
        x_query(company, ["ttunguz", "jaminball", "ericnewcomer", "danprimack"]),
    ]

def data_queries(company: str, ticker: str = "") -> list[str]:
    return [
        f'"{company}" {ticker} ARR NRR revenue growth gross margin KPIs {_YEARS} ({SITE_QUERY_T1_T2})',
        f'"{company}" {ticker} financials investor presentation site:sacra.com OR site:meritech.com OR site:bvp.com',
        f'"{company}" {ticker} comps comparable companies EV revenue multiple ({EARNINGS_SITE_QUERY})',
    ]


# ── Orchestrator prompt templates ──────────────────────────────────────────────

SOURCE_RULES = """
SOURCE RULES — non-negotiable:
- ONLY cite from: WSJ, Bloomberg, FT, Reuters, NYT, Axios, TechCrunch, The Information,
  Stratechery, Sacra, Semafor, Not Boring (Packy McCormick), PitchBook, Crunchbase, Sacra,
  official company IR pages, SEC filings, or the approved X accounts below.
- X accounts approved: @danprimack @ericnewcomer @benedictevans @packyM @ttunguz
  @jaminball @karaswisher @sriramk @garrytan @sama @chamath @jasonlk @sarahtavel @delian
- If you cannot find information from these sources, say "not found in trusted sources" —
  do NOT pull from random blogs, PR aggregators, Reddit, or unknown Substack newsletters.
- Always include the source name and URL in your JSON output.
- Label company-issued press releases as "company-issued" — treat as less authoritative.
"""

PRIVATE_COMPANY_PROMPT = """
You are a research agent for an investment banking analyst covering tech companies.
Research the PRIVATE company "{company}".

{source_rules}

Search these sources in order of priority:
1. Axios Pro Rata (@danprimack) — best source for VC/PE deal scoops
2. Bloomberg / WSJ — funding announcements, M&A
3. TechCrunch — Series A through pre-IPO rounds
4. The Information — exclusive private company coverage
5. Sacra.com — private company revenue estimates with methodology
6. Crunchbase / PitchBook — round history and investor lists
7. Stratechery / Not Boring — strategic analysis if available
8. SEC Form D filings — legally required for US private placements
9. X accounts: @danprimack @ericnewcomer @benedictevans @packyM for deal commentary
10. Official company IR / press releases (flag as company-issued)

Return ONLY valid JSON:
{{
  "name": "Official company name",
  "website": "https://...",
  "founded": "YYYY",
  "headquarters": "City, State",
  "employeeCount": "estimated, cite source",
  "stage": "Series X / Pre-IPO / etc.",
  "lastKnownValuation": "$XB (as of YYYY-MM, source: Bloomberg)",
  "totalRaised": number_in_millions,
  "verticals": ["SaaS", "AI/ML"],
  "shortDescription": "one tight sentence, max 18 words",
  "businessModel": "2-3 sentences on revenue model and customer segments",
  "marketPositioning": "2-3 sentences",
  "endMarkets": ["Enterprise", "DoD"],
  "growthDrivers": ["driver1", "driver2"],
  "techDifferentiation": "2 sentences",
  "competitors": ["Competitor1", "Competitor2"],
  "leadership": [
    {{
      "name": "First Last",
      "title": "Chief Executive Officer",
      "since": "YYYY or Month YYYY",
      "background": "1-2 sentences, sourced facts only — prior roles, prior companies",
      "linkedin": "https://linkedin.com/in/... or empty string",
      "source": "publication or company press release",
      "sourceUrl": "https://direct-url"
    }}
  ],
  "fundingRounds": [
    {{
      "round": "Series C",
      "date": "2024-03",
      "amount": 500,
      "amountFormatted": "$500M",
      "postMoneyValuation": 5000,
      "postMoneyValuationFormatted": "$5B",
      "leadInvestors": ["Lead VC"],
      "allInvestors": ["Lead VC", "Follow-on VC"],
      "source": "Axios Pro Rata",
      "sourceUrl": "https://axios.com/..."
    }}
  ],
  "notableInvestors": ["Sequoia", "a16z"],
  "ipoReadiness": "assessment with signals and sources",
  "xSources": [
    {{
      "account": "@danprimack",
      "relevantPost": "summary of relevant post",
      "url": "https://x.com/..."
    }}
  ],
  "dataConfidence": "high / medium / low — explain what was verifiable"
}}
""".format(source_rules=SOURCE_RULES, company="{company}")

PUBLIC_COMPANY_PROMPT = """
You are a research agent for an investment banking analyst covering tech companies.
Research the PUBLIC company "{company}" (ticker: {ticker}).

{source_rules}

Search for: official company description, product suite, revenue model, market positioning,
competitive landscape, end markets, key growth drivers, and technology differentiation.

Prefer: company investor relations pages, WSJ/Bloomberg coverage, Stratechery analysis,
Sacra/Meritech for metrics benchmarking, TechCrunch for product news.

Return ONLY valid JSON:
{{
  "name": "Official company name",
  "ticker": "{ticker}",
  "website": "https://...",
  "founded": "YYYY",
  "headquarters": "City, State",
  "employeeCount": "~X,XXX",
  "verticals": ["Cloud & Infrastructure", "SaaS"],
  "shortDescription": "one tight sentence max 18 words",
  "businessModel": "2-3 sentences on revenue model and customer segments",
  "marketPositioning": "2-3 sentences on where they sit vs competitors",
  "endMarkets": ["Enterprise", "Financial Services"],
  "growthDrivers": ["driver1", "driver2", "driver3", "driver4"],
  "techDifferentiation": "2 sentences on what makes the tech defensible",
  "competitors": ["Competitor1", "Competitor2", "Competitor3"],
  "leadership": [
    {{
      "name": "First Last",
      "title": "Chief Executive Officer",
      "since": "YYYY or Month YYYY",
      "background": "1-2 sentences, sourced facts only — prior roles, prior companies",
      "linkedin": "https://linkedin.com/in/... or empty string",
      "source": "publication or company press release",
      "sourceUrl": "https://direct-url"
    }}
  ]
}}

IMPORTANT for leadership: search the company's own /about/leadership or /company/leadership page, recent press releases announcing executive appointments, and LinkedIn. Only include people confirmed in role as of the current date. Every entry must have a sourceUrl. Do not include anyone based on prior knowledge alone.
""".format(source_rules=SOURCE_RULES, company="{company}", ticker="{ticker}")

NEWS_AGENT_PROMPT = """
You are the News Agent for Alfred, an IB analyst research system.
Find the 6 most important recent news items about "{company}".

{source_rules}

Search queries to run (always target the current period — never an old year):
1. "{company}" news M&A funding earnings announcement {cur_year} — WSJ, Bloomberg, Axios, Reuters, FT
2. "{company}" analysis strategy product {cur_year} — Stratechery, The Information, Not Boring, Semafor
3. X accounts: @danprimack @ericnewcomer @karaswisher @benedictevans @packyM for commentary

Prioritize the most recent items. For each item, explain WHY it matters to an investment
banker — deal implications, valuation impact, competitive signal, or regulatory risk.

Return ONLY valid JSON:
{{
  "recentNews": [
    {{
      "date": "YYYY-MM-DD",
      "headline": "concise headline, no em dashes",
      "source": "Bloomberg",
      "sourceUrl": "https://...",
      "whyItMatters": "1 sentence, IB analyst lens — deal/valuation/competitive implication"
    }}
  ]
}}
""".format(source_rules=SOURCE_RULES, company="{company}", cur_year=_CUR_YEAR)

TRANSCRIPT_AGENT_PROMPT = """
You are the Transcript Agent for Alfred, an IB analyst research system.
Find management commentary and earnings context for "{company}".

{source_rules}

For PUBLIC companies: search for earnings call transcripts and analyst day notes.
  - Prefer: Seeking Alpha transcripts, Bloomberg earnings summaries, Reuters earnings
  - Also search: Stratechery post-earnings analysis, WSJ/FT earnings coverage
  - X: @ttunguz @jaminball for SaaS metric commentary, @ericnewcomer for exclusive takes

For PRIVATE companies: search for founder interviews and conference talks.
  - Prefer: WSJ/Bloomberg CEO interviews, Axios Pro Rata founder commentary
  - Also: Stratechery interviews, Dwarkesh podcast, podcast transcripts indexed in search
  - X: @sama @garrytan @danprimack @ericnewcomer for ecosystem commentary

Return ONLY valid JSON:
{{
  "managementCommentary": {{
    "source": "name of interview/call/conference + date",
    "sourceUrl": "https://...",
    "keyQuotes": ["direct quote or close paraphrase — always cite source"],
    "strategicThemes": ["theme 1", "theme 2"],
    "demandCommentary": "paragraph on demand signals, customer wins, pipeline",
    "aiCommentary": "paragraph on AI/product direction"
  }}
}}
""".format(source_rules=SOURCE_RULES, company="{company}")

DATA_AGENT_PROMPT = """
You are the Data Agent for Alfred, an IB analyst research system.
Gather financial data and trading metrics for "{company}".

{source_rules}

DATA FRESHNESS MANDATE (non-negotiable — see CLAUDE.md):
- For any PUBLIC company or comp, trading multiples MUST come from the LIVE pull:
  run `python3 agents/data_agent.py TICKER COMP1 COMP2 ...` and use its output verbatim.
  NEVER write a price, market cap, or EV/Rev multiple from memory.
- Pass ALL comp tickers in the SAME command so every multiple shares one `marketCloseAsOf`
  close anchor. Carry the `priceAsOf`, `marketCloseAsOf`, and `freshnessNote` through to output;
  surface any lagging ticker rather than hiding it.
- For PRIVATE companies (no ticker), use Sacra/Meritech/PitchBook/Bessemer estimates and label
  them clearly as estimates with their as-of date and source — they are NOT market-priced.
- Every single metric carries a `source` and `sourceUrl`. No number without provenance.

Source preference for non-market metrics (ARR/NRR/KPIs/benchmarks):
  - Sacra.com — private company ARR/revenue estimates (cites methodology)
  - Meritech Capital (meritech.com) — public SaaS comps and benchmarks
  - Bessemer State of Cloud (bvp.com) — cloud software benchmarks
  - Bloomberg/WSJ — public company financials and segment detail
  - PitchBook — private company valuation benchmarks

Return ONLY valid JSON in this shape:
{{
  "marketCloseAsOf": "YYYY-MM-DD (from data_agent.py; null for pure-private)",
  "freshnessNote": "the data_agent freshnessNote, or estimate caveat for private cos",
  "trading": {{ "...": "data_agent.py 'trading' block verbatim for public cos" }},
  "kpis": [
    {{ "metric": "ARR", "value": "$X.XB", "period": "FY{cur_year}", "source": "Sacra", "sourceUrl": "https://..." }}
  ],
  "comps": [
    {{
      "name": "Comp Co", "ticker": "TCKR", "evRevenueLTM": "12.3x", "revenueGrowth": "28% YoY",
      "grossMargin": "78%", "priceAsOf": "YYYY-MM-DD", "source": "yfinance", "sourceUrl": "https://..."
    }}
  ]
}}
""".format(source_rules=SOURCE_RULES, company="{company}", cur_year=_CUR_YEAR)


if __name__ == "__main__":
    print("Research agent loaded. Sources:")
    from agents.sources import TIER_1, TIER_2
    print("Tier 1:", list(TIER_1.values()))
    print("Tier 2:", list(TIER_2.values()))
