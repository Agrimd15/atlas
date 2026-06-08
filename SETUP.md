# Deploy your own Atlas

Atlas turns a company name typed into Claude Code into a banker-grade brief, saved to your own
coverage database and published as a private, password-gated site. This takes you from clone to a
live site in ~15 minutes. **Fastest path: open this repo in Claude Code and run `/setup`** - it does
all of the below interactively. Here's the manual version.

## What you'll end up with
- A private coverage database (`data-dumps/`) that grows as you research companies.
- A self-contained **HTML + PDF brief** per company.
- A static coverage site with two views: a **public demo** at `/` and your **full coverage** at
  `/full`, behind a password.

## Prerequisites
- **[Claude Code](https://claude.com/claude-code)** - the research agents run inside it.
- **Node.js 18+** and **Python 3.9+** - for the site build and brief/PDF generation.
- **Google Chrome / Chromium** - used to render the PDF (no extra setup).
- *(optional)* a free **FMP API key** ([financialmodelingprep.com](https://financialmodelingprep.com)) for live comps. yfinance works with no key.

## 1. Clone
```bash
git clone https://github.com/<you>/atlas.git
cd atlas
pip3 install yfinance requests
```

## 2. Configure (optional)
```bash
cp .env.example .env      # add FMP_API_KEY if you have one
```

## 3. Make the coverage yours
This repo ships a handful of sample companies under `data-dumps/` (the public demo set is whatever you list in `DEMO_IDS` - see step 5). To start clean:
```bash
rm -rf data-dumps/*/      # removes sample companies, keeps the folder
```
Companies you research are gitignored by default, so your private coverage never lands in a public fork.

## 4. Research a company - the core loop
In Claude Code, from the repo root:
```
/atlas SNOW
```
(or just type a company name). Four parallel agents run, write `data-dumps/SNOW/profile.json`, and
generate an HTML + PDF brief in the run folder. Every number is pulled live and dated.

## 5. Choose your public demo
Edit `DEMO_IDS` at the top of [`site/build.mjs`](site/build.mjs) - only these companies appear on the
public `/` view; everything else stays behind the password at `/full`.
```js
const DEMO_IDS = ['CRM', 'EGAN', 'NTSK'];   // folder ids: ticker for public cos, kebab-slug for private
```

## 6. Build & preview locally
```bash
node site/build.mjs
python3 -m http.server 4321 --directory site/dist   # → http://localhost:4321
```

## 7. Deploy to Vercel
1. Push your repo to GitHub.
2. Vercel → **Add New → Project** → import it.
3. **Leave Root Directory at the repo root**; Framework = **Other** (build command + output dir come
   from `vercel.json` automatically).
4. *(recommended)* add env var **`SITE_PASSWORD`** = your password - gates `/full`; the demo at `/` stays public.
5. **Deploy.** Vercel auto-issues HTTPS.

Every push to `main` redeploys. To add a company later: `/atlas TICKER` → `git push` → live in ~1 minute.

## 8. Custom domain (optional)
Vercel → Project → **Settings → Domains** → add your domain, then add the DNS record Vercel shows at
your registrar. SSL is automatic.

## Security & rules
- `vercel.json` ships with HSTS, a Content-Security-Policy, and other hardening headers (A/A+ on securityheaders.com).
- `/full` is gated by `SITE_PASSWORD` (HTTP Basic Auth over HTTPS); the public demo exposes only your `DEMO_IDS`.
- **Public information only** - no MNPI, client names, or deal data. Every output is **DRAFT** until you review it.
