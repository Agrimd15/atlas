# Alfred Design Language — Institutional Light

The design register for all Alfred deliverables: HTML briefs, the PDF print, the coverage
site, and any future dashboards. This codifies the **sell-side research note** look the
brief actually ships: paper-white ground, navy structure, crimson signals, serif masthead.
All UI in this repo must comply. Do not deviate.

> History: the original dark "Neo Kinpaku" (gold-on-lacquer) spec is retired — it read as a
> dashboard, not a research note, and printed poorly. It survives in git history if ever needed.

---

## Aesthetic Register

**Institutional research note.** The reference is a bulge-bracket equity research PDF, not a
SaaS dashboard.

- Paper-white surfaces. Ink-dark text. No dark mode.
- **Navy** is the structural accent: values, links, table chrome, the platform node.
- **Crimson** is the signal accent: section eyebrows, the wordmark, DRAFT, risk.
- **Green** marks positive metrics only. Never decoration.
- Serif voice for the company masthead and pull-quotes; neutral sans for everything else.
- Hairlines structure the page. Density over decoration. Print is a first-class target.

---

## Color Tokens

Use these exact values (they are the `--ks-*` custom properties in `deliverable_agent.py`).
Do not hand-type other hex values.

```css
/* Surfaces */
--ks-lacquer:      #ffffff;   /* paper / page ground */
--ks-lacquer-deep: #ffffff;   /* header ground */
--ks-raised:       #f7f9fb;   /* cards, bands */
--ks-graphite:     #f1f4f8;   /* stat strip, TOC, callout fills */
--ks-graphite-2:   #eef1f6;   /* module fill, hover */

/* Structure (navy family) */
--ks-kinpaku:      #13315c;   /* primary structural accent: values, badges, table rules */
--ks-kinpaku-pale: #1f4d86;   /* links, tickers */
--ks-kinpaku-rich: #102a4d;
--ks-kinpaku-deep: #0c2140;

/* Signals */
--ks-accent:       #b3122b;   /* crimson: section eyebrows, wordmark, lede label */
--ks-vermilion:    #b3122b;   /* crimson: DRAFT, risk markers, negative values */
--ks-patina:       #0a7d4d;   /* green: positive metrics, growth, live markers */

/* Text */
--ks-champagne:    #15181f;   /* headings ink */
--ks-body:         #2a2f37;   /* body copy */
--ks-muted:        #3d434f;   /* secondary copy */
--ks-faint:        #727a89;   /* labels, captions, metadata */

/* Hairlines */
--ks-rule:         #dce0e7;   /* neutral dividers */
--ks-rule-strong:  #c2c8d2;   /* emphasized rules (axes, footer top) */

/* Type + motion */
--ks-serif:        Georgia, "Iowan Old Style", "Times New Roman", serif;
--ks-ease:         cubic-bezier(0.2, 0.8, 0.2, 1);
```

(The legacy `--ks-*` token names are kept so older templates keep rendering; the values are
the institutional palette above.)

---

## Typography

| Role | Family | Use |
|------|--------|-----|
| Masthead / lede | Georgia (serif stack) | Company name, "In one sentence" lede, slide-kit name |
| Body / UI | Arial / Helvetica | Everything else: body, labels, tables, values |
| Numerals | `font-variant-numeric: tabular-nums` (set globally) | All figures align vertically |

### Scale

| Level | Size | Weight | Notes |
|-------|------|--------|-------|
| Masthead | clamp(1.9rem, 3.4vw, 2.5rem) | 700 | Serif, ink |
| Lede ("In one sentence") | 17.5px | 400 | Serif, ink |
| Hero value | 1.5rem (1.1rem long) | 700 | Navy; one line, shrink don't wrap |
| Metric value | 1.15rem (0.95rem long) | 700 | Navy (green when positive-keyed) |
| Body | 14–15.5px | 400 | line-height 1.55–1.7 |
| Eyebrow / label | 9–10px | 600–700 | uppercase, tracked 0.10–0.20em |
| Table header | 9px | 700 | uppercase, tracked; units in a `.th-unit` sub-line |
| Caption / source row | 9.5–10.5px | 400 | faint |

### Typography Rules

1. **Serif only at masthead/lede size.** Never set serif below ~17px — it's the note's voice, not a body font.
2. **Tracked uppercase labels are short.** System markers only, never sentences.
3. **Numbers never wrap.** A long value shrinks (`.long`) or the layout is wrong.
4. **Prose has a measure.** Body paragraphs and bullet lists cap at ~920px (~75ch).
5. **One date, stated once.** The as-of anchor band dates the whole trading strip; individual
   figures carry a tag only when their window differs.

---

## Spacing & Radii

Spacing: 8 / 16 / 24 / 32 / 48px steps; sections pad 24px vertical, 40px horizontal (0 in print).
Radii: 2px badges · 3–4px cards/tables · 5–6px feature cards · 20px only for chips/pills.
No 12px+ radii on data elements. No random values.

---

## Component Patterns

### Header
- White ground, **2px navy bottom border** (the note's top rule).
- Company name: serif, ink. Ticker: navy tracked caps, no chip. Stage: outlined chip.
- **DRAFT: navy filled chip — non-negotiable on every output.**
- Right meta: website link + "Updated <date>" + version-history disclosure (`<details>`).

### Hero stat strip + as-of anchor
- `--ks-graphite` band, 5 fixed columns; label faint caps, value navy 700.
- Below it the **as-of band**: one line dating ALL trading data to the close, naming the
  source and the EV recomputation basis. Per-card date tags appear only for differing windows.

### "What matters" band
- Directly under the TOC: 3px navy left border, crimson `WHAT MATTERS` eyebrow.
- Rows: `THESIS` / `KEY DEBATE` / `NEXT CATALYST` — navy tracked labels, body text. Empty rows drop.

### Section labels (eyebrows)
- Crimson, 10px, 700, tracked 0.15em, hairline underneath. Metadata goes in a `.sec-meta`
  line under the eyebrow, never inline. No decorative icons.

### Explainer (the product's signature block)
- **Lede**: "In one sentence" callout — graphite fill, 3px crimson left border, serif text.
- Three cards: Plain English (crimson top border) / The technical version (green) /
  Explained simply (navy), each with a faint sublabel ("What it does, who pays" · "How it
  actually works" · "The analogy").
- **Bullets scan**: one idea per bullet, ≤ ~20 words; render caps at 5 per card; QA warns on long bullets.
- Glossary ("Key terms, decoded"): two-column dl, terms bold ink, expansions italic faint.

### Tables (comps, diff, quarterly matrix)
- Headers: 9px tracked caps, faint, **1.5px navy bottom rule**; units live in `.th-unit` under
  the header so every cell is one clean token. `thead` repeats across print pages.
- Numeric cells: right-aligned, tabular numerals, never wrap.
- Subject row: `#eef3fa` fill, 700. **Median row**: graphite fill, 1.5px strong top rule,
  labeled "Peer median ex-subject".
- Comp notes ride under the company name (10px faint, max 340px), not in their own column.
- No alternating row colors.

### Metric cards
- `--ks-raised`, 1px rule border, 4px radius. Label faint caps (2-line min-height); value navy
  (green via `GREEN_KEYS`); growth sub-line signed and green when positive; **period tag**
  bottom-bordered on every card.

### Charts (inline SVG, no JS)
- Bars: navy, opacity ramp old→new, value labels on top, growth % above in green.
- Quarterly revenue bars are labeled **YoY**; QoQ lives in the matrix below the chart.
- Scatter (growth vs EV/Rev): navy peer dots, **crimson subject dot**, ticker labels, faint
  axis ticks ("%" x, "x" y), tracked-caps axis titles.
- Every chart carries a `Sources:` row naming source + basis.

### Risk list / bullets / diligence
- Risk marker: crimson `!` disc on 10% crimson fill. Slide bullets: navy numbered squares
  (26×26, 2px radius). Diligence: outlined squares with navy `Q#`.

### Footer
- `--ks-raised`, strong top rule. Left: sources + "DRAFT for internal use only. Human review
  required before distribution." Right: ATLAS wordmark, navy tracked caps.

### Print / PDF
- The PDF **is** this HTML printed: Letter, margins via `@page`/DevTools, running
  header/footer with `Page X / Y`.
- Hidden in print: TOC, version menu, **Slide Kit** (working artifact, not note content).
- Atomic blocks (`cards`, `li`, `tr`, charts) never break across pages; headings never strand.

---

## Anti-Patterns (Never)

- Dark surfaces, gold accents, or any return to the dashboard look
- Purple/indigo/cyan accents; gradients; glassmorphism; decorative shadows
- Rounded corners > 8px on data elements; nested cards
- Pure-black text (`#000`) — ink is `#15181f`
- An undated trading number, or the same date repeated on every card
- A multiple hard-typed into prose (it goes stale; cite the live table or date the claim)
- Uppercase tracked labels above every heading; icon tiles above headings (template tells)
- Em dashes in output text — use commas or restructure (house rule, enforced by `clean()`)
- Shipping without the DRAFT badge

---

## Financial Deliverable Rules

1. **Density over decoration.** Data-dense layouts are correct; don't pad for "clean".
2. **Page-one discipline.** Hero multiples → as-of anchor → What Matters (thesis/debate/catalyst)
   before any narrative.
3. **Metric hierarchy.** KPIs get metric cards with period tags, not inline text.
4. **Color codes data, not decoration.** Navy = structure. Green = positive. Crimson = risk/signal. Never invert.
5. **Numbers are mono-aligned, dated, and tie everywhere** — the renderer reconciles market
   multiples to one live pull; QA blocks contradictions and flags prose drift.
6. **Scannable structure.** Section order is fixed (Overview → Product → News → Financials →
   Growth → Risks → Comps/SWOT → Filings → Bullets → Questions). Do not reorder.
7. **No client-ready polish without human sign-off.** DRAFT stays on.
