"""
Deliverable Agent — generates a clean HTML research brief and a print-faithful PDF.

Usage:
    python3 agents/deliverable_agent.py SNOW              # brief (HTML + PDF)
    python3 agents/deliverable_agent.py SNOW --detailed   # detailed variant

Writes both files to data-dumps/FOLDER_ID/runs/YYYY-MM-DD/. The PDF is rendered from
the HTML via the locally-installed headless Chrome. No network or credentials required
(beyond the optional FMP_API_KEY in .env used for live comps).
"""

import sys, os, json, re, datetime, subprocess, shutil, time, base64, socket, urllib.request, urllib.error
from pathlib import Path

# yfinance-backed live comps enrichment (optional — gracefully skipped if not installed)
def _enrich_comps_live(comps: list) -> list:
    """
    For any comp with a real exchange ticker (not 'Private', 'N/A', 'Acquired', etc.),
    overwrite EV/Rev, revenue growth, gross margin, and market cap with LIVE numbers
    from the shared live_quote helper — never model-memory values. Multiples are
    recomputed from, and stamped with, the ACTUAL last market close date (not the
    run date), so every comp shares one consistent, defensible anchor.
    Manual fields (note, type) are preserved.
    """
    try:
        from data_agent import live_quote        # shared single source of truth
    except Exception:
        return comps

    skip_words = {"private", "n/a", "acquired", "delisted"}
    enriched = []
    for c in comps:
        ticker = c.get("ticker", "").strip()
        ticker_clean = re.sub(r'[^a-z]', '', ticker.lower())  # letters only
        if not ticker_clean or len(ticker_clean) > 5 or ticker_clean in skip_words:
            enriched.append(c)
            continue
        q = live_quote(ticker_clean.upper())
        if "error" in q:
            enriched.append(c)
            continue
        merged = dict(c)
        if q.get("evRevenueLTM"):
            merged["evRevenue"] = f"{q['evRevenueLTM']} LTM"
            merged["asOf"]      = q.get("priceAsOf") or ""   # the real close date
        if q.get("revenueGrowthYoY"):
            merged["revenueGrowth"] = f"{q['revenueGrowthYoY']} YoY"
        if q.get("grossMargin"):
            merged["grossMargin"] = q["grossMargin"]
        if q.get("marketCap"):
            merged["marketCap"] = q["marketCap"]
        merged["source"]    = f"yfinance, close of {q.get('priceAsOf','n/a')} ({q.get('evBasis','')})"
        merged["sourceUrl"] = q.get("sourceUrl", "")
        enriched.append(merged)
    return enriched

# Load .env from the Atlas tool root (.env)
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

ROOT       = Path(__file__).parent.parent
DATA_DUMPS = ROOT / "data-dumps"


# ── Load profile ──────────────────────────────────────────────────────────────

def load_profile(ticker: str) -> dict:
    # Try exact input first (private company slugs like "applied-intuition"),
    # then uppercase (public tickers like "SNOW").
    for candidate in [ticker, ticker.upper()]:
        p = DATA_DUMPS / candidate / "profile.json"
        if p.exists():
            return json.loads(p.read_text())
    raise FileNotFoundError(f"No profile found for {ticker}. Run a research run first.")


# ── Text helpers ─────────────────────────────────────────────────────────────

# Placeholder tokens that should NEVER reach the page. A figure with no honest
# value is left out entirely, not rendered as "N/A" / "-" / "TBD" (house rule:
# an MD reads a dash as a hole in the work, not as information).
_EMPTY_TOKENS = {
    "", "null", "none", "nan", "n/a", "n.a.", "na", "not disclosed",
    "undisclosed", "tbd", "tbc", "-", "--", "—", "–", "ineligible",
    "not applicable", "not available", "unknown", "n/m", "nm",
}

def _is_empty(v) -> bool:
    """True if a value is missing or a placeholder we should suppress."""
    if v is None:
        return True
    return str(v).strip().lower() in _EMPTY_TOKENS

def clean(text: str) -> str:
    """Enforce the no-em-dash / limited-dash house style: never emit em or en dashes,
    and convert dash-as-punctuation (em/en dashes, and spaced hyphens used as a dash)
    into commas. Hyphens inside compound words (non-GAAP, year-over-year) are kept
    because they have no surrounding spaces."""
    text = re.sub(r'\s*[—–]\s*', ', ', text)      # em / en dash -> comma
    text = re.sub(r'\s+-{1,2}\s+', ', ', text)     # spaced hyphen used as a dash -> comma
    text = re.sub(r',\s*,', ', ', text)            # collapse doubled commas
    text = re.sub(r'\s+', ' ', text)               # tighten whitespace
    return text.strip().strip(',').strip()

def to_bullets(text, max_bullets: int = 0) -> str:
    """Convert a paragraph string or list of strings into HTML bullet points."""
    if not text:
        return ""
    # If already a list, use directly
    if isinstance(text, list):
        parts = [clean(str(p)).strip().rstrip(".") for p in text if str(p).strip()]
        if max_bullets:
            parts = parts[:max_bullets]
        if not parts:
            return ""
        return "<ul class='body-list'>" + "".join(f"<li>{p}.</li>" for p in parts) + "</ul>"
    # Otherwise split paragraph string
    text = clean(text)
    # Only split after lowercase letter or digit followed by ". " then uppercase/digit
    # This avoids splitting "U.S. Department" or "Inc. was" etc.
    parts = re.split(r'(?<=[a-z0-9])\.\s+(?=[A-Z\$\(])', text)
    parts = [p.strip().rstrip(".") for p in parts if len(p.strip()) > 20]
    if len(parts) <= 1:
        return f"<p class='body-p'>{text}</p>"
    if max_bullets:
        parts = parts[:max_bullets]
    return "<ul class='body-list'>" + "".join(f"<li>{p}.</li>" for p in parts) + "</ul>"


# ── Visual helpers ────────────────────────────────────────────────────────────

def build_bar_chart(series: list, eyebrow: str = "REVENUE TRAJECTORY",
                    accent: str = "var(--ks-kinpaku)", growth_color: str = "var(--ks-patina)",
                    caption: str = "") -> str:
    """Larger, legible inline SVG bar chart. series items: {value, label, year, source?, sourceUrl?}."""
    if not series or len(series) < 2:
        return ""
    max_val = max(r["value"] for r in series)
    # TOP reserves headroom so the tallest bar's value + growth labels sit INSIDE the
    # chart and never collide with the eyebrow title above it.
    TOP, plot_h, bar_w, gap, pad = 38, 118, 78, 32, 30
    base_y = TOP + plot_h                       # baseline the bars sit on
    total_w = len(series) * (bar_w + gap) + pad
    svg_h = base_y + 34                          # room for the year labels below
    bars = ""
    for i, r in enumerate(series):
        bar_h = max(6, int((r["value"] / max_val) * plot_h))
        x = pad + i * (bar_w + gap)
        y = base_y - bar_h
        opacity = 0.55 + 0.45 * (i / max(1, len(series) - 1))
        growth = ""
        if i > 0 and series[i-1]["value"]:
            pct = int(round(((r["value"] - series[i-1]["value"]) / series[i-1]["value"]) * 100))
            sign = "+" if pct >= 0 else ""
            growth = f'<text x="{x + bar_w//2}" y="{y - 27}" text-anchor="middle" font-size="11" fill="{growth_color}" font-family="SFMono-Regular,Roboto Mono,monospace" font-weight="700">{sign}{pct}%</text>'
        bars += f"""
        <rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{accent}" rx="3" opacity="{opacity:.2f}"/>
        <text x="{x + bar_w//2}" y="{y - 9}" text-anchor="middle" font-size="14" fill="var(--ks-champagne)" font-family="SFMono-Regular,Roboto Mono,monospace" font-weight="700">{r.get("label","")}</text>
        {growth}
        <text x="{x + bar_w//2}" y="{base_y + 22}" text-anchor="middle" font-size="11.5" fill="var(--ks-faint)" font-family="SFMono-Regular,Roboto Mono,monospace">{r.get("year","")}</text>"""
    seen, footnotes = set(), []
    for r in series:
        src, url = r.get("source",""), r.get("sourceUrl","")
        if src and src not in seen:
            seen.add(src)
            footnotes.append(f'<a class="chart-source-link" href="{url}" target="_blank" rel="noopener">{src}</a>' if url
                             else f'<span class="chart-source-text">{src}</span>')
    source_html = ('<div class="chart-sources"><span class="chart-source-label">Sources:</span> ' + " · ".join(footnotes) + '</div>') if footnotes else ""
    caption_html = f'<div class="chart-caption">{caption}</div>' if caption else ""
    return f"""
    <div class="chart-wrap">
      <div class="chart-eyebrow">{eyebrow}</div>
      <svg width="{total_w}" height="{svg_h}" viewBox="0 0 {total_w} {svg_h}" style="overflow:visible;max-width:100%">
        {bars}
        <line x1="{pad}" y1="{base_y + 2}" x2="{total_w - pad}" y2="{base_y + 2}" stroke="var(--ks-rule-strong)" stroke-width="1"/>
      </svg>
      {caption_html}
      {source_html}
    </div>"""


def build_arr_chart(rev_history: list) -> str:
    """Annual revenue trajectory (kinpaku/gold bars)."""
    return build_bar_chart(rev_history, eyebrow="ANNUAL REVENUE ($B)", accent="var(--ks-kinpaku)")


def build_biz_flow(profile: dict, b: dict) -> str:
    """Three-column value chain: Customers (+ what they need) → Platform (modules)
    → Value Delivered (+ the concrete payoff). Driven by an explicit profile['bizFlow']
    object when present, so the diagram explains the business A-to-Z rather than just
    listing names; falls back to a keyword-derived version for older profiles."""
    name = profile.get("name", "")
    flow = profile.get("bizFlow") or {}

    # ── Customers column: each node can carry a "need" sub-line ──
    cust_src = flow.get("customers")
    if cust_src:
        cust_html = "".join(
            f'<div class="biz-node biz-cust"><div class="biz-node-name">{c.get("name","")}</div>'
            + (f'<div class="biz-node-sub">{c.get("need","")}</div>' if c.get("need") else "")
            + '</div>'
            for c in cust_src[:5]
        )
    else:
        cust_nodes = (profile.get("customers") or ["Enterprise Customers"])[:4]
        cust_html = "".join(f'<div class="biz-node biz-cust"><div class="biz-node-name">{c}</div></div>' for c in cust_nodes)

    # ── Platform column: name + modules (what the platform actually is) ──
    plat = flow.get("platform") or {}
    plat_name = plat.get("name") or name
    modules = plat.get("modules")
    if not modules:
        skip = {"vertical saas", "saas", "software", "b2b", "enterprise software", "ai hardware"}
        modules = [v for v in (profile.get("verticals") or []) if v.lower() not in skip][:3] or (profile.get("verticals") or [])[:3]
    mod_html = "".join(f'<div class="biz-mod">{m}</div>' for m in modules)

    # ── Value Delivered column: each node can carry a "detail" sub-line ──
    val_src = flow.get("valueDelivered")
    if val_src:
        out_html = "".join(
            (f'<div class="biz-node biz-out"><div class="biz-node-name">{o.get("label","")}</div>'
             + (f'<div class="biz-node-sub">{o.get("detail","")}</div>' if o.get("detail") else "")
             + '</div>') if isinstance(o, dict) else
            f'<div class="biz-node biz-out"><div class="biz-node-name">{o}</div></div>'
            for o in val_src[:5]
        )
    else:
        biz_text = (profile.get("businessModel","") + " " + (b.get("productModel") or "")).lower()
        output_map = [
            ("defense","Defense Autonomous Systems"), ("autonom","Validated Autonomy Software"),
            ("simulat","Compressed Dev Cycles"), ("cybersec","Threat Detection & Response"),
            ("cloud","Cloud Infrastructure"), ("fintech","Financial Intelligence"),
            ("health","Clinical Decision Support"), ("data","Data & Analytics Platform"),
            ("market","Go-To-Market Acceleration"),
        ]
        outputs = [label for kw, label in output_map if kw in biz_text][:3] or ["Software Products", "Platform APIs", "Enterprise Workflows"]
        out_html = "".join(f'<div class="biz-node biz-out"><div class="biz-node-name">{o}</div></div>' for o in outputs)

    return f"""
    <div class="biz-flow">
      <div class="biz-col">
        <div class="biz-col-label">CUSTOMERS &middot; WHAT THEY NEED</div>
        {cust_html}
      </div>
      <div class="biz-arrow">&#8594;</div>
      <div class="biz-col biz-col-mid">
        <div class="biz-col-label">PLATFORM</div>
        <div class="biz-platform">{plat_name}</div>
        {mod_html}
      </div>
      <div class="biz-arrow">&#8594;</div>
      <div class="biz-col">
        <div class="biz-col-label">VALUE DELIVERED</div>
        {out_html}
      </div>
    </div>"""


def build_funding_timeline(funding_rounds: list) -> str:
    """Flex-card funding timeline — chronological, scrollable, no absolute positioning."""
    if not funding_rounds:
        return ""
    rounds = sorted(funding_rounds, key=lambda r: r.get("date", ""))
    cards = ""
    for r in rounds:
        val  = r.get("postMoneyValuationFormatted") or ""
        amt  = r.get("amountFormatted") or ""
        rnd  = r.get("round") or ""
        dt   = (r.get("date") or "")[:7]
        leads = ", ".join((r.get("leadInvestors") or [])[:2])
        val_html   = f'<div class="tl-val">{val}</div>' if val else ""
        leads_html = f'<div class="tl-leads">{leads}</div>' if leads else ""
        cards += f"""
        <div class="tl-card">
          <div class="tl-round">{rnd}</div>
          <div class="tl-amt">{amt}</div>
          {val_html}
          <div class="tl-date">{dt}</div>
          {leads_html}
        </div>
        <div class="tl-arrow">&#8594;</div>"""
    # Remove last arrow
    cards = cards.rsplit('<div class="tl-arrow">&#8594;</div>', 1)[0]
    return f'<div class="tl-flex">{cards}</div>'


def fetch_brand_colors(website: str, max_colors: int = 5) -> list[str]:
    """
    Fetch the company homepage + any linked CSS, extract hex colors, and return
    only the handful that actually read as brand colors: the dominant saturated
    hue(s) plus a few distinct accents — NOT every incidental hex in the CSS.
    Ranked by frequency weighted by saturation so a vivid logo color outranks a
    frequently-used incidental grey. Falls back to [] on any network error.
    """
    if not website:
        return []
    try:
        url = website if website.startswith("http") else f"https://{website}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", errors="ignore")

        # pull linked CSS hrefs
        css_urls = re.findall(r'href=["\']([^"\']*\.css[^"\']*)["\']', html)
        css_text = html  # inline styles already in HTML
        base = url.rstrip("/")
        for href in css_urls[:5]:
            try:
                css_url = href if href.startswith("http") else base + "/" + href.lstrip("/")
                css_req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0"})
                css_text += urllib.request.urlopen(css_req, timeout=4).read().decode("utf-8", errors="ignore")
            except Exception:
                pass

        # find all hex colors (3- and 6-digit)
        raw = re.findall(r'#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b', css_text)
        # normalise to 6-digit uppercase
        def norm(h: str) -> str:
            return (h[0]*2 + h[1]*2 + h[2]*2).upper() if len(h) == 3 else h.upper()
        normalized = [norm(h) for h in raw]

        # Common CSS-framework default palettes (Bootstrap/Tailwind/etc.) — these
        # show up on countless sites and are NOT brand colors; exclude them.
        FRAMEWORK_DEFAULTS = {
            "007BFF", "6C757D", "28A745", "DC3545", "FFC107", "17A2B8", "6610F2",
            "E83E8C", "FD7E14", "20C997", "343A40", "F8F9FA", "6F42C1", "3B82F6",
            "EF4444", "10B981", "F59E0B", "8B5CF6", "EC4899",
        }
        # filter out near-black, near-white, pure greys, and framework defaults
        def is_interesting(h: str) -> bool:
            if h in FRAMEWORK_DEFAULTS:
                return False
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            lum = 0.299*r + 0.587*g + 0.114*b
            if lum < 18 or lum > 237:          # too dark / too light
                return False
            spread = max(r,g,b) - min(r,g,b)
            return spread > 20                  # must have some chroma

        from collections import Counter
        counts = Counter(h for h in normalized if is_interesting(h))
        if not counts:
            return []

        def saturation(h: str) -> float:
            r, g, b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return (max(r,g,b) - min(r,g,b)) / 255.0

        # Rank by frequency weighted by saturation: a vivid, repeatedly-used color
        # (the brand color) beats an incidental grey that merely appears often.
        scored = sorted(counts.items(), key=lambda kv: kv[1] * (0.4 + saturation(kv[0])), reverse=True)
        candidates = [h for h, _ in scored[:60]]

        # Deduplicate perceptually similar colors so we keep distinct accents only
        selected: list[str] = []
        for c in candidates:
            r1,g1,b1 = int(c[0:2],16), int(c[2:4],16), int(c[4:6],16)
            if any(((r1-int(s[0:2],16))**2 + (g1-int(s[2:4],16))**2 + (b1-int(s[4:6],16))**2) ** 0.5 < 48
                   for s in selected):
                continue
            selected.append(c)
            if len(selected) >= max_colors:
                break
        return ["#" + h for h in selected]
    except Exception:
        return []


def _brand_colors_html(colors: list) -> str:
    if not colors:
        return '<div class="kit-url" style="color:var(--ks-faint);font-size:10px">fetching colors failed — check website URL in profile</div>'
    swatches = "".join(
        f'<div class="kit-swatch-wrap" title="{c}">'
        f'<div class="kit-swatch" style="background:{c}"></div>'
        f'<div class="kit-hex">{c}</div>'
        f'</div>'
        for c in colors
    )
    return f'<div class="kit-swatches">{swatches}</div>'


def build_slide_kit(profile: dict, logo_url: str, brand_colors: list = None) -> str:
    """Brand artifact block for slide building: logo, colors, copy-paste stats."""
    name    = profile.get("name", "")
    ticker  = profile.get("ticker") or ""
    stage   = profile.get("stage", "")
    website = profile.get("website", "")
    last_val = profile.get("lastKnownValuation", "")
    total_raised = profile.get("totalRaised")
    verticals = profile.get("verticals", [])[:3]
    b       = profile.get("brief", {})
    et      = b.get("earningsTakeaways", {})
    metrics = et.get("keyMetrics", {}) or {}
    rev     = metrics.get("revenue", "")
    growth  = metrics.get("revenueGrowth", "")
    bullets = b.get("slideBullets") or []

    # Copy-paste stat strings
    stats = []
    if rev and str(rev).lower() not in ("null","none","not disclosed"):
        stats.append(rev + (" growing " + growth if growth else ""))
    if last_val:
        stats.append("Valued at " + last_val.split(" as of")[0])
    if total_raised:
        stats.append(f"${total_raised:,}M total raised")
    ticker_str = f" ({ticker})" if ticker else ""
    stage_str  = f" · {stage.upper()}" if stage else ""
    header_str = f"{name}{ticker_str}{stage_str}"

    stats_html = "".join(f'<div class="kit-stat">{s}</div>' for s in stats)
    tag_html   = "".join(f'<span class="kit-tag">{v}</span>' for v in verticals)
    logo_html  = f'<img src="{logo_url}" class="kit-logo-lg" alt="{name} logo" onerror="this.style.display=\'none\'">' if logo_url else ""
    bullets_html = "".join(f'<div class="kit-bullet">{clean(bl)}</div>' for bl in bullets[:3]) if bullets else ""
    website_html = f'<a href="{website}" class="kit-link" target="_blank">{website.replace("https://","").rstrip("/")}</a>' if website else ""

    return f"""
    <div class="kit-grid">
      <div class="kit-identity">
        {logo_html}
        <div class="kit-name">{name}</div>
        <div class="kit-sub">{stage_str.strip(" · ")}{" · " if stage_str and last_val else ""}{last_val.split(" as of")[0] if last_val else ""}</div>
        {website_html}
        <div class="kit-tags">{tag_html}</div>
      </div>
      <div class="kit-copy">
        <div class="kit-copy-label">COPY-PASTE STATS</div>
        {stats_html}
        <div class="kit-copy-label" style="margin-top:14px">TOP 3 SLIDE BULLETS</div>
        {bullets_html}
      </div>
      <div class="kit-assets">
        <div class="kit-copy-label">BRAND COLORS</div>
        {_brand_colors_html(brand_colors or [])}
        <div class="kit-copy-label" style="margin-top:14px">BRAND TAGS</div>
        <div class="kit-tags">{tag_html}</div>
      </div>
    </div>"""


# ── HTML generation ───────────────────────────────────────────────────────────

def build_html(profile: dict) -> str:
    b           = profile.get("brief", {})
    name        = profile.get("name", "Unknown")
    ticker      = profile.get("ticker", "")
    date        = b.get("runDate") or profile.get("lastRunDate") or datetime.date.today().isoformat()
    date_fmt    = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y") if date else ""
    website     = profile.get("website", "")
    verticals   = profile.get("verticals", [])
    notes_raw   = profile.get("notes", "")
    biz_model   = profile.get("businessModel", "")
    market_ctx  = profile.get("marketContext", "")
    short_desc  = profile.get("shortDescription", "")
    competitors = profile.get("competitors", [])
    investors   = profile.get("investors", [])
    total_raised= profile.get("totalRaised")
    revenue_str = profile.get("revenue", "")
    growth_str  = profile.get("growth", "")
    funding_rounds = profile.get("fundingRounds", [])
    stage          = profile.get("stage", "")
    last_val       = profile.get("lastKnownValuation", "")
    ipo_read       = profile.get("ipoReadiness", "")
    employee_count = profile.get("employeeCount", "")
    rev_history    = profile.get("revenueHistory") or []

    # Logo URL via Clearbit (kept as fallback; often blocked)
    domain      = website.replace("https://","").replace("http://","").rstrip("/").split("/")[0] if website else ""
    logo_url    = f"https://logo.clearbit.com/{domain}" if domain else ""
    # Brand colors: use stored ones or fetch live
    brand_colors = profile.get("brandColors") or fetch_brand_colors(website)
    detail_level = profile.get("_detail", "brief")   # "brief" or "detailed"
    max_ov_bullets = 0 if detail_level == "detailed" else 9   # overview should explain the business A-to-Z

    # Parse trading line from notes
    trading_line = ""
    for line in profile.get("notes","").split("\n"):
        if line.startswith("TRADING:"):
            trading_line = line.replace("TRADING:", "").strip()

    # ── Earnings ──
    et      = b.get("earningsTakeaways", {})
    metrics = et.get("keyMetrics", {}) or {}

    # ── Stat value/label helpers ──
    METRIC_LABELS = {
        "revenue": "Revenue", "revenueGrowth": "Rev Growth",
        "arr": "ARR", "nrr": "NRR", "rpo": "RPO",
        "grossMargin": "Gross Margin", "grossMarginNonGAAP": "Gross Margin",
        "operatingMargin": "Op Margin", "operatingMarginNonGAAP": "Op Margin",
        "fcfMargin": "FCF Margin", "freeCashFlow": "Free Cash Flow", "fcf": "Free Cash Flow",
        "productRevenue": "Product Rev",
        "aiRevenue": "AI Revenue", "semiconductorRevenue": "Semiconductor Rev",
        "softwareRevenue": "Software Rev", "infrastructureSoftwareRevenue": "Software Rev",
        "epsNonGAAP": "EPS (non-GAAP)", "eps": "EPS",
        "ebitda": "EBITDA", "adjustedEbitda": "Adj. EBITDA",
        "q2Guidance": "Next-Q Guide", "guidance": "Guidance", "backlog": "Backlog",
        "capitalReturns": "Capital Returned", "dividend": "Dividend",
        "customers": "Customers", "customerCount": "Customers",
        "enterprise_customers": "Enterprise Customers",
        "valuation": "Last Valuation", "runRate": "Revenue Run-rate", "arrRunRate": "ARR Run-rate",
        "users": "Registered Users", "payingUsers": "Paying Users",
        "generationsPerDay": "Generations / Day",
        "impressions": "Impressions", "socialImpressions": "Impressions",
    }
    GREEN_KEYS = {"revenueGrowth", "nrr", "grossMargin", "grossMarginNonGAAP",
                  "operatingMargin", "operatingMarginNonGAAP", "fcfMargin", "aiRevenue"}

    def _humanize(k):
        return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', k).replace("_", " ").strip().title()

    def _split_stat(s):
        """Split a stat into (head, sub): a big number up top, small context below.
        Two rules, in order:
          1. 'value (qualifier)'    -> head=value, sub=first clause of qualifier
          2. 'value trailing words' -> head=leading numeric token, sub=the words
        so '4.5M per day' renders as a big 4.5M over a small 'per day' instead of a
        bold blob that wraps to two lines. Pure values and non-numeric text stay whole."""
        s = str(s).strip()
        m = re.match(r'^\s*([^(]+?)\s*\(([^)]+)\)', s)
        if m:
            return m.group(1).strip(), m.group(2).strip().split(",")[0].strip()
        # Peel a leading value token (optional ~/$/comparator + number + unit) off
        # the rest of the words, e.g. '4.5M per day', '~$300M est.', '29.5% YoY'.
        m = re.match(r'^\s*([~<>≈]?\s*\$?\s*\d[\d.,]*\s?(?:[KMBTkmbt]|bn|mn|x|%|bps|pp)?\+?)\s+(\S.*)$', s)
        if m and m.group(2):
            return m.group(1).strip(), m.group(2).strip()
        return s, ""

    # ── Financials metric cards (value + sub, never overflowing) ──
    metrics_cards_html = ""
    for k, v in metrics.items():
        if _is_empty(v):
            continue
        lbl = METRIC_LABELS.get(k, _humanize(k))
        head, sub = _split_stat(v)
        if _is_empty(head):                         # e.g. "Not disclosed (private)" -> drop
            continue
        cls = "metric-value green" if k in GREEN_KEYS else "metric-value"
        if len(str(head)) > 7:                      # long head -> shrink, don't wrap
            cls += " long"
        sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ""
        metrics_cards_html += (f'<div class="metric-card"><div class="metric-label">{lbl}</div>'
                               f'<div class="{cls}">{head}</div>{sub_html}</div>')

    # ── Hero stats bar — live trading multiples + headline KPIs, all SHORT ──
    # Institutional: stat values read navy (set in CSS); keep map navy for any inline use.
    color_map = {"gold": "var(--ks-kinpaku)", "muted": "var(--ks-kinpaku)", "faint": "var(--ks-faint)"}
    hero_items = []   # (label, value, sub, color)
    ticker_sym = (profile.get("ticker") or "").strip()

    # Live, dated trading multiples for the subject (public tickers only)
    if ticker_sym and re.fullmatch(r"[A-Za-z.\-]{1,6}", ticker_sym):
        try:
            from data_agent import live_quote
            q = live_quote(ticker_sym)
        except Exception:
            q = {}
        if q and "error" not in q:
            asof = q.get("priceAsOf") or ""
            asof_sub = f"{asof} close" if asof else ""
            if q.get("marketCap"):
                hero_items.append(("Market Cap", q["marketCap"], asof_sub, "gold"))
            if q.get("evRevenueLTM"):
                hero_items.append(("EV / Revenue", q["evRevenueLTM"], (f"LTM · {asof} close" if asof else "LTM"), "gold"))
            if q.get("closePrice") is not None:
                hero_items.append(("Share Price", f"${q['closePrice']:,.2f}", asof_sub, "muted"))

    # Headline operating KPIs from the latest quarter (curated order, short values)
    HERO_KEYS = [
        ("valuation", "Last Valuation"), ("runRate", "Revenue Run-rate"), ("arrRunRate", "ARR Run-rate"),
        ("revenue", "Revenue"), ("arr", "ARR"), ("aiRevenue", "AI Revenue"),
        ("revenueGrowth", "Rev Growth"), ("customers", "Customers"),
        ("users", "Registered Users"), ("payingUsers", "Paying Users"),
        ("nrr", "NRR"), ("grossMarginNonGAAP", "Gross Margin"), ("grossMargin", "Gross Margin"),
        ("freeCashFlow", "Free Cash Flow"), ("rpo", "RPO"),
    ]
    seen_lbls = {l for l, _, _, _ in hero_items}
    for key, lbl in HERO_KEYS:
        v = metrics.get(key, "")
        if _is_empty(v) or lbl in seen_lbls:
            continue
        head, sub = _split_stat(v)
        if _is_empty(head):                         # e.g. "Not disclosed (private)" -> drop
            continue
        clr = "gold" if key in ("revenue", "arr", "aiRevenue") else "muted"
        hero_items.append((lbl, head, sub, clr))
        seen_lbls.add(lbl)

    # Private-company / fallback stats
    if last_val:
        _lv_head = last_val.split(" as of")[0].split(" (")[0].strip()
        if not _is_empty(_lv_head):
            hero_items.append(("Valuation", _lv_head,
                               last_val.split("as of")[-1].strip() if "as of" in last_val else "", "gold"))
    if total_raised:
        hero_items.append(("Total Raised", f"${total_raised:,}M", "", "muted"))
    if employee_count and not _is_empty(employee_count) and "Employees" not in seen_lbls:
        head, sub = _split_stat(employee_count)
        hero_items.append(("Employees", head.replace(" worldwide", ""), sub, "faint"))
    # NOTE: stage is intentionally NOT a hero card — it already shows as a header
    # badge, and a lone "Stage" stat stretched into its own full-width row.

    hero_cards = ""
    for label, val, sub, clr in hero_items[:8]:
        sub_cls = " pos" if sub and sub.strip().startswith("+") else ""
        sub_html = f'<div class="hero-sub{sub_cls}">{sub}</div>' if sub else ""
        val_cls = "hero-value long" if len(str(val)) > 7 else "hero-value"   # shrink, don't wrap
        hero_cards += (f'<div class="hero-card"><div class="hero-label">{label}</div>'
                       f'<div class="{val_cls}" style="color:{color_map.get(clr,"var(--ks-champagne)")}">{val}</div>{sub_html}</div>')
    hero_html = f'<div class="hero-stats">{hero_cards}</div>' if hero_cards else ""

    # ── Visuals ──
    arr_chart_html     = build_arr_chart(rev_history)
    ai_hist            = profile.get("aiRevenueHistory") or []
    ai_chart_html      = build_bar_chart(
        ai_hist, eyebrow="AI SEMICONDUCTOR REVENUE ($B)", accent="var(--ks-accent)",
        growth_color="var(--ks-patina)",
        caption="Forward quarters marked E reflect company guidance, not reported actuals.")
    charts_html        = (f'<div class="chart-row">{arr_chart_html}{ai_chart_html}</div>'
                          if (arr_chart_html and ai_chart_html) else (arr_chart_html or ai_chart_html))
    biz_flow_html      = build_biz_flow(profile, b)
    funding_tl_html    = build_funding_timeline(funding_rounds)
    slide_kit_html     = build_slide_kit(profile, logo_url, brand_colors)

    # ── Comps table ──
    # Private peer sets carry "valuation"/"lastRaise" (no market multiples); public
    # sets carry tickers we re-pull live for dated EV/Rev. Pick the right table.
    # House rules: every numeric cell is a SINGLE clean token (units live in the
    # column header, the shared close date lives once in the caption), placeholders
    # are blanked, and any column empty for every row is dropped entirely.
    raw_comps_in = b.get("comps") or []
    is_private_comps = any(c.get("valuation") for c in raw_comps_in)
    comps_html = ""

    def _cell(v):
        return "" if _is_empty(v) else str(v).strip()

    def _amt_split(s):
        """'$315M Series E (Feb 2026)' -> ('$315M', 'Series E · Feb 2026')."""
        s = str(s).strip()
        m = re.match(r'^(\$?\s*[\d.,]+\s?[KMBT]?\+?)\s+(\S.*)$', s)
        if m:
            sub = m.group(2).strip().strip("()").replace(") (", " · ")
            return m.group(1).strip(), sub
        return s, ""

    if is_private_comps:
        norm = [{
            "name": c.get("name",""),
            "type": _cell(c.get("type","")),
            "val":  _cell(c.get("valuation","")),
            "raise": _cell(c.get("lastRaise","")),
            "note": _cell(c.get("note","")),
            "sourceUrl": c.get("sourceUrl",""),
            "is_subject": c.get("type","").strip().lower() == "subject",
        } for c in raw_comps_in]
        cols = {k: any(r[k] for r in norm) for k in ("type","val","raise","note")}
        head = '<th class="comp-name-col">Company</th>'
        if cols["type"]:  head += '<th>Category</th>'
        if cols["val"]:   head += '<th class="right">Last Valuation</th>'
        if cols["raise"]: head += '<th class="right">Last Raise</th>'
        if cols["note"]:  head += '<th>Note</th>'
        prows = ""
        for r in norm:
            row_cls = ' class="subj"' if r["is_subject"] else ""
            val_cell = (f'<a class="comp-source-link" href="{r["sourceUrl"]}" target="_blank" rel="noopener">{r["val"]}</a>'
                        if r["sourceUrl"] and r["val"] else r["val"])
            amt, amt_sub = _amt_split(r["raise"])
            raise_cell = amt + (f'<div class="comp-sub">{amt_sub}</div>' if amt_sub else "")
            cells = f'<td class="comp-name">{r["name"]}</td>'
            if cols["type"]:  cells += f'<td class="comp-type-cell">{r["type"]}</td>'
            if cols["val"]:   cells += f'<td class="mono right comp-val">{val_cell}</td>'
            if cols["raise"]: cells += f'<td class="mono right comp-raise">{raise_cell}</td>'
            if cols["note"]:  cells += f'<td class="note-cell">{r["note"]}</td>'
            prows += f"<tr{row_cls}>{cells}</tr>"
        comps_source_html = ('<div class="chart-sources"><span class="chart-source-label">Sources:</span> '
            'Private valuations and rounds from the cited reporting (TechCrunch, Bloomberg, CNBC, Sacra, PitchBook). '
            'These are last-round marks, not market prices, and the dates differ by company.</div>') if prows else ""
        comps_html = f"""
    <table class="comps-table comps-private">
      <thead><tr>{head}</tr></thead>
      <tbody>{prows}</tbody>
    </table>{comps_source_html}""" if prows else ""
    else:
        raw_comps = _enrich_comps_live(raw_comps_in)
        norm = []
        live_asof_dates = set()
        for c in raw_comps:
            as_of = (c.get("asOf","") or "").replace("Live — ","").strip()
            if as_of:
                live_asof_dates.add(as_of)
            ev = re.sub(r'\s*LTM$', '', _cell(c.get("evRevenue","")))      # header says (LTM)
            rg = re.sub(r'\s*YoY$', '', _cell(c.get("revenueGrowth","")))  # header says (YoY)
            norm.append({
                "name": c.get("name",""),
                "ticker": _cell(c.get("ticker","")),
                "type": _cell(c.get("type","")),
                "ev": ev, "rg": rg, "gm": _cell(c.get("grossMargin","")),
                "note": _cell(c.get("note","")),
                "sourceUrl": c.get("sourceUrl",""),
                "is_subject": c.get("type","").strip().lower() == "subject",
            })
        cols = {k: any(r[k] for r in norm) for k in ("ticker","type","ev","rg","gm","note")}
        head = '<th class="comp-name-col">Company</th>'
        if cols["ticker"]: head += '<th>Ticker</th>'
        if cols["type"]:   head += '<th>Type</th>'
        if cols["ev"]:     head += '<th class="right">EV / Rev<span class="th-unit">LTM</span></th>'
        if cols["rg"]:     head += '<th class="right">Rev Growth<span class="th-unit">YoY</span></th>'
        if cols["gm"]:     head += '<th class="right">Gross Margin</th>'
        if cols["note"]:   head += '<th>Note</th>'
        comps_rows = ""
        for r in norm:
            row_cls = ' class="subj"' if r["is_subject"] else ""
            tkr_cell = (f'<a class="comp-source-link" href="{r["sourceUrl"]}" target="_blank" rel="noopener">{r["ticker"]}</a>'
                        if r["sourceUrl"] and r["ticker"] else r["ticker"])
            cells = f'<td class="comp-name">{r["name"]}</td>'
            if cols["ticker"]: cells += f'<td class="mono comp-ticker">{tkr_cell}</td>'
            if cols["type"]:   cells += f'<td class="comp-type-cell">{r["type"]}</td>'
            if cols["ev"]:     cells += f'<td class="mono right comp-ev">{r["ev"]}</td>'
            if cols["rg"]:     cells += f'<td class="mono right">{r["rg"]}</td>'
            if cols["gm"]:     cells += f'<td class="mono right">{r["gm"]}</td>'
            if cols["note"]:   cells += f'<td class="note-cell">{r["note"]}</td>'
            comps_rows += f"<tr{row_cls}>{cells}</tr>"
        comps_source_html = ""
        if comps_rows:
            if len(live_asof_dates) == 1:
                asof_str = f"as of the {next(iter(live_asof_dates))} market close"
            elif len(live_asof_dates) > 1:
                asof_str = f"as of last close ({', '.join(sorted(live_asof_dates))}; dates differ, do not compare at face value)"
            else:
                asof_str = ""
            if live_asof_dates:
                caption = ("Public-ticker multiples pulled live from "
                           '<a class="chart-source-link" href="https://finance.yahoo.com" target="_blank" rel="noopener">yfinance / Yahoo Finance</a>, '
                           f"{asof_str}; EV/Rev recomputed from last close × shares + net debt.")
            else:
                caption = "Private comps: multiples are estimates from cited research sources, not market-priced."
            comps_source_html = (
                '<div class="chart-sources"><span class="chart-source-label">Sources:</span> '
                f'{caption}</div>')
        comps_html = f"""
    <table class="comps-table">
      <thead><tr>{head}</tr></thead>
      <tbody>{comps_rows}</tbody>
    </table>{comps_source_html}""" if comps_rows else ""

    # ── Risks ──  Only bold a label when there's a genuine short "Label: body";
    # otherwise render the whole risk as plain text. (The old split(':') echoed the
    # entire line twice when a risk had no colon, e.g. "…remain soft.: …remain soft.")
    risks = b.get("keyRisks") or []
    risks_items_html = ""
    for r in risks:
        rc = clean(r)
        head, sep, tail = rc.partition(":")
        if sep and tail.strip() and len(head) <= 40 and "." not in head:
            risks_items_html += f"<li><span class='risk-label'>{head.strip()}:</span> {tail.strip()}</li>"
        else:
            risks_items_html += f"<li>{rc}</li>"
    risks_section_html = (
        f'<div class="section" id="risks"><div class="sec-label">Key Risks &amp; Debates</div>'
        f'<ul class="risk-list">{risks_items_html}</ul></div>'
    ) if risks else ""

    # ── Slide bullets + diligence ──
    bullets = b.get("slideBullets") or []
    dqs     = b.get("diligenceQuestions") or []

    # ── Investors chips ──
    investors_html = ""
    if investors:
        investors_html = "<div class='chip-list'>" + "".join(
            f"<span class='chip'>{i}</span>" for i in investors) + "</div>"

    # ── Earn bullets (2-sentence cap per point) ──
    def first_two_sentences(text: str) -> str:
        """Return first 2 sentences of a paragraph."""
        text = clean(text)
        parts = re.split(r'(?<=[a-z0-9])\.\s+(?=[A-Z\$])', text)
        return ". ".join(p.strip().rstrip(".") for p in parts[:2]) + "."

    earn_bullets = []
    if et:
        if et.get("aiCommentary"):
            earn_bullets.append(f"<strong>AI / Product:</strong> {first_two_sentences(et['aiCommentary'])}")
        if et.get("demandCommentary"):
            earn_bullets.append(f"<strong>Demand:</strong> {first_two_sentences(et['demandCommentary'])}")
        if et.get("analystTake"):
            earn_bullets.append(f"<strong>Analyst take:</strong> {first_two_sentences(et['analystTake'])}")

    # ── SEC primary filings (live from EDGAR, no key) ──
    filings_html = ""
    if ticker_sym and re.fullmatch(r"[A-Za-z.\-]{1,6}", ticker_sym):
        try:
            from data_agent import get_sec_filings
            secf = get_sec_filings(ticker_sym)
        except Exception:
            secf = {}
        rows = ""
        for fl in (secf.get("filings") or []):
            rows += (f'<a class="filing-row" href="{fl.get("url","")}" target="_blank" rel="noopener">'
                     f'<span class="filing-form">{fl.get("form","")}</span>'
                     f'<span class="filing-meta">filed {fl.get("filingDate","")}'
                     + (f' &nbsp;·&nbsp; period {fl.get("reportDate","")}' if fl.get("reportDate") else '')
                     + '</span><span class="filing-go">View on EDGAR &rsaquo;</span></a>')
        if rows:
            filings_html = (
                f'<div class="filings-wrap">{rows}</div>'
                f'<div class="chart-sources"><span class="chart-source-label">Source:</span> '
                f'<a class="chart-source-link" href="{secf.get("sourceUrl","")}" target="_blank" rel="noopener">SEC EDGAR</a>'
                f' &nbsp;·&nbsp; CIK {secf.get("cik","")} &nbsp;·&nbsp; primary filings of record.</div>')
    filings_section_html = (
        f'<div class="section" id="filings"><div class="sec-label">Primary Filings (SEC EDGAR)</div>{filings_html}</div>'
    ) if filings_html else ""

    # ── "Understand the business" explainer: plain -> technical -> simple ──
    # Each card renders as bullets. Values may be a list (deliberate bullets) or a
    # paragraph string (auto-split into sentence bullets) for back-compat.
    explainer = profile.get("explainer") or {}
    explainer_html = ""
    if explainer:
        def _explain_body(val):
            if isinstance(val, list):
                items = [clean(str(x)).rstrip(".") for x in val if str(x).strip()]
            else:
                t = clean(str(val))
                items = [s.strip().rstrip(".") for s in re.split(r'(?<=[a-z0-9\)%])\.\s+(?=[A-Z])', t) if len(s.strip()) > 12]
            return ("<ul class='explain-list'>" + "".join(f"<li>{x}.</li>" for x in items) + "</ul>") if items else ""
        levels = [("Plain English", explainer.get("plain", "")),
                  ("The technical version", explainer.get("technical", "")),
                  ("Explained simply", explainer.get("simple", ""))]
        cards = "".join(
            f'<div class="explain-card explain-{i}"><div class="explain-label">{lbl}</div>{_explain_body(txt)}</div>'
            for i, (lbl, txt) in enumerate(levels) if txt)
        explainer_html = f'<div class="explain-grid">{cards}</div>' if cards else ""

    # ── Differentiation vs peers (how the subject company is different) ──
    diff = profile.get("differentiation") or []
    differentiation_html = ""
    if diff:
        diff_name = (profile.get("name", "") or "").replace(" Inc.", "").replace(" AI", "").split(",")[0].strip() or "the company"
        drows = "".join(
            f'<tr><td class="diff-player">{clean(d.get("player",""))}</td>'
            f'<td class="diff-make">{clean(d.get("theyMake",""))}</td>'
            f'<td class="diff-edge">{clean(d.get("howDiffers") or d.get("avgoEdge",""))}</td></tr>'
            for d in diff)
        differentiation_html = (
            f'<div class="section" id="diff"><div class="sec-label">How {diff_name} Is Different</div>'
            f'<table class="diff-table"><thead><tr>'
            f'<th class="diff-player">Player</th><th class="diff-make">What they make</th>'
            f'<th class="diff-edge">How {diff_name} differs</th></tr></thead>'
            f'<tbody>{drows}</tbody></table></div>')

    # ── TOC ──
    toc_items = []
    if b.get("businessOverview") or short_desc: toc_items.append(("overview",  "Overview"))
    if differentiation_html:                    toc_items.append(("diff",      "Differs"))
    if profile.get("leadership"):               toc_items.append(("leadership","Leadership"))
    if b.get("productModel"):                   toc_items.append(("product",   "Revenue Model"))
    if b.get("recentNews"):                     toc_items.append(("news",      "News"))
    if et:                                      toc_items.append(("earnings",  "Financials"))
    if rev_history:                             toc_items.append(("growth",    "Growth"))
    if risks:                                   toc_items.append(("risks",     "Risks"))
    if b.get("comps") or competitors:           toc_items.append(("comps",     "Comps"))
    if filings_section_html:                     toc_items.append(("filings",   "Filings"))
    if funding_rounds or total_raised or stage: toc_items.append(("funding",   "Funding"))
    if investors:                               toc_items.append(("investors", "Investors"))
    if bullets:                                 toc_items.append(("bullets",   "Bullets"))
    if dqs:                                     toc_items.append(("diligence", "Diligence"))
    toc_items.append(("slidekit", "Slide Kit"))
    toc_html = " ".join(f'<a href="#{sid}" class="toc-link">{label}</a>' for sid, label in toc_items)

    # ── Leadership section ──
    leadership_html = ""
    leadership = profile.get("leadership") or []
    if leadership:
        cards = ""
        for exc in leadership:
            ename    = clean(exc.get("name",""))
            title    = clean(exc.get("title",""))
            bg       = clean(exc.get("background",""))
            since    = exc.get("since","")
            linkedin = exc.get("linkedin","")
            name_html = (f'<a class="exec-linkedin" href="{linkedin}" target="_blank" rel="noopener">{ename}</a>'
                         if linkedin else f'<span class="exec-name">{ename}</span>')
            since_html = f' <span class="exec-since">since {since}</span>' if since else ""
            bg_html = f'<div class="exec-bg">{bg}</div>' if bg else ""
            cards += (f'<div class="exec-card">'
                      f'<div class="exec-title">{title}{since_html}</div>'
                      f'<div class="exec-name-row">{name_html}</div>'
                      f'{bg_html}'
                      f'</div>')
        leadership_html = f'<div class="section" id="leadership"><div class="sec-label">Executive Leadership</div><div class="exec-grid">{cards}</div></div>'

    # ── Pre-compute complex inline sections (avoid escaped quotes in f-string) ──
    news_items_html = ""
    for n in (b.get("recentNews") or []):
        # Build source list — support both `sources: [{name, url}]` array and legacy singular fields
        raw_sources = n.get("sources") or []
        if not raw_sources:
            # fall back to singular source/sourceUrl
            if n.get("source"):
                raw_sources = [{"name": n["source"], "url": n.get("sourceUrl","")}]
        src_links = []
        for s in raw_sources:
            sname = s.get("name") or s.get("source","")
            surl  = s.get("url") or s.get("sourceUrl","")
            if surl:
                src_links.append(f'<a class="news-source-link" href="{surl}" target="_blank" rel="noopener">{sname}</a>')
            elif sname:
                src_links.append(f'<span class="news-source-link news-source-nolink">{sname}</span>')
        if src_links:
            label_word = "Sources" if len(src_links) > 1 else "Source"
            joined = ' <span class="news-source-sep">·</span> '.join(src_links)
            source_row = f'<div class="news-source-row"><span class="news-source-label">{label_word}:</span> {joined}</div>'
        else:
            source_row = ""
        news_items_html += (
            f'<div class="news-item">'
            f'<div class="news-row"><span class="news-date">{n.get("date","")}</span>'
            f'<span class="news-headline">{clean(n.get("headline",""))}</span></div>'
            f'{source_row}'
            f'<div class="news-why">{clean(n.get("whyItMatters",""))}</div>'
            f'</div>'
        )
    news_section_html = (
        f'<div class="section" id="news"><div class="sec-label">Recent News</div>'
        f'{news_items_html}</div>'
    ) if news_items_html else ""

    earnings_section_html = ""
    if et:
        earn_ul = ('<ul class="earn-bullets">' + "".join(f"<li>{b_}</li>" for b_ in earn_bullets) + "</ul>") if earn_bullets else ""
        q_label = clean(et.get("quarter",""))
        q_date  = et.get("reportDate","")
        q_meta  = " &middot; ".join(x for x in (q_label, q_date) if x)
        meta_row = f'<div class="sec-meta">{q_meta}</div>' if q_meta else ""
        earnings_section_html = (
            f'<div class="section" id="earnings">'
            f'<div class="sec-label">Financials &amp; Key Metrics</div>{meta_row}'
            f'<div class="metrics-grid">{metrics_cards_html}</div>'
            f'{earn_ul}'
            f'</div>'
        )

    funding_meta = f'<div class="meta-note">Total raised: <strong>${total_raised:,}M</strong></div>' if total_raised else ""
    funding_section_html = (
        f'<div class="section" id="funding"><div class="sec-label">Funding History</div>'
        f'<div class="tl-scroll">{funding_tl_html}</div>{funding_meta}</div>'
    ) if funding_rounds else ""

    competitors_section_html = ""
    if competitors and not b.get("comps"):
        chips = "".join(f'<span class="chip">{c}</span>' for c in competitors)
        competitors_section_html = (
            f'<div class="section" id="comps"><div class="sec-label">Competitors</div>'
            f'<div class="chip-list">{chips}</div></div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} · Atlas Research Brief</title>
<link href="https://fonts.googleapis.com/css2?family=Alumni+Sans+Pinstripe&family=Albert+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  /* Institutional (light) design tokens: sell-side research note */
  :root {{
    --ks-lacquer:      #ffffff;            /* paper */
    --ks-lacquer-deep: #ffffff;            /* header */
    --ks-raised:       #f7f9fb;            /* card / band */
    --ks-graphite:     #f1f4f8;            /* stat strip / toc */
    --ks-graphite-2:   #eef1f6;            /* module fill */
    --ks-kinpaku:      #13315c;            /* navy: primary structural accent */
    --ks-kinpaku-pale: #1f4d86;            /* navy-soft (links / ticker) */
    --ks-kinpaku-rich: #102a4d;
    --ks-kinpaku-deep: #0c2140;
    --ks-accent:       #b3122b;            /* crimson: section eyebrows + wordmark */
    --ks-patina:       #0a7d4d;            /* positive green */
    --ks-vermilion:    #b3122b;            /* crimson (draft / risk) */
    --ks-champagne:    #15181f;            /* headings ink */
    --ks-body:         #2a2f37;            /* body */
    --ks-muted:        #3d434f;
    --ks-faint:        #727a89;
    --ks-rule:         #dce0e7;            /* hairline */
    --ks-rule-strong:  #c2c8d2;
    --ks-serif:        Georgia, "Iowan Old Style", "Times New Roman", serif;
    --ks-ease:         cubic-bezier(0.2, 0.8, 0.2, 1);
  }}

  /* ── Base ── */
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: "Albert Sans", "Avenir Next", "Helvetica Neue", Arial, system-ui, sans-serif;
         background: var(--ks-lacquer); color: var(--ks-body); font-size: 16.5px; line-height: 1.65; }}
  a {{ color: inherit; text-decoration: none; }}
  p {{ color: var(--ks-body); line-height: 1.75; margin-bottom: 6px; }}
  strong {{ color: var(--ks-champagne); }}
  .mono {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .right {{ text-align: right; }}

  .wrapper {{ width: 100%; max-width: 1400px; margin: 0 auto; background: var(--ks-lacquer);
              border: 1px solid var(--ks-rule); }}

  /* ── Header ── */
  .header {{ background: var(--ks-lacquer-deep); padding: 26px 40px 20px;
             border-bottom: 2px solid var(--ks-kinpaku); }}
  .header-top {{ display: flex; align-items: center; gap: 18px; margin-bottom: 10px; }}
  .company-logo {{ width: 44px; height: 44px; border-radius: 8px; object-fit: contain;
                   background: var(--ks-raised); padding: 4px;
                   border: 1px solid var(--ks-rule); flex-shrink: 0; }}
  .header-name {{ flex: 1; }}
  .company-name {{ font-family: var(--ks-serif);
                   font-size: clamp(1.9rem, 3.4vw, 2.5rem); font-weight: 700;
                   letter-spacing: -0.01em; line-height: 1.04; color: var(--ks-champagne);
                   display: block; }}
  .header-badges {{ display: flex; align-items: center; gap: 7px; margin-top: 6px; flex-wrap: wrap; }}
  .ticker-badge {{ background: transparent; color: var(--ks-kinpaku);
                   font-family: "SFMono-Regular", "Roboto Mono", monospace;
                   font-size: 10.5px; font-weight: 700; padding: 0; border-radius: 0;
                   letter-spacing: 0.16em; text-transform: uppercase; }}
  .stage-badge {{ background: var(--ks-raised); border: 1px solid var(--ks-rule);
                  color: var(--ks-muted); font-size: 10px; font-weight: 600; padding: 2px 8px;
                  border-radius: 2px; letter-spacing: 0.12em;
                  font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .draft-badge {{ background: var(--ks-kinpaku); border: 1px solid var(--ks-kinpaku);
                  color: #ffffff; font-size: 10px; font-weight: 700; padding: 2px 9px;
                  border-radius: 2px; letter-spacing: 0.15em;
                  font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .header-meta {{ font-size: 11.5px; color: var(--ks-faint); }}
  .header-meta a {{ color: var(--ks-kinpaku-pale); }}
  .verticals {{ margin-top: 10px; display: flex; flex-wrap: wrap; gap: 6px; }}
  .vertical-tag {{ background: var(--ks-graphite); border: 1px solid var(--ks-rule);
                   color: var(--ks-muted); font-size: 10px; padding: 2px 9px; border-radius: 3px;
                   font-family: "SFMono-Regular", "Roboto Mono", monospace; letter-spacing: 0.06em; }}
  .trading-bar {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); border-radius: 3px;
                  padding: 9px 14px; margin-top: 14px; font-size: 11px; color: var(--ks-faint);
                  font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .trading-bar strong {{ color: var(--ks-champagne); margin-right: 4px; }}

  /* ── Hero stats bar ── */
  .hero-stats {{ display: flex; flex-wrap: wrap; background: var(--ks-graphite);
                 border-bottom: 1px solid var(--ks-rule); }}
  /* fixed 20% basis -> exactly 5 per row; a partial last row stays left-aligned
     under the columns instead of stretching to fill the width. */
  .hero-card {{ flex: 0 0 20%; min-width: 0; padding: 13px 18px;
                border-right: 1px solid var(--ks-rule); }}
  .hero-card:nth-child(5n) {{ border-right: none; }}
  .hero-card:last-child {{ border-right: none; }}
  .hero-label {{ font-size: 9.5px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.13em;
                 color: var(--ks-faint); margin-bottom: 6px; white-space: nowrap;
                 font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  /* big number stays on ONE line; a long head shrinks to fit rather than wrapping */
  .hero-value {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-size: 1.5rem; font-weight: 700;
                 line-height: 1.1; color: var(--ks-kinpaku); white-space: nowrap; }}
  .hero-value.long {{ font-size: 1.1rem; letter-spacing: -0.01em; }}
  .hero-sub {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-size: 10.5px;
               color: var(--ks-faint); margin-top: 4px; line-height: 1.3; }}
  .hero-sub.pos {{ color: var(--ks-patina); }}
  /* narrow screens: let the 5-col strip reflow (print/desktop keep 5 across) */
  @media (max-width: 820px) {{ .hero-card {{ flex-basis: 33.333%; }} }}
  @media (max-width: 520px) {{ .hero-card {{ flex-basis: 50%; }} }}

  /* ── TOC ── */
  .toc {{ background: var(--ks-graphite); border-bottom: 1px solid var(--ks-rule-strong);
          padding: 9px 40px; display: flex; flex-wrap: wrap; gap: 5px;
          position: sticky; top: 0; z-index: 10; }}
  .toc-link {{ font-size: 10px; font-weight: 600; color: var(--ks-faint); padding: 3px 10px;
               border-radius: 20px; border: 1px solid var(--ks-rule); background: transparent;
               transition: background 150ms var(--ks-ease), color 150ms var(--ks-ease);
               white-space: nowrap; font-family: "SFMono-Regular", "Roboto Mono", monospace;
               letter-spacing: 0.04em; }}
  .toc-link:hover {{ background: var(--ks-kinpaku); color: var(--ks-lacquer-deep); border-color: var(--ks-kinpaku); }}

  /* ── Sections ── */
  .section {{ border-bottom: 1px solid var(--ks-rule); padding: 24px 40px; scroll-margin-top: 48px; }}
  .section:last-of-type {{ border-bottom: none; }}
  .sec-label {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-size: 10px; font-weight: 700;
                letter-spacing: 0.15em; text-transform: uppercase; color: var(--ks-accent);
                margin-bottom: 15px; padding-bottom: 7px; border-bottom: 1px solid var(--ks-rule); }}
  /* normal-weight metadata line under a section label (quarter, as-of, captions) —
     keeps the eyebrow itself short and uncluttered instead of wrapping inline */
  .sec-meta {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-size: 10.5px;
               color: var(--ks-faint); margin: -9px 0 14px; letter-spacing: 0.03em; line-height: 1.4; }}

  /* ── Two-col layout (overview) ── */
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px; align-items: start; }}
  @media (max-width: 760px) {{ .two-col {{ grid-template-columns: 1fr; }} }}
  .diagram-caption {{ font-size: 11px; color: var(--ks-faint); margin-bottom: 10px; line-height: 1.4;
                      font-family: "SFMono-Regular", "Roboto Mono", monospace; }}

  /* ── "Understand the business" explainer (plain / technical / simple) ── */
  .explain-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 24px; }}
  @media (max-width: 820px) {{ .explain-grid {{ grid-template-columns: 1fr; }} }}
  .explain-card {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); border-radius: 5px;
                   padding: 15px 16px; border-top: 3px solid var(--ks-kinpaku); }}
  .explain-1 {{ border-top-color: var(--ks-accent); }}
  .explain-2 {{ border-top-color: var(--ks-patina); }}
  .explain-label {{ font-size: 10px; font-weight: 700; letter-spacing: 0.13em; text-transform: uppercase;
                    color: var(--ks-kinpaku); margin-bottom: 9px;
                    font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .explain-1 .explain-label {{ color: var(--ks-accent); }}
  .explain-2 .explain-label {{ color: var(--ks-patina); }}
  .explain-text {{ font-size: 14px; line-height: 1.6; color: var(--ks-body); }}
  .explain-list {{ list-style: none; padding: 0; margin: 0; }}
  .explain-list li {{ position: relative; padding: 5px 0 5px 16px; font-size: 14px; line-height: 1.5;
                      color: var(--ks-body); }}
  .explain-list li:before {{ content: ""; position: absolute; left: 2px; top: 10px; width: 5px; height: 5px;
                             border-radius: 50%; background: var(--ks-kinpaku); }}
  .explain-1 .explain-list li:before {{ background: var(--ks-accent); }}
  .explain-2 .explain-list li:before {{ background: var(--ks-patina); }}

  /* ── Differentiation table ── */
  .diff-table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  .diff-table th {{ text-align: left; font-size: 9px; font-weight: 700; letter-spacing: 0.1em;
                    text-transform: uppercase; color: var(--ks-faint); padding: 0 14px 8px 0;
                    border-bottom: 1.5px solid var(--ks-kinpaku);
                    font-family: "SFMono-Regular", "Roboto Mono", monospace; vertical-align: bottom; }}
  .diff-table td {{ padding: 11px 14px 11px 0; border-bottom: 1px solid var(--ks-rule);
                    vertical-align: top; color: var(--ks-body); line-height: 1.55; }}
  .diff-table tr:last-child td {{ border-bottom: none; }}
  .diff-table .diff-player {{ font-weight: 700; color: var(--ks-champagne); width: 17%; white-space: nowrap; }}
  .diff-table .diff-make {{ color: var(--ks-muted); width: 30%; }}
  .diff-table .diff-edge {{ color: var(--ks-body); }}
  @media (max-width: 680px) {{ .diff-table, .diff-table thead, .diff-table tbody, .diff-table tr, .diff-table td {{ display: block; width: auto; }}
    .diff-table thead {{ display: none; }} .diff-table .diff-player {{ white-space: normal; padding-top: 12px; }} }}

  /* ── Body bullet list ── */
  .body-list {{ list-style: none; padding: 0; margin: 0; }}
  .body-list li {{ padding: 9px 0 9px 18px; position: relative; color: var(--ks-body);
                   font-size: 15.5px; line-height: 1.6; border-bottom: 1px solid var(--ks-rule); }}
  .body-list li:last-child {{ border-bottom: none; }}
  .body-list li:before {{ content: ""; position: absolute; left: 2px; top: 14px;
                          width: 5px; height: 5px; border-radius: 50%; background: var(--ks-kinpaku); }}

  /* ── Business flow diagram ── */
  .biz-flow {{ display: flex; align-items: stretch; gap: 0; margin: 6px 0; }}
  .biz-col {{ display: flex; flex-direction: column; gap: 7px; flex: 1; min-width: 0; }}
  .biz-col-mid {{ flex: 1.05; }}
  .biz-col-label {{ font-size: 9px; text-transform: uppercase; letter-spacing: 0.14em;
                    color: var(--ks-faint); margin-bottom: 3px; line-height: 1.3;
                    font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .biz-node {{ padding: 9px 11px; border-radius: 4px; }}
  .biz-node-name {{ font-size: 12.5px; font-weight: 600; line-height: 1.25; }}
  .biz-node-sub {{ font-size: 10.5px; font-weight: 400; line-height: 1.3; margin-top: 2px;
                   color: var(--ks-muted); }}
  .biz-cust {{ background: rgba(19,49,92,0.05); border: 1px solid rgba(19,49,92,0.18);
               color: var(--ks-champagne); }}
  .biz-out  {{ background: rgba(10,125,77,0.06); border: 1px solid rgba(10,125,77,0.22);
               color: var(--ks-champagne); }}
  .biz-platform {{ background: var(--ks-kinpaku); color: var(--ks-lacquer-deep); padding: 11px 12px;
                   border-radius: 4px; font-size: 13px; font-weight: 700; text-align: center; }}
  .biz-mod {{ background: var(--ks-graphite-2); border: 1px solid var(--ks-rule); color: var(--ks-body);
              padding: 8px 10px; border-radius: 4px; font-size: 12px; text-align: center; line-height: 1.3; }}
  .biz-arrow {{ display: flex; align-items: center; padding: 0 9px; color: var(--ks-kinpaku);
                font-size: 18px; flex-shrink: 0; align-self: center; }}
  @media (max-width: 720px) {{ .biz-flow {{ flex-direction: column; }} .biz-arrow {{ transform: rotate(90deg); margin: 2px auto; }} }}

  /* ── News ── */
  .news-item {{ padding: 11px 0; border-bottom: 1px solid var(--ks-rule); }}
  .news-item:last-child {{ border-bottom: none; }}
  .news-row {{ display: flex; gap: 14px; align-items: flex-start; }}
  .news-date {{ font-size: 10px; color: var(--ks-faint); white-space: nowrap; min-width: 74px;
                font-family: "SFMono-Regular", "Roboto Mono", monospace; padding-top: 2px; }}
  .news-headline {{ font-size: 15.5px; font-weight: 600; color: var(--ks-champagne); line-height: 1.4; }}
  .news-why {{ font-size: 14px; color: var(--ks-muted); margin-top: 6px; margin-left: 88px; line-height: 1.6; }}

  /* ── Financials / metrics ── */
  .fin-meta {{ font-size: 11px; color: var(--ks-faint); margin-bottom: 14px;
               font-family: "SFMono-Regular", "Roboto Mono", monospace; letter-spacing: 0.05em; }}
  /* auto-fill (not auto-fit): a partial last row keeps card width + stays left-aligned */
  .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                   gap: 10px; margin-bottom: 18px; }}
  .metric-card {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); border-radius: 4px; padding: 14px 16px;
                  min-width: 0; }}
  /* label may wrap to 2 lines (never truncate the metric name); min-height keeps
     cards aligned whether the label is 1 or 2 lines */
  .metric-label {{ font-size: 9.5px; font-weight: 500; color: var(--ks-faint); text-transform: uppercase;
                   letter-spacing: 0.12em; margin-bottom: 6px; line-height: 1.3; min-height: 1.9em;
                   font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  /* big number stays on ONE line; a long head shrinks rather than wrapping */
  .metric-value {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-size: 1.15rem; font-weight: 700;
                   color: var(--ks-kinpaku); line-height: 1.2; white-space: nowrap; }}
  .metric-value.long {{ font-size: 0.98rem; letter-spacing: -0.01em; }}
  .metric-value.green {{ color: var(--ks-patina); }}
  .metric-sub {{ font-size: 10.5px; color: var(--ks-faint); margin-top: 4px; line-height: 1.35;
                 font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .earn-bullets {{ list-style: none; padding: 0; margin: 0; }}
  .earn-bullets li {{ padding: 8px 0 8px 16px; position: relative; font-size: 14.5px;
                      color: var(--ks-body); border-bottom: 1px solid var(--ks-rule); line-height: 1.65; }}
  .earn-bullets li:before {{ content: ""; position: absolute; left: 2px; top: 14px;
                             width: 5px; height: 5px; border-radius: 50%; background: var(--ks-patina); }}
  .earn-bullets li:last-child {{ border-bottom: none; }}

  /* ── ARR chart sources ── */
  .chart-sources {{ margin-top: 8px; font-size: 9.5px; color: var(--ks-faint); }}
  .chart-source-label {{ font-weight: 600; letter-spacing: .06em; text-transform: uppercase; margin-right: 4px; }}
  .chart-source-link {{ color: var(--ks-kinpaku); text-decoration: none; border-bottom: 1px solid transparent;
                        transition: border-color .15s; }}
  .chart-source-link:hover {{ border-bottom-color: var(--ks-kinpaku); }}
  .chart-source-text {{ color: var(--ks-faint); }}

  /* ── ARR chart ── */
  .chart-row {{ display: flex; flex-wrap: wrap; gap: 28px 40px; align-items: flex-start; }}
  .chart-row .chart-wrap {{ flex: 1 1 320px; min-width: 0; }}
  .chart-caption {{ font-size: 10.5px; color: var(--ks-faint); margin-top: 6px; font-style: italic; }}
  .chart-wrap {{ margin: 4px 0 8px; }}
  .chart-eyebrow {{ font-size: 9px; text-transform: uppercase; letter-spacing: 0.18em;
                    color: var(--ks-faint); margin-bottom: 12px;
                    font-family: "SFMono-Regular", "Roboto Mono", monospace; }}

  /* ── Funding timeline (flex cards) ── */
  .tl-flex  {{ display: flex; align-items: center; gap: 0; overflow-x: auto;
               padding-bottom: 6px; margin: 8px 0; }}
  .tl-card  {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); border-radius: 3px;
               padding: 10px 12px; min-width: 88px; text-align: center; flex-shrink: 0; }}
  .tl-arrow {{ color: var(--ks-kinpaku); font-size: 14px; padding: 0 4px; flex-shrink: 0; }}
  .tl-round {{ font-size: 8px; text-transform: uppercase; letter-spacing: 0.10em;
               color: var(--ks-faint); font-family: "SFMono-Regular", "Roboto Mono", monospace;
               margin-bottom: 3px; }}
  .tl-amt   {{ font-size: 12px; font-weight: 700; color: var(--ks-kinpaku);
               font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .tl-val   {{ font-size: 10px; color: var(--ks-patina);
               font-family: "SFMono-Regular", "Roboto Mono", monospace; margin-top: 2px; }}
  .tl-date  {{ font-size: 9px; color: var(--ks-faint); margin-top: 1px; }}
  .tl-leads {{ font-size: 9px; color: var(--ks-muted); margin-top: 3px; line-height: 1.3; }}

  /* ── News source tag ── */
  .news-source-row {{ margin-left: 88px; margin-top: 4px; margin-bottom: 1px; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }}
  .news-source-label {{ font-size: 9px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: var(--ks-faint); margin-right: 2px; }}
  .news-source-sep {{ color: var(--ks-faint); font-size: 9px; }}
  .news-source-link {{ font-size: 9.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase;
    color: var(--ks-kinpaku); text-decoration: none; border-bottom: 1px solid transparent;
    transition: border-color .15s; }}
  .news-source-link:hover {{ border-bottom-color: var(--ks-kinpaku); }}
  .news-source-nolink {{ color: var(--ks-faint); }}
  /* legacy: keep so old references do not break */
  .news-source {{ font-size: 9.5px; font-weight: 600; color: var(--ks-faint); margin-left: 8px;
                  font-family: "SFMono-Regular", "Roboto Mono", monospace; letter-spacing: 0.05em;
                  background: var(--ks-raised); border: 1px solid var(--ks-rule);
                  padding: 1px 6px; border-radius: 3px; vertical-align: middle; }}

  /* ── body-p (single paragraph, no bullets) ── */
  .body-p {{ color: var(--ks-body); font-size: 15.5px; line-height: 1.7; }}

  /* ── SEC filings ── */
  .filings-wrap {{ display: flex; flex-direction: column; }}
  .filing-row {{ display: flex; align-items: baseline; gap: 14px; padding: 9px 0;
                 border-bottom: 1px solid var(--ks-rule); }}
  .filing-row:last-child {{ border-bottom: none; }}
  .filing-row:hover .filing-go {{ opacity: 1; }}
  .filing-form {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-weight: 700;
                  font-size: 12.5px; color: var(--ks-kinpaku); min-width: 52px; }}
  .filing-meta {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-size: 11.5px;
                  color: var(--ks-faint); flex: 1; }}
  .filing-go {{ font-family: "SFMono-Regular", "Roboto Mono", monospace; font-size: 10.5px;
                font-weight: 700; letter-spacing: 0.04em; color: var(--ks-kinpaku-pale);
                opacity: 0.55; transition: opacity .15s; white-space: nowrap; }}

  /* ── Slide Kit ── */
  .kit-grid {{ display: grid; grid-template-columns: 160px 1fr 1fr; gap: 24px; align-items: start; }}
  @media (max-width: 680px) {{ .kit-grid {{ grid-template-columns: 1fr; }} }}
  .kit-identity {{ display: flex; flex-direction: column; gap: 8px; }}
  .kit-logo-lg  {{ width: 64px; height: 64px; border-radius: 10px; object-fit: contain;
                   background: var(--ks-raised); padding: 6px; border: 1px solid var(--ks-rule); }}
  .kit-name {{ font-family: var(--ks-serif); font-size: 1.3rem;
               font-weight: 400; color: var(--ks-champagne); line-height: 1.1; }}
  .kit-sub  {{ font-size: 11px; color: var(--ks-muted); }}
  .kit-link {{ font-size: 11px; color: var(--ks-kinpaku-pale); }}
  .kit-tags {{ display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }}
  .kit-tag  {{ font-size: 9px; background: var(--ks-graphite); border: 1px solid var(--ks-rule);
               color: var(--ks-kinpaku-pale); padding: 2px 7px; border-radius: 3px;
               font-family: "SFMono-Regular", "Roboto Mono", monospace; letter-spacing: 0.04em; }}
  .kit-copy {{ display: flex; flex-direction: column; gap: 6px; }}
  .kit-copy-label {{ font-size: 8.5px; text-transform: uppercase; letter-spacing: 0.18em;
                     color: var(--ks-faint); font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .kit-stat {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); border-radius: 3px;
               padding: 8px 12px; font-size: 12.5px; font-weight: 600; color: var(--ks-champagne);
               font-family: "SFMono-Regular", "Roboto Mono", monospace; cursor: text; }}
  .kit-bullet {{ background: var(--ks-graphite); border-left: 2px solid var(--ks-kinpaku);
                 padding: 7px 10px; font-size: 12px; color: var(--ks-body); line-height: 1.5;
                 margin-top: 2px; }}
  .kit-assets {{ display: flex; flex-direction: column; gap: 6px; }}
  .kit-url  {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); border-radius: 3px;
               padding: 7px 10px; font-size: 10.5px; color: var(--ks-patina); word-break: break-all;
               font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .kit-swatches {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }}
  .kit-swatch-wrap {{ display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: default; }}
  .kit-swatch {{ width: 36px; height: 36px; border-radius: 6px; border: 1px solid rgba(0,0,0,.12);
                 box-shadow: 0 1px 4px rgba(0,0,0,.4); }}
  .kit-hex {{ font-size: 9px; font-family: "SFMono-Regular","Roboto Mono",monospace;
              color: var(--ks-faint); letter-spacing: .03em; text-transform: uppercase; }}

  /* ── Leadership ── */
  .exec-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }}
  .exec-card {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); border-radius: 4px;
                padding: 14px 16px; }}
  .exec-title {{ font-size: 9px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase;
                 color: var(--ks-faint); margin-bottom: 5px; }}
  .exec-since {{ font-weight: 400; color: var(--ks-faint); opacity: .7; }}
  .exec-name-row {{ margin-bottom: 6px; }}
  .exec-name {{ font-size: 13px; font-weight: 700; color: var(--ks-champagne); }}
  .exec-linkedin {{ font-size: 13px; font-weight: 700; color: var(--ks-kinpaku);
                    text-decoration: none; border-bottom: 1px solid transparent;
                    transition: border-color .15s; }}
  .exec-linkedin:hover {{ border-bottom-color: var(--ks-kinpaku); }}
  .exec-bg {{ font-size: 11px; color: var(--ks-muted); line-height: 1.55; }}

  /* ── Risk list ── */
  .risk-list {{ list-style: none; padding: 0; }}
  .risk-list li {{ padding: 10px 0 10px 22px; border-bottom: 1px solid var(--ks-rule);
                   position: relative; font-size: 14.5px; color: var(--ks-body); line-height: 1.65; }}
  .risk-list li:before {{ content: "!"; position: absolute; left: 3px; top: 10px; width: 13px; height: 13px;
                          border-radius: 50%; background: rgba(179,18,43,0.1);
                          color: var(--ks-vermilion); font-size: 9px; font-weight: 900;
                          text-align: center; line-height: 13px;
                          font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .risk-list li:last-child {{ border-bottom: none; }}
  .risk-label {{ font-weight: 600; color: var(--ks-champagne); }}

  /* ── Comps table ── */
  .comps-table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  .comps-table th {{ text-align: left; font-size: 9px; font-weight: 700; letter-spacing: 0.1em;
                     text-transform: uppercase; color: var(--ks-faint); padding: 0 12px 8px 0;
                     border-bottom: 1.5px solid var(--ks-kinpaku); vertical-align: bottom;
                     font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .comps-table th.right {{ text-align: right; }}
  /* unit (LTM / YoY) parked under the header so each cell value is one clean token */
  .th-unit {{ display: block; text-transform: none; font-weight: 400; font-size: 8.5px;
              letter-spacing: 0.03em; color: var(--ks-faint); opacity: 0.85; margin-top: 2px; }}
  .comps-table td {{ padding: 8px 12px 8px 0; border-bottom: 1px solid var(--ks-rule);
                     vertical-align: middle; color: var(--ks-body); }}
  /* numeric cells never wrap — a single clean token per cell */
  .comps-table td.mono, .comps-table td.right {{ white-space: nowrap; }}
  .comps-table tr:last-child td {{ border-bottom: none; }}
  .comps-table tr:hover td {{ background: var(--ks-raised); }}
  .comps-table tr.subj td {{ background: #eef3fa; font-weight: 700; color: var(--ks-champagne); }}
  .comp-name {{ font-weight: 700; color: var(--ks-champagne); font-size: 13px; }}
  .comp-ticker {{ color: var(--ks-kinpaku-pale); font-size: 11px; font-weight: 700; }}
  .comp-type-cell {{ font-size: 10px; color: var(--ks-faint); white-space: nowrap; }}
  .comp-ev {{ vertical-align: middle; }}
  .comp-val {{ font-size: 13px; font-weight: 700; color: var(--ks-kinpaku); }}
  .comp-val a {{ color: var(--ks-kinpaku); border-bottom: 1px solid transparent; }}
  .comp-val a:hover {{ border-bottom-color: var(--ks-kinpaku); }}
  .comp-raise {{ font-weight: 700; color: var(--ks-champagne); }}
  .comp-sub {{ display: block; font-size: 9px; font-weight: 400; color: var(--ks-faint);
               margin-top: 1px; white-space: nowrap; }}
  .comp-source-link {{ font-size: 9.5px; color: var(--ks-kinpaku); text-decoration: none;
                       border-bottom: 1px solid transparent; transition: border-color .15s; }}
  .comp-source-link:hover {{ border-bottom-color: var(--ks-kinpaku); }}
  .comp-source-nolink {{ font-size: 9.5px; color: var(--ks-faint); }}
  .subject-row td {{ background: rgba(179,18,43,0.05); font-weight: 700; color: var(--ks-champagne); }}
  .subject-row td:first-child {{ border-left: 3px solid var(--ks-kinpaku); padding-left: 8px; color: var(--ks-kinpaku); }}
  .note-cell {{ color: var(--ks-faint); font-size: 11px; }}

  /* ── Slide bullets ── */
  .slide-list {{ list-style: none; padding: 0; counter-reset: slides; }}
  .slide-list li {{ padding: 10px 0 10px 42px; border-bottom: 1px solid var(--ks-rule);
                    position: relative; font-size: 13px; color: var(--ks-body); line-height: 1.7; }}
  .slide-list li:last-child {{ border-bottom: none; }}
  .slide-list li:before {{ counter-increment: slides; content: counter(slides);
                           position: absolute; left: 0; top: 8px; width: 26px; height: 26px;
                           border-radius: 2px; background: var(--ks-kinpaku); color: var(--ks-lacquer-deep);
                           font-size: 11px; font-weight: 700; text-align: center; line-height: 26px;
                           font-family: "SFMono-Regular", "Roboto Mono", monospace; }}

  /* ── Diligence ── */
  .dq-list {{ list-style: none; padding: 0; counter-reset: dqs; }}
  .dq-list li {{ padding: 10px 0 10px 42px; border-bottom: 1px solid var(--ks-rule);
                 position: relative; font-size: 13px; color: var(--ks-body); line-height: 1.7; }}
  .dq-list li:last-child {{ border-bottom: none; }}
  .dq-list li:before {{ counter-increment: dqs; content: "Q" counter(dqs);
                        position: absolute; left: 0; top: 8px; width: 26px; height: 26px;
                        border-radius: 2px; background: var(--ks-raised); color: var(--ks-kinpaku);
                        border: 1px solid var(--ks-rule); font-size: 9.5px; font-weight: 700;
                        text-align: center; line-height: 26px;
                        font-family: "SFMono-Regular", "Roboto Mono", monospace; }}

  /* ── Chips ── */
  .chip-list {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .chip {{ background: var(--ks-raised); border: 1px solid var(--ks-rule); color: var(--ks-muted);
           font-size: 11.5px; padding: 3px 11px; border-radius: 20px; font-weight: 500; }}

  /* ── Footer ── */
  .footer {{ background: var(--ks-raised); border-top: 1px solid var(--ks-rule-strong);
             padding: 14px 40px; display: flex; justify-content: space-between; align-items: center; }}
  .footer-left {{ font-size: 10.5px; color: var(--ks-faint); line-height: 1.7; }}
  .footer-right {{ font-size: 10.5px; font-weight: 700; color: var(--ks-kinpaku);
                   letter-spacing: 0.22em; font-family: "SFMono-Regular", "Roboto Mono", monospace; }}
  .meta-note {{ font-size: 12px; color: var(--ks-muted); margin-top: 8px; }}
  .meta-note strong {{ color: var(--ks-champagne); }}

  @media (prefers-reduced-motion: reduce) {{
    * {{ animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }}
  }}

  /* ── Print / PDF (the deliverable) ──────────────────────────────────────────
     The PDF is just this HTML printed, so all pagination lives here. Goals:
     consistent page geometry, no block ever sliced by a page edge, no orphaned
     headings, running context on every page, and tighter density.            */
  @media print {{
    @page {{ size: Letter; margin: 16mm 12mm; }}
    * {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
    body {{ background: #fff; font-size: 10.5pt; line-height: 1.45; }}
    a {{ color: inherit; }}
    .toc {{ display: none; }}                              /* interactive nav only */
    .wrapper {{ max-width: none; border: none; }}

    /* edge-to-edge: the page margin (set by the DevTools render / @page) provides
       the side gutters, so sections sit flush to the printable area */
    .header, .toc, .section, .footer {{ padding-left: 0; padding-right: 0; }}

    /* Keep atomic blocks whole — never sliced by a page break */
    .hero-card, .metric-card, .explain-card, .exec-card, .tl-card, .news-item,
    .biz-flow, .chart-wrap, .kit-grid, .filing-row,
    .body-list li, .earn-bullets li, .risk-list li, .explain-list li,
    .slide-list li, .dq-list li, .comps-table tr, .diff-table tr,
    img, svg {{ break-inside: avoid; }}

    /* Never strand a heading at the foot of a page */
    .sec-label, .sec-meta, .chart-eyebrow, .biz-col-label, .kit-copy-label,
    .explain-label, .diagram-caption {{ break-after: avoid; }}
    .section {{ break-inside: auto; }}                     /* long sections break BETWEEN items */
    thead {{ display: table-header-group; }}               /* repeat table headers on continued pages */

    /* Print is always desktop-width, so keep the designed horizontal value chain
       (override the narrow-screen column fallback that the print viewport triggers) */
    .biz-flow {{ flex-direction: row; }}
    .biz-arrow {{ transform: none; align-self: center; margin: 0 4px; }}

    /* Density — same content, tighter so it reads in fewer pages */
    .header {{ padding-top: 0; padding-bottom: 12px; }}
    .section {{ padding-top: 12px; padding-bottom: 12px; }}
    .footer {{ padding-top: 12px; padding-bottom: 0; }}
    .hero-card {{ padding: 9px 14px; }}
    .hero-value {{ font-size: 1.2rem; }}
    .hero-value.long {{ font-size: 0.95rem; }}
    .metric-card {{ padding: 10px 13px; }}
    .metrics-grid {{ gap: 7px; margin-bottom: 12px; }}
    .metric-value {{ font-size: 1.05rem; }}
    .exec-card {{ padding: 11px 13px; }}
    .explain-card {{ padding: 10px 13px; }}
    .explain-grid {{ gap: 9px; margin-bottom: 14px; }}
    .explain-list li {{ padding: 3px 0 3px 16px; font-size: 12.5px; line-height: 1.45; }}
    .body-list li {{ padding: 6px 0 6px 18px; font-size: 13px; line-height: 1.5; }}
    .earn-bullets li, .risk-list li {{ padding-top: 6px; padding-bottom: 6px; }}
    .news-item {{ padding: 8px 0; }}
    .news-why {{ margin-top: 4px; }}
    .chart-wrap {{ margin: 2px 0 4px; }}
  }}
</style>
</head>
<body>
<div class="wrapper">

  <!-- ① HEADER: Logo + Name + Badges -->
  <div class="header">
    <div class="header-top">
      {'<img class="company-logo" src="' + logo_url + '" alt="' + name + ' logo" onerror="this.style.display=\'none\'">' if logo_url else ''}
      <div class="header-name">
        <span class="company-name">{name}</span>
        <div class="header-badges">
          {'<span class="ticker-badge">' + ticker + '</span>' if ticker else ''}
          {'<span class="stage-badge">' + stage.upper() + '</span>' if stage else ''}
          <span class="draft-badge">DRAFT</span>
        </div>
      </div>
      <div class="header-meta" style="text-align:right">
        {'<a href="' + website + '" target="_blank">' + website.replace("https://","").rstrip("/") + '</a><br>' if website else ''}
        Atlas &nbsp;·&nbsp; {date_fmt}
      </div>
    </div>
    {'<div class="verticals">' + "".join(f'<span class="vertical-tag">{v}</span>' for v in verticals[:4]) + '</div>' if verticals else ''}
    {'<div class="trading-bar"><strong>Trading</strong>' + " &nbsp;|&nbsp; ".join(p.strip() for p in trading_line.split("|")) + '</div>' if trading_line else ''}
  </div>

  <!-- ② HERO STATS: 5 KPIs at a glance -->
  {hero_html}

  <!-- ③ TOC -->
  <div class="toc">{toc_html}</div>

  <!-- ④ BUSINESS OVERVIEW: explainer (3 levels) + bullets + value-chain diagram -->
  {'<div class="section" id="overview"><div class="sec-label">Business Overview</div>' + explainer_html + '<div class="two-col"><div>' + to_bullets(b.get("businessOverview") or short_desc, max_bullets=max_ov_bullets) + '</div><div><div class="diagram-caption">How the business works, left to right: who buys, what the platform provides, and the payoff.</div>' + biz_flow_html + '</div></div></div>' if (b.get("businessOverview") or short_desc) else ''}

  <!-- ④a HOW BROADCOM IS DIFFERENT (vs peers) -->
  {differentiation_html}

  <!-- ④b EXECUTIVE LEADERSHIP -->
  {leadership_html}

  <!-- ⑤ PRODUCT & REVENUE MODEL -->
  {'<div class="section" id="product"><div class="sec-label">Product &amp; Revenue Model</div>' + to_bullets(b.get("productModel") or biz_model) + '</div>' if (b.get("productModel") or biz_model) else ''}

  <!-- ⑥ RECENT NEWS -->
  {news_section_html}

  <!-- ⑦ FINANCIALS / EARNINGS -->
  {earnings_section_html}

  <!-- ⑧ ARR GROWTH CHART -->
  {'<div class="section" id="growth"><div class="sec-label">Revenue Trajectory</div>' + charts_html + '</div>' if charts_html else ''}

  <!-- ⑨ KEY RISKS -->
  {risks_section_html}

  <!-- ⑩ COMPARABLE COMPANIES -->
  {'<div class="section" id="comps"><div class="sec-label">Comparable Companies</div>' + comps_html + '</div>' if b.get("comps") else ''}

  <!-- ⑩b COMPETITORS (if no comps table) -->
  {competitors_section_html}

  <!-- ⑩c PRIMARY FILINGS (SEC EDGAR) -->
  {filings_section_html}

  <!-- ⑪ FUNDING TIMELINE -->
  {funding_section_html}

  <!-- ⑫ INVESTORS -->
  {'<div class="section" id="investors"><div class="sec-label">Notable Investors</div>' + investors_html + '</div>' if investors else ''}

  <!-- ⑬ IPO READINESS -->
  {'<div class="section"><div class="sec-label">IPO Readiness</div>' + to_bullets(ipo_read) + '</div>' if ipo_read else ''}

  <!-- ⑭ SLIDE-READY BULLETS -->
  {'<div class="section" id="bullets"><div class="sec-label">Slide-Ready Bullets</div><ol class="slide-list">' + "".join(f"<li>{clean(bl)}</li>" for bl in bullets) + '</ol></div>' if bullets else ''}

  <!-- ⑮ DILIGENCE QUESTIONS -->
  {'<div class="section" id="diligence"><div class="sec-label">Smart Diligence Questions</div><ol class="dq-list">' + "".join(f"<li>{clean(q)}</li>" for q in dqs) + '</ol></div>' if dqs else ''}

  <!-- ⑯ SLIDE KIT -->
  <div class="section" id="slidekit">
    <div class="sec-label">Slide Kit</div>
    <div class="sec-meta">Logo, stats, and copy-paste artifacts</div>
    {slide_kit_html}
  </div>

  <!-- FOOTER -->
  <div class="footer">
    <div class="footer-left">
      Sources: Company IR, earnings transcripts, Bloomberg, SEC filings, Sacra, Crunchbase, yfinance<br>
      DRAFT for internal use only. Human review required before distribution.
    </div>
    <div class="footer-right">ATLAS</div>
  </div>

</div>
</body>
</html>"""


# ── PDF render (headless Chrome) ───────────────────────────────────────────────

def _find_chrome():
    """Locate a Chrome/Chromium-family binary for headless PDF rendering."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "chrome", "microsoft-edge", "brave-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# Minimal WebSocket client — just enough to issue a single DevTools printToPDF.
def _ws_send(sock, payload):
    data = json.dumps(payload).encode("utf-8")
    header = bytearray([0x81])                          # FIN + text frame
    n = len(data)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126); header += n.to_bytes(2, "big")
    else:
        header.append(0x80 | 127); header += n.to_bytes(8, "big")
    mask = os.urandom(4)
    header += mask
    sock.sendall(bytes(header) + bytes(c ^ mask[i % 4] for i, c in enumerate(data)))


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("socket closed")
        buf += chunk
    return buf


def _ws_recv(sock):
    """Read one (possibly fragmented) text message; return parsed JSON."""
    msg = b""
    while True:
        b0, b1 = _recv_exact(sock, 2)
        fin, opcode, length = b0 & 0x80, b0 & 0x0f, b1 & 0x7f
        if length == 126:
            length = int.from_bytes(_recv_exact(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(_recv_exact(sock, 8), "big")
        payload = _recv_exact(sock, length) if length else b""
        if opcode == 0x9:                               # ping -> ignore, keep reading
            continue
        if opcode == 0x8:                               # close
            raise ConnectionError("websocket closed by peer")
        msg += payload
        if fin:
            break
    return json.loads(msg.decode("utf-8"))


def _render_pdf_cdp(chrome, html_path, pdf_path, header_html, footer_html):
    """Drive Chrome over the DevTools protocol so the PDF carries a real per-page
    header/footer + 'Page X / Y' in the margins (the one thing --print-to-pdf cannot
    do). Returns True on success; raises on any failure so the caller can fall back."""
    port = _free_port()
    proc = subprocess.Popen(
        [chrome, "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", f"--remote-debugging-port={port}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    sock = None
    try:
        ws_url = None
        for _ in range(50):                             # wait for DevTools endpoint
            try:
                raw = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1).read()
                for t in json.loads(raw):
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        ws_url = t["webSocketDebuggerUrl"]; break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.1)
        if not ws_url:
            raise RuntimeError("DevTools endpoint not ready")

        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", ws_url)
        host, wport, path = m.group(1), int(m.group(2)), m.group(3)
        sock = socket.create_connection((host, wport), timeout=10)
        sock.settimeout(30)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{wport}\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
                      f"Sec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += sock.recv(1024)
        if b"101" not in resp.split(b"\r\n", 1)[0]:
            raise RuntimeError("websocket upgrade failed")

        _ws_send(sock, {"id": 1, "method": "Page.enable"})
        _ws_send(sock, {"id": 2, "method": "Page.navigate",
                        "params": {"url": html_path.resolve().as_uri()}})
        for _ in range(300):                            # wait for load
            if _ws_recv(sock).get("method") == "Page.loadEventFired":
                break
        time.sleep(0.5)                                 # let web fonts settle

        _ws_send(sock, {"id": 3, "method": "Page.printToPDF", "params": {
            "printBackground": True, "preferCSSPageSize": False,
            "paperWidth": 8.5, "paperHeight": 11,
            "marginTop": 0.6, "marginBottom": 0.6, "marginLeft": 0.5, "marginRight": 0.5,
            "displayHeaderFooter": True,
            "headerTemplate": header_html, "footerTemplate": footer_html,
        }})
        data_b64 = None
        for _ in range(300):
            msg = _ws_recv(sock)
            if msg.get("id") == 3:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                data_b64 = msg["result"]["data"]; break
        if not data_b64:
            raise RuntimeError("no printToPDF result")
        pdf_path.write_bytes(base64.b64decode(data_b64))
        return True
    finally:
        try:
            if sock:
                sock.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def render_pdf(html_path: Path, profile=None):
    """
    Render the HTML brief to a print-faithful PDF via the locally-installed headless
    Chrome. Preferred path drives DevTools printToPDF so every page carries a running
    header/footer + 'Page X / Y'; falls back to the plain --print-to-pdf CLI (clean
    pagination, no running footer) and finally to HTML-only. Returns the .pdf Path
    or None.
    """
    chrome = _find_chrome()
    if not chrome:
        print("⚠️  No Chrome/Chromium found — skipping PDF render (HTML only).")
        return None
    pdf_path = html_path.with_suffix(".pdf")

    # Build the running header/footer (rendered into the page margins by DevTools).
    profile = profile or {}
    nm  = (profile.get("name") or "").replace("&", "&amp;").replace("<", "&lt;")
    tkr = (profile.get("ticker") or "").strip()
    date = (profile.get("brief", {}) or {}).get("runDate") or profile.get("lastRunDate") \
        or datetime.date.today().isoformat()
    try:
        date_fmt = datetime.datetime.strptime(date, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        date_fmt = date
    hl = nm + (f" &middot; {tkr}" if tkr else "")
    base_style = ("font-family:Arial,Helvetica,sans-serif;font-size:7px;color:#9aa3b2;"
                  "width:100%;padding:0 12mm;display:flex;justify-content:space-between;"
                  "letter-spacing:.08em;")
    header_html = (f'<div style="{base_style}text-transform:uppercase">'
                   f'<span>{hl}</span><span>Draft</span></div>')
    footer_html = (f'<div style="{base_style}">'
                   f'<span>Atlas &middot; {date_fmt} &middot; internal use only</span>'
                   f'<span>Page <span class="pageNumber"></span> / '
                   f'<span class="totalPages"></span></span></div>')

    # Preferred: DevTools render (running footer + page numbers).
    try:
        if _render_pdf_cdp(chrome, html_path, pdf_path, header_html, footer_html) \
           and pdf_path.exists() and pdf_path.stat().st_size > 1024:
            print(f"📕  PDF rendered (running footer + page numbers): {pdf_path}")
            return pdf_path
    except Exception as e:
        print(f"⚠️  DevTools render failed ({e}); falling back to CLI render.")

    # Fallback: plain CLI render — correct pagination, no running footer.
    try:
        subprocess.run(
            [chrome, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()],
            check=True, capture_output=True, timeout=120,
        )
    except Exception as e:
        print(f"⚠️  PDF render failed ({e}) — HTML only.")
        return None
    if not pdf_path.exists() or pdf_path.stat().st_size < 1024:
        print("⚠️  PDF render produced no output — HTML only.")
        return None
    print(f"📕  PDF rendered: {pdf_path}")
    return pdf_path


# ── Main ─────────────────────────────────────────────────────────────────────

def run(ticker: str, detail: str = "brief"):
    folder_id = ticker.strip()
    profile   = load_profile(folder_id)
    # resolve the actual folder name on disk (may differ in case)
    for candidate in [folder_id, folder_id.upper()]:
        if (DATA_DUMPS / candidate / "profile.json").exists():
            folder_id = candidate
            break
    profile["_detail"] = detail   # inject detail level for build_html

    html = build_html(profile)

    # Save HTML to runs folder (latest run date)
    run_date  = profile.get("brief", {}).get("runDate") or datetime.date.today().isoformat()
    out_dir   = DATA_DUMPS / folder_id / "runs" / run_date
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix    = f"_{detail}" if detail != "brief" else ""
    html_path = out_dir / f"{folder_id}_brief_{run_date}{suffix}.html"
    html_path.write_text(html)
    print(f"📄  Brief saved: {html_path}")

    # Render a print-faithful PDF alongside the HTML (the primary deliverable).
    pdf_path = render_pdf(html_path, profile)

    return pdf_path or html_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 agents/deliverable_agent.py TICKER [--detailed]")
        sys.exit(1)

    ticker = sys.argv[1]
    detail = "detailed" if "--detailed" in sys.argv else "brief"
    run(ticker, detail=detail)
