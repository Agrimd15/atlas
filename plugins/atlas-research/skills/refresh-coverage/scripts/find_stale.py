#!/usr/bin/env python3
"""
find_stale.py — list Atlas coverage whose latest run is older than a threshold.

Deterministic and LLM-free: this is the cheap "what needs refreshing" scan that
keeps the refresh skill from burning tokens just to figure out what's stale.

For each company it reports the last run date, age in days, whether it's public,
the comp ticker set (so the refresh can re-pull the SAME peer group), and the
newest SEC filing date already on record (so the skill can later tell, for ~0
tokens, whether a NEW earnings filing has appeared since the last run).

Usage:
    python3 find_stale.py [--days N] [--today YYYY-MM-DD] [--data-dumps PATH] [--all]

    --days N         staleness threshold in days (default 7)
    --today          override "today" (default: system date) — handy for testing
    --data-dumps     path to the coverage dir (default: ./data-dumps)
    --all            list every company with its age, not just the stale ones

Output: a JSON array on stdout, sorted oldest-first:
    [{ "id", "lastRunDate", "ageDays", "isPublic", "ticker",
       "compTickers", "newestKnownFilingDate", "stale" }, ...]
"""
import os, json, re, argparse, datetime, sys


def _latest_run_date(runs_dir):
    if not os.path.isdir(runs_dir):
        return None
    dates = []
    for d in os.listdir(runs_dir):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
            try:
                dates.append(datetime.date.fromisoformat(d))
            except ValueError:
                pass
    return max(dates) if dates else None


def _newest_filing_date(runs_dir, last_run):
    """Newest SEC filingDate recorded in the latest run's data.json, if any."""
    if not last_run:
        return None
    data = os.path.join(runs_dir, last_run.isoformat(), "data.json")
    try:
        d = json.load(open(data))
    except Exception:
        return None
    # secFilings appears either as {"filings": [...]} or as a bare list across runs.
    sec = d.get("secFilings") if isinstance(d, dict) else None
    if isinstance(sec, dict):
        filings = sec.get("filings") or []
    elif isinstance(sec, list):
        filings = sec
    else:
        filings = []
    dates = []
    for f in filings:
        fd = f.get("filingDate")
        if fd and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fd):
            dates.append(fd)
    return max(dates) if dates else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--today", default=None)
    ap.add_argument("--data-dumps", default="data-dumps")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.date.today())
    dd = args.data_dumps
    if not os.path.isdir(dd):
        print(json.dumps({"error": f"data-dumps not found at {dd}"}))
        sys.exit(1)

    rows = []
    for cid in sorted(os.listdir(dd)):
        cdir = os.path.join(dd, cid)
        if not os.path.isdir(cdir):
            continue
        runs_dir = os.path.join(cdir, "runs")
        last = _latest_run_date(runs_dir)
        if not last:
            continue
        age = (today - last).days

        ticker, comps = "", []
        try:
            p = json.load(open(os.path.join(cdir, "profile.json")))
            ticker = (p.get("ticker") or "").strip()
            comps = [c.get("ticker") for c in (p.get("brief", {}).get("comps") or [])
                     if c.get("ticker")]
        except Exception:
            pass
        is_public = bool(re.fullmatch(r"[A-Za-z][A-Za-z.\-]{0,5}", ticker))

        rows.append({
            "id": cid,
            "lastRunDate": last.isoformat(),
            "ageDays": age,
            "isPublic": is_public,
            "ticker": ticker,
            "compTickers": comps,
            "newestKnownFilingDate": _newest_filing_date(runs_dir, last),
            "stale": age >= args.days,
        })

    rows.sort(key=lambda r: r["ageDays"], reverse=True)
    out = rows if args.all else [r for r in rows if r["stale"]]
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
