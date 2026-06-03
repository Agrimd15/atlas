# Atlas - Local Viewer: Daily Usage Guide

> **Scope:** this covers the **local viewer** component of Atlas (`atlas.html` + `backend/`) - the
> single-file browser app for capturing and browsing companies by hand. For the automated
> research → brief → publish pipeline, see the [Atlas README](README.md) and the root
> [`CLAUDE.md`](../../CLAUDE.md).

This is the practical "how I actually use this every week" guide.

## First 10 Minutes (Setup)

1. Open `atlas.html` (keep it in your bookmarks bar or pin the tab)
2. Hit `N` and add 5-8 companies you already know well from your internship or current coverage list
3. For each one:
   - Tag 1-2 verticals
   - Write a tight one-liner
   - Paste or write 3-4 sentences on the business model
   - Add 3-5 real competitors you actually talk about
4. Star the 3-4 that matter most right now

## The Core Daily Loop

### When you hear a new name (in a meeting, on a call, in the news)

1. `N` → type name + website (if you have it)
2. Immediately add the 1-2 verticals you think it belongs in
3. Run **Quick Research** (the big indigo button)
4. It will open:
   - Valuation/funding search
   - Competitor search
   - PitchBook (pre-filled)
   - Crunchbase
   - Substack coverage
   - Recent news
   - LinkedIn
5. As you scan the tabs, fill in the fields you can in Atlas (you'll get faster at this)

### Before a company meeting or prep session

1. Click the company in your list
2. Read your own notes first (this is the whole point)
3. If the notes feel stale, hit Quick Research again and update the valuation / recent developments
4. Extract colors if you need to drop the logo into a deck

### End of week / Sunday night (Knowledge compounding)

- Open Atlas
- Look at the companies you touched that week
- Spend 8-12 minutes tightening the business model descriptions and notes
- This is where the real edge comes from - your future self will thank you

## Vertical Strategy

The preset verticals are deliberately a bit coarse. Use them as buckets, not precise taxonomy.

Recommended approach:
- Use the broad ones for filtering ("show me all my AI Infrastructure names")
- Use custom tags on the company itself for more precision (e.g. "GPU Cloud", "Inference Optimization", "Agent Frameworks")

You can always rename or consolidate later via export + edit + reimport.

## Branding / PPT Workflow

1. When you first add a company, try to get a decent logo (either upload a high-res one or at least have the favicon)
2. Click "Extract Colors" - this is shockingly useful for making clean decks fast
3. Click any swatch to copy the hex
4. For important companies, manually upload a proper logo (drag from their site or press kit) - the color extraction gets much better

## Data Hygiene Rules

- **Never** put client names or deal names in here
- Keep valuation numbers as "best public knowledge" - always verify before using in real materials
- If something feels sensitive, don't write it. Use the notes field for your own synthesis instead of raw quotes from calls.

## Backup Discipline (Important)

Every couple of weeks:
1. Click **Export**
2. Save the JSON somewhere sensible (this repo is fine, or your personal Dropbox/iCloud)
3. Optional: commit it with a date tag so you have history

If your laptop dies, you want that file.

## Future Evolution (when you need it)

The current single-file version is intentionally simple so you actually use it.

When you start feeling the limits, the logical next steps are:

1. **Local desktop app** (Tauri or Electron) - data lives as real files on disk instead of localStorage
2. **Run it on your home desktop** + access via Tailscale / ngrok / Cloudflare tunnel (this solves the "access from anywhere" problem without cloud)
3. Turn the JSON exports into input for small research agents (this is the real long-term vision)

## Pro Tips From Early Use

- The Quick Research button is the highest-ROI feature. Use it aggressively.
- The competitor field is underrated - being able to see "who else is in this bucket" at a glance is very useful in coverage meetings.
- Color extraction has saved me real time in decks. Do it early for any name you think might end up in a client presentation.
- Don't over-invest in perfect notes on day one. The value compounds when you come back and update them after the second and third time you touch the company.

---

This tool only works if you actually use it for real companies you care about. Start small. Add the names that are actually showing up in your week.

Welcome to the job. Let's make the research part less painful.