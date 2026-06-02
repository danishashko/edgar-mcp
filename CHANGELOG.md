# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-06-02

Initial release. Every tool was verified end to end by driving the real MCP
server over stdio against the live SEC EDGAR API, and through Claude's own MCP
client.

### Added

- **`search_company`** — find a company by name or ticker and get its CIK.
- **`get_recent_filings`** — a company's recent filings, optionally filtered by
  form type, with direct document links.
- **`get_latest_filing`** — the single most recent filing of a given type
  (10-K, 10-Q, 8-K, ...) with a direct link to the primary document.
- **`get_company_facts`** — a summary of headline financials (revenue, net
  income, assets, liabilities, equity, cash, EPS) from XBRL data.
- **`get_concept`** — the reported history of a single financial concept (XBRL
  tag) over time.
- **`full_text_search`** — search the full text of SEC filings by keyword or
  phrase, optionally filtered by form type.
- **`npx -y edgar-mcp`** launcher (`bin/cli.js`) that finds Python 3.10+, builds
  an isolated venv, installs dependencies on first run, and passes
  `SEC_USER_AGENT` through.
- No API key required; sends the SEC-required descriptive User-Agent, handles
  gzip, and retries on rate limits (10 req/s).

[1.0.0]: https://github.com/danishashko/edgar-mcp/releases/tag/v1.0.0
