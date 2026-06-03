"""
Atlas Backend — v0.3
FastAPI server that powers live company search and research.
Uses the 'claude' CLI (Claude Code) so no API key is needed — just your normal login.
Run with: ./start.sh  (or: python3 -m uvicorn backend.main:app --reload --port 8000)
"""

import json
import re
import asyncio
import shutil
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Atlas Backend", version="0.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # local-only tool
    allow_methods=["*"],
    allow_headers=["*"],
)

ATLAS_HTML  = Path(__file__).parent.parent / "atlas.html"
DATA_DUMPS  = Path(__file__).parent.parent.parent / "data-dumps"   # data-dumps (sibling of backend/)


def _load_saved_companies() -> list:
    """Scan data-dumps/TICKER/profile.json files — each company is its own file."""
    companies = []
    if not DATA_DUMPS.exists():
        return companies
    for profile_path in sorted(DATA_DUMPS.glob("*/profile.json")):
        try:
            company = json.loads(profile_path.read_text())
            companies.append(company)
        except Exception:
            continue
    # Sort: starred first, then by lastResearchedAt descending
    companies.sort(key=lambda c: (
        not c.get("isStarred", False),
        c.get("lastResearchedAt", "") or ""
    ), reverse=False)
    return companies


def _save_company(company: dict) -> None:
    """Write a single company to data-dumps/TICKER/profile.json."""
    ticker = (company.get("ticker") or company.get("name", "UNKNOWN")).upper().replace(" ", "_")
    company_dir = DATA_DUMPS / ticker
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "profile.json").write_text(json.dumps(company, indent=2))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse(ATLAS_HTML)


@app.get("/api/companies")
def get_companies():
    """Return all Alfred-researched companies saved to disk."""
    return {"companies": _load_saved_companies()}


class CompanyPayload(BaseModel):
    company: dict


@app.post("/api/companies")
def add_company(payload: CompanyPayload):
    """Save/update a company profile. Called by Alfred after each research run."""
    company = payload.company
    if not company.get("name"):
        raise HTTPException(status_code=400, detail="company.name is required")
    _save_company(company)
    return {"status": "saved", "ticker": company.get("ticker") or company.get("name")}


@app.get("/api/health")
def health():
    claude_path = shutil.which("claude")
    return {
        "status": "ok",
        "version": "0.3",
        "api_key_set": bool(claude_path),  # reuse this field — true = claude CLI found
        "claude_cli": claude_path or "not found",
    }


@app.get("/api/search")
async def search_companies(q: str = Query(..., min_length=2, max_length=100)):
    """Quick disambiguation — returns 1-4 matching company candidates."""
    try:
        return await asyncio.to_thread(_search_sync, q)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {e}")


class ResearchRequest(BaseModel):
    name: str
    website: str | None = None


@app.post("/api/research")
async def research_company(req: ResearchRequest):
    """Full company research — returns a complete structured profile."""
    if not req.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    try:
        return await asyncio.to_thread(_research_sync, req.name.strip(), req.website)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Research failed: {e}")


# ── Claude CLI helpers ─────────────────────────────────────────────────────────

def _get_claude() -> str:
    path = shutil.which("claude")
    if not path:
        raise HTTPException(
            status_code=500,
            detail=(
                "'claude' CLI not found in PATH. "
                "Make sure Claude Code is installed and you've run it at least once."
            ),
        )
    return path


def _run_claude(prompt: str, timeout: int = 150) -> str:
    """
    Run 'claude -p <prompt>' and return the text output.
    Tries with WebSearch/WebFetch tools enabled first (richer results),
    falls back to knowledge-only if those tools aren't available.
    """
    claude = _get_claude()

    # Try with web search tools so Claude can pull live data
    for args in (
        [claude, "--allowedTools", "WebSearch,WebFetch", "-p", prompt],
        [claude, "-p", prompt],                  # fallback: training knowledge only
    ):
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode == 0 and result.stdout.strip():
                return _clean(result.stdout)
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

    raise HTTPException(status_code=500, detail="Claude CLI returned no output.")


def _clean(text: str) -> str:
    """Strip ANSI escape codes and control characters from CLI output."""
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)
    text = re.sub(r"\x1b\][^\x07]*\x07", "", text)
    return text.strip()


def _extract_json(text: str) -> dict | None:
    """Pull the first top-level JSON object out of a text blob."""
    # Strip markdown fences
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE)

    # Try greedy match first (handles nested objects)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try extracting the largest valid JSON block
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    start = None

    return None


# ── Search (disambiguation) ───────────────────────────────────────────────────

def _search_sync(query: str) -> dict:
    prompt = f"""Search the web and identify the tech company or companies that best match: "{query}"

Return ONLY valid JSON, no markdown fences or extra text:
{{
  "results": [
    {{
      "name": "Exact official company name",
      "website": "https://domain.com",
      "oneLiner": "What they build or do, max 15 words",
      "vertical": "AI | SaaS | Fintech | Cybersecurity | Cloud & Infrastructure | Consumer Technology | Semiconductors & Hardware | Healthcare Technology | Marketplaces & Commerce | Defense & Aerospace | Other",
      "confidence": 0.95
    }}
  ]
}}

Return 1-3 results ordered by relevance. If one company is clearly the best match, just return that one."""

    text = _run_claude(prompt, timeout=60)
    data = _extract_json(text)
    if data and "results" in data:
        return data
    # Best-effort fallback
    return {
        "results": [
            {
                "name": query.title(),
                "website": None,
                "oneLiner": "Found via search — click to get full profile",
                "vertical": "Other",
                "confidence": 0.4,
            }
        ]
    }


# ── Full research ─────────────────────────────────────────────────────────────

_VERTICALS = (
    "SaaS | Fintech | Cybersecurity | Cloud & Infrastructure | Artificial Intelligence | "
    "Consumer Technology | Semiconductors & Hardware | Healthcare Technology | "
    "Marketplaces & Commerce | Defense & Aerospace | Other"
)

_SCHEMA = """{
  "name": "Official company name",
  "website": "https://...",
  "founded": "YYYY",
  "headquarters": "City, State/Country",
  "employeeCount": "500-1,000",
  "vertical": "one of: """ + _VERTICALS + """",
  "shortDescription": "One tight sentence, max 18 words",
  "techDescription": "4-6 sentences for IB analysts: what they build, technical differentiation, technical moat, customer profile",
  "plainEnglishDescription": "3-4 sentences anyone can understand: what it is, who uses it, why it matters",
  "businessModel": "Revenue model, customer segments, pricing approach, growth drivers, key risks",
  "marketContext": "2-3 sentences: what this sector is, why it's growing — helpful for someone new to the space",
  "totalRaised": 1500,
  "fundingRounds": [
    {
      "round": "Series C",
      "date": "2024-03",
      "amount": 500,
      "postMoneyValuation": 2500,
      "investors": ["Lead Investor", "Other Investor"],
      "source": "TechCrunch"
    }
  ],
  "investors": ["All notable investors deduplicated"],
  "competitors": ["Competitor 1", "Competitor 2", "Competitor 3"],
  "revenue": "$50M ARR",
  "growth": "3x YoY",
  "primaryColor": "#HEX brand primary color or null",
  "notes": "Key analyst insights:\\n• Recent development\\n• Strategic context\\n• Key risk or watch item\\n• Notable customers or partners"
}"""


def _research_sync(name: str, website: str | None) -> dict:
    site_clause = f" (website: {website})" if website else ""

    prompt = f"""You are a senior investment banking analyst at a tech-focused firm.
Research the company "{name}"{site_clause}.

Use web search to find: their official website, Crunchbase profile, PitchBook data, recent funding news, competitor analysis.
List fundingRounds newest-first. Use null for unknown numeric fields, [] for unknown arrays.

Return ONLY valid JSON — no markdown fences, no other text:

{_SCHEMA}"""

    text = _run_claude(prompt, timeout=180)
    data = _extract_json(text)

    if not data:
        raise HTTPException(
            status_code=500,
            detail=f"Could not parse response. First 300 chars: {text[:300]}",
        )

    data.setdefault("name", name)
    data.setdefault("competitors", [])
    data.setdefault("fundingRounds", [])
    data.setdefault("investors", [])
    data.setdefault("colorPalette", [])

    # Promote primaryColor into colorPalette for the branding section
    if data.get("primaryColor") and re.match(r"^#[0-9A-Fa-f]{6}$", str(data["primaryColor"])):
        data["colorPalette"] = [data["primaryColor"]]

    return data
