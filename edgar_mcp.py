#!/usr/bin/env python3
"""
SEC EDGAR MCP Server

Access U.S. SEC filings and XBRL financial data from EDGAR
(https://www.sec.gov/edgar) — company filings (10-K, 10-Q, 8-K, Form 4, ...),
financial facts, and full-text search across all filings.

No API key required. The SEC requires a descriptive User-Agent with contact
info on every request; set the SEC_USER_AGENT environment variable to your own
(e.g. "your-app your@email.com"). A default is provided.

Built with FastMCP.
"""

import gzip
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from enum import Enum
from typing import Annotated, Any, Dict, List, Optional

from pydantic import Field

from mcp.server.fastmcp import FastMCP

logging.getLogger("edgar_mcp").addHandler(logging.NullHandler())

mcp = FastMCP("edgar_mcp")

# Constants
CHARACTER_LIMIT = 25000
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
# SEC asks for a descriptive User-Agent with contact info; 10 requests/sec max.
DEFAULT_UA = "edgar-mcp daniel@organikpi.com"


class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


# ============================================================================
# API ACCESS
# ============================================================================


class EdgarError(Exception):
    """Raised for EDGAR API/transport failures with a clean message."""


def _user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT", "").strip() or DEFAULT_UA


def _fetch(url: str) -> bytes:
    last_err: Optional[str] = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": _user_agent(),
                    "Accept-Encoding": "gzip, deflate",
                    "Host": urllib.parse.urlparse(url).netloc,
                },
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise EdgarError("not_found")
            if e.code == 429 and attempt < MAX_RETRIES - 1:
                time.sleep(1.0 * (attempt + 1))
                last_err = "rate_limit"
                continue
            if e.code == 429:
                raise EdgarError("rate_limit")
            raise EdgarError(f"http_{e.code}")
        except urllib.error.URLError as e:
            last_err = f"network:{e.reason}"
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            raise EdgarError(last_err)
    raise EdgarError(last_err or "unknown")


def fetch_json(url: str) -> Dict[str, Any]:
    return json.loads(_fetch(url).decode("utf-8", "replace"))


def _error_text(what: str, exc: Exception) -> str:
    msg = str(exc)
    if msg == "not_found":
        return f"Not found ({what}). Check the company name, ticker, or CIK."
    if msg == "rate_limit":
        return (
            f"SEC EDGAR is rate-limiting requests ({what}).\n\n"
            "EDGAR allows ~10 requests/second. Wait a moment and try again."
        )
    return (
        f"Error fetching {what}: {msg}\n\n"
        "Check your internet connection. If this persists, EDGAR may be briefly unavailable."
    )


# ============================================================================
# HELPERS
# ============================================================================

_TICKER_CACHE: Optional[List[Dict[str, Any]]] = None


def _load_tickers() -> List[Dict[str, Any]]:
    """Load and cache the company_tickers map (name/ticker -> CIK)."""
    global _TICKER_CACHE
    if _TICKER_CACHE is None:
        data = fetch_json("https://www.sec.gov/files/company_tickers.json")
        _TICKER_CACHE = list(data.values())
    return _TICKER_CACHE


def _cik10(cik: Any) -> str:
    """Zero-pad a CIK to 10 digits."""
    return str(int(str(cik).lstrip("CIK").strip())).zfill(10)


def _resolve_cik(identifier: str) -> Optional[Dict[str, Any]]:
    """Resolve a ticker, CIK, or company name to a {cik_str, ticker, title}."""
    ident = identifier.strip()
    if not ident:
        return None
    tickers = _load_tickers()
    # Numeric or CIK-prefixed -> treat as CIK directly.
    digits = ident.lstrip("CIKcik ").strip()
    if digits.isdigit():
        cik = int(digits)
        for t in tickers:
            if t.get("cik_str") == cik:
                return t
        return {"cik_str": cik, "ticker": "", "title": f"CIK {cik}"}
    up = ident.upper()
    # Exact ticker match first.
    for t in tickers:
        if t.get("ticker", "").upper() == up:
            return t
    # Then name contains.
    matches = [t for t in tickers if up in t.get("title", "").upper()]
    return matches[0] if matches else None


def truncate_response(text: str, message: str = "") -> str:
    if len(text) <= CHARACTER_LIMIT:
        return text
    return (
        text[:CHARACTER_LIMIT]
        + f"\n\n⚠️ Response truncated at {CHARACTER_LIMIT} characters. {message}"
    )


def truncate_json_response(payload: str, message: str = "") -> str:
    if len(payload) <= CHARACTER_LIMIT:
        return payload
    note = f"Response exceeded {CHARACTER_LIMIT} characters and was truncated. {message}".strip()
    return json.dumps(
        {"warning": note, "truncatedPreview": payload[:CHARACTER_LIMIT]}, indent=2
    )


def fmt_num(v: Any) -> str:
    try:
        n = float(v)
        if abs(n) >= 1e9:
            return f"${n / 1e9:,.2f}B"
        if abs(n) >= 1e6:
            return f"${n / 1e6:,.2f}M"
        return f"${n:,.0f}"
    except (ValueError, TypeError):
        return str(v)


def _filing_url(cik: int, accession: str, primary_doc: str) -> str:
    accn = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{primary_doc}"


# ============================================================================
# MCP TOOLS
# ============================================================================


@mcp.tool(
    name="search_company",
    annotations={
        "title": "Find a Company on SEC EDGAR",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def search_company(
    query: Annotated[
        str,
        Field(
            description="Company name or ticker (e.g., 'Apple', 'AAPL', 'Tesla')",
            min_length=1,
            max_length=120,
        ),
    ],
    limit: Annotated[
        int, Field(description="Max matches to return (1-25)", ge=1, le=25)
    ] = 10,
    response_format: Annotated[
        ResponseFormat, Field(description="'markdown' or 'json'")
    ] = ResponseFormat.MARKDOWN,
) -> str:
    """Find a company on SEC EDGAR by name or ticker, returning its CIK.

    The CIK (Central Index Key) is the ID used by the other tools. Use this
    first when the user names a company but you don't have its CIK/ticker.

    Args:
        query: Company name or ticker.
        limit: Max matches.
        response_format: 'markdown' or 'json'.

    Returns:
        str: Matching companies with name, ticker, and CIK.

    Example:
        Input: {"query": "Apple"}
        Output: Apple Inc. — AAPL — CIK 320193
    """
    try:
        tickers = _load_tickers()
        up = query.strip().upper()
        exact = [t for t in tickers if t.get("ticker", "").upper() == up]
        contains = [
            t for t in tickers if up in t.get("title", "").upper() and t not in exact
        ]
        results = (exact + contains)[:limit]
        if not results:
            return f"No companies found matching '{query}'."

        if response_format == ResponseFormat.MARKDOWN:
            out = f'# EDGAR Company Search: "{query}"\n\n'
            for t in results:
                out += f"- **{t.get('title')}** — {t.get('ticker') or 'N/A'} — CIK `{t.get('cik_str')}`\n"
            return truncate_response(out, "")
        return truncate_json_response(
            json.dumps(
                {
                    "query": query,
                    "results": [
                        {
                            "name": t.get("title"),
                            "ticker": t.get("ticker"),
                            "cik": t.get("cik_str"),
                        }
                        for t in results
                    ],
                },
                indent=2,
            ),
            "",
        )
    except Exception as e:
        return _error_text("company search", e)


@mcp.tool(
    name="get_recent_filings",
    annotations={
        "title": "Get Recent SEC Filings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_recent_filings(
    identifier: Annotated[
        str,
        Field(
            description="Company ticker, CIK, or name (e.g., 'AAPL', '320193', 'Apple')",
            min_length=1,
            max_length=120,
        ),
    ],
    form_type: Annotated[
        str,
        Field(
            description="Optional filter by form type, e.g. '10-K', '10-Q', '8-K', '4'. Empty for all."
        ),
    ] = "",
    limit: Annotated[
        int, Field(description="Max filings to return (1-50)", ge=1, le=50)
    ] = 15,
    response_format: Annotated[
        ResponseFormat, Field(description="'markdown' or 'json'")
    ] = ResponseFormat.MARKDOWN,
) -> str:
    """Get a company's most recent SEC filings, optionally filtered by form type.

    Use this tool when:
    - The user wants to see what a company has filed recently
    - The user asks for a specific form type (10-K annual, 10-Q quarterly, 8-K events)

    Args:
        identifier: Ticker, CIK, or company name.
        form_type: Optional form filter (e.g. '10-K').
        limit: Max filings.
        response_format: 'markdown' or 'json'.

    Returns:
        str: Recent filings with form type, dates, and a direct document link.

    Example:
        Input: {"identifier": "AAPL", "form_type": "10-K", "limit": 5}
        Output: Apple's 5 most recent annual reports with links
    """
    try:
        company = _resolve_cik(identifier)
        if not company:
            return f"No company found for '{identifier}'. Try search_company first."
        cik = int(company["cik_str"])
        data = fetch_json(f"https://data.sec.gov/submissions/CIK{_cik10(cik)}.json")
        rec = data.get("filings", {}).get("recent", {})
        forms = rec.get("form", [])
        ff = form_type.strip().upper()
        rows = []
        for i in range(len(forms)):
            if ff and forms[i].upper() != ff:
                continue
            rows.append(
                {
                    "form": forms[i],
                    "filingDate": rec["filingDate"][i],
                    "reportDate": rec.get("reportDate", [""] * len(forms))[i],
                    "accession": rec["accessionNumber"][i],
                    "primaryDocument": rec.get("primaryDocument", [""] * len(forms))[i],
                    "url": _filing_url(
                        cik,
                        rec["accessionNumber"][i],
                        rec.get("primaryDocument", [""] * len(forms))[i],
                    ),
                }
            )
            if len(rows) >= limit:
                break
        if not rows:
            return f"No {form_type or ''} filings found for {data.get('name', identifier)}.".replace(
                "  ", " "
            )

        if response_format == ResponseFormat.MARKDOWN:
            out = f"# Recent Filings: {data.get('name')} (CIK {cik})\n\n"
            if ff:
                out += f"*Filtered to form {form_type}.*\n\n"
            for r in rows:
                out += f"- **{r['form']}** — filed {r['filingDate']}"
                if r["reportDate"]:
                    out += f" (period {r['reportDate']})"
                out += f" — [document]({r['url']})\n"
            return truncate_response(out, "Lower the limit or filter by form_type.")
        return truncate_json_response(
            json.dumps(
                {"company": data.get("name"), "cik": cik, "filings": rows}, indent=2
            ),
            "",
        )
    except Exception as e:
        return _error_text(f"filings for {identifier}", e)


@mcp.tool(
    name="get_latest_filing",
    annotations={
        "title": "Get a Company's Latest Filing of a Type",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_latest_filing(
    identifier: Annotated[
        str,
        Field(
            description="Company ticker, CIK, or name (e.g., 'AAPL', 'Tesla')",
            min_length=1,
            max_length=120,
        ),
    ],
    form_type: Annotated[
        str,
        Field(
            description="Form type to fetch the latest of: '10-K' (annual), '10-Q' (quarterly), '8-K' (events), etc."
        ),
    ] = "10-K",
    response_format: Annotated[
        ResponseFormat, Field(description="'markdown' or 'json'")
    ] = ResponseFormat.MARKDOWN,
) -> str:
    """Get the single most recent filing of a given type, with a direct link to the document.

    Use this tool when:
    - The user wants "the latest 10-K" / "most recent quarterly report" / "newest 8-K"
    - You want to point the user straight at the primary document

    Args:
        identifier: Ticker, CIK, or company name.
        form_type: Form type (default '10-K').
        response_format: 'markdown' or 'json'.

    Returns:
        str: The latest matching filing's metadata and document URL.

    Example:
        Input: {"identifier": "TSLA", "form_type": "10-Q"}
        Output: Tesla's most recent quarterly report with a link
    """
    try:
        company = _resolve_cik(identifier)
        if not company:
            return f"No company found for '{identifier}'. Try search_company first."
        cik = int(company["cik_str"])
        data = fetch_json(f"https://data.sec.gov/submissions/CIK{_cik10(cik)}.json")
        rec = data.get("filings", {}).get("recent", {})
        forms = rec.get("form", [])
        ff = form_type.strip().upper()
        for i in range(len(forms)):
            if forms[i].upper() == ff:
                url = _filing_url(
                    cik, rec["accessionNumber"][i], rec.get("primaryDocument", [""])[i]
                )
                meta = {
                    "company": data.get("name"),
                    "cik": cik,
                    "form": forms[i],
                    "filingDate": rec["filingDate"][i],
                    "reportDate": rec.get("reportDate", [""] * len(forms))[i],
                    "accession": rec["accessionNumber"][i],
                    "url": url,
                }
                if response_format == ResponseFormat.MARKDOWN:
                    out = f"# Latest {forms[i]}: {data.get('name')} (CIK {cik})\n\n"
                    out += f"- **Filed:** {meta['filingDate']}\n"
                    if meta["reportDate"]:
                        out += f"- **Period:** {meta['reportDate']}\n"
                    out += f"- **Accession:** {meta['accession']}\n"
                    out += f"- **Document:** [{meta['url'].split('/')[-1]}]({meta['url']})\n"
                    sic = data.get("sicDescription")
                    if sic:
                        out += f"- **Industry:** {sic}\n"
                    return out
                return json.dumps(meta, indent=2)
        return f"No {form_type} filing found for {data.get('name', identifier)}."
    except Exception as e:
        return _error_text(f"latest {form_type} for {identifier}", e)


@mcp.tool(
    name="get_company_facts",
    annotations={
        "title": "Get Key Company Financials (XBRL)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_company_facts(
    identifier: Annotated[
        str,
        Field(
            description="Company ticker, CIK, or name (e.g., 'AAPL', 'Microsoft')",
            min_length=1,
            max_length=120,
        ),
    ],
    response_format: Annotated[
        ResponseFormat, Field(description="'markdown' or 'json'")
    ] = ResponseFormat.MARKDOWN,
) -> str:
    """Get a summary of a company's key reported financials from XBRL data.

    Pulls the most recent value of headline metrics (revenue, net income, total
    assets, liabilities, equity, cash, EPS) from the company's filings. (The full
    XBRL dataset has hundreds of concepts; this returns the highlights — use
    get_concept for the full history of a single metric.)

    Use this tool when:
    - The user wants a quick financial overview of a company

    Args:
        identifier: Ticker, CIK, or company name.
        response_format: 'markdown' or 'json'.

    Returns:
        str: Latest value of headline financial metrics.

    Example:
        Input: {"identifier": "AAPL"}
        Output: Apple's latest revenue, net income, assets, etc.
    """
    try:
        company = _resolve_cik(identifier)
        if not company:
            return f"No company found for '{identifier}'. Try search_company first."
        cik = int(company["cik_str"])
        data = fetch_json(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{_cik10(cik)}.json"
        )
        gaap = data.get("facts", {}).get("us-gaap", {})

        # Map friendly labels to candidate XBRL tags (first that exists wins).
        wanted = [
            (
                "Revenue",
                [
                    "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "Revenues",
                    "SalesRevenueNet",
                ],
            ),
            ("Net Income", ["NetIncomeLoss"]),
            ("Total Assets", ["Assets"]),
            ("Total Liabilities", ["Liabilities"]),
            ("Stockholders Equity", ["StockholdersEquity"]),
            ("Cash & Equivalents", ["CashAndCashEquivalentsAtCarryingValue"]),
            ("Diluted EPS", ["EarningsPerShareDiluted"]),
        ]

        def latest_fact(tags: List[str]):
            for tag in tags:
                concept = gaap.get(tag)
                if not concept:
                    continue
                units = concept.get("units", {})
                unit_key = next(iter(units), None)
                if not unit_key or not units[unit_key]:
                    continue
                # Most recent by filed date.
                facts = sorted(units[unit_key], key=lambda f: f.get("filed", ""))
                f = facts[-1]
                return f.get("val"), f.get("end"), f.get("form"), unit_key
            return None

        rows = []
        for label, tags in wanted:
            res = latest_fact(tags)
            if res:
                val, end, form, unit = res
                rows.append((label, val, end, form, unit))

        if not rows:
            return f"No XBRL financial facts available for {data.get('entityName', identifier)}."

        if response_format == ResponseFormat.MARKDOWN:
            out = f"# Financial Highlights: {data.get('entityName')} (CIK {cik})\n\n"
            out += "| Metric | Latest Value | As of | Source |\n|--------|--------------|-------|--------|\n"
            for label, val, end, form, unit in rows:
                shown = (
                    fmt_num(val)
                    if unit == "USD"
                    else (f"{val}" if unit != "USD/shares" else f"${val}")
                )
                out += f"| {label} | {shown} | {end} | {form} |\n"
            out += "\n*Use get_concept for the full history of any single metric.*"
            return truncate_response(out, "")
        return truncate_json_response(
            json.dumps(
                {
                    "company": data.get("entityName"),
                    "cik": cik,
                    "highlights": [
                        {"metric": l, "value": v, "asOf": e, "form": fm, "unit": u}
                        for l, v, e, fm, u in rows
                    ],
                },
                indent=2,
            ),
            "",
        )
    except Exception as e:
        return _error_text(f"company facts for {identifier}", e)


@mcp.tool(
    name="get_concept",
    annotations={
        "title": "Get a Financial Concept's History",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def get_concept(
    identifier: Annotated[
        str,
        Field(description="Company ticker, CIK, or name", min_length=1, max_length=120),
    ],
    concept: Annotated[
        str,
        Field(
            description="US-GAAP XBRL tag, e.g. 'Revenues', 'NetIncomeLoss', 'Assets', 'StockholdersEquity'"
        ),
    ] = "NetIncomeLoss",
    limit: Annotated[
        int,
        Field(
            description="Max periods to return, most recent first (1-40)", ge=1, le=40
        ),
    ] = 12,
    response_format: Annotated[
        ResponseFormat, Field(description="'markdown' or 'json'")
    ] = ResponseFormat.MARKDOWN,
) -> str:
    """Get the reported history of one financial concept (XBRL tag) for a company.

    Use this tool when:
    - The user wants a metric over time (e.g. "Apple's revenue over the years")
    - You need the trend of a specific GAAP line item

    Common tags: Revenues / RevenueFromContractWithCustomerExcludingAssessedTax,
    NetIncomeLoss, Assets, Liabilities, StockholdersEquity, EarningsPerShareDiluted.

    Args:
        identifier: Ticker, CIK, or company name.
        concept: US-GAAP XBRL tag.
        limit: Max periods.
        response_format: 'markdown' or 'json'.

    Returns:
        str: The concept's values over time with period end dates.

    Example:
        Input: {"identifier": "AAPL", "concept": "NetIncomeLoss", "limit": 8}
        Output: Apple's net income across recent periods
    """
    try:
        company = _resolve_cik(identifier)
        if not company:
            return f"No company found for '{identifier}'. Try search_company first."
        cik = int(company["cik_str"])
        tag = concept.strip()
        try:
            data = fetch_json(
                f"https://data.sec.gov/api/xbrl/companyconcept/CIK{_cik10(cik)}/us-gaap/{urllib.parse.quote(tag)}.json"
            )
        except EdgarError as e:
            if str(e) == "not_found":
                return (
                    f"Concept '{tag}' not found for this company. "
                    "Try a standard US-GAAP tag like 'Revenues', 'NetIncomeLoss', 'Assets', or 'StockholdersEquity'."
                )
            raise
        units = data.get("units", {})
        unit_key = next(iter(units), None)
        facts = units.get(unit_key, []) if unit_key else []
        # Most recent first, de-duplicate by (end, val).
        seen = set()
        uniq = []
        for f in sorted(facts, key=lambda x: x.get("end", ""), reverse=True):
            k = (f.get("end"), f.get("val"))
            if k in seen:
                continue
            seen.add(k)
            uniq.append(f)
            if len(uniq) >= limit:
                break

        if not uniq:
            return f"No data for concept '{tag}'."

        is_usd = unit_key == "USD"
        if response_format == ResponseFormat.MARKDOWN:
            out = (
                f"# {data.get('label', tag)} — {data.get('entityName')} (CIK {cik})\n\n"
            )
            desc = data.get("description")
            if desc:
                out += f"*{desc[:200]}*\n\n"
            out += f"**Unit:** {unit_key}\n\n| Period End | Value | Form | FY |\n|------------|-------|------|----|\n"
            for f in uniq:
                shown = fmt_num(f["val"]) if is_usd else f"{f['val']}"
                out += f"| {f.get('end')} | {shown} | {f.get('form')} | {f.get('fy')}{f.get('fp', '')} |\n"
            return truncate_response(out, "Lower the limit for fewer periods.")
        return truncate_json_response(
            json.dumps(
                {
                    "company": data.get("entityName"),
                    "concept": tag,
                    "unit": unit_key,
                    "facts": [
                        {
                            "end": f.get("end"),
                            "val": f.get("val"),
                            "form": f.get("form"),
                            "fy": f.get("fy"),
                            "fp": f.get("fp"),
                        }
                        for f in uniq
                    ],
                },
                indent=2,
            ),
            "",
        )
    except Exception as e:
        return _error_text(f"concept {concept} for {identifier}", e)


@mcp.tool(
    name="full_text_search",
    annotations={
        "title": "Full-Text Search SEC Filings",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def full_text_search(
    query: Annotated[
        str,
        Field(
            description='Words or a "quoted phrase" to search for across filings',
            min_length=1,
            max_length=200,
        ),
    ],
    forms: Annotated[
        str,
        Field(
            description="Optional comma-separated form filter, e.g. '10-K' or '10-K,10-Q'. Empty for all."
        ),
    ] = "",
    limit: Annotated[
        int, Field(description="Max results to return (1-25)", ge=1, le=25)
    ] = 10,
    response_format: Annotated[
        ResponseFormat, Field(description="'markdown' or 'json'")
    ] = ResponseFormat.MARKDOWN,
) -> str:
    """Search the full text of SEC filings (last ~10 years) by keyword or phrase.

    Use this tool when:
    - The user wants to find which companies mention a topic in their filings
    - The user wants filings discussing a specific term, product, or risk

    Args:
        query: Words or a quoted phrase.
        forms: Optional form-type filter.
        limit: Max results.
        response_format: 'markdown' or 'json'.

    Returns:
        str: Matching filings with company, form, date, and a link.

    Example:
        Input: {"query": "\"artificial intelligence\"", "forms": "10-K", "limit": 5}
        Output: Recent 10-K filings discussing artificial intelligence
    """
    try:
        params = {"q": query.strip()}
        if forms.strip():
            params["forms"] = forms.strip()
        url = "https://efts.sec.gov/LATEST/search-index?" + urllib.parse.urlencode(
            params
        )
        data = fetch_json(url)
        hits = data.get("hits", {}).get("hits", [])[:limit]
        total = data.get("hits", {}).get("total", {}).get("value", 0)
        if not hits:
            return f"No filings found matching {query}."

        def _first(v):
            return v[0] if isinstance(v, list) and v else (v or "")

        def row(h):
            src = h.get("_source", {})
            # _id is like "accession:primaryDoc"; accession is also in src["adsh"].
            doc = h.get("_id", "").split(":")
            accn = src.get("adsh") or (doc[0] if doc else "")
            primary = doc[1] if len(doc) == 2 else ""
            cik = _first(src.get("ciks"))
            url = ""
            if accn and primary and cik:
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn.replace('-', '')}/{primary}"
            elif accn and cik:
                # Fall back to the filing index page.
                url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={int(cik)}"
            names = src.get("display_names") or []
            return {
                "company": names[0] if names else "Unknown",
                "form": _first(src.get("root_forms"))
                or src.get("form")
                or src.get("file_type"),
                "date": src.get("file_date"),
                "url": url,
            }

        rows = [row(h) for h in hits]
        if response_format == ResponseFormat.MARKDOWN:
            out = f"# Full-Text Search: {query}\n\n*~{total:,} total matches; showing {len(rows)}.*\n\n"
            for r in rows:
                out += f"- **{r['company']}** — {r['form']} ({r['date']})"
                if r["url"]:
                    out += f" — [document]({r['url']})"
                out += "\n"
            return truncate_response(out, "Add a form filter or refine the query.")
        return truncate_json_response(
            json.dumps({"query": query, "total": total, "results": rows}, indent=2), ""
        )
    except Exception as e:
        return _error_text("full-text search", e)


# ============================================================================
# RUN SERVER
# ============================================================================


def main() -> None:
    """Run the MCP server with stdio transport (default for Claude Desktop)."""
    mcp.run()


if __name__ == "__main__":
    main()
