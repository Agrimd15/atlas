#!/usr/bin/env python3
"""
Atlas → Notion sync.

Pushes an Atlas coverage run into a Notion database (e.g. a "tech startup tracker"),
upserting one row per company and linking back to the published brief on the
coverage site. The row carries the company name, description, competitors and
founders pulled from `data-dumps/<ID>/profile.json`; the link points at the live
brief at <SITE>/full/briefs/<ID>/<DATE>.html. Re-running updates the existing row
in place (matched on the company name), so daily runs never duplicate it.

Zero extra dependencies — uses only the Python standard library (urllib), so it
runs anywhere the rest of Atlas does.

Setup (one time):
  1. Create an internal integration at https://www.notion.so/my-integrations and
     copy its secret. Put it in .env as  NOTION_TOKEN=secret_xxx
  2. Open your Notion database → ••• menu → Connections → add the integration so
     it can read & write the database.
  3. Copy the database id (the 32-char hash in the database URL) into .env as
     NOTION_DB_ID=...  and set ATLAS_SITE_URL=https://your-site.vercel.app
     so the brief links resolve.

Run:
  python3 agents/notion_sync.py SNOW
  python3 agents/notion_sync.py SNOW --body      # also write a summary into the page
  python3 agents/notion_sync.py SNOW --dry-run   # print what would be sent, send nothing
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ── Load .env from the Atlas tool root (same loader the other agents use) ──────
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# data-dumps lives next to the tool by default; ATLAS_DATA_ROOT overrides it (plugin mode).
_DATA_ROOT = Path(os.environ["ATLAS_DATA_ROOT"]) if os.environ.get("ATLAS_DATA_ROOT") else Path(__file__).parent.parent
DATA_DUMPS = _DATA_ROOT / "data-dumps"

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN", "").strip()


def _clean_db_id(raw):
    """Tolerate a pasted database URL, slug prefix, or ?v=… view suffix — pull out the id.
    Accepts a bare 32-char hex id or a dashed 8-4-4-4-12 UUID; returns the last one found."""
    raw = (raw or "").strip().split("?", 1)[0]   # drop any ?v=… view query
    matches = re.findall(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                         r"|[0-9a-fA-F]{32}", raw)
    return matches[-1] if matches else raw


NOTION_DB_ID   = _clean_db_id(os.environ.get("NOTION_DB_ID", ""))
ATLAS_SITE_URL = os.environ.get("ATLAS_SITE_URL", "").rstrip("/")
NOTION_VERSION = "2022-06-28"
API = "https://api.notion.com/v1"


# ── Notion REST helper (stdlib only) ──────────────────────────────────────────
def _api(method, path, payload=None):
    url = f"{API}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {NOTION_TOKEN}")
    req.add_header("Notion-Version", NOTION_VERSION)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise SystemExit(f"✗ Notion API {e.code} on {method} {path}:\n  {body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"✗ Could not reach Notion ({e.reason}).")


# ── Field extraction from profile.json ────────────────────────────────────────
def latest_run_date(folder_id, profile):
    runs_dir = DATA_DUMPS / folder_id / "runs"
    if runs_dir.exists():
        dates = sorted(d.name for d in runs_dir.iterdir() if d.is_dir())
        if dates:
            return dates[-1]
    return profile.get("lastRunDate")


def description_bullets(profile, max_n=2):
    """1-2 bullet lines for the Description column. Splits shortDescription into
    sentences, keeps the first max_n, and renders each as a `• ` line."""
    raw = (profile.get("shortDescription") or "").strip()
    if not raw:
        return ""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw) if p.strip()][:max_n]
    return "\n".join(f"• {p}" for p in parts)


def founders_from(profile):
    out = []
    for p in profile.get("leadership", []) or []:
        title = (p.get("title") or "").lower()
        if "founder" in title and p.get("name"):
            out.append(p["name"])
    return out


def is_public(profile):
    stage = (profile.get("stage") or "").lower()
    if "public" in stage:
        return True
    if "private" in stage:
        return False
    return bool((profile.get("ticker") or "").strip())


def latest_round(profile):
    """The most recent funding round (max by date string), or None."""
    rounds = profile.get("fundingRounds") or []
    if not rounds:
        return None
    return max(rounds, key=lambda r: r.get("date") or "")


def stage_label(profile, public):
    """Public/IPO for listed names; the latest series for private ones."""
    if public:
        return "Public"
    r = latest_round(profile)
    if r and r.get("round"):
        # Trim editorial noise: "Seed / early-stage (a16z…)" → "Seed".
        return r["round"].split(" / ")[0].split(" (")[0].strip()
    return "Private"


def revenue_label(profile, public):
    """LTM revenue for public names; latest reported figure for private (often blank)."""
    t = profile.get("trading") or {}
    if public and t.get("totalRevenueLTM"):
        return f"{t['totalRevenueLTM']} (LTM)"
    rh = profile.get("revenueHistory") or []
    if rh:
        last = rh[-1]
        if last.get("label"):
            yr = last.get("year")
            return f"{last['label']} ({yr})" if yr else last["label"]
    return None


def valuation_label(profile, public):
    """Market cap for public names; last reported post-money for private ones."""
    t = profile.get("trading") or {}
    if public and t.get("marketCap"):
        return f"{t['marketCap']} (mkt cap)"
    r = latest_round(profile)
    pm = (r or {}).get("postMoneyValuationFormatted")
    if pm and pm.strip().lower() not in ("undisclosed", "not disclosed", ""):
        return pm
    lkv = (profile.get("lastKnownValuation") or "").strip()
    if lkv and "not disclosed" not in lkv.lower():
        return lkv
    return None


def brief_url(folder_id, run_date):
    """Public URL of the brief on the coverage site, if ATLAS_SITE_URL is set."""
    if not (ATLAS_SITE_URL and run_date):
        return None
    return f"{ATLAS_SITE_URL}/full/briefs/{folder_id}/{run_date}.html"


def gather(folder_id):
    profile_path = DATA_DUMPS / folder_id / "profile.json"
    if not profile_path.exists():
        raise SystemExit(f"✗ No profile at {profile_path} — run Atlas for {folder_id} first.")
    profile = json.loads(profile_path.read_text())
    run_date = latest_run_date(folder_id, profile)
    comps = profile.get("competitors") or []
    public = is_public(profile)
    return {
        "name": profile.get("name") or folder_id,
        "ticker": profile.get("ticker"),
        "description": description_bullets(profile),
        "competitors": [c if isinstance(c, str) else str(c) for c in comps],
        "founders": founders_from(profile),
        "website": profile.get("website"),
        "type": "Public" if public else "Private",
        "stage": stage_label(profile, public),
        "revenue": revenue_label(profile, public),
        "valuation": valuation_label(profile, public),
        "run_date": run_date,
        "url": brief_url(folder_id, run_date),
        "_profile": profile,
    }


# ── Map our values onto whatever properties the database actually has ──────────
# We look up each target column by name (case-insensitive) and format the value to
# match the column's REAL type, so the sync works whether "Competitors" is a text
# field or a multi-select, etc. Unknown columns are skipped silently.
def _parse_money(s):
    """Turn a formatted money string into a raw USD number for Number columns.
    '$152.1B (mkt cap)' → 152100000000.0, '$850M' → 850000000.0. None if no figure."""
    if s is None:
        return None
    m = re.search(r"\$?\s*([0-9][0-9,]*\.?[0-9]*)\s*([KMBT])?", str(s), re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", ""))
    mult = {"k": 1e3, "m": 1e6, "b": 1e9, "t": 1e12}.get((m.group(2) or "").lower(), 1)
    return num * mult


def _format_value(prop_type, value):
    if value in (None, "", []):
        return None
    if prop_type == "title":
        return {"title": [{"text": {"content": str(value)}}]}
    if prop_type == "rich_text":
        text = ", ".join(value) if isinstance(value, list) else str(value)
        return {"rich_text": [{"text": {"content": text[:2000]}}]}
    if prop_type == "url":
        return {"url": str(value)}
    if prop_type == "number":
        num = value if isinstance(value, (int, float)) else _parse_money(value)
        return {"number": num} if num is not None else None
    if prop_type == "select":
        v = value[0] if isinstance(value, list) else value
        return {"select": {"name": str(v)[:100]}}
    if prop_type == "multi_select":
        items = value if isinstance(value, list) else [value]
        return {"multi_select": [{"name": str(v)[:100]} for v in items if v]}
    if prop_type == "date":
        return {"date": {"start": str(value)}}
    return None


def build_properties(schema, data):
    """schema = Notion DB `properties` dict. Returns properties payload + the title prop name."""
    by_lower = {name.lower(): (name, meta["type"]) for name, meta in schema.items()}
    title_name = next((n for n, m in schema.items() if m["type"] == "title"), None)

    # Candidate column-name → value. First match by name wins. The URL goes to whichever
    # URL-typed column exists (preferring obvious names) so users can call it anything.
    # Many aliases per field so the sync finds the column whatever you named it.
    # Exact (case-insensitive) name match keeps "Revenue" from grabbing "Revenue Growth".
    wants = {
        "company name": data["name"],
        "name": data["name"],
        "description": data["description"],
        "competitors": data["competitors"],
        "founders": data["founders"],
        "ticker": data["ticker"],
        "website": data["website"],
        "type": data["type"],
        "public/private": data["type"],
        "public / private": data["type"],
        "ownership": data["type"],
        "stage": data["stage"],
        "series": data["stage"],
        "series/ipo": data["stage"],
        "series / ipo": data["stage"],
        "round": data["stage"],
        "revenue": data["revenue"],
        "ltm revenue": data["revenue"],
        "arr/revenue": data["revenue"],
        "valuation": data["valuation"],
        "market cap": data["valuation"],
        "last valuation": data["valuation"],
        "last updated": data["run_date"],
    }

    props = {}
    for col_lower, value in wants.items():
        if col_lower in by_lower:
            real_name, ptype = by_lower[col_lower]
            formatted = _format_value(ptype, value)
            if formatted is not None and real_name not in props:
                props[real_name] = formatted

    # Brief link → a URL column. Prefer a sensibly-named one, else the first URL column.
    if data["url"]:
        url_cols = [(n, m["type"]) for n, m in schema.items() if m["type"] == "url"]
        preferred = next((n for n, _ in url_cols
                          if any(k in n.lower() for k in ("brief", "atlas", "report", "link"))), None)
        target = preferred or (url_cols[0][0] if url_cols else None)
        if target:
            props[target] = {"url": data["url"]}

    return props, title_name


# ── Summary blocks for the page body (written on first create only) ───────────
def _para(text):
    return {"object": "block", "type": "paragraph",
            "paragraph": {"rich_text": [{"text": {"content": text[:2000]}}]}}


def _heading(text):
    return {"object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"text": {"content": text}}]}}


def _bullet(text):
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": [{"text": {"content": text[:2000]}}]}}


def summary_blocks(data):
    p = data["_profile"]
    brief = p.get("brief") or {}
    blocks = []
    overview = brief.get("businessOverview")
    if isinstance(overview, list):
        overview = " ".join(overview)
    overview = overview or data["description"]
    if overview:
        blocks += [_heading("Business overview"), _para(overview)]
    bullets = brief.get("slideBullets") or []
    if bullets:
        blocks.append(_heading("Slide-ready bullets"))
        blocks += [_bullet(b if isinstance(b, str) else str(b)) for b in bullets[:5]]
    if data["url"]:
        blocks.append(_para(f"Full brief: {data['url']}"))
    return blocks


# ── Upsert ────────────────────────────────────────────────────────────────────
def find_page(title_name, name):
    res = _api("POST", f"/databases/{NOTION_DB_ID}/query", {
        "filter": {"property": title_name, "title": {"equals": name}},
        "page_size": 1,
    })
    results = res.get("results", [])
    return results[0]["id"] if results else None


def is_configured():
    """True when both credentials are present — used to auto-skip when unset."""
    return bool(NOTION_TOKEN and NOTION_DB_ID)


def sync(folder_id, write_body=False):
    """Upsert one company into the Notion DB. Raises SystemExit on API/config errors.
    Returns a one-line status string."""
    missing = [k for k, v in (("NOTION_TOKEN", NOTION_TOKEN), ("NOTION_DB_ID", NOTION_DB_ID)) if not v]
    if missing:
        raise SystemExit(f"✗ Missing env: {', '.join(missing)} — see the setup notes in this file's docstring.")

    data = gather(folder_id)
    db = _api("GET", f"/databases/{NOTION_DB_ID}")
    schema = db.get("properties", {})
    props, title_name = build_properties(schema, data)
    if not title_name:
        raise SystemExit("✗ That database has no title (Name) column — can't match rows.")

    page_id = find_page(title_name, data["name"])
    link = data["url"] or "no link — set ATLAS_SITE_URL"
    if page_id:
        _api("PATCH", f"/pages/{page_id}", {"properties": props})
        return f"✓ Updated “{data['name']}” in Notion  ({link})"
    payload = {"parent": {"database_id": NOTION_DB_ID}, "properties": props}
    if write_body:
        payload["children"] = summary_blocks(data)
    _api("POST", "/pages", payload)
    return f"✓ Created “{data['name']}” in Notion  ({link})"


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        raise SystemExit("usage: python3 agents/notion_sync.py FOLDER_ID [--body] [--dry-run]")
    folder_id = args[0]
    write_body = "--body" in flags
    dry = "--dry-run" in flags

    if dry:
        data = gather(folder_id)
        print(f"DRY RUN — would upsert “{data['name']}” into Notion DB {NOTION_DB_ID or '(unset)'}")
        print(json.dumps({k: v for k, v in data.items() if k != "_profile"}, indent=2))
        return

    print(sync(folder_id, write_body=write_body))


if __name__ == "__main__":
    main()
