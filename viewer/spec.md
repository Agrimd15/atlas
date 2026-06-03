# Atlas - Local Viewer: Technical Spec (v0.1)

> **Scope:** this spec describes the **local viewer** component (`atlas.html`) only - not the full
> Atlas pipeline. See the [Atlas README](README.md) for the tool as a whole.

## Goals

Deliver a zero-friction, beautiful, local-only company intelligence capture tool that an SF tech IB analyst can start using on day 1 without any setup.

## Non-Goals (v0.1)

- Real-time web scraping / enrichment of descriptions or valuations (too brittle + compliance risk)
- Cloud sync or multi-device
- PDF export or deck generation
- Agent automation

## Core User Flows

1. **Rapid Capture**
   - `N` → modal with Name + Website
   - On save: auto-attempt favicon, create record, select it
   - Immediately fill short description + verticals (most important)

2. **Research Acceleration**
   - On any company view: prominent "Quick Research" button row
   - Clicking opens multiple curated search tabs with pre-filled queries

3. **Branding Capture** (huge for decks)
   - Logo area supports:
     - Auto favicon (from website)
     - Manual image upload (stored as base64)
   - "Extract Colors" runs client-side dominant color analysis
   - Swatches are one-click copy to clipboard as #hex

4. **Organization**
   - Sidebar list with search + vertical filter chips
   - Starred companies appear at top or in a dedicated section
   - Optional "By Vertical" grouped view

5. **Backup / Portability**
   - One-click "Export All" downloads a dated JSON
   - Import replaces or merges (user choice)

## Data Shape (per company)

```ts
interface Company {
  id: string;                    // uuid or nanoid
  name: string;
  website?: string;
  logoDataUrl?: string;          // base64 when user uploads
  faviconUrl?: string;           // external or cached
  verticals: string[];           // from presets + custom
  shortDescription: string;      // one-liner
  businessModel: string;         // longer explanation
  valuation?: {
    round?: string;              // e.g. "Series D", "Pre-IPO"
    amount?: number;             // in millions or actual
    currency?: string;
    date?: string;               // "2025-03"
    source?: string;             // "PitchBook", "public", "management"
  };
  competitors: string[];         // simple string names for v0.1
  notes: string;                 // markdown-ish long form
  colorPalette: string[];        // #hex values
  isStarred: boolean;
  addedAt: string;               // ISO
  updatedAt: string;             // ISO
}
```

## UI Sections (Company Detail View)

- Header: Logo | Name (inline edit) | Website link | Star | Quick Actions
- Vertical Tags (editable multi-select)
- Two-column or stacked:
  - Overview (short + business model)
  - Valuation & Financial Snapshot (structured + free notes)
  - Competitors (chip editor)
  - Branding & Assets (logo + color extraction + manual swatches)
  - Deep Notes (large textarea + preview toggle)
- Metadata bar: added, last updated, id (for debugging)

## Keyboard Shortcuts (v0.1)

- `n` or `N` - New company modal
- `/` - Focus global search (when not typing in field)
- `Esc` - Close modals / clear selection / blur
- `Cmd/Ctrl + K` - Future command palette hook
- Arrow keys in list - navigate companies (nice-to-have)

## Technical Constraints

- Single HTML file + Tailwind via CDN
- No external runtime dependencies
- All persistence via localStorage (`atlas_companies_v1`)
- Color extraction must be pure client-side (Canvas + simple bucketing)
- Must work completely offline after initial open

## Polish Requirements

- Professional dark theme (slate + subtle indigo accents)
- Excellent empty states
- Smooth but not flashy interactions
- Mobile/tablet usable but optimized for desktop (big screens in banking)
- Clear visual hierarchy so you can scan a company in < 3 seconds

## Success Criteria for v0.1

An analyst can:
- Add 10 real companies in < 15 minutes total
- Have useful structured data + colors for 3 of them
- Feel the tool is faster than their previous Notion/Excel/brain method
- Export and feel confident the data is theirs

## Next Version Triggers

- You use it for 2+ weeks and it saves real time
- You start wanting it on your phone or second laptop
- You want one-click brief generation
