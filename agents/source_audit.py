"""
Source Integrity Auditor — the gate that makes a brief defensible to an MD.

A brief lives and dies by its sources, so before one ships this checks every datapoint's
citation along four axes:

  1. Live      — does the URL actually resolve? (catches dead/typo'd/rotted links)
  2. Trusted   — is the domain in the Alfred source registry (sources.py)? (catches
                 random blogs, press-release aggregators, Motley Fool, etc.)
  3. Deep      — is it a specific article, not a bare homepage? (a "bloomberg.com" cite
                 is not a source an MD will accept)
  4. Covered   — does every synthesized section actually carry a source at all?
                 (catches the "great fact, no citation" problem)

Returns a list of (level, message) tuples — level in {'error','warn'} — plus a one-line
summary. Wired into deliverable_agent.audit_brief; per the workflow it reports always and
blocks only under --strict. Network is best-effort: if the host is offline, liveness is
skipped (and said so) rather than failing the whole brief.
"""

import re
import socket
import urllib.request
import urllib.error
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

try:                                   # run as `python3 agents/deliverable_agent.py` (agents/ on path)
    from sources import TIER_1, TIER_2, TIER_3, tier as _domain_tier, label as _domain_label
except ImportError:                    # imported as a package
    from agents.sources import TIER_1, TIER_2, TIER_3, tier as _domain_tier, label as _domain_label


# Domains that are always acceptable even though they're not in the tiered press registry:
# primary filings, the live-quote source, and curated social. The subject company's own
# domain (its IR/press pages) is added per-run in audit_sources().
_ALWAYS_OK = {
    "sec.gov", "finance.yahoo.com", "x.com", "twitter.com",
    "linkedin.com",   # leadership identity verification (sanctioned by the research spec)
}

# A browser-ish UA — many publishers 403 a bare urllib agent, which would look like a
# dead link when the page is actually fine.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Only these HTTP codes mean a link is actually dead. Everything else — 401/403/429 (paywall),
# 999 (LinkedIn anti-bot), 5xx (transient) — means the server answered, so the URL resolves to
# a live host even if a script can't read the body. Flagging those would be a false positive,
# and a noisy auditor gets ignored. Unreachable host (DNS/conn/timeout) is handled separately.
_DEAD_CODES = {404, 410}


def _norm_domain(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _registered_domain(host: str) -> str:
    """Last two labels — 'investors.planet.com' -> 'planet.com'. Good enough for the
    TLDs this tool sees (no co.uk handling needed for US financial press)."""
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


# Section URLs the workflow explicitly blesses as THE citation (CLAUDE.md: Ramp Data
# "is free and citable as source: ramp.com/data") — never flag these as shallow.
_SHALLOW_OK = {"ramp.com/data"}


def _is_shallow(url: str) -> bool:
    """True if the URL is a bare homepage / section landing page rather than a specific
    article — i.e. no real path and no query that would identify a document."""
    try:
        p = urlparse(url)
    except Exception:
        return False
    if f"{_norm_domain(url)}/{(p.path or '').strip('/')}" in _SHALLOW_OK:
        return False
    path = (p.path or "").strip("/")
    if p.query:                       # ?id=... etc. identifies a document
        return False
    if not path:
        return True
    segments = [s for s in path.split("/") if s]
    # A single short slug like "/news" or "/quote" is a section, not an article.
    if len(segments) == 1 and len(segments[0]) <= 12 and "-" not in segments[0]:
        return True
    return False


def _domain_ok(host: str, subject_domains: set) -> tuple:
    """(ok, tier_or_None). ok=False means untrusted/unknown domain."""
    reg = _registered_domain(host)
    if host in _ALWAYS_OK or reg in _ALWAYS_OK:
        return True, None
    if host in subject_domains or reg in subject_domains:
        return True, None             # company's own IR / press pages
    t = _domain_tier(reg)
    if t == 99:
        t = _domain_tier(host)
    return (t != 99), (t if t != 99 else None)


def _check_live(url: str, timeout: float = 10.0) -> tuple:
    """(state, detail). state in {'ok','broken'}. Tries HEAD then GET (many CDNs reject
    HEAD). A link is 'broken' only on a definitive dead code (404/410) or an unreachable
    host after both attempts; any other server response counts as resolving. Redirects are
    followed by urllib by default."""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method,
                                         headers={"User-Agent": _UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return "ok", r.status
        except urllib.error.HTTPError as e:
            if e.code in _DEAD_CODES:
                return "broken", e.code
            return "ok", e.code        # server answered (paywall/anti-bot/transient) → resolves
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            if method == "GET":        # unreachable after HEAD+GET → dead host
                return "broken", str(getattr(e, "reason", e))[:60]
            continue
        except Exception as e:
            if method == "GET":
                return "broken", str(e)[:60]
            continue
    return "broken", "no response"


def _network_up() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=4).close()
        return True
    except Exception:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=4).close()
            return True
        except Exception:
            return False


# ── Source extraction ──────────────────────────────────────────────────────────

def _sources_of(obj) -> list:
    """Normalize an item's citation(s) into [(name, url)]. Supports a `sources` array
    of {name,url}/{source,sourceUrl} and the legacy singular source/sourceUrl pair."""
    out = []
    for s in (obj.get("sources") or []):
        out.append((s.get("name") or s.get("source") or "", s.get("url") or s.get("sourceUrl") or ""))
    if not out and (obj.get("source") or obj.get("sourceUrl")):
        out.append((obj.get("source") or "", obj.get("sourceUrl") or ""))
    return out


def _iter_sources(profile: dict):
    """Yield (location, name, url) for every citation in the brief."""
    b = profile.get("brief") or {}

    for n in (b.get("recentNews") or []):
        loc = f"news “{str(n.get('headline',''))[:40]}”"
        for nm, url in _sources_of(n):
            yield loc, nm, url

    for c in (b.get("comps") or []):
        if c.get("sourceUrl") or c.get("sources"):
            for nm, url in _sources_of(c):
                yield f"comp {c.get('name','?')}", nm, url

    et = b.get("earningsTakeaways") or {}
    if isinstance(et, dict):
        for nm, url in _sources_of(et):
            yield "earnings takeaways", nm, url
    elif isinstance(et, list):
        for e in et:
            for nm, url in _sources_of(e):
                yield "earnings takeaways", nm, url

    for fld, loc in (("businessOverviewSources", "business overview"),
                     ("productModelSources", "product/revenue model"),
                     ("keyRisksSources", "key risks")):
        for s in (b.get(fld) or []):
            yield loc, (s.get("name") or s.get("source") or ""), (s.get("url") or s.get("sourceUrl") or "")

    for ex in (profile.get("leadership") or []):
        if ex.get("sourceUrl"):
            yield f"leadership {ex.get('name','?')}", ex.get("source",""), ex.get("sourceUrl","")

    for fr in (profile.get("fundingRounds") or []):
        if fr.get("sourceUrl"):
            yield f"funding {fr.get('round', fr.get('date','?'))}", fr.get("source",""), fr.get("sourceUrl","")


# ── Main audit ───────────────────────────────────────────────────────────────

def audit_sources(profile: dict, live: bool = True) -> tuple:
    """Returns (issues, summary). issues: list of (level, message). All source issues are
    'warn' (block only under --strict, per the workflow); the summary is one headline line."""
    profile = profile or {}
    b = profile.get("brief") or {}
    issues = []

    website = (profile.get("website") or "").lower()
    subject_domains = set()
    if website:
        host = _norm_domain(website if website.startswith("http") else "https://" + website)
        if host:
            subject_domains.add(host)
            subject_domains.add(_registered_domain(host))

    # Gather + de-dupe by URL (one liveness hit per unique URL).
    seen = {}                          # url -> list of (location, name)
    no_url = []                        # (location, name) cited by name only
    for loc, name, url in _iter_sources(profile):
        url = (url or "").strip()
        if not url:
            no_url.append((loc, name))
            continue
        seen.setdefault(url, []).append((loc, name))

    # Static checks (domain trust + shallow link) on every unique URL.
    for url in seen:
        host = _norm_domain(url)
        if not host or not re.match(r"^https?://", url):
            issues.append(("warn", f"malformed source URL ({url[:60]}) — {seen[url][0][0]}"))
            continue
        ok, t = _domain_ok(host, subject_domains)
        if not ok:
            issues.append(("warn", f"untrusted source domain '{host}' — not in the registry "
                                   f"({seen[url][0][0]}); prefer a Tier 1/2 publication"))
        elif t == 3:
            issues.append(("warn", f"Tier-3 source '{host}' ({seen[url][0][0]}) — acceptable for "
                                   f"context, confirm with a Tier 1/2 cite where possible"))
        if _is_shallow(url):
            issues.append(("warn", f"shallow source link ({url}) — homepage/section, not a "
                                   f"specific article ({seen[url][0][0]})"))

    # Liveness — parallel, best-effort.
    checked = broken = 0
    if live and seen:
        if not _network_up():
            issues.append(("warn", "offline — skipped live link checking (run again online to "
                                   "verify URLs resolve)"))
        else:
            urls = list(seen)
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(_check_live, urls))
            for url, (state, detail) in zip(urls, results):
                checked += 1
                if state == "broken":
                    broken += 1
                    for loc, _ in seen[url][:1]:
                        issues.append(("warn", f"broken source link (HTTP/err {detail}): {url} — {loc}"))

    # Coverage — synthesized prose sections that assert facts but cite nothing.
    for nm, _ in no_url:
        issues.append(("warn", f"source named but no URL provided ({nm})"))
    if (b.get("businessOverview")) and not b.get("businessOverviewSources"):
        issues.append(("warn", "Business Overview has no source — add the reporting/IR pages it draws on"))
    if (b.get("productModel")) and not b.get("productModelSources"):
        issues.append(("warn", "Product & Revenue Model has no source"))
    et = b.get("earningsTakeaways") or {}
    if et and not (et.get("sources") if isinstance(et, dict) else any(_sources_of(e) for e in et)):
        issues.append(("warn", "Earnings & Key Metrics has no source — cite the earnings "
                               "release / 10-Q / transcript the numbers come from"))
    if (b.get("keyRisks")) and not b.get("keyRisksSources"):
        issues.append(("warn", "Key Risks section has no source"))

    n_unique = len(seen)
    parts = [f"{n_unique} unique source link(s)"]
    if live and checked:
        parts.append(f"{checked} live-checked, {broken} broken")
    n_untrusted = sum(1 for lvl, m in issues if "untrusted source domain" in m)
    n_shallow = sum(1 for lvl, m in issues if "shallow source link" in m)
    if n_untrusted:
        parts.append(f"{n_untrusted} untrusted")
    if n_shallow:
        parts.append(f"{n_shallow} shallow")
    summary = "; ".join(parts)
    return issues, summary
