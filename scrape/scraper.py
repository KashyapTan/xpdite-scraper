#!/usr/bin/env python3
"""
scraper.py — Universal tiered web scraper with interactive CLI.

Single self-contained file. No separate imports needed.

Install:
    uv add questionary rich curl_cffi camoufox nodriver twikit trafilatura browserforge beautifulsoup4 markdownify httpx
    uv run python -m camoufox fetch

Usage:
    python scraper.py          # interactive mode
    python scraper.py <url>    # non-interactive, auto mode, precision extraction
"""

import sys
import os
import asyncio
import re
import random
import time
import io
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from contextlib import redirect_stderr

# ═══════════════════════════════════════════════════════════════════════════════
# DEPENDENCY CHECK
# ═══════════════════════════════════════════════════════════════════════════════

def _check_ui_deps():
    missing = []
    for pkg in ["questionary", "rich"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"\n  Missing UI packages: {', '.join(missing)}")
        print(f"  Run: uv add {' '.join(missing)}\n")
        sys.exit(1)

_check_ui_deps()

import questionary
from questionary import Style
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.syntax import Syntax
from rich.rule import Rule
from rich import box
from rich.align import Align

# ═══════════════════════════════════════════════════════════════════════════════
# THEME
# ═══════════════════════════════════════════════════════════════════════════════

console = Console()

Q_STYLE = Style([
    ("qmark",        "fg:#00d7af bold"),
    ("question",     "fg:#ffffff bold"),
    ("answer",       "fg:#00d7af bold"),
    ("pointer",      "fg:#00d7af bold"),
    ("highlighted",  "fg:#00d7af bold"),
    ("selected",     "fg:#00d7af"),
    ("separator",    "fg:#444444"),
    ("instruction",  "fg:#666666"),
    ("text",         "fg:#cccccc"),
    ("disabled",     "fg:#444444 italic"),
])

ACCENT   = "#00d7af"
DIM_COL  = "#555555"
WARN_COL = "#ffaf00"
ERR_COL  = "#ff5f5f"
OK_COL   = "#00d7af"

# ═══════════════════════════════════════════════════════════════════════════════
# BANNER
# ═══════════════════════════════════════════════════════════════════════════════

BANNER = r"""
   _____                                 
  / ____|                                
 | (___   ___ _ __ __ _ _ __   ___ _ __ 
  \___ \ / __| '__/ _` | '_ \ / _ \ '__|
  ____) | (__| | | (_| | |_) |  __/ |   
 |_____/ \___|_|  \__,_| .__/ \___|_|   
                        | |              
                        |_|              
"""

def show_banner():
    console.print()
    console.print(Align.center(Text(BANNER, style=f"bold {ACCENT}")))
    console.print(Align.center(Text("Universal Web Scraper  •  Interactive Mode", style=f"dim {ACCENT}")))
    console.print()

# ═══════════════════════════════════════════════════════════════════════════════
# SITE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

TWITTER_DOMAINS = {"twitter.com", "x.com", "www.twitter.com", "www.x.com"}

MEDIUM_DOMAINS = {
    "medium.com", "towardsdatascience.com", "betterprogramming.pub",
    "levelup.gitconnected.com", "javascript.plainenglish.io",
    "uxdesign.cc", "hackernoon.com", "codeburst.io", "itnext.io",
    "proandroiddev.com", "infosecwriteups.com",
}

JS_REQUIRED_DOMAINS = {
    "x.com", "twitter.com", "www.x.com", "www.twitter.com",
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com",
    "linkedin.com", "www.linkedin.com",
    "tiktok.com", "www.tiktok.com",
    "reddit.com", "www.reddit.com",
    "notion.so", "www.notion.so",
    "figma.com", "www.figma.com",
}

JS_WALL_SIGNALS = [
    "javascript is disabled",
    "javascript must be enabled",
    "enable javascript",
    "please enable javascript",
    "enhanced tracking protection",
]

def _host(url: str) -> str:
    return urlparse(url).hostname or ""

def is_twitter(url: str) -> bool:
    return _host(url) in TWITTER_DOMAINS

def is_medium(url: str) -> bool:
    h = _host(url)
    return h in MEDIUM_DOMAINS or h.endswith(".medium.com")

def needs_js(url: str) -> bool:
    return _host(url) in JS_REQUIRED_DOMAINS

def has_js_wall(html: str) -> bool:
    return any(s in html[:3000].lower() for s in JS_WALL_SIGNALS)

def detect_site_type(url: str) -> str:
    if is_twitter(url): return "twitter"
    if is_medium(url):  return "medium"
    if needs_js(url):   return "js-spa"
    return "general"

# ═══════════════════════════════════════════════════════════════════════════════
# JS SKELETON DETECTOR
# ═══════════════════════════════════════════════════════════════════════════════

_SKELETON_RATIO    = 0.04
_SKELETON_MIN_HTML = 10_000

SPA_SIGNATURES = [
    '<div id="root">', '<div id="app">', '<div id="__next">',
    '<div id="gatsby-focus-wrapper">', 'window.__next_data__',
    'ng-version=', 'data-reactroot',
]

def is_js_skeleton(html: str, text: str) -> bool:
    if len(html) < _SKELETON_MIN_HTML:
        return False
    if len(text) / max(len(html), 1) < _SKELETON_RATIO:
        return True
    html_lower = html[:5000].lower()
    if any(sig.lower() in html_lower for sig in SPA_SIGNATURES) and len(text) < 500:
        return True
    return False

# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════

# Global extraction mode — set by the UI before each scrape
_EXTRACT_MODE: str = "precision"

def extract(html: str, url: str = "") -> str:
    """
    precision: trafilatura — main content only (articles, blogs, docs)
    full:      markdownify — entire DOM as Markdown (crawl4ai equivalent)
    """
    if _EXTRACT_MODE == "full":
        try:
            import markdownify
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "svg", "noscript", "meta", "head"]):
                tag.decompose()
            md = markdownify.markdownify(
                str(soup),
                heading_style="ATX",
                bullets="-",
                strip=["a"],
                convert_as_inline=["img"],
            )
            md = re.sub(r'\n{3,}', '\n\n', md).strip()
            if md and len(md) > 100:
                return md
        except ImportError:
            pass
        except Exception:
            pass

    # precision / fallback
    try:
        import trafilatura
        result = trafilatura.extract(
            html, url=url or None,
            include_comments=False, include_tables=True,
            no_fallback=False, favor_recall=True, deduplicate=True,
        )
        if result and len(result.strip()) > 100:
            return result.strip()
    except Exception:
        pass

    # BeautifulSoup plain-text fallback
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer",
                          "aside", "form", "svg", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception:
        text = re.sub(r'<[^>]+>', ' ', html)

    return re.sub(r'\n{3,}', '\n\n', text).strip()

# ═══════════════════════════════════════════════════════════════════════════════
# FETCH TIERS
# ═══════════════════════════════════════════════════════════════════════════════

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
]

async def tier1_curl(url: str) -> tuple[str, str] | None:
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return None

    targets = ["chrome124", "chrome120", "chrome110", "edge101", "edge99"]
    try:
        async with AsyncSession() as s:
            r = await s.get(
                url,
                impersonate=random.choice(targets),
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.google.com/",
                },
                timeout=15,
                allow_redirects=True,
            )
        if r.status_code == 200 and len(r.text) > 500:
            if has_js_wall(r.text):
                return None
            text = extract(r.text, url)
            return (text, r.text)
        return None
    except Exception:
        return None


async def tier1_5_jina(url: str) -> str | None:
    try:
        import httpx
    except ImportError:
        return None

    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Accept": "text/plain", "X-Return-Format": "text"}
    api_key = os.environ.get("JINA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            r = await client.get(jina_url, headers=headers)
            r.raise_for_status()
        content = r.text.strip()
        return content if content and len(content) > 200 else None
    except Exception:
        return None


async def tier2_camoufox(url: str) -> str | None:
    try:
        from camoufox.async_api import AsyncCamoufox
        from browserforge.fingerprints import Screen
    except ImportError:
        return None
    try:
        async with AsyncCamoufox(
            headless=True,
            os=["windows", "macos"],
            screen=Screen(max_width=1920, max_height=1080),
            humanize=True,
            firefox_user_prefs={
                "privacy.trackingprotection.enabled": False,
                "privacy.trackingprotection.pbmode.enabled": False,
                "privacy.trackingprotection.socialtracking.enabled": False,
                "privacy.trackingprotection.fingerprinting.enabled": False,
                "privacy.trackingprotection.cryptomining.enabled": False,
                "privacy.contentblocking.category": "standard",
                "network.cookie.cookieBehavior": 0,
            },
        ) as browser:
            page = await browser.new_page()
            await page.goto(url, wait_until="load", timeout=30_000)
            html = await page.content()
            await page.close()

        if has_js_wall(html):
            return None
        result = extract(html, url)
        return result if len(result) > 100 else None
    except Exception:
        return None


async def tier3_nodriver(url: str) -> str | None:
    try:
        import nodriver as uc
    except ImportError:
        return None
    browser = None
    try:
        browser = await uc.start(headless=True)
        page = await asyncio.wait_for(browser.get(url), timeout=45.0)
        html = await asyncio.wait_for(page.get_content(), timeout=10.0)
        if not html or has_js_wall(html):
            return None
        return extract(html, url)
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None
    finally:
        if browser:
            try:
                await browser.stop()
            except Exception:
                pass

# ═══════════════════════════════════════════════════════════════════════════════
# SPECIAL HANDLERS
# ═══════════════════════════════════════════════════════════════════════════════

async def handle_twitter(url: str) -> str | None:
    try:
        from twikit.guest import GuestClient
    except ImportError:
        return None

    m = re.search(r'/status/(\d+)', url)
    if not m:
        return None
    tweet_id = m.group(1)

    try:
        client = GuestClient()
        await client.activate()
        tweet = await client.get_tweet_by_id(tweet_id)
        if not tweet:
            return None

        lines = []
        if hasattr(tweet, 'user') and tweet.user:
            lines.append(f"@{tweet.user.screen_name} — {tweet.user.name}")
        if hasattr(tweet, 'created_at') and tweet.created_at:
            lines.append(f"Posted: {tweet.created_at}")
        lines.append("")
        lines.append(getattr(tweet, 'full_text', None) or getattr(tweet, 'text', '') or "")
        lines.append("")
        stats = []
        for attr, label in [('favorite_count', 'Likes'), ('retweet_count', 'Retweets'), ('reply_count', 'Replies')]:
            if hasattr(tweet, attr):
                stats.append(f"{label}: {getattr(tweet, attr)}")
        if stats:
            lines.append("  ".join(stats))
        if getattr(tweet, 'media', None):
            lines.append(f"\nMedia ({len(tweet.media)} item(s)):")
            for med in tweet.media:
                src = getattr(med, 'media_url_https', None) or getattr(med, 'url', None)
                if src:
                    lines.append(f"  {src}")
        return "\n".join(lines)
    except Exception:
        return None


async def handle_medium(url: str) -> str | None:
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return None

    for mirror in [f"https://freedium.cfd/{url}", f"https://freedium-mirror.cfd/{url}"]:
        try:
            async with AsyncSession() as s:
                r = await s.get(mirror, impersonate="chrome124",
                                headers={"Accept-Language": "en-US,en;q=0.9"},
                                timeout=20, allow_redirects=True)
            if r.status_code == 200 and len(r.text) > 500:
                text = extract(r.text, url)
                if len(text) > 300:
                    return text
        except Exception:
            continue
    return None


async def handle_archive(url: str) -> str | None:
    try:
        from curl_cffi.requests import AsyncSession
        async with AsyncSession() as s:
            r = await s.get(f"https://archive.ph/newest/{url}",
                            impersonate="chrome124",
                            headers={"Accept-Language": "en-US,en;q=0.9"},
                            timeout=20, allow_redirects=True)
        if r.status_code == 200 and len(r.text) > 500:
            text = extract(r.text, url)
            if len(text) > 300:
                return text
    except Exception:
        pass
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape(url: str, force_tier: int | None = None) -> tuple[str, str] | None:
    if force_tier is None:
        if is_twitter(url):
            r = await handle_twitter(url)
            if r: return ("twitter_twikit", r)
        elif is_medium(url):
            r = await handle_medium(url)
            if r: return ("medium_freedium", r)
            r = await handle_archive(url)
            if r: return ("medium_archive", r)

    run_t1 = force_tier == 1 or (force_tier is None and not needs_js(url))
    if run_t1:
        t1 = await tier1_curl(url)
        if t1 is not None:
            text, raw_html = t1
            if not is_js_skeleton(raw_html, text) and text:
                return ("tier1_curl_cffi", text)
            # skeleton — fall through to Jina
        if force_tier == 1:
            return None

    # Tier 1.5 — Jina Reader (free, serverside JS rendering)
    if force_tier not in (1, 2, 3) or force_tier is None:
        if not (force_tier in (2, 3)):
            r = await tier1_5_jina(url)
            if r: return ("tier1_5_jina", r)

    if force_tier in (None, 2):
        r = await tier2_camoufox(url)
        if r: return ("tier2_camoufox", r)
        if force_tier == 2:
            return None

    if force_tier in (None, 3):
        r = await tier3_nodriver(url)
        if r: return ("tier3_nodriver", r)

    return None

# ═══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _site_hint(site_type: str) -> str:
    return {
        "twitter":  "twikit API handler will run automatically",
        "medium":   "freedium.cfd paywall bypass will run first",
        "js-spa":   "Tier 1 skipped — known JS-only domain",
        "general":  "Tier 1 fast-path, auto-escalates if JS skeleton",
    }.get(site_type, "")

def _save_path(url: str, label: str) -> Path:
    host = re.sub(r'[^\w.-]', '_', _host(url) or "output")
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext  = ".md" if _EXTRACT_MODE == "full" else ".txt"
    return Path(f"{host}_{label}_{ts}{ext}")

def show_summary(url: str, mode: str, tier_label: str, output: str):
    site_type = detect_site_type(url)
    hint      = _site_hint(site_type)

    table = Table(box=box.ROUNDED, border_style=DIM_COL, show_header=False,
                  padding=(0, 2), expand=False)
    table.add_column("key",   style="dim", width=12)
    table.add_column("value", style="white")
    table.add_row("URL",    f"[bold]{url}[/]")
    table.add_row("Site",   f"[{ACCENT}]{site_type}[/]  [dim]{hint}[/]")
    table.add_row("Mode",   f"[{ACCENT}]{mode}[/]")
    table.add_row("Tier",   f"[{ACCENT}]{tier_label}[/]")
    table.add_row("Output", f"[{ACCENT}]{output}[/]")

    console.print()
    console.print(Panel(table, title="[bold]Scrape Job[/]", border_style=ACCENT,
                        title_align="left", padding=(1, 2)))
    console.print()

def show_result(label: str, content: str, url: str, elapsed: float, output_choice: str):
    char_count = len(content)
    line_count = content.count('\n')

    stats = Table(box=None, show_header=False, padding=(0, 3), expand=False)
    stats.add_column("k", style="dim")
    stats.add_column("v", style=f"bold {ACCENT}")
    stats.add_row("method",  label)
    stats.add_row("chars",   f"{char_count:,}")
    stats.add_row("lines",   f"{line_count:,}")
    stats.add_row("time",    f"{elapsed:.1f}s")
    stats.add_row("mode",    _EXTRACT_MODE)

    console.print(Panel(stats, title=f"[bold {OK_COL}]✓  Succeeded[/]",
                        border_style=OK_COL, title_align="left", padding=(1, 2)))
    console.print()

    # Preview (first 35 lines)
    preview = "\n".join(content.splitlines()[:35])
    if content.count('\n') > 35:
        preview += f"\n\n... ({content.count(chr(10)) - 35} more lines)"

    if _EXTRACT_MODE == "full":
        console.print(Panel(
            Syntax(preview, "markdown", theme="monokai", word_wrap=True),
            title="[bold]Preview[/] [dim](full/markdown)[/]",
            border_style=DIM_COL, padding=(1, 2)
        ))
    else:
        console.print(Panel(
            Text(preview, style="white"),
            title="[bold]Preview[/] [dim](precision)[/]",
            border_style=DIM_COL, padding=(1, 2)
        ))
    console.print()

    if output_choice == "Save to file":
        path = _save_path(url, label)
        header = (
            f"URL     : {url}\n"
            f"Method  : {label}\n"
            f"Mode    : {_EXTRACT_MODE}\n"
            f"Scraped : {datetime.now().isoformat()}\n"
            f"Chars   : {char_count:,}\n"
            f"{'─' * 60}\n\n"
        )
        path.write_text(header + content, encoding="utf-8")
        console.print(f"  [{OK_COL}]✓[/]  Saved → [bold]{path}[/]  ({char_count:,} chars)")

    elif output_choice == "Print full content":
        console.print(Rule(style=DIM_COL))
        console.print(content)
        console.print(Rule(style=DIM_COL))

    elif output_choice == "Copy to clipboard":
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.run(["pbcopy"], input=content.encode(), check=True)
            elif sys.platform == "win32":
                subprocess.run(["clip"], input=content.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"],
                               input=content.encode(), check=True)
            console.print(f"  [{OK_COL}]✓[/]  Copied {char_count:,} chars to clipboard")
        except Exception as e:
            fallback = Path("clipboard_output.txt")
            fallback.write_text(content, encoding="utf-8")
            console.print(f"  [{WARN_COL}]⚠[/]  Clipboard failed ({e}) — saved to {fallback}")

    console.print()

def show_failure():
    console.print()
    console.print(Panel(
        Text(
            "All tiers failed.\n\n"
            "Common causes:\n"
            "  • Site requires login / authentication\n"
            "  • Interactive CAPTCHA (not solvable without human)\n"
            "  • Site blocks all known scrapers\n\n"
            "Things to try:\n"
            "  • Switch to 'full' mode and retry\n"
            "  • Force a higher tier (Tier 2 or 3)\n"
            "  • For paywalled news — try archive.ph manually",
            style="white"
        ),
        title=f"[bold {ERR_COL}]✗  Failed[/]",
        border_style=ERR_COL, padding=(1, 2)
    ))
    console.print()

# ═══════════════════════════════════════════════════════════════════════════════
# INTERACTIVE PROMPTS
# ═══════════════════════════════════════════════════════════════════════════════

def ask_url() -> str:
    console.print(f"  [{DIM_COL}]Enter the URL to scrape[/]")
    console.print()
    while True:
        url = questionary.text("  URL:", style=Q_STYLE).ask()
        if url is None:
            sys.exit(0)
        url = url.strip()
        if not url:
            console.print(f"  [{WARN_COL}]Please enter a URL.[/]")
            continue
        if not url.startswith(("http://", "https://")):
            # Auto-prepend https:// as a convenience
            suggested = f"https://{url}"
            fix = questionary.confirm(
                f"  Add https://? ({suggested})",
                default=True, style=Q_STYLE
            ).ask()
            if fix:
                return suggested
            continue
        return url


def ask_mode() -> str:
    console.print()
    choice = questionary.select(
        "  Extraction mode:",
        choices=[
            questionary.Choice(
                "precision  —  trafilatura, main content only  (articles, blogs, docs)",
                value="precision",
            ),
            questionary.Choice(
                "full       —  markdownify, entire DOM as Markdown  (product pages, tables, e-commerce)",
                value="full",
            ),
        ],
        style=Q_STYLE,
        use_indicator=True,
    ).ask()
    if choice is None:
        sys.exit(0)
    return choice


def ask_tier(site_type: str) -> tuple[int | None, str]:
    console.print()

    # Show smart hint for known site types
    if site_type == "twitter":
        console.print(f"  [{ACCENT}]ℹ[/]  Twitter/X → twikit API handler runs regardless of tier")
    elif site_type == "medium":
        console.print(f"  [{ACCENT}]ℹ[/]  Medium → freedium.cfd bypass runs first")
    elif site_type == "js-spa":
        console.print(f"  [{ACCENT}]ℹ[/]  Known JS-only SPA → Tier 1 will be skipped automatically")
    console.print()

    choices = [
        questionary.Choice("Auto  —  smart escalation, recommended for most sites", value="auto"),
        questionary.Choice("Tier 1  —  curl_cffi, TLS impersonation, no browser  (~200ms)", value="1"),
        questionary.Choice("Tier 2  —  Camoufox, patched Firefox, C++ fingerprint spoofing", value="2"),
        questionary.Choice("Tier 3  —  Nodriver, undetected Chrome CDP", value="3"),
    ]

    val = questionary.select("  Fetch tier:", choices=choices,
                             style=Q_STYLE, use_indicator=True).ask()
    if val is None:
        sys.exit(0)

    tier_map = {"auto": None, "1": 1, "2": 2, "3": 3}
    label_map = {"auto": "Auto", "1": "Tier 1 (curl_cffi)",
                 "2": "Tier 2 (Camoufox)", "3": "Tier 3 (Nodriver)"}
    return tier_map[val], label_map[val]


def ask_output() -> str:
    console.print()
    choice = questionary.select(
        "  What to do with the result:",
        choices=[
            "Preview only  (no save)",
            "Save to file",
            "Print full content",
            "Copy to clipboard",
        ],
        style=Q_STYLE,
        use_indicator=True,
    ).ask()
    if choice is None:
        sys.exit(0)
    # Normalise to short key
    if "Preview" in choice:   return "Preview only"
    if "Save"    in choice:   return "Save to file"
    if "Print"   in choice:   return "Print full content"
    if "Copy"    in choice:   return "Copy to clipboard"
    return choice


def ask_confirm() -> bool:
    console.print()
    return bool(questionary.confirm("  Start scraping?", default=True, style=Q_STYLE).ask())


def ask_again() -> bool:
    console.print()
    result = questionary.confirm("  Scrape another URL?", default=True, style=Q_STYLE).ask()
    return bool(result)

# ═══════════════════════════════════════════════════════════════════════════════
# SCRAPE WITH SPINNER
# ═══════════════════════════════════════════════════════════════════════════════

def run_scrape_interactive(url: str, force_tier: int | None) -> tuple[str, str] | None:
    result_holder: list = []
    error_holder:  list = []

    async def _run():
        try:
            r = await scrape(url, force_tier=force_tier)
            result_holder.append(r)
        except Exception as e:
            error_holder.append(e)

    tier_msgs = {
        None: "Running auto mode…",
        1:    "Running Tier 1 (curl_cffi)…",
        2:    "Running Tier 2 (Camoufox)…",
        3:    "Running Tier 3 (Nodriver)…",
    }

    devnull = io.StringIO()
    with Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {ACCENT}"),
        TextColumn("[bold white]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(tier_msgs.get(force_tier, "Scraping…"), total=None)
        with redirect_stderr(devnull):
            asyncio.run(_run())

    if error_holder:
        console.print(f"  [{ERR_COL}]Error: {error_holder[0]}[/]")
        return None

    return result_holder[0] if result_holder else None

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN INTERACTIVE LOOP
# ═══════════════════════════════════════════════════════════════════════════════

def interactive_mode():
    global _EXTRACT_MODE
    show_banner()

    while True:
        url         = ask_url()
        mode        = ask_mode()
        _EXTRACT_MODE = mode

        site_type            = detect_site_type(url)
        force_tier, tier_lbl = ask_tier(site_type)
        output_choice        = ask_output()

        show_summary(url, mode, tier_lbl, output_choice)

        if not ask_confirm():
            console.print(f"\n  [{DIM_COL}]Cancelled.[/]\n")
        else:
            console.print()
            start   = time.monotonic()
            result  = run_scrape_interactive(url, force_tier)
            elapsed = time.monotonic() - start

            if result is None:
                show_failure()
            else:
                label, content = result
                show_result(label, content, url, elapsed, output_choice)

        if not ask_again():
            console.print(f"\n  [{DIM_COL}]Done.[/]\n")
            break

        console.print()
        console.print(Rule(style=DIM_COL))
        console.print()


# ═══════════════════════════════════════════════════════════════════════════════
# NON-INTERACTIVE FALLBACK  (python scraper.py <url>)
# ═══════════════════════════════════════════════════════════════════════════════

def cli_mode(url: str):
    global _EXTRACT_MODE
    if not url.startswith(("http://", "https://")):
        print(f"Error: URL must start with http:// or https://")
        sys.exit(1)
    print(f"\nScraping: {url}")
    result = None
    async def _run():
        nonlocal result
        result = await scrape(url)
    asyncio.run(_run())
    if result is None:
        print("Failed — all tiers exhausted.")
        sys.exit(1)
    label, content = result
    print(f"Method : {label}")
    print(f"Chars  : {len(content):,}")
    print("─" * 60)
    print(content)


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    try:
        if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
            cli_mode(sys.argv[1])
        else:
            interactive_mode()
    except KeyboardInterrupt:
        console.print(f"\n\n  [{DIM_COL}]Interrupted.[/]\n")
        sys.exit(0)

if __name__ == "__main__":
    main()