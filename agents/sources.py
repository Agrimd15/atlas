"""
Alfred Source Registry — canonical trusted sources for all research agents.

Agents MUST prefer these sources. Do not cite random blogs, press release aggregators,
Reddit, Substack newsletters from unknown writers, or unverified Medium posts.

Source tiers:
  TIER_1 — Primary of record. Cite directly. Treat as ground truth.
  TIER_2 — Strong secondary. Good for color, confirmatory, or exclusive scoops.
  TIER_3 — Acceptable for context, background, or when Tier 1/2 unavailable.
  X_ACCOUNTS — Curated X (Twitter) accounts. High bar: verified expert or journalist only.

Usage:
    from agents.sources import SITE_QUERY, NEWS_SITE_QUERY, X_QUERY, ALL_TRUSTED_DOMAINS
"""

# ── Tier 1: Primary sources of record ─────────────────────────────────────────
# Major financial press and wire services. Cite by name. Use for facts and quotes.

TIER_1 = {
    "wsj.com":          "Wall Street Journal",
    "bloomberg.com":    "Bloomberg",
    "ft.com":           "Financial Times",
    "reuters.com":      "Reuters",
    "nytimes.com":      "New York Times",
    "axios.com":        "Axios",         # Pro Rata, Axios Markets, Axios Pro
}

# ── Tier 2: Strong secondary ───────────────────────────────────────────────────
# Reputable tech/finance press, respected analysis, and subscription newsletters.
# Stratechery and The Information are paywalled but search indices find public excerpts.

TIER_2 = {
    "techcrunch.com":       "TechCrunch",
    "theinformation.com":   "The Information",
    "stratechery.com":      "Stratechery (Ben Thompson)",
    "semafor.com":          "Semafor",
    "businessinsider.com":  "Business Insider",
    "cnbc.com":             "CNBC",
    "fortune.com":          "Fortune",
    "wired.com":            "Wired",
    "protocol.com":         "Protocol",
    "notboring.co":         "Not Boring (Packy McCormick)",
    "pitchbook.com":        "PitchBook",
    "crunchbase.com":       "Crunchbase",
    "sacra.com":            "Sacra",         # private co revenue estimates
    "meritech.com":         "Meritech Capital (SaaS comps)",
    "bvp.com":              "Bessemer Venture Partners (State of Cloud)",
    "ramp.com":             "Ramp Data (B2B vendor spend signals, 50k+ businesses)",   # cited as ramp.com/data
}

# ── Tier 3: Acceptable context sources ────────────────────────────────────────
# Use only to fill gaps. Always note tier in source citation.

TIER_3 = {
    "venturebeat.com":      "VentureBeat",
    "zdnet.com":            "ZDNet",
    "seekingalpha.com":     "Seeking Alpha",
    "morningstar.com":      "Morningstar",
    "barrons.com":          "Barron's",
    "marketwatch.com":      "MarketWatch",
    "apnews.com":           "AP News",
    "prnewswire.com":       "PR Newswire (company-issued)",
    "businesswire.com":     "Business Wire (company-issued)",
    "ir.company.com":       "Company IR page (official)",
}

# ── X / Twitter accounts ───────────────────────────────────────────────────────
# High bar. Only: verified journalists at Tier 1/2 publications, major fund GPs,
# respected independent analysts with strong track records, and official company accounts.
# Do NOT use: anonymous accounts, low-follower accounts, promotional accounts.

X_ACCOUNTS = {

    # Tech analysis / newsletters
    "benedictevans":    "Benedict Evans — independent tech analyst, ex-a16z",
    "stratechery":      "Ben Thompson — Stratechery founder, deep tech strategy",
    "packyM":           "Packy McCormick — Not Boring, deep-dive tech investing",
    "dwarkesh_sp":      "Dwarkesh Patel — longform interviews, AI/tech",
    "hoodiev":          "Horace Dediu — mobile/tech industry analyst",

    # Venture capital (GP level only)
    "pmarca":           "Marc Andreessen — a16z cofounder",
    "bhorowitz":        "Ben Horowitz — a16z cofounder",
    "cdixon":           "Chris Dixon — a16z crypto/tech GP",
    "sriramk":          "Sriram Krishnan — a16z general partner",
    "garrytan":         "Garry Tan — Y Combinator president",
    "sama":             "Sam Altman — OpenAI CEO, YC alum",
    "naval":            "Naval Ravikant — AngelList founder",
    "delian":           "Delian Asparouhov — Founders Fund partner",
    "ttunguz":          "Tomasz Tunguz — Theory Ventures, SaaS metrics expert",
    "sarahtavel":       "Sarah Tavel — Benchmark partner",
    "jasonlk":          "Jason Lemkin — SaaStr, enterprise SaaS expert",
    "semil":            "Semil Shah — Haystack Ventures",

    # Finance / macro commentary
    "chamath":          "Chamath Palihapitiya — Social Capital, All-In Podcast",
    "morganhousel":     "Morgan Housel — Collaborative Fund, finance writing",
    "elerianm":         "Mohamed El-Erian — macro economist, Bloomberg Opinion",
    "howardlindzon":    "Howard Lindzon — Stocktwits founder, fintech",

    # Journalists (Tier 1/2 publications only)
    "karaswisher":      "Kara Swisher — Pivot podcast, NYT/Bloomberg contributor",
    "ericnewcomer":     "Eric Newcomer — Newcomer Newsletter, tech M&A scoops",
    "alex":             "Alex Wilhelm — TechCrunch/Equity podcast",
    "stevesi":          "Steven Sinofsky — ex-Microsoft, product strategy",
    "lora_kolodny":     "Lora Kolodny — CNBC tech reporter",
    "danprimack":       "Dan Primack — Axios Pro Rata author",   # key for VC/PE deals

    # Defense tech (given user's coverage)
    "andurilindustries": "Anduril Industries — official company account",
    "palantir":          "Palantir — official company account",

    # SaaS / cloud metrics
    "jaminball":        "Jamin Ball — Clouded Judgement, SaaS metrics newsletter",
    "davidbhochman":    "David Hochman — enterprise software",
}

# ── Search query builders ──────────────────────────────────────────────────────

# site: query for general research
ALL_TRUSTED_DOMAINS = list(TIER_1.keys()) + list(TIER_2.keys())

def site_query(domains: list = None) -> str:
    """Build a 'site:X OR site:Y' query string."""
    return " OR ".join(f"site:{d}" for d in (domains or list(TIER_1.keys())))

# Pre-built query strings for agent use
SITE_QUERY_T1 = site_query(list(TIER_1.keys()))
SITE_QUERY_T1_T2 = site_query(ALL_TRUSTED_DOMAINS)

NEWS_SITE_QUERY = (
    "site:wsj.com OR site:bloomberg.com OR site:ft.com OR site:reuters.com "
    "OR site:nytimes.com OR site:axios.com OR site:techcrunch.com "
    "OR site:theinformation.com OR site:semafor.com"
)

FUNDING_SITE_QUERY = (
    "site:axios.com OR site:bloomberg.com OR site:wsj.com OR site:techcrunch.com "
    "OR site:theinformation.com OR site:ft.com OR site:crunchbase.com OR site:sacra.com"
)

EARNINGS_SITE_QUERY = (
    "site:wsj.com OR site:bloomberg.com OR site:ft.com OR site:reuters.com "
    "OR site:cnbc.com OR site:axios.com OR site:seekingalpha.com"
)

ANALYSIS_SITE_QUERY = (
    "site:stratechery.com OR site:notboring.co OR site:theinformation.com "
    "OR site:bloomberg.com OR site:ft.com OR site:wsj.com OR site:sacra.com"
)

def x_query(company: str, accounts: list = None) -> str:
    """Build an X/Twitter search for a company from trusted accounts."""
    accts = accounts or ["danprimack", "ericnewcomer", "benedictevans", "packyM", "ttunguz"]
    account_sites = " OR ".join(f"site:x.com/{a}" for a in accts)
    return f'"{company}" ({account_sites})'

# ── Source citation helper ─────────────────────────────────────────────────────

def label(domain: str) -> str:
    """Return human-readable label for a domain."""
    for d in [TIER_1, TIER_2, TIER_3]:
        if domain in d:
            return d[domain]
    return domain

def tier(domain: str) -> int:
    """Return tier number (1, 2, 3) for a domain, or 99 if unknown."""
    if domain in TIER_1: return 1
    if domain in TIER_2: return 2
    if domain in TIER_3: return 3
    return 99
