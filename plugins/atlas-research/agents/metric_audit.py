"""
Metric Consistency & Clarity Auditor — the guard that keeps the same number from
telling two stories.

An MD catches a self-contradicting brief instantly: a figure that reads "$202M" in the
metrics grid and "$210M" in a slide bullet, or a quarterly revenue that happens to equal
the full-year number (the classic "Q3 rev $200M / total rev $200M" mislabel). Once one
number doesn't tie, the whole brief is suspect. This module re-reads the assembled brief
the way a reviewer would and flags three failure modes:

  1. Conflict   — the SAME metric for the SAME period appears with two different values
                  across sections (metrics grid vs. slide bullet vs. revenue history).
  2. Collision  — a flow metric (revenue / EBITDA / FCF / net income) carries an identical
                  value tagged both quarterly AND annual: almost always a mislabel.
  3. Unperioded — a headline figure (revenue, ARR, valuation, market cap, …) ships with no
                  period anywhere near it, so a reader can't tell what window it covers.

Design choice: MONEY amounts are the high-confidence axis (a dollar figure is hard to
misread), so cross-section money conflicts among STRUCTURED fields (keyMetrics, revenue
history, the subject comp row) are reported as 'error'. Anything that leans on prose
parsing — or any growth-rate (%) comparison, which is genuinely ambiguous (ARR growth vs.
revenue growth vs. LTM growth are all different and all legitimately differ) — is at most a
'warn'. A noisy auditor gets ignored; this one is built to stay quiet unless a number
actually doesn't tie.

Returns (issues, summary): issues is a list of (level, message), level in {'error','warn'}.
"""

import re
from collections import defaultdict

# ── Concept taxonomy ────────────────────────────────────────────────────────────
# Canonical metric concepts. Two figures only "conflict" if they map to the SAME concept,
# so ARR ($845M) and quarterly revenue ($202M) never get compared — they're different things.

# Flow metrics are earned OVER a period (a quarter's worth, a year's worth), so a quarterly
# value and an annual value of the SAME flow concept should differ ~4x; an exact match is the
# tell-tale mislabel. Balances/point-in-time metrics (ARR, RPO, cash, valuation, market cap)
# are NOT flows — an FY-end balance can legitimately equal a later point-in-time balance.
_FLOW_CONCEPTS = {"revenue", "ebitda", "fcf", "netincome", "operatingincome"}

# keyMetrics label (camelCase / snake) -> canonical concept. Order matters: more specific
# keys are tested before generic ones (e.g. 'arr' before 'revenue').
def _concept_from_label(label: str):
    k = re.sub(r"[^a-z0-9]", "", (label or "").lower())
    if not k:
        return None
    # specific first
    if "knowledgehubarr" in k or k.endswith("arr") or k == "arr" or "arrrunrate" in k:
        # Segment/product ARR (Agentforce ARR, Knowledge-Hub ARR…) is a different
        # concept from company ARR — same rule as segment revenue below.
        if k not in ("arr", "arrrunrate") and re.search(
                r"(commercial|government|gov|product|segment|cloud|ai|agent|knowledgehub|netnew)", k):
            return "arr_" + k
        return "arr"
    if "rpo" in k or "remainingperformance" in k:
        return "rpo"
    if "nrr" in k or "netretention" in k or "netrevenueretention" in k:
        return "nrr"
    if "grr" in k or "grossretention" in k:
        return "grr"
    if "grossmargin" in k:
        return "grossmargin"
    if "operatingmargin" in k:
        return "opmargin"
    if "ebitda" in k:
        return "ebitda"
    if "freecashflow" in k or k == "fcf" or "fcfmargin" in k:
        return "fcf"
    if "netincome" in k:
        return "netincome"
    if "eps" in k:
        return "eps"
    if "marketcap" in k:
        return "marketcap"
    if "valuation" in k:
        return "valuation"
    if "runrate" in k:
        return "runrate"
    if "cash" in k and "flow" not in k:
        return "cash"
    if "customer" in k or "logos" in k:
        return "customers"
    if "revenuegrowth" in k:
        return "revenue_growth"
    if "revenue" in k or k == "rev":
        # Segment/geo revenue (US commercial, government, product, intl…) is a DIFFERENT
        # concept from total revenue — $595M US commercial vs $1.63B total is not a
        # contradiction. Key each qualified revenue label as its own concept.
        if re.search(r"(commercial|government|gov|international|intl|product|subscription|"
                     r"services|software|segment|cloud|license|ai|^us|domestic|americas|"
                     r"europe|emea|apac|uk)", k):
            return "revenue_" + k
        return "revenue"
    return None

# Prose concept keywords -> canonical concept (longest phrase wins). Used only to label a
# dollar figure found in running text; deliberately narrow to stay high-confidence.
_PROSE_CONCEPTS = [
    ("annual recurring revenue", "arr"), ("arr", "arr"),
    ("market cap", "marketcap"), ("market capitalization", "marketcap"),
    ("net revenue retention", "nrr"), ("net retention", "nrr"),
    ("remaining performance obligation", "rpo"), ("rpo", "rpo"),
    ("free cash flow", "fcf"),
    ("adjusted ebitda", "ebitda"), ("ebitda", "ebitda"),
    ("post-money", "valuation"), ("valuation", "valuation"), ("valued at", "valuation"),
    ("gross margin", "grossmargin"),
    ("total revenue", "revenue"), ("revenue", "revenue"),
]

# Period descriptors near a figure tell us which window it covers.
def _period_of(text: str):
    """Return (period_type, period_label) for a snippet. period_type in
    {'quarter','annual','ltm','guidance','asof','runrate',None}."""
    if not text:
        return None, ""
    s = text.lower()
    # guidance / forward look — never a 'reported' figure, so excluded from collision checks
    if re.search(r"\b(guid|outlook|expect|forecast|target|next[\s-]?q)\w*", s):
        return "guidance", _first_match(text, r"(FY\s?\d{2,4}|Q[1-4]\s?(?:FY)?\s?\d{2,4})") or "guidance"
    # quarterly: Q1 FY2027, Q3 2026, a bare Q3, "third quarter", "quarter ended"
    mq = (re.search(r"Q[1-4]\s?(?:FY)?\s?\d{2,4}", text, re.I)
          or re.search(r"\bQ[1-4]\b", text)
          or re.search(r"\b(?:first|second|third|fourth)[\s-]quarter\b", s)
          or re.search(r"\bquarter(?:ly)?\b", s))
    # annual: FY2026 (no Q), "full year", "fiscal year", "for the year"
    ma = re.search(r"\bFY\s?\d{2,4}\b", text, re.I) or re.search(r"\b(full[\s-]?year|fiscal year|for the year|annual)\b", s)
    if re.search(r"\b(ltm|ttm|trailing twelve|trailing 12)\b", s):
        return "ltm", "LTM"
    if mq and not re.search(r"Q[1-4]", _safe(ma.group(0)) if ma else ""):
        # a Q-token present => quarterly (even if an FY appears, "Q1 FY2027" is quarterly)
        return "quarter", _safe(mq.group(0) if hasattr(mq, "group") else "quarter")
    if ma:
        return "annual", _safe(ma.group(0))
    if re.search(r"\b(run[\s-]?rate|annualized)\b", s):
        return "runrate", "run-rate"
    masof = re.search(r"as of\s+([A-Za-z0-9,\s/.-]{4,30})", text, re.I)
    if masof:
        return "asof", "as of " + masof.group(1).strip().rstrip(".,")
    return None, ""


def _safe(x):
    return (x or "").strip()


def _first_match(text, pat):
    m = re.search(pat, text or "", re.I)
    return m.group(0) if m else ""


# ── Value parsing ────────────────────────────────────────────────────────────────

_MONEY_RE = re.compile(
    r"(?<![\w])\$\s?(\d[\d,]*(?:\.\d+)?)\s*(trillion|billion|million|thousand|[KMBT])?\b",
    re.I,
)
_MULT = {"t": 1_000_000, "trillion": 1_000_000, "b": 1_000, "billion": 1_000,
         "m": 1, "million": 1, "k": 0.001, "thousand": 0.001}


def _money_to_millions(num_str: str, unit: str):
    try:
        v = float(num_str.replace(",", ""))
    except ValueError:
        return None
    u = (unit or "").lower()
    if not u:
        # No unit ("$2,900,000,000" or a "$12" share price): the value is raw dollars,
        # so convert to millions directly.
        return v / 1_000_000
    return v * _MULT.get(u, 1)


def _money_in(text: str):
    """Yield (value_in_millions, raw_token) for every $ figure in text."""
    for m in _MONEY_RE.finditer(text or ""):
        val = _money_to_millions(m.group(1), m.group(2))
        if val is not None:
            yield val, m.group(0)


def _lead_money(value_str: str):
    """The headline $ figure of a keyMetrics value string, in millions. Ranges
    ('$90.5-91.0M') and 'pre-revenue' return None (not a single comparable point)."""
    s = str(value_str)
    if re.search(r"\d\s*[-–]\s*\d", s):          # a range -> not one point
        return None
    g = list(_money_in(s))
    return g[0][0] if g else None


def _money_eq(a: float, b: float) -> bool:
    """Equal within tolerance: the larger of $1M or 1.5% (covers $845M vs $0.845B,
    '~$500M' vs '$500M', rounding between sources)."""
    if a is None or b is None:
        return False
    return abs(a - b) <= max(1.0, 0.015 * max(abs(a), abs(b)))


def _fmt_m(v: float) -> str:
    if v >= 1000:
        return f"${v/1000:.2f}B".replace(".00B", "B")
    if v >= 1:
        return f"${v:.0f}M"
    return f"${v*1000:.0f}K"


# ── Fact extraction ──────────────────────────────────────────────────────────────

class _Fact:
    __slots__ = ("concept", "value", "ptype", "plabel", "loc", "raw", "structured")

    def __init__(self, concept, value, ptype, plabel, loc, raw, structured):
        self.concept, self.value = concept, value
        self.ptype, self.plabel = ptype, plabel
        self.loc, self.raw, self.structured = loc, raw, structured


def _section_period(et: dict):
    """Default period for the metrics grid, taken from earningsTakeaways.quarter."""
    q = (et or {}).get("quarter") or ""
    return _period_of(q)


def _collect_facts(profile: dict):
    b = profile.get("brief") or {}
    et = b.get("earningsTakeaways") or {}
    facts = []
    sec_ptype, sec_plabel = _section_period(et if isinstance(et, dict) else {})

    # 1) keyMetrics — the structured grid. Concept from the label; period from the value
    #    if it carries one, else the section default.
    metrics = (et.get("keyMetrics") if isinstance(et, dict) else {}) or {}
    for label, val in metrics.items():
        concept = _concept_from_label(label)
        if not concept:
            continue
        vs = str(val)
        ptype, plabel = _period_of(vs)
        if not ptype:
            ptype, plabel = sec_ptype, sec_plabel
        money = _lead_money(vs)
        if money is not None:
            facts.append(_Fact(concept, money, ptype, plabel,
                               f"metrics grid · {label}", vs, True))

    # 2) revenueHistory — dated annual points. Per the spec the `value` is in $B
    #    (e.g. 41.45 → $41.45B); facts are kept in $M, so convert. The label string
    #    is the cross-check: if it parses to ~1000× the raw value, the value was $B.
    for r in (profile.get("revenueHistory") or []):
        yr = str(r.get("year") or "")
        lbl = str(r.get("label") or "")
        concept = "arr" if re.search(r"\barr\b", lbl, re.I) or re.search(r"\barr\b", yr, re.I) else "revenue"
        ptype, plabel = _period_of(yr + " " + lbl)
        v = r.get("value")
        if isinstance(v, (int, float)):
            v_m = float(v) * 1000.0                       # $B (spec) -> $M
            lbl_m = _lead_money(lbl)
            if lbl_m is not None and _money_eq(lbl_m, float(v)):
                v_m = float(v)                            # legacy profile stored $M
            facts.append(_Fact(concept, v_m, ptype or "annual", plabel or yr,
                               f"revenue history · {yr}", lbl or yr, True))

    # 3) subject comp row — live LTM multiples/growth (kept for completeness; money only).
    for c in (b.get("comps") or []):
        if (c.get("type") or "").strip().lower() != "subject":
            continue
        for key, concept in (("marketCap", "marketcap"),):
            money = _lead_money(str(c.get(key) or ""))
            if money is not None:
                facts.append(_Fact(concept, money, "asof", "last close",
                                   f"comp row · {c.get('name','subject')}", str(c.get(key)), True))

    # 4) prose — businessOverview, productModel, slide bullets, risks, news, commentary.
    #    Only record a $ figure when a concept keyword sits within a tight window before it.
    prose_blocks = []
    for fld in ("businessOverview", "productModel"):
        if b.get(fld):
            prose_blocks.append((fld, str(b[fld])))
    for i, s in enumerate(b.get("slideBullets") or []):
        prose_blocks.append((f"slide bullet {i+1}", str(s)))
    for i, s in enumerate(b.get("keyRisks") or []):
        prose_blocks.append((f"key risk {i+1}", str(s)))
    for n in (b.get("recentNews") or []):
        prose_blocks.append(("news", f"{n.get('headline','')} {n.get('whyItMatters','')}"))
    if isinstance(et, dict):
        for fld in ("aiCommentary", "demandCommentary", "analystTake"):
            if et.get(fld):
                prose_blocks.append((f"earnings {fld}", str(et[fld])))

    for loc, text in prose_blocks:
        for m in _MONEY_RE.finditer(text):
            val = _money_to_millions(m.group(1), m.group(2))
            if val is None:
                continue
            start, end = m.start(), m.end()
            window = text[max(0, start - 48):end + 24]
            concept = None
            for phrase, cpt in _PROSE_CONCEPTS:
                if phrase in window.lower():
                    concept = cpt
                    break
            if not concept:
                continue
            ptype, plabel = _period_of(window)
            facts.append(_Fact(concept, val, ptype, plabel, loc, m.group(0), False))

    return facts


# ── Audit ────────────────────────────────────────────────────────────────────────

def _competitor_names(profile: dict):
    """Lowercased name fragments of every OTHER company named in the brief (competitors +
    comp rows that aren't the subject). Used to drop prose $ figures that belong to a peer
    — e.g. 'Zscaler ($2.2B ARR)' is not the subject's ARR and must not be cross-checked."""
    names = set()
    for c in (profile.get("competitors") or []):
        n = re.sub(r"[^a-z0-9 ]", "", str(c).lower()).strip()
        if len(n) >= 3:
            names.add(n)
    for c in ((profile.get("brief") or {}).get("comps") or []):
        if (c.get("type") or "").strip().lower() == "subject":
            continue
        n = re.sub(r"[^a-z0-9 ]", "", str(c.get("name") or "").lower()).strip()
        if len(n) >= 3:
            names.add(n)
    return names


def audit_metrics(profile: dict):
    """Returns (issues, summary). issues: list of (level, message)."""
    profile = profile or {}
    facts = _collect_facts(profile)
    issues = []

    money_facts = [f for f in facts if f.value is not None]
    # Conflict/collision run on STRUCTURED facts only (keyMetrics, revenue history, subject
    # comp row): their concept and ownership are unambiguous, so a mismatch is a real defect.
    # Prose figures are checked separately, precision-gated, because text can't reliably say
    # WHOSE number it is (a peer's ARR, a TAM, a prior-year figure).
    struct = [f for f in money_facts if f.structured]

    # ── 1) Conflict: same concept + same period, different value (structured) ──
    groups = defaultdict(list)
    for f in struct:
        if f.ptype == "guidance":
            continue
        pkey = (f.plabel or f.ptype or "").lower()
        groups[(f.concept, pkey)].append(f)

    for (concept, pkey), fs in groups.items():
        if len(fs) < 2:
            continue
        lo_f = min(fs, key=lambda x: x.value)
        hi_f = max(fs, key=lambda x: x.value)
        if _money_eq(lo_f.value, hi_f.value):
            continue
        per = f" ({pkey})" if pkey else ""
        issues.append(("error",
            f"{_concept_name(concept)}{per} doesn't tie: "
            f"{_fmt_m(lo_f.value)} in {lo_f.loc} vs {_fmt_m(hi_f.value)} in {hi_f.loc} "
            f"— the same metric must match everywhere it appears"))

    # ── 1b) Prose vs structured: the headline case ("$202M in the grid, $210M in a
    # slide bullet"). Prose attribution is fuzzier (could be a peer's or prior-year
    # figure), so a mismatch is a WARN, not a blocker — and peer-attributed figures
    # are excluded up front.
    competitors = _competitor_names(profile)
    for f in money_facts:
        if f.structured or f.ptype == "guidance":
            continue
        head = f.raw.split("$")[0]
        if any(cn and cn in (f.loc + " " + head).lower() for cn in competitors):
            continue
        pkey = (f.plabel or f.ptype or "").lower()
        anchors = groups.get((f.concept, pkey))
        if anchors and not any(_money_eq(f.value, s.value) for s in anchors):
            s0 = anchors[0]
            per = f" ({pkey})" if pkey else ""
            issues.append(("warn",
                f"{_concept_name(f.concept)}{per} in prose doesn't tie: "
                f"{_fmt_m(f.value)} in {f.loc} vs {_fmt_m(s0.value)} in {s0.loc} "
                f"— verify, or label the basis if it legitimately differs"))

    # ── 2) Collision: a FLOW metric shown with the same value as both a quarter AND a year ──
    # This is the classic mislabel the user flagged ("Q3 rev $200M / total rev $200M"): a
    # quarterly flow can't equal the annual flow. Runs on structured facts PLUS prose flow
    # facts (a peer's number is excluded), since the mistake often lives in the narrative.
    # Prose flow figures below $1M are dropped to avoid stray parses ("$0", a share price).
    flow_facts = [f for f in struct if f.concept in _FLOW_CONCEPTS]
    for f in money_facts:
        if f.structured or f.concept not in _FLOW_CONCEPTS or f.value is None or f.value < 1.0:
            continue
        head = f.raw.split("$")[0]
        if any(cn and cn in (f.loc + " " + head).lower() for cn in competitors):
            continue                              # a peer's flow figure, not the subject's
        flow_facts.append(f)
    for concept in _FLOW_CONCEPTS:
        q = [f for f in flow_facts if f.concept == concept and f.ptype == "quarter"]
        a = [f for f in flow_facts if f.concept == concept and f.ptype == "annual"]
        flagged = False
        for fq in q:
            for fa in a:
                if _money_eq(fq.value, fa.value) and not flagged:
                    flagged = True
                    issues.append(("warn",
                        f"{_concept_name(concept)} is shown as {_fmt_m(fq.value)} for a "
                        f"QUARTER ({fq.loc}) and the same {_fmt_m(fa.value)} for the YEAR "
                        f"({fa.loc}) — a quarterly figure should not equal the annual; "
                        f"verify one isn't mislabeled"))

    # ── 3) Unperioded headline figures in the metrics grid ──
    et = (profile.get("brief") or {}).get("earningsTakeaways") or {}
    sec_ptype, _ = _section_period(et if isinstance(et, dict) else {})
    # Flows/operating balances where the window is essential; valuation & market cap are
    # inherently point-in-time ('reported'/'last close') so they're not flagged here.
    HEADLINE = {"revenue", "arr", "ebitda", "fcf", "rpo", "runrate", "nrr", "grr"}
    if not sec_ptype:                                 # no section-level period to fall back on
        for f in struct:
            if f.loc.startswith("metrics grid") and f.concept in HEADLINE and not f.ptype:
                issues.append(("warn",
                    f"{_concept_name(f.concept)} ({f.raw}) has no period — label the window "
                    f"(e.g. Q_ FY____, FY____, LTM, or 'as of <date>') so the reader knows "
                    f"what it covers"))

    # ── summary ──
    n_err = sum(1 for lvl, _ in issues if lvl == "error")
    n_warn = sum(1 for lvl, _ in issues if lvl == "warn")
    parts = [f"{len(money_facts)} financial figure(s) cross-checked"]
    if n_err:
        parts.append(f"{n_err} contradiction(s)")
    if n_warn:
        parts.append(f"{n_warn} to verify")
    if not n_err and not n_warn:
        parts.append("all tie")
    summary = "; ".join(parts)
    return issues, summary


_CONCEPT_NAMES = {
    "revenue": "Revenue", "arr": "ARR", "nrr": "NRR", "grr": "GRR", "rpo": "RPO",
    "grossmargin": "Gross margin", "opmargin": "Operating margin", "ebitda": "EBITDA",
    "fcf": "Free cash flow", "netincome": "Net income", "operatingincome": "Operating income",
    "eps": "EPS", "marketcap": "Market cap", "valuation": "Valuation",
    "runrate": "Revenue run-rate", "cash": "Cash", "customers": "Customer count",
    "revenue_growth": "Revenue growth",
}


def _concept_name(c):
    return _CONCEPT_NAMES.get(c, c.title())


if __name__ == "__main__":
    import sys, json, os
    from pathlib import Path
    # Honour ATLAS_DATA_ROOT (set by the plugin) so audits read the user's project
    # coverage db; default to the tool root when running in-repo.
    root = Path(os.environ["ATLAS_DATA_ROOT"]) if os.environ.get("ATLAS_DATA_ROOT") else Path(__file__).parent.parent
    for tk in sys.argv[1:]:
        for cand in (tk, tk.upper()):
            p = root / "data-dumps" / cand / "profile.json"
            if p.exists():
                prof = json.loads(p.read_text())
                issues, summary = audit_metrics(prof)
                print(f"\n=== {cand} ===\n🧮 {summary}")
                for lvl, m in issues:
                    print(f"   {'❌' if lvl=='error' else '⚠️ '} {m}")
                break
