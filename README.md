---
title: Xpdite Scraper
emoji: 🕷️
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---
# XpditeS: Tiered Web Scraper

![XpditeS Header](https://img.shields.io/badge/Status-Active-brightgreen) ![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue)

**[Try it live on Hugging Face Spaces](https://huggingface.co/spaces/Kashyaptan/xpdite-scraper)**

**XpditeS** is a high-performance, tiered web scraping engine that powers the official Xpdite Web Fetch MCP tool. It is designed to navigate complex bot protections, JavaScript-heavy sites, and rate limits through an intelligent escalation waterfall (Basic HTTP → JS Rendering → Undetected Headless Browsers).

This repository contains both a **Terminal User Interface (TUI)** and a **FastAPI Web UI** designed for testing, benchmarking, and extracting data from target websites.

## ✨ Key Features
- **Intelligent Tiered Fallback**: Automatically escalates from fast HTTP requests (`httpx`/`curl_cffi`) up to fully undetected headless browser environments (`Playwright`, `Nodriver`, `Camoufox`).
- **Dual Interfaces**: 
  - An interactive, rich Terminal UI (`XpditeS`).
  - A responsive Web UI built with FastAPI + vanilla HTML/JS.
- **Precision Modes**: Select between extracting exactly the main article body (`Trafilatura`) or capturing the complete DOM as raw Markdown.
- **Performance Benchmarking**: Built-in timers and character counts to evaluate the efficiency of specific extraction strategies on target sites.
- **Docker Ready**: Fully containerized with headless browser requirements pre-configured, ready for immediate deployment on platforms like Hugging Face Spaces.

## 🚀 Quick Start

### Local Terminal (TUI)
Install the CLI tool globally via `uv`:
```bash
uv tool install .
XpditeS
```

### Local Web UI
Launch the FastAPI web interface locally:
```bash
uv run uvicorn main:app --reload --port 7860
```
Then open http://127.0.0.1:7860

## 🐳 Docker
Build and run with Docker:
```bash
docker build -t xpdites-scraper .
docker run -p 7860:7860 xpdites-scraper
```

## 📁 Project Structure
```
├── main.py              # FastAPI backend
├── static/              # Frontend assets (HTML, CSS, JS)
├── scrape/
│   └── scraper.py       # Core scraping engine
├── assets/
│   └── logo.jpg         # Logo image
├── Dockerfile           # Docker configuration
└── requirements.txt     # Python dependencies
```

## 🔧 Scraping Tiers
| Tier | Method | Speed | Use Case |
|------|--------|-------|----------|
| Auto | Smart fallback | Varies | Recommended for most sites |
| 1 | curl_cffi | ~200ms | Static sites, articles |
| 2 | Camoufox | ~2-5s | JS-rendered content |
| 3 | Nodriver | ~3-8s | Heavy bot protection |
