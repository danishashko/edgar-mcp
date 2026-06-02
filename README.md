# SEC EDGAR MCP Server 🏛️

[![npm version](https://img.shields.io/npm/v/edgar-mcp.svg)](https://www.npmjs.com/package/edgar-mcp)
[![npm downloads](https://img.shields.io/npm/dm/edgar-mcp.svg)](https://www.npmjs.com/package/edgar-mcp)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

U.S. SEC filings and financial data for Claude Desktop and any MCP-compatible client, powered by [SEC EDGAR](https://www.sec.gov/edgar). Search companies, pull filings (10-K, 10-Q, 8-K, Form 4, ...), read XBRL financials, and full-text search across all filings — all from natural language. **No API key required.**

> **npm package:** [`edgar-mcp`](https://www.npmjs.com/package/edgar-mcp) &nbsp;·&nbsp; **GitHub repo:** [`danishashko/edgar-mcp`](https://github.com/danishashko/edgar-mcp).

## 🎯 What You Get

- 🔎 **Company lookup** by name or ticker → CIK
- 🗂️ **Recent filings** (any form type) with direct document links
- 📄 **Latest filing** of a type (newest 10-K / 10-Q / 8-K) in one call
- 💰 **Financial highlights** (revenue, net income, assets, equity, EPS) from XBRL
- 📈 **Concept history** — any GAAP line item over time
- 🔬 **Full-text search** across the last ~10 years of filings

Every tool returns human-readable **markdown** by default, or structured **JSON** on request (`response_format: "json"`). Lightweight (Python standard library + `mcp` only), no API key, retries on rate limits.

## 🚀 Quick Start

Add this to your Claude Desktop config and restart Claude:

- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "edgar": {
      "command": "npx",
      "args": ["-y", "edgar-mcp"],
      "env": {
        "SEC_USER_AGENT": "your-app-name your@email.com"
      }
    }
  }
}
```

The SEC asks every API client to send a descriptive `User-Agent` with contact info. Set `SEC_USER_AGENT` to your own name/email (a default is provided so it works out of the box). On first launch the npx wrapper creates an isolated Python environment and installs the dependency (one-time, ~a minute). You need **Python 3.10+** and **Node.js 16+**.

### Prefer a global install?

```bash
npm install -g edgar-mcp
```

```json
{
  "mcpServers": {
    "edgar": {
      "command": "edgar-mcp",
      "env": { "SEC_USER_AGENT": "your-app-name your@email.com" }
    }
  }
}
```

## 🔧 Available Tools

| Tool | What it returns | Parameters |
|------|-----------------|------------|
| `search_company` | Companies matching a name/ticker, with their CIK | `query`, `limit` |
| `get_recent_filings` | Recent filings (form, dates, link), optional form filter | `identifier`, `form_type`, `limit` |
| `get_latest_filing` | The newest filing of a given type, with a document link | `identifier`, `form_type` |
| `get_company_facts` | Headline financials (revenue, net income, assets, equity, cash, EPS) | `identifier` |
| `get_concept` | One XBRL concept's reported history over time | `identifier`, `concept`, `limit` |
| `full_text_search` | Filings matching a keyword/phrase across all companies | `query`, `forms`, `limit` |

Every tool also accepts `response_format` (`"markdown"`, the default, or `"json"`). `identifier` accepts a ticker, CIK, or company name.

**Common XBRL concepts for `get_concept`:** `Revenues` / `RevenueFromContractWithCustomerExcludingAssessedTax`, `NetIncomeLoss`, `Assets`, `Liabilities`, `StockholdersEquity`, `EarningsPerShareDiluted`.

## 💬 Example Prompts

Once the server is connected, just ask Claude:

- "What's Apple's latest 10-K?"
- "Show me Tesla's recent 8-K filings."
- "What are Microsoft's headline financials?"
- "Show me NVIDIA's net income over the last few years."
- "Which companies mention 'quantum computing' in their 10-Ks?"
- "Find the CIK for Berkshire Hathaway."

## 🐛 Troubleshooting

**"SEC EDGAR is rate-limiting requests"**
EDGAR allows ~10 requests/second. The server retries automatically; wait a moment if it persists.

**"Not found"**
Use `search_company` to confirm the exact ticker/CIK first.

**"Command not found" / "Python not found"**
Ensure Python 3.10+ and Node.js 16+ are installed and on your PATH. On macOS/Linux, try `python3`.

**Tools not showing up in Claude**
1. Confirm the config file is valid JSON (no trailing commas).
2. Fully quit and reopen Claude Desktop.

## 🛠️ Manual Installation (Alternative)

If you would rather run the Python file directly instead of via npx:

**1. Download the server and install the dependency**

```bash
pip install mcp
```

(or `pip3` on macOS/Linux)

**2. Point Claude Desktop at it**

```json
{
  "mcpServers": {
    "edgar": {
      "command": "python3",
      "args": ["/absolute/path/to/edgar_mcp.py"],
      "env": { "SEC_USER_AGENT": "your-app-name your@email.com" }
    }
  }
}
```

On Windows use `"command": "python"` and a path like `"C:\\path\\to\\edgar_mcp.py"`.

**3. Restart Claude Desktop.**

## 🔒 Privacy & Rate Limits

- Uses the official [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) — public, no key.
- Requests go straight from your machine to the SEC. Nothing is stored or proxied.
- The SEC requires a descriptive `User-Agent` with contact info and limits ~10 requests/second.
- Intended for personal, educational, and research use.

## 📝 Notes

- `identifier` is flexible: ticker (`AAPL`), CIK (`320193`), or name (`Apple`).
- Financial data comes from XBRL, first required by the SEC in 2009, so history goes back that far for most filers.
- `get_company_facts` returns highlights; use `get_concept` for the full series of any one metric.

## 📋 Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

## 📚 Resources

- [Model Context Protocol](https://modelcontextprotocol.io/)
- [SEC EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [EDGAR full-text search](https://efts.sec.gov/LATEST/search-index?q=example)

## ⚖️ Legal Disclaimer

This tool uses the public SEC EDGAR APIs but is not affiliated with or endorsed by the U.S. Securities and Exchange Commission. Use is subject to the SEC's [website policies](https://www.sec.gov/privacy.htm). Data is provided as-is for personal, educational, and research purposes; verify against the original filings before relying on it.

## 👤 Author

**Daniel Shashko**
- GitHub: [@danishashko](https://github.com/danishashko)
- LinkedIn: [daniel-shashko](https://linkedin.com/in/daniel-shashko)
- npm: [danielshashko](https://www.npmjs.com/~danielshashko)

## 📄 License

MIT © Daniel Shashko
