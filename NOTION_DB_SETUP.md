# Build the Atlas → Notion coverage database

Instructions for an agent (or a person) to stand up the Notion database that
`agents/notion_sync.py` pushes Atlas coverage runs into. Follow top to bottom.
When you're done you'll have three values for Atlas's `.env`:
`NOTION_TOKEN`, `NOTION_DB_ID`, `ATLAS_SITE_URL`.

The sync matches columns **by name (case-insensitive)** and formats each value to
the column's real type, so the exact types below aren't load-bearing — but the
**Revenue and Valuation columns MUST be text/select, never Number** (they hold
strings like `"$42.8B"`, which a Number column silently drops).

---

## 1. Create the integration (gives you `NOTION_TOKEN`)

1. Go to <https://www.notion.so/my-integrations> → **New integration**.
2. Name it e.g. `Atlas Coverage Sync`, type **Internal**, associate it with your workspace.
3. Capabilities: **Read content**, **Update content**, **Insert content** (no user info needed).
4. Submit, then copy the **Internal Integration Secret** (starts with `ntn_` or `secret_`).
   → this is `NOTION_TOKEN`.

## 2. Create the database with these columns

Create a new **full-page database** (Table view). Add exactly these properties.
Left column = the property name to create; the sync also recognizes the listed
aliases, so any one of them works.

| Property (create this) | Type | Aliases the sync also accepts |
|---|---|---|
| **Company Name** | Title | `Name` |
| **Description** | Text | — |
| **Competitors** | Text *(or Multi-select)* | — |
| **Founders** | Text *(or Multi-select)* | — |
| **Ticker** | Text | — |
| **Website** | URL *(or Text)* | — |
| **Type** | Select *(or Text)* | `Public/Private`, `Ownership` |
| **Stage** | Select *(or Text)* | `Series`, `Series/IPO`, `Round` |
| **Revenue** | **Text** *(never Number)* | `LTM Revenue`, `ARR/Revenue` |
| **Valuation** | **Text** *(never Number)* | `Market Cap`, `Last Valuation` |
| **Brief** | **URL** | any URL column whose name contains `brief`/`atlas`/`report`/`link` |
| **Last Updated** | Date | — |

For **Type**, seed two select options: `Public`, `Private`.
For **Stage**, useful seed options: `Public`, `Seed`, `Series A`, `Series B`,
`Series C`, `Series D+` (Notion will also auto-create any value the sync sends).

### Doing it via the Notion API instead of the UI

If you're an agent creating this programmatically, POST to
`https://api.notion.com/v1/databases` with header `Notion-Version: 2022-06-28`
and a `parent` of `{ "type": "page_id", "page_id": "<a page the integration can edit>" }`.
Property schema (`Revenue`/`Valuation` as `rich_text`, not `number`):

```jsonc
{
  "parent": { "type": "page_id", "page_id": "<PARENT_PAGE_ID>" },
  "title": [{ "type": "text", "text": { "content": "Atlas Coverage" } }],
  "properties": {
    "Company Name": { "title": {} },
    "Description":  { "rich_text": {} },
    "Competitors":  { "rich_text": {} },
    "Founders":     { "rich_text": {} },
    "Ticker":       { "rich_text": {} },
    "Website":      { "url": {} },
    "Type":   { "select": { "options": [ { "name": "Public" }, { "name": "Private" } ] } },
    "Stage":  { "select": { "options": [
      { "name": "Public" }, { "name": "Seed" }, { "name": "Series A" },
      { "name": "Series B" }, { "name": "Series C" }, { "name": "Series D+" }
    ] } },
    "Revenue":      { "rich_text": {} },
    "Valuation":    { "rich_text": {} },
    "Brief":        { "url": {} },
    "Last Updated": { "date": {} }
  }
}
```

The response's `id` (a 32-char hash, dashed) is your `NOTION_DB_ID`.

## 3. Connect the integration to the database

Open the database → **•••** (top-right) → **Connections** → add `Atlas Coverage Sync`.
Without this the integration gets a 404/permission error even with a valid token.
*(If you created the DB via the API under a parent page the integration already
had access to, it's connected automatically — but verify here.)*

## 4. Grab the database ID (`NOTION_DB_ID`)

From the database URL:
`https://www.notion.so/<workspace>/`**`8a1b2c3d4e5f60718293a4b5c6d7e8f9`**`?v=...`
The bold 32-char hex string is `NOTION_DB_ID` (dashes optional).

## 5. Fill in `.env`

Add to Atlas's `.env` (see `.env.example`):

```
NOTION_TOKEN=ntn_xxxxxxxxxxxx
NOTION_DB_ID=8a1b2c3d4e5f60718293a4b5c6d7e8f9
ATLAS_SITE_URL=https://<your-deployed-site>
```

## 6. Test

```bash
python3 agents/notion_sync.py SNOW --dry-run   # prints the payload, sends nothing
python3 agents/notion_sync.py SNOW             # real upsert (creates the SNOW row)
python3 agents/notion_sync.py SNOW --body      # also writes a summary into the page body
```

A second run of the same company **updates** its row in place (matched on Company
Name) — it never duplicates. To wire it into every Atlas run, call
`python3 agents/notion_sync.py FOLDER_ID` as an extra step after Step 4 of the
Execution Protocol.
