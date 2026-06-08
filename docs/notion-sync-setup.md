# Mirroring Atlas coverage into Notion

`agents/notion_sync.py` pushes a finished Atlas run into a Notion database, so a team can
browse coverage from Notion with each row linking back to the published brief. One row per
company, **upserted on the company name** — re-running a company updates its row instead of
duplicating it.

This guide walks through building the database from scratch and connecting it.

---

## 1. Build the database in Notion

Create a new **Table** database (or reuse an existing one — e.g. *tech startup tracker*) and add
these properties. **Type matters** — a Number column can't hold `$42.8B`, so revenue/valuation
must be **Text**.

| Property name | Notion type | What it holds |
|---|---|---|
| **Company Name** | Title *(default — rename the title column)* | Company name (this is the match key) |
| **Description** | Text | One-line business summary |
| **Competitors** | Text | Competitor list |
| **Founders** | Text | Founders |
| **Type** | Select — options `Public`, `Private` | Public vs. private |
| **Stage** | Select or Text | `Public` for listed names; `Seed` / `Series A` … for private |
| **Revenue** | **Text** | LTM revenue (public) or latest reported (private) |
| **Valuation** | **Text** | Market cap (public) or last post-money (private) |
| **Brief** | **URL** | Link to the published brief on your site |
| **Last Updated** | Date *(optional)* | Run date |

> **Column names are flexible.** The sync matches by name (case-insensitive) and accepts aliases:
> `Type` ↔ `Public/Private` ↔ `Ownership`; `Stage` ↔ `Series` ↔ `Series/IPO` ↔ `Round`;
> `Valuation` ↔ `Market Cap` ↔ `Last Valuation`. The brief link goes to any **URL** column
> (preferring one named `Brief`, `Atlas`, `Report`, or `Link`). Columns you don't create are simply skipped.

---

## 2. Create a Notion integration

1. Go to **https://www.notion.so/my-integrations**.
2. Click **New integration** → give it a name (e.g. "Atlas") → keep it **Internal** → **Save**.
3. Copy the **Internal Integration Secret** (starts with `secret_` or `ntn_`). You'll need it in step 4.

---

## 3. Connect the integration to your database

1. Open the database as a full page in Notion.
2. Top-right **•••** menu → **Connections** → **Connect to** → pick the integration you just created.

This grants it read/write on that database. Without this step the script gets a permission error.

---

## 4. Get the database ID

Open the database as a full page and look at the URL:

```
https://www.notion.so/myworkspace/22a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5?v=...
                                   └──────────────┬──────────────┘
                                    this 32-char hash is your DB ID
```

Copy the 32-character hash **before** the `?v=`.

---

## 5. Configure `.env`

In the repo root, add these to `.env` (copy from `.env.example` if you don't have one yet):

```bash
NOTION_TOKEN=secret_your_token_here       # from step 2
NOTION_DB_ID=your_32char_db_id            # from step 4
ATLAS_SITE_URL=https://your-site.vercel.app   # your deployed coverage site (for brief links)
```

`ATLAS_SITE_URL` is your deployed Vercel domain — it's what makes the **Brief** links resolve to
`<site>/full/briefs/<ID>/<date>.html`. If you haven't deployed the site yet you can leave it blank;
rows still sync, just without the link.

---

## 6. Run it

```bash
# Preview — prints the row it would write, sends nothing, no token required
python3 agents/notion_sync.py CRM --dry-run

# Upsert the row into Notion
python3 agents/notion_sync.py CRM

# Also write a one-page summary (overview + slide bullets + link) into the page body.
# Only applied when the row is first created, so it never clobbers notes you add later.
python3 agents/notion_sync.py CRM --body
```

`CRM` is the folder ID under `data-dumps/` (the ticker for public names, the kebab-case slug for
private ones, e.g. `standard-intelligence`). Re-running the same company updates its row in place.

---

## 7. (Optional) Run it automatically after every brief

Add the sync as a step right after the brief is generated (Step 4 in the Atlas protocol):

```bash
python3 agents/deliverable_agent.py CRM
python3 agents/notion_sync.py CRM
```

---

## What lands in each row

| | Public (e.g. Salesforce) | Private (e.g. Standard Intelligence) |
|---|---|---|
| **Type** | `Public` | `Private` |
| **Stage** | `Public` | `Series A` |
| **Revenue** | `$42.8B (LTM)` | latest reported, or **blank** if undisclosed |
| **Valuation** | `$152.1B (mkt cap)` | `~$500M (reported)`, or **blank** if undisclosed |
| **Brief** | → live brief | → live brief |

Undisclosed private figures are left **blank, never guessed** — consistent with Atlas's data-freshness rules.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Missing env: NOTION_TOKEN, NOTION_DB_ID` | Fill them in `.env` (step 5). |
| Notion API `401` / `unauthorized` | Token wrong, or the integration isn't connected to the DB (step 3). |
| Notion API `404` on the database | Wrong `NOTION_DB_ID`, or integration not connected to that DB. |
| Revenue/Valuation column stays empty on a public name | The column is typed **Number** — change it to **Text** (Number can't hold `$42.8B`). |
| Brief link is empty | `ATLAS_SITE_URL` isn't set, or the company has no run folder yet. |
| Run with `--dry-run` first | Validates the data side with no token and no writes. |
