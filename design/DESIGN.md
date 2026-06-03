# Alfred Design Language

Derived from [Impeccable / Neo Kinpaku](https://github.com/pbakaus/impeccable). All UI in this repo - HTML briefs, Atlas, any future dashboards - must comply with these rules. Do not deviate.

---

## Aesthetic Register

**Neo Kinpaku** applied to financial analyst deliverables.

- Dark mineral and lacquer surfaces. Never pure black or pure white.
- Kinpaku gold is the primary accent signal. Not indigo, not cyan, not magenta.
- Verdigris patina marks live data, improved states, and positive metrics.
- Vermilion is for risk, warnings, and negative states only.
- Geometric sans voice. Small radii. Thin gold hairlines as structural anchors.
- No glass. No bounce. No gradients. No glassmorphism. No neon glow.

---

## Color Tokens

Use these exact values. Do not hand-type other hex/rgb values.

```css
/* Surfaces */
--ks-lacquer:       oklch(7%  0.006 95);   /* #0d0d0b - page ground */
--ks-lacquer-deep:  oklch(4%  0.004 95);   /* #080806 - inset, picker bars */
--ks-raised:        oklch(11% 0.006 95);   /* #161614 - panels, cards, inputs */
--ks-graphite:      oklch(15% 0.008 95);   /* #202020 - inactive surfaces */
--ks-graphite-2:    oklch(19% 0.008 95);   /* #282826 - one step above graphite */

/* Brand accents */
--ks-kinpaku:       oklch(84% 0.19  80);   /* ~#d4a843 - primary accent, CTAs, active */
--ks-kinpaku-pale:  oklch(86% 0.07  84);   /* ~#ddc98a - hover state */
--ks-kinpaku-rich:  oklch(77% 0.13  82);   /* ~#b8912f - pressed/active */
--ks-kinpaku-deep:  oklch(61% 0.085 78);   /* ~#8a6b24 - borders */
--ks-patina:        oklch(70% 0.12 188);   /* ~#3d9e8c - positive metrics, live */
--ks-patina-pale:   oklch(82% 0.07 188);   /* ~#7ec4ba - subtle patina bg */
--ks-patina-deep:   oklch(49% 0.08 188);   /* ~#2a6e65 - contrast patina */
--ks-vermilion:     oklch(58% 0.15  35);   /* ~#c0533a - risk, warning, negative */

/* Text */
--ks-champagne:     oklch(91% 0 0);        /* ~#e8e8e8 - headlines, strong */
--ks-body:          oklch(88% 0 0);        /* ~#e0e0e0 - body copy */
--ks-muted:         oklch(72% 0 0);        /* ~#b8b8b8 - metadata, captions */
--ks-faint:         oklch(62% 0 0);        /* ~#9e9e9e - subdued labels */
--ks-disabled:      oklch(52% 0 0);        /* ~#858585 - disabled copy */

/* Hairlines */
--ks-rule:          oklch(78% 0 0 / 0.16); /* neutral dividers */
--ks-rule-strong:   oklch(74% 0.09 82 / 0.6); /* gold hairlines, active borders */

/* Motion */
--ks-ease:          cubic-bezier(0.2, 0.8, 0.2, 1);
```

---

## Typography

### Fonts

| Role | Family | Use |
|------|--------|-----|
| Display | Alumni Sans Pinstripe | Section titles (h1, h2 at display size only) |
| Body/UI | Albert Sans | All body copy, labels, controls, metadata |
| Mono | SFMono-Regular, Roboto Mono | Tickers, KPIs, table headers, code |

Load via Google Fonts:
```html
<link href="https://fonts.googleapis.com/css2?family=Alumni+Sans+Pinstripe&family=Albert+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
```

### Scale

| Level | Size | Weight | Line-height | Letter-spacing | Font |
|-------|------|--------|-------------|----------------|------|
| Display | clamp(2.4rem, 5vw, 3.8rem) | 300 | 1.02 | -0.01em | Alumni Sans Pinstripe |
| Section title | 1.18rem | 600 | 1.35 | 0 | Albert Sans |
| Body | 1.0rem | 400 | 1.75 | 0 | Albert Sans |
| Eyebrow/label | 0.68rem | 500 | 1 | 0.20em | Mono, uppercase |
| Metric value | 1.6rem | 700 | 1 | 0 | Albert Sans |
| Table header | 0.68rem | 700 | 1 | 0.10em | Mono, uppercase |

### Typography Rules

1. **Weight inversion**: Section h2 is heavier (600) than hero h1 (300). Do not normalize.
2. **Pinstripe only at display size**: Do not use Alumni Sans Pinstripe below 1.2rem - it loses identity.
3. **Tracked labels are short**: Uppercase tracking for system markers only, not sentences.
4. **Light text needs air**: Line-height 1.7-1.8 on dark backgrounds. Max-width 65-72ch for prose.
5. **Modular scale ≥ 1.25×** between steps. Flat scales read uncommitted.
6. **Banned fonts**: Inter, DM Sans, Playfair Display, IBM Plex family, Space Mono, Outfit, Plus Jakarta Sans, Instrument family, Fraunces, Cormorant.

---

## Spacing Scale

| Token | Value | Use |
|-------|-------|-----|
| xs | 8px | Tight internal gaps, icon padding |
| sm | 16px | Field padding, small gaps |
| md | 24px | Component gaps, paragraph spacing |
| lg | 32px | Section gaps |
| xl | 48px | Generous spacing |
| 2xl | 80px | Major sections |
| 3xl | 112px | Hero/viewport spacing |

No random values. No 13px gaps.

---

## Radii

| Token | Value | Use |
|-------|-------|-----|
| none | 0 | Buttons, sharp geometry |
| xs | 2px | Small controls, buttons |
| sm | 4px | Panels, cards, inputs |
| md | 6px | Moderate |
| lg | 8px | Large features |

No wide rounded cards. No 12px+ radii on data elements.

---

## Elevation / Material

- **Hairline first**: Use 1px gold hairline (`var(--ks-rule-strong)`) before adding shadow.
- **No glass**: No backdrop-filter blur, no translucent panels.
- **No decorative shadows on cards**: Cards use border + background shift only.
- **Shadows only for**: Large framed modules (panel setback), CTA lift on hover.
- **No pure black backgrounds**: Always use lacquer (warm mineral).

---

## Component Patterns (Financial Deliverables)

### Header / Company Card
- Background: `var(--ks-lacquer-deep)` or `var(--ks-lacquer)`
- Company name: Alumni Sans Pinstripe, display size, champagne
- Ticker: kinpaku badge, 2px radius, uppercase mono
- DRAFT badge: vermilion-tinted, outlined
- Vertical tags: kinpaku-tinted chips, 3px radius
- Trading bar: raised surface, mono font, muted text

### Section Labels (Eyebrows)
- Uppercase mono, 0.68rem, letter-spacing 0.2em
- Kinpaku gold color
- No decorative icons before every heading (AI slop tell)
- One icon per section max, used functionally not decoratively

### Tables (Comps, News, Funding)
- Header: uppercase mono, faint text, 2px border-bottom gold hairline
- Row: 1px rule bottom, normal hover background shift
- Subject/highlighted row: kinpaku-tinted left border (3px), raised bg
- No alternating row colors
- Mono font on all numeric columns

### Metric Cards (Earnings KPIs)
- Surface: `var(--ks-raised)`, 1px `var(--ks-rule)` border, 4px radius
- Label: uppercase mono, faint
- Value: 1.6rem, 700 weight
- Positive values: `var(--ks-patina)`
- Neutral values: `var(--ks-champagne)`
- Negative values: `var(--ks-vermilion)`

### Risk List
- Warning marker: vermilion circle with `!`
- Text: body color, 1.7 line-height
- No alternating backgrounds

### Slide Bullets
- Counter: kinpaku square (2px radius), champagne number, 26×26px
- Text: champagne, 1.65 line-height
- Separator: 1px rule

### Diligence Questions
- Counter: raised graphite square, kinpaku `Q` prefix
- Same sizing as slide bullets

### Chips (Competitors, Investors)
- Background: `var(--ks-raised)`, 1px `var(--ks-rule)`, 20px radius (pills)
- Text: body color, 500 weight, 12px

### TOC / Sticky Nav
- Background: `var(--ks-graphite)`, bottom 1px gold hairline
- Links: pill shape, 1px rule border, faint text
- Hover/active: kinpaku fill + lacquer text

### Footer
- Background: `var(--ks-raised)`, top 1px rule
- DRAFT label: vermilion
- Alfred wordmark: kinpaku, tracked uppercase

---

## Motion

- Default ease: `cubic-bezier(0.2, 0.8, 0.2, 1)`
- Feedback (hover, toggle): 100-150ms
- State changes (tooltip, menu): 200-300ms
- **Never**: bounce (`cubic-bezier(0.34, 1.56, ...)`) or elastic easing
- **Never**: animate layout properties (width, height, margin) casually
- Always respect `prefers-reduced-motion`

---

## Anti-Patterns (Never Use)

- Purple/indigo as primary accent - use kinpaku gold
- Neon cyan, magenta, or green as brand color
- Glassmorphism / backdrop-filter blur panels
- Rounded corners > 8px on data cards
- Gradients on surfaces or buttons
- Nested cards
- Bounce or elastic easing
- Pure black (`#000`) or pure white (`#fff`) surfaces
- Gray text on colored backgrounds
- Monospace fonts as a "technical" shorthand everywhere
- Uppercase tracked labels above every section heading (AI tell)
- Large rounded icon tiles above headings (template tell)
- Em dashes in any output text - use hyphens or restructure

---

## Financial Analyst Adaptations

These rules adapt Neo Kinpaku to banker deliverables:

1. **Density over decoration**: Data-dense layouts are correct. Do not pad tables with whitespace to seem "cleaner."
2. **Metric hierarchy**: Earnings KPIs are the most important data element. They get metric cards, not inline text.
3. **Source credibility**: Footer must always cite sources and mark as DRAFT.
4. **No client-ready polish**: The DRAFT badge is non-negotiable on every output.
5. **Scannable structure**: Section order is fixed (Overview → Product → News → Earnings → Risks → Comps → Bullets → Questions). Do not reorder.
6. **Monospace for all numbers**: Tickers, prices, percentages, multiples - all mono font for alignment.
7. **Color codes data, not decoration**: Kinpaku gold = structure/navigation. Patina = positive/growth. Vermilion = risk/negative. Never invert these.
