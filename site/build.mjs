#!/usr/bin/env node
// Atlas site build — assembles the static coverage viewer into site/dist.
//
// Emits TWO views from data-dumps:
//   • dist/        → PUBLIC demo: only DEMO_IDS (e.g. Decagon + Broadcom), no auth
//   • dist/full/   → FULL coverage: every company, gated by middleware.js (SITE_PASSWORD)
// Each view gets its own index.json + index.html + briefs/, so the shared template's
// relative fetches ("index.json", "briefs/…") just work in either directory. A company's
// brief is only published into a view that includes it, so private briefs never land in
// the public root.
//
// Zero dependencies. Run from repo root: `node site/build.mjs`. Vercel runs the same
// (project repo root (default), so the build command is just `node site/build.mjs`).

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');          // repo root (data-dumps lives here)
const DATA = path.join(ROOT, 'data-dumps');
const OUT = path.join(__dirname, 'dist');            // site/dist (published)
const TEMPLATE = path.join(__dirname, 'template', 'index.html');

// Companies shown on the PUBLIC demo at the site root. Everything else is reachable
// only via the gated /full view. Add more demo ids over time. (Folder ids: Broadcom = "AVGO".)
const DEMO_IDS = ['decagon', 'AVGO', 'GOOGL', 'AAPL', 'MSFT'];

// Linked from the demo banner's "Get Atlas" CTA so visitors can deploy their own.
const REPO_URL = 'https://github.com/Agrimd15/atlas';

const readJSON = (p) => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return null; } };
const ensureDir = (p) => fs.mkdirSync(p, { recursive: true });

// Choose the right brief when a run folder has more than one HTML file.
function pickBrief(files, id) {
  if (!files.length) return null;
  const lid = id.toLowerCase();
  return files.find((f) => f.toLowerCase().includes(lid))      // matches the folder id
      || files.find((f) => /brief/i.test(f))                   // any *brief*.html
      || files.slice().sort()[0];                              // fallback: first
}

// Bare domain (no protocol, no www, no path) — the client builds logo URLs from this.
function cleanDomain(profile) {
  const host = (profile.website || '')
    .replace(/^https?:\/\//, '').replace(/\/.*$/, '').replace(/^www\./, '').trim();
  return host || null;
}

// Honor an explicit faviconUrl from the profile, but drop the deprecated Clearbit
// logo API — it no longer serves reliably, so we let the client resolve from domain.
function explicitFavicon(profile) {
  const u = profile.faviconUrl;
  return u && !/clearbit\.com/i.test(u) ? u : null;
}

const cap = (s, n = 220) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s);
function firstSentence(s) {
  s = String(s || '').replace(/\s+/g, ' ').trim();
  const m = s.match(/^.*?[.!?](\s|$)/);
  return (m ? m[0] : s).trim();
}

// Card blurb: prefer the curated one-liner, else the lead sentence of the brief's
// business overview, else the business model / market context — all real data,
// never invented. Keeps cards from reading "No description yet".
function blurbFor(profile) {
  const sd = (profile.shortDescription || '').trim();
  if (sd) return cap(sd);
  const bo = profile.brief && profile.brief.businessOverview;
  const lead = Array.isArray(bo) ? (bo[0] || '') : (bo || '');
  if (lead) return cap(firstSentence(lead));
  const bm = (profile.businessModel || '').trim();
  if (bm) return cap(firstSentence(bm));
  return cap((profile.marketContext || '').trim());
}

console.log('▶ Atlas site build');
fs.rmSync(OUT, { recursive: true, force: true });

// ── Scan every company once. Record brief SOURCE paths; copy per-view later. ──
const companies = [];
const ids = fs.existsSync(DATA)
  ? fs.readdirSync(DATA, { withFileTypes: true }).filter((d) => d.isDirectory()).map((d) => d.name)
  : [];

for (const id of ids.sort()) {
  const profile = readJSON(path.join(DATA, id, 'profile.json'));
  if (!profile) continue;

  const runsDir = path.join(DATA, id, 'runs');
  const runs = [];
  if (fs.existsSync(runsDir)) {
    const dates = fs.readdirSync(runsDir, { withFileTypes: true })
      .filter((d) => d.isDirectory()).map((d) => d.name).sort().reverse(); // newest first
    for (const date of dates) {
      const rdir = path.join(runsDir, date);
      const files = fs.readdirSync(rdir);
      const chosen = pickBrief(files.filter((f) => /\.html$/i.test(f)), id);
      if (!chosen) continue;
      const pdfs = files.filter((f) => /\.pdf$/i.test(f));
      const pdf = pdfs.find((f) => f.toLowerCase().includes(id.toLowerCase())) || pdfs[0];
      runs.push({
        date,
        srcHtml: path.join(rdir, chosen),
        srcPdf: pdf ? path.join(rdir, pdf) : null,
        href: `briefs/${id}/${date}.html`,
        pdf: pdf ? `briefs/${id}/${date}.pdf` : null,
      });
    }
  }

  companies.push({
    id,
    name: profile.name || id,
    ticker: profile.ticker || null,
    isPublic: !!(profile.ticker && /^[A-Z.]{1,6}$/.test(profile.ticker)),
    shortDescription: blurbFor(profile),
    verticals: Array.isArray(profile.verticals) ? profile.verticals : [],
    website: profile.website || null,
    domain: cleanDomain(profile),
    faviconUrl: explicitFavicon(profile),
    isStarred: !!profile.isStarred,
    latestRunDate: runs.length ? runs[0].date : (profile.lastRunDate || null),
    runs,
  });
}

// Starred first, then most-recent run first.
companies.sort((a, b) =>
  (Number(b.isStarred) - Number(a.isStarred)) ||
  String(b.latestRunDate || '').localeCompare(String(a.latestRunDate || '')));

// ── Emit one view: copy its briefs, write its manifest + the shared template. ──
function emitView(outDir, list, opts = {}) {
  ensureDir(path.join(outDir, 'briefs'));
  for (const c of list) {
    for (const r of c.runs) {
      ensureDir(path.join(outDir, 'briefs', c.id));
      fs.copyFileSync(r.srcHtml, path.join(outDir, 'briefs', c.id, `${r.date}.html`));
      if (r.srcPdf) fs.copyFileSync(r.srcPdf, path.join(outDir, 'briefs', c.id, `${r.date}.pdf`));
    }
  }
  // Published manifest carries only the web-facing run fields (no source paths).
  const clean = list.map((c) => ({
    ...c,
    runs: c.runs.map(({ date, href, pdf }) => ({ date, href, pdf })),
  }));
  const manifest = {
    generatedAt: new Date().toISOString(),
    demo: !!opts.demo,
    repoUrl: opts.demo ? REPO_URL : undefined,
    count: clean.length,
    latestRunDate: clean.reduce((m, c) => (c.latestRunDate && c.latestRunDate > m ? c.latestRunDate : m), ''),
    companies: clean,
  };
  fs.writeFileSync(path.join(outDir, 'index.json'), JSON.stringify(manifest, null, 2));
  fs.copyFileSync(TEMPLATE, path.join(outDir, 'index.html'));
  return clean.reduce((n, c) => n + c.runs.length, 0);
}

// Demo subset (keeps the sorted order), case-insensitive id match.
const demoSet = new Set(DEMO_IDS.map((s) => s.toLowerCase()));
const demo = companies.filter((c) => demoSet.has(c.id.toLowerCase()));

ensureDir(OUT);
const fullBriefs = emitView(path.join(OUT, 'full'), companies);              // /full → gated, everything
const demoBriefs = emitView(OUT, demo, { demo: true });                      // /     → public demo

// Surface a missing demo id so a typo doesn't silently ship an empty demo.
const found = new Set(demo.map((c) => c.id.toLowerCase()));
const missing = [...demoSet].filter((d) => !found.has(d));
if (missing.length) console.log(`⚠ demo id(s) not found in data-dumps: ${missing.join(', ')}`);

console.log(`✓ demo: ${demo.length} companies, ${demoBriefs} briefs → site/dist  (public)`);
console.log(`✓ full: ${companies.length} companies, ${fullBriefs} briefs → site/dist/full  (gated)`);
