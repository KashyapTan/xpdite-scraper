<div align="center">
  <img alt="XpditeS" src="./assets/logo.svg" width="180">
</div>

<h2 align="center">XpditeS - Tiered Web Scraper</h2>

<p align="center">High-performance, defensive scraping engine powering the official Xpdite Web Fetch MCP tool.</p>

<div align="center">
  <table>
    <tr>
      <td align="center">
        <a href="https://xpdites.vercel.app/"><img alt="Status" src="https://img.shields.io/badge/Status-Active-16a34a?style=for-the-badge"></a>
      </td>
      <td align="center">
        <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-2563eb?style=for-the-badge&logo=python&logoColor=white"></a>
      </td>
      <td align="center">
        <a href="https://fastapi.tiangolo.com/"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0ea5e9?style=for-the-badge&logo=fastapi&logoColor=white"></a>
      </td>
      <td align="center">
        <a href="https://xpdites.vercel.app/"><img alt="Vercel" src="https://img.shields.io/badge/Deploy-Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white"></a>
      </td>
    </tr>
    <tr>
      <td align="center">
        <a href="#scraping-tiers"><img alt="Tiered Escalation" src="https://img.shields.io/badge/Tiered-Escalation-0f766e?style=for-the-badge"></a>
      </td>
      <td align="center">
        <a href="#local-terminal-tui"><img alt="TUI" src="https://img.shields.io/badge/Interface-TUI-111827?style=for-the-badge"></a>
      </td>
      <td align="center">
        <a href="https://xpdites.vercel.app/"><img alt="Web UI" src="https://img.shields.io/badge/Interface-Web%20UI-1d4ed8?style=for-the-badge"></a>
      </td>
      <td align="center">
        <a href="https://xpdites.vercel.app/docs"><img alt="FastAPI API" src="https://img.shields.io/badge/API-FastAPI-0ea5e9?style=for-the-badge&logo=fastapi&logoColor=white"></a>
      </td>
    </tr>
  </table>
</div>

---

## What it does

XpditeS is a tiered, concurrent web scraper built to extract clean text from modern, JS-heavy sites without wasting time on heavy browser automation when it is not needed. It starts with fast HTTP impersonation, escalates to stealthy browsers on demand, and reports exactly which tier won along with timing and character counts.

It ships with both a rich Terminal UI and a FastAPI-powered Web UI so you can benchmark, compare tiers, and ship reliable fetch results at scale.

---

## Why XpditeS

- **Concurrent tiered escalation**: Starts fast, staggers browser tiers, and cancels when a winner hits quality thresholds.
- **Real-world site handling**: JS-wall detection, SPA skeleton checks, access restriction signals, and optional Medium/archive relays.
- **Precision extraction**: Clean article text via Trafilatura or full-page Markdown from the DOM.
- **Observability built in**: Tier timing, character counts, warnings, and suggestions are surfaced in CLI/UI output.
- **Safety guardrails**: URL validation blocks localhost/private IPs and enforces safe redirects and browser requests.
- **Multiple interfaces**: Interactive TUI, FastAPI Web UI, plus Streamlit UI for quick demos.

---

## Scraping tiers

| Tier | Method | Notes | Typical Use |
| --- | --- | --- | --- |
| Auto | Concurrent fallback | Staggers tiers and stops on strong results | Recommended default |
| 1 | curl_cffi HTTP | Fast impersonated HTTP with redirect safety | Static pages, articles |
| 2 | Camoufox | Stealthy Firefox with fingerprinting | JS-heavy sites |
| 3 | Nodriver | Undetected headless browser | Tough anti-bot flows (disabled by default) |

Special handlers:
- **X/Twitter**: Guest-mode extraction via `twikit`.
- **Medium**: Optional external relay and archive fallbacks when enabled.

---

## Extraction modes

- **precision**: Main content only (Trafilatura + HTML fallback).
- **full**: Full DOM converted to Markdown for maximum context.

---

## Quick start

### Local Terminal (TUI)
Install the CLI with `uv` and launch interactive mode:
```bash
uv tool install .
XpditeS
```

Run a single URL without prompts:
```bash
XpditeS https://example.com/article
```

### Local Web UI (FastAPI)
```bash
uv run uvicorn main:app --reload --port 7860
```
Open http://127.0.0.1:7860

### Streamlit UI (optional)
```bash
uv run streamlit run web_ui.py
```

---

## Vercel Deployment

XpditeS is configured for 1-click deployment on Vercel's Hobby plan:
**Live Demo:** [https://xpdites.vercel.app/](https://xpdites.vercel.app/)

> **⚠️ Limitation:** Due to Vercel's serverless constraints (500MB storage limit and no persistent environment), **browser-based tiers (Tier 2 and Tier 3) are not available** in this cloud deployment. The Vercel instance relies entirely on Tier 1 (HTTP) and Tier 1.5 (Jina) scraping. For full tier support, run XpditeS locally or via Docker.

---

## Docker

```bash
docker build -t xpdites-scraper .
docker run -p 7860:7860 xpdites-scraper
```

---

## API

`POST /api/scrape`
```json
{
  "url": "https://example.com/article",
  "mode": "precision",
  "tier": "Auto"
}
```

Response fields include `success`, `tier_used`, `content`, `char_count`, `elapsed_time`, and `error`.

---

## Configuration

| Env var | Default | Purpose |
| --- | --- | --- |
| `WEBSEARCH_ENABLE_EXTERNAL_RELAYS` | off | Enable Medium/Archive relay fallbacks |
| `WEBSEARCH_ENABLE_UNSAFE_TIER3_BROWSER` | off | Enable Nodriver Tier 3 |
| `PORT` | 7860 | FastAPI server port |

---

## Project structure

```
├── main.py              # FastAPI backend
├── static/              # Web UI (HTML, CSS, JS)
├── scrape/
│   └── scraper.py       # Core engine + TUI
├── web_ui.py            # Streamlit UI (optional)
├── assets/
│   └── logo.svg         # Logo image
├── Dockerfile           # Container build
└── requirements.txt     # Python dependencies
```
