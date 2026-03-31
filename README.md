# XpditeS: Tiered Web Scraper

![XpditeS Header](https://img.shields.io/badge/Status-Active-brightgreen) ![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)

**XpditeS** is a high-performance, tiered web scraping engine that powers the official Xpdite Web Fetch MCP tool. It is designed to navigate complex bot protections, JavaScript-heavy sites, and rate limits through an intelligent escalation waterfall (Basic HTTP → JS Rendering → Undetected Headless Browsers).

This repository contains both a **Terminal User Interface (TUI)** and a **Streamlit Web UI** designed for testing, benchmarking, and extracting data from target websites. It allows developers to test scraping times, efficiency, and success rates across various extraction modes and fallback tiers.

## ✨ Key Features
- **Intelligent Tiered Fallback**: Automatically escalates from fast HTTP requests (`httpx`/`curl_cffi`) up to fully undetected headless browser environments (`Playwright`, `Nodriver`, `Camoufox`).
- **Dual Interfaces**: 
  - An interactive, rich Terminal UI (`XpditeS`).
  - A responsive Web Dashboard built with Streamlit (`web_ui.py`).
- **Precision Modes**: Select between extracting exactly the main article body (`Trafilatura`) or capturing the complete DOM as raw Markdown.
- **Performance Benchmarking**: Built-in timers and character counts to evaluate the efficiency of specific extraction strategies on target sites.
- **Docker Ready**: Fully containerized with headless browser requirements pre-configured, ready for immediate deployment on platforms like Hugging Face Spaces.

## 🚀 Quick Start
### Local Terminal (TUI) Use
Install the CLI tool globally via `uv`:
```bash
uv tool install .
XpditeS
```

### Local Web UI
Launch the Streamlit testing interface locally:
```bash
uv run streamlit run web_ui.py
```
