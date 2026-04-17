#!/usr/bin/env python3
"""
scraper.py - tiered web scraper with interactive TUI.

This module keeps backward-compatible interfaces used by:
- FastAPI backend (`main.py`)
- Streamlit UIs (`web_ui.py`, `web_ui_temp.py`)
- Terminal command (`XpditeS`, mapped to `scrape.scraper:main`)

Core scraping behavior is updated to the concurrent tiered strategy.
"""

import asyncio
from contextlib import redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
import io
import ipaddress
import os
from pathlib import Path
import random
import re
import socket
import sys
import time
from typing import Any
from urllib.parse import urljoin, urlparse

try:
    import questionary
    from questionary import Style
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.rule import Rule
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.text import Text
except ImportError:
    questionary = None
    Style = None
    box = None
    Align = None
    Console = None
    Panel = None
    Progress = None
    SpinnerColumn = None
    TextColumn = None
    TimeElapsedColumn = None
    Rule = None
    Syntax = None
    Table = None
    Text = None


_MAX_RETURN_CHARS = 95_000
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_EXTERNAL_RELAY_ENV = "WEBSEARCH_ENABLE_EXTERNAL_RELAYS"
_UNSAFE_TIER3_ENV = "WEBSEARCH_ENABLE_UNSAFE_TIER3_BROWSER"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECT_HOPS = 8

# Thresholds tuned from benchmark in updated scraper
_SUCCESS_CHAR_THRESHOLD = 5000
_SPARSE_CHAR_THRESHOLD = 500
_TIER1_TIMEOUT = 7.0
_TIER2_TIMEOUT = 10.0
_TIER3_TIMEOUT = 12.0
_GLOBAL_TIMEOUT = 12.0
_STAGGER_DELAY = 1.5
_URL_VALIDATION_TIMEOUT = 3.0

# Extraction mode kept for backward compatibility with existing callers.
_EXTRACT_MODE: str = "precision"

# Connection pooling
_curl_session_instance: Any = None
_httpx_client_instance: Any = None
_httpx_noredirect_client_instance: Any = None

_curl_session_lock = asyncio.Lock()
_httpx_client_lock = asyncio.Lock()
_httpx_noredirect_client_lock = asyncio.Lock()

# Browser pooling
_camoufox_pool: asyncio.Queue[Any] | None = None
_camoufox_pool_lock = asyncio.Lock()
_CAMOUFOX_POOL_SIZE = 2

# URL validation cache
_url_validation_cache: dict[tuple[str, str, int], str | None] = {}
_url_validation_cache_lock = asyncio.Lock()
_URL_VALIDATION_CACHE_MAX = 1024


@dataclass
class TierAttempt:
    """Result from a single tier attempt."""

    tier: str
    success: bool
    content: str | None = None
    content_length: int = 0
    elapsed_seconds: float = 0.0
    error: str | None = None


@dataclass
class ScrapeResult:
    """Result from scraping a URL across one or more tiers."""

    url: str
    mode: str
    success: bool
    content: str | None = None
    content_length: int = 0
    winning_tier: str | None = None
    total_elapsed_seconds: float = 0.0
    tier_attempts: list[TierAttempt] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    access_restriction_detected: bool = False
    sparse_content: bool = False


ACCESS_RESTRICTION_SIGNALS = [
    "please log in",
    "please sign in",
    "sign in to continue",
    "sign in to view",
    "log in to continue",
    "log in to view",
    "create an account",
    "you don't have permission",
    "you do not have permission",
    "access denied",
    "access restricted",
    "subscription required",
    "subscribe to read",
    "subscribe to continue",
    "members only",
    "premium content",
    "unlock this article",
    "verify you are human",
    "complete the captcha",
    "prove you're not a robot",
    "enable cookies",
    "cookies are required",
    "403 forbidden",
    "401 unauthorized",
    "payment required",
    "upgrade to access",
    "join to unlock",
    "register to view",
    "login required",
    "authentication required",
]

PAYWALL_SIGNALS = [
    "subscribe now",
    "start your free trial",
    "limited articles remaining",
    "you've reached your limit",
    "become a member",
    "premium subscriber",
    "exclusive content",
    "paywall",
    "meter limit",
]


TWITTER_DOMAINS = {"twitter.com", "x.com", "www.twitter.com", "www.x.com"}

MEDIUM_DOMAINS = {
    "medium.com",
    "towardsdatascience.com",
    "betterprogramming.pub",
    "levelup.gitconnected.com",
    "javascript.plainenglish.io",
    "uxdesign.cc",
    "hackernoon.com",
    "codeburst.io",
    "itnext.io",
    "proandroiddev.com",
    "infosecwriteups.com",
}

JS_REQUIRED_DOMAINS = {
    "x.com",
    "twitter.com",
    "www.x.com",
    "www.twitter.com",
    "instagram.com",
    "www.instagram.com",
    "facebook.com",
    "www.facebook.com",
    "linkedin.com",
    "www.linkedin.com",
    "tiktok.com",
    "www.tiktok.com",
    "reddit.com",
    "www.reddit.com",
    "notion.so",
    "www.notion.so",
    "figma.com",
    "www.figma.com",
}

JS_WALL_SIGNALS = [
    "javascript is disabled",
    "javascript must be enabled",
    "enable javascript",
    "please enable javascript",
    "enhanced tracking protection",
]

_SKELETON_RATIO = 0.04
_SKELETON_MIN_HTML = 10_000

SPA_SIGNATURES = [
    '<div id="root">',
    '<div id="app">',
    '<div id="__next">',
    '<div id="gatsby-focus-wrapper">',
    "window.__next_data__",
    "ng-version=",
    "data-reactroot",
]


@lru_cache(maxsize=4)
def _normalize_mode(mode: str | None) -> str | None:
    normalized_mode = (mode or "").strip().lower()
    if normalized_mode in {"precision", "full"}:
        return normalized_mode
    return None


def _coerce_force_tier(force_tier: int | str | None) -> tuple[int | None, str | None]:
    if force_tier is None:
        return None, None

    if isinstance(force_tier, bool):
        return (
            None,
            f"ERROR: Invalid force_tier '{force_tier}'. Valid values are 1, 2, or 3.",
        )

    parsed_force_tier: int | str = force_tier
    if isinstance(force_tier, str):
        stripped = force_tier.strip()
        if stripped in {"1", "2", "3"}:
            parsed_force_tier = int(stripped)
        else:
            return (
                None,
                f"ERROR: Invalid force_tier '{force_tier}'. Valid values are 1, 2, or 3.",
            )

    if parsed_force_tier not in (1, 2, 3):
        return (
            None,
            f"ERROR: Invalid force_tier '{force_tier}'. Valid values are 1, 2, or 3.",
        )

    return int(parsed_force_tier), None


@lru_cache(maxsize=128)
def _host(url: str) -> str:
    return urlparse(url).hostname or ""


def _is_public_ip_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return address.is_global


def _validate_read_website_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return f"ERROR: Invalid URL: {url}. URL must start with http:// or https://"

    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if not host:
        return f"ERROR: Invalid URL: {url}. URL host is missing."
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        return f"ERROR: URL host '{host}' is not allowed."

    try:
        resolved_ips = [ipaddress.ip_address(host)]
    except ValueError:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            addr_info = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            return f"ERROR: Could not resolve host '{host}': {exc}."

        resolved_ips = []
        seen_ips: set[str] = set()
        for _family, _socktype, _proto, _canonname, sockaddr in addr_info:
            ip_text = sockaddr[0]
            if ip_text in seen_ips:
                continue
            seen_ips.add(ip_text)
            try:
                resolved_ips.append(ipaddress.ip_address(ip_text))
            except ValueError:
                continue

        if not resolved_ips:
            return f"ERROR: Could not resolve host '{host}' to an IP address."

    for resolved_ip in resolved_ips:
        if not _is_public_ip_address(resolved_ip):
            return (
                f"ERROR: URL host '{host}' resolves to non-public IP '{resolved_ip}' "
                "and is not allowed."
            )

    return None


def _external_relays_enabled() -> bool:
    return os.environ.get(_EXTERNAL_RELAY_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def _unsafe_tier3_enabled() -> bool:
    return os.environ.get(_UNSAFE_TIER3_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


async def _validate_read_website_url_async(url: str) -> str | None:
    """Async URL validation with timeout and caching."""
    parsed = urlparse(url)
    scheme = parsed.scheme or ""
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    port = parsed.port or (443 if scheme == "https" else 80)
    cache_key = (host, scheme, port)

    async with _url_validation_cache_lock:
        if cache_key in _url_validation_cache:
            return _url_validation_cache[cache_key]

    try:
        validation_result = await asyncio.wait_for(
            asyncio.to_thread(_validate_read_website_url, url),
            timeout=_URL_VALIDATION_TIMEOUT,
        )
    except asyncio.TimeoutError:
        return (
            f"ERROR: URL validation timed out after {_URL_VALIDATION_TIMEOUT:.1f}s for "
            f"{url}. This is usually a DNS/network issue."
        )

    async with _url_validation_cache_lock:
        should_cache = validation_result is None or (
            isinstance(validation_result, str) and "not allowed" in validation_result
        )
        if should_cache:
            if len(_url_validation_cache) >= _URL_VALIDATION_CACHE_MAX:
                _url_validation_cache.pop(next(iter(_url_validation_cache)))
            _url_validation_cache[cache_key] = validation_result

    return validation_result


async def _get_curl_session():
    """Get or create reusable curl_cffi AsyncSession."""
    global _curl_session_instance
    if _curl_session_instance is None:
        async with _curl_session_lock:
            if _curl_session_instance is None:
                try:
                    from curl_cffi.requests import AsyncSession

                    _curl_session_instance = AsyncSession(timeout=20)
                except ImportError:
                    return None
    return _curl_session_instance


async def _get_httpx_client():
    """Get or create reusable httpx AsyncClient with redirects."""
    global _httpx_client_instance
    if _httpx_client_instance is None:
        async with _httpx_client_lock:
            if _httpx_client_instance is None:
                try:
                    import httpx

                    _httpx_client_instance = httpx.AsyncClient(
                        timeout=20, follow_redirects=True
                    )
                except ImportError:
                    return None
    return _httpx_client_instance


async def _get_httpx_noredirect_client():
    """Get or create reusable httpx AsyncClient without redirects."""
    global _httpx_noredirect_client_instance
    if _httpx_noredirect_client_instance is None:
        async with _httpx_noredirect_client_lock:
            if _httpx_noredirect_client_instance is None:
                try:
                    import httpx

                    _httpx_noredirect_client_instance = httpx.AsyncClient(
                        timeout=10, follow_redirects=False
                    )
                except ImportError:
                    return None
    return _httpx_noredirect_client_instance


async def _create_camoufox_browser():
    """Create a new Camoufox browser instance."""
    try:
        from browserforge.fingerprints import Screen
        from camoufox.async_api import AsyncCamoufox

        browser = await AsyncCamoufox(
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
        ).__aenter__()
        return browser
    except ImportError:
        return None
    except Exception:
        return None


async def _get_camoufox_browser():
    """Get a browser from pool or create a new one."""
    global _camoufox_pool

    async with _camoufox_pool_lock:
        if _camoufox_pool is None:
            _camoufox_pool = asyncio.Queue(maxsize=_CAMOUFOX_POOL_SIZE)

    try:
        return _camoufox_pool.get_nowait()
    except asyncio.QueueEmpty:
        return await _create_camoufox_browser()


async def _return_camoufox_browser(browser):
    """Return browser to pool, or close if pool is full."""
    global _camoufox_pool

    if browser is None:
        return

    try:
        if _camoufox_pool is not None:
            _camoufox_pool.put_nowait(browser)
        else:
            await browser.__aexit__(None, None, None)
    except asyncio.QueueFull:
        try:
            await browser.__aexit__(None, None, None)
        except Exception:
            pass
    except Exception:
        pass


async def cleanup_http_clients():
    """Clean up pooled clients and browser resources."""
    global _curl_session_instance
    global _httpx_client_instance
    global _httpx_noredirect_client_instance
    global _camoufox_pool

    if _curl_session_instance is not None:
        try:
            await _curl_session_instance.close()
        except Exception:
            pass
        _curl_session_instance = None

    if _httpx_client_instance is not None:
        try:
            await _httpx_client_instance.aclose()
        except Exception:
            pass
        _httpx_client_instance = None

    if _httpx_noredirect_client_instance is not None:
        try:
            await _httpx_noredirect_client_instance.aclose()
        except Exception:
            pass
        _httpx_noredirect_client_instance = None

    if _camoufox_pool is not None:
        while not _camoufox_pool.empty():
            try:
                browser = _camoufox_pool.get_nowait()
                await browser.__aexit__(None, None, None)
            except Exception:
                pass
        _camoufox_pool = None


def _detect_access_restriction(text: str) -> tuple[bool, list[str]]:
    """Detect access restrictions (login, paywall, captcha) in extracted content."""
    if not text:
        return False, []

    text_lower = text[:3000].lower()
    detected_signals: list[str] = []

    for signal in ACCESS_RESTRICTION_SIGNALS:
        if signal in text_lower:
            detected_signals.append(signal)

    for signal in PAYWALL_SIGNALS:
        if signal in text_lower:
            detected_signals.append(f"paywall: {signal}")

    return len(detected_signals) > 0, detected_signals[:3]


def is_twitter(url: str) -> bool:
    return _host(url) in TWITTER_DOMAINS


def is_medium(url: str) -> bool:
    host = _host(url)
    return host in MEDIUM_DOMAINS or host.endswith(".medium.com")


def needs_js(url: str) -> bool:
    return _host(url) in JS_REQUIRED_DOMAINS


def has_js_wall(html: str) -> bool:
    return any(signal in html[:3000].lower() for signal in JS_WALL_SIGNALS)


def is_js_skeleton(html: str, text: str) -> bool:
    if len(html) < _SKELETON_MIN_HTML:
        return False
    if len(text) / max(len(html), 1) < _SKELETON_RATIO:
        return True
    html_lower = html[:5000].lower()
    if (
        any(signature.lower() in html_lower for signature in SPA_SIGNATURES)
        and len(text) < 500
    ):
        return True
    return False


def detect_site_type(url: str) -> str:
    if is_twitter(url):
        return "twitter"
    if is_medium(url):
        return "medium"
    if needs_js(url):
        return "js-spa"
    return "general"


async def _resolve_safe_redirect_chain(
    url: str,
    max_hops: int = _MAX_REDIRECT_HOPS,
    *,
    fail_open: bool = False,
) -> str | None:
    client = await _get_httpx_noredirect_client()
    if client is None:
        return None

    current_url = url
    seen_urls: set[str] = set()

    try:
        for _ in range(max_hops):
            if current_url in seen_urls:
                return None
            seen_urls.add(current_url)

            if await _validate_read_website_url_async(current_url):
                return None

            response = await client.get(
                current_url,
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )

            if response.status_code not in _REDIRECT_STATUSES:
                return str(response.request.url)

            location = response.headers.get("location")
            if not location:
                return str(response.request.url)

            next_url = urljoin(str(response.request.url), location)
            if await _validate_read_website_url_async(next_url):
                return None
            current_url = next_url
    except Exception:
        return url if fail_open else None

    return None


def extract(html: str, mode: str | None = None, url: str = "") -> str:
    selected_mode = _normalize_mode(mode or _EXTRACT_MODE) or "precision"

    if selected_mode == "full":
        try:
            import markdownify
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "svg", "noscript", "meta", "head"]):
                tag.decompose()
            markdown_text = markdownify.markdownify(
                str(soup),
                heading_style="ATX",
                bullets="-",
                strip=["a"],
            )
            markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()
            if markdown_text and len(markdown_text) > 100:
                return markdown_text
        except Exception:
            pass

    try:
        import trafilatura

        result = trafilatura.extract(
            html,
            url=url or None,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
            deduplicate=True,
        )
        if result and len(result.strip()) > 100:
            return result.strip()
    except Exception:
        pass

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "header",
                "footer",
                "aside",
                "form",
                "svg",
                "noscript",
            ]
        ):
            tag.decompose()
        text = soup.get_text(separator="\n")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)

    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def tier1_curl(url: str, mode: str) -> tuple[str, str] | None:
    session = await _get_curl_session()
    if session is None:
        return None

    targets = ["chrome124", "chrome120", "chrome110", "edge101", "edge99"]
    try:
        current_url = url
        response = None
        seen_urls: set[str] = set()

        for _ in range(_MAX_REDIRECT_HOPS):
            if current_url in seen_urls:
                return None
            seen_urls.add(current_url)

            if await _validate_read_website_url_async(current_url):
                return None

            response = await session.get(
                current_url,
                impersonate=random.choice(targets),
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://www.google.com/",
                },
                timeout=_TIER1_TIMEOUT,
                allow_redirects=False,
            )

            if response.status_code not in _REDIRECT_STATUSES:
                break

            location = response.headers.get("location")
            if not location:
                break

            next_url = urljoin(str(getattr(response, "url", current_url)), location)
            if await _validate_read_website_url_async(next_url):
                return None
            current_url = next_url
        else:
            return None

        if response is None:
            return None

        if response.status_code == 200 and len(response.text) > 500:
            final_url = str(getattr(response, "url", url))
            if await _validate_read_website_url_async(final_url):
                return None
            if has_js_wall(response.text):
                return None
            text = extract(response.text, mode, final_url)
            return text, response.text
        return None
    except Exception:
        return None


async def tier1_5_jina(url: str) -> str | None:
    client = await _get_httpx_client()
    if client is None:
        return None

    jina_url = f"https://r.jina.ai/{url}"
    headers = {"Accept": "text/plain", "X-Return-Format": "text"}
    api_key = os.environ.get("JINA_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = await client.get(jina_url, headers=headers)
        response.raise_for_status()
        content = response.text.strip()
        return content if content and len(content) > 200 else None
    except Exception:
        return None


async def tier2_camoufox(url: str, mode: str) -> str | None:
    browser = None
    try:
        from browserforge.fingerprints import Screen
        from camoufox.async_api import AsyncCamoufox
    except ImportError:
        return None

    try:
        safe_url = await _resolve_safe_redirect_chain(url, fail_open=True)
        if not safe_url:
            return None

        browser = await _get_camoufox_browser()
        if browser is None:
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
            ) as fallback_browser:
                page = await fallback_browser.new_page()

                async def _enforce_safe_requests(route):
                    request = route.request
                    request_url = getattr(request, "url", "")
                    parsed = urlparse(request_url)
                    if parsed.scheme not in {"http", "https"}:
                        await route.continue_()
                        return

                    if await _validate_read_website_url_async(request_url):
                        await route.abort()
                        return
                    await route.continue_()

                await page.route("**/*", _enforce_safe_requests)
                await page.goto(
                    safe_url, wait_until="load", timeout=int(_TIER2_TIMEOUT * 1000)
                )
                html = await page.content()
                final_url = getattr(page, "url", safe_url)
                await page.close()

            if isinstance(final_url, str) and await _validate_read_website_url_async(
                final_url
            ):
                return None
            if has_js_wall(html):
                return None
            result = extract(
                html, mode, final_url if isinstance(final_url, str) else url
            )
            return result if len(result) > 100 else None

        page = await browser.new_page()

        async def _enforce_safe_requests(route):
            request = route.request
            request_url = getattr(request, "url", "")
            parsed = urlparse(request_url)
            if parsed.scheme not in {"http", "https"}:
                await route.continue_()
                return

            if await _validate_read_website_url_async(request_url):
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", _enforce_safe_requests)
        await page.goto(safe_url, wait_until="load", timeout=int(_TIER2_TIMEOUT * 1000))
        html = await page.content()
        final_url = getattr(page, "url", safe_url)
        await page.close()

        await _return_camoufox_browser(browser)
        browser = None

        if isinstance(final_url, str) and await _validate_read_website_url_async(
            final_url
        ):
            return None
        if has_js_wall(html):
            return None
        result = extract(html, mode, final_url if isinstance(final_url, str) else url)
        return result if len(result) > 100 else None
    except Exception:
        return None
    finally:
        if browser is not None:
            await _return_camoufox_browser(browser)


async def tier3_nodriver(url: str, mode: str) -> str | None:
    try:
        import nodriver as uc
    except ImportError:
        return None

    browser = None
    try:
        safe_url = await _resolve_safe_redirect_chain(url)
        if not safe_url:
            return None

        browser = await uc.start(headless=True)
        page = await asyncio.wait_for(browser.get(safe_url), timeout=_TIER3_TIMEOUT)
        html = await asyncio.wait_for(page.get_content(), timeout=10.0)
        final_url = getattr(page, "url", safe_url)
        if isinstance(final_url, str) and await _validate_read_website_url_async(
            final_url
        ):
            return None
        if not html or has_js_wall(html):
            return None
        return extract(html, mode, final_url if isinstance(final_url, str) else url)
    except Exception:
        return None
    finally:
        if browser:
            try:
                browser.stop()
            except Exception:
                pass


async def handle_twitter(url: str) -> str | None:
    try:
        from twikit.guest import GuestClient
    except ImportError:
        return None

    match = re.search(r"/status/(\d+)", url)
    if not match:
        return None
    tweet_id = match.group(1)

    try:
        client = GuestClient()
        await client.activate()
        tweet = await client.get_tweet_by_id(tweet_id)
        if not tweet:
            return None

        lines: list[str] = []
        if hasattr(tweet, "user") and tweet.user:
            lines.append(f"@{tweet.user.screen_name} - {tweet.user.name}")
        if hasattr(tweet, "created_at") and tweet.created_at:
            lines.append(f"Posted: {tweet.created_at}")
        lines.append("")
        lines.append(
            getattr(tweet, "full_text", None) or getattr(tweet, "text", "") or ""
        )
        lines.append("")

        stats: list[str] = []
        for attr, label in [
            ("favorite_count", "Likes"),
            ("retweet_count", "Retweets"),
            ("reply_count", "Replies"),
        ]:
            if hasattr(tweet, attr):
                stats.append(f"{label}: {getattr(tweet, attr)}")
        if stats:
            lines.append("  ".join(stats))

        if getattr(tweet, "media", None):
            lines.append(f"\nMedia ({len(tweet.media)} item(s)):")
            for media in tweet.media:
                source = getattr(media, "media_url_https", None) or getattr(
                    media, "url", None
                )
                if source:
                    lines.append(f"  {source}")

        return "\n".join(lines)
    except Exception:
        return None


async def handle_medium(url: str, mode: str) -> str | None:
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return None

    mirrors = [f"https://freedium.cfd/{url}", f"https://freedium-mirror.cfd/{url}"]
    for mirror in mirrors:
        try:
            async with AsyncSession() as session:
                response = await session.get(
                    mirror,
                    impersonate="chrome124",
                    headers={"Accept-Language": "en-US,en;q=0.9"},
                    timeout=20,
                    allow_redirects=True,
                )
            if response.status_code == 200 and len(response.text) > 500:
                text = extract(response.text, mode, url)
                if len(text) > 300:
                    return text
        except Exception:
            continue
    return None


async def handle_archive(url: str, mode: str) -> str | None:
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        return None

    try:
        async with AsyncSession() as session:
            response = await session.get(
                f"https://archive.ph/newest/{url}",
                impersonate="chrome124",
                headers={"Accept-Language": "en-US,en;q=0.9"},
                timeout=20,
                allow_redirects=True,
            )
        if response.status_code == 200 and len(response.text) > 500:
            text = extract(response.text, mode, url)
            if len(text) > 300:
                return text
    except Exception:
        pass
    return None


async def _run_tier_with_timeout(
    tier_fn,
    url: str,
    mode: str,
    tier_name: str,
    timeout: float,
) -> TierAttempt:
    """Run one tier with timeout and return structured metadata."""
    start = time.perf_counter()

    try:
        async with asyncio.timeout(timeout):
            result = await tier_fn(url, mode)

        elapsed = time.perf_counter() - start

        if result is None:
            return TierAttempt(
                tier=tier_name,
                success=False,
                content_length=0,
                elapsed_seconds=elapsed,
                error="No content returned",
            )

        content = result[0] if isinstance(result, tuple) else result
        content_length = len(content) if content else 0

        return TierAttempt(
            tier=tier_name,
            success=content_length > 0,
            content=content,
            content_length=content_length,
            elapsed_seconds=elapsed,
        )
    except asyncio.TimeoutError:
        elapsed = time.perf_counter() - start
        return TierAttempt(
            tier=tier_name,
            success=False,
            content_length=0,
            elapsed_seconds=elapsed,
            error=f"Timeout after {timeout:.1f}s",
        )
    except Exception as exc:
        elapsed = time.perf_counter() - start
        return TierAttempt(
            tier=tier_name,
            success=False,
            content_length=0,
            elapsed_seconds=elapsed,
            error=str(exc)[:200],
        )


async def scrape_concurrent(
    url: str,
    mode: str,
    force_tier: int | None = None,
    skip_twitter: bool = False,
    allow_external_relays: bool = False,
    allow_unsafe_tier3: bool = False,
) -> ScrapeResult:
    """Scrape URL with concurrent, staggered tier execution."""
    start_time = time.perf_counter()

    result = ScrapeResult(url=url, mode=mode, success=False)
    best_attempt: TierAttempt | None = None
    pending_tasks: dict[asyncio.Task[Any], str] = {}
    stagger_task: asyncio.Task[Any] | None = None

    try:
        async with asyncio.timeout(_GLOBAL_TIMEOUT):
            if force_tier is None:
                if is_twitter(url) and not skip_twitter:
                    try:
                        twitter_result = await asyncio.wait_for(
                            handle_twitter(url), timeout=_TIER1_TIMEOUT
                        )
                        if (
                            twitter_result
                            and len(twitter_result) > _SPARSE_CHAR_THRESHOLD
                        ):
                            result.success = True
                            result.content = twitter_result
                            result.content_length = len(twitter_result)
                            result.winning_tier = "twitter_twikit"
                            result.total_elapsed_seconds = (
                                time.perf_counter() - start_time
                            )
                            return result
                    except asyncio.TimeoutError:
                        result.tier_attempts.append(
                            TierAttempt(
                                tier="twitter_twikit",
                                success=False,
                                error=f"Timeout after {_TIER1_TIMEOUT:.1f}s",
                                elapsed_seconds=_TIER1_TIMEOUT,
                            )
                        )
                    except Exception as exc:
                        result.tier_attempts.append(
                            TierAttempt(
                                tier="twitter_twikit",
                                success=False,
                                error=str(exc)[:200],
                                elapsed_seconds=time.perf_counter() - start_time,
                            )
                        )

                if is_medium(url) and allow_external_relays:
                    try:
                        medium_result = await asyncio.wait_for(
                            handle_medium(url, mode), timeout=_TIER1_TIMEOUT
                        )
                        if (
                            medium_result
                            and len(medium_result) > _SPARSE_CHAR_THRESHOLD
                        ):
                            result.success = True
                            result.content = medium_result
                            result.content_length = len(medium_result)
                            result.winning_tier = "medium_freedium"
                            result.total_elapsed_seconds = (
                                time.perf_counter() - start_time
                            )
                            return result
                    except asyncio.TimeoutError:
                        pass
                    except Exception:
                        pass

                    try:
                        archive_result = await asyncio.wait_for(
                            handle_archive(url, mode), timeout=_TIER1_TIMEOUT
                        )
                        if (
                            archive_result
                            and len(archive_result) > _SPARSE_CHAR_THRESHOLD
                        ):
                            result.success = True
                            result.content = archive_result
                            result.content_length = len(archive_result)
                            result.winning_tier = "medium_archive"
                            result.total_elapsed_seconds = (
                                time.perf_counter() - start_time
                            )
                            return result
                    except asyncio.TimeoutError:
                        pass
                    except Exception:
                        pass

            tiers_to_run: list[tuple[str, Any, float]] = []

            if force_tier == 1 or (force_tier is None and not needs_js(url)):
                tiers_to_run.append(("tier1_curl", tier1_curl, _TIER1_TIMEOUT))

            if force_tier in (None, 2):
                tiers_to_run.append(("tier2_camoufox", tier2_camoufox, _TIER2_TIMEOUT))

            if force_tier in (None, 3) and allow_unsafe_tier3:
                tiers_to_run.append(("tier3_nodriver", tier3_nodriver, _TIER3_TIMEOUT))

            if not tiers_to_run:
                result.warnings.append("No tiers available to run")
                if force_tier == 3 and not allow_unsafe_tier3:
                    result.suggestions.append(
                        f"Set {_UNSAFE_TIER3_ENV}=1 to enable Tier 3 browser"
                    )
                else:
                    result.suggestions.append(
                        "Enable tier 3 with WEBSEARCH_ENABLE_UNSAFE_TIER3_BROWSER=1"
                    )
                result.total_elapsed_seconds = time.perf_counter() - start_time
                return result

            first_tier_name, first_tier_fn, first_tier_timeout = tiers_to_run[0]
            first_task = asyncio.create_task(
                _run_tier_with_timeout(
                    first_tier_fn, url, mode, first_tier_name, first_tier_timeout
                )
            )
            pending_tasks[first_task] = first_tier_name

            remaining_tiers = tiers_to_run[1:]
            browser_tiers_started = False

            if remaining_tiers:

                async def _start_remaining_tiers():
                    await asyncio.sleep(_STAGGER_DELAY)
                    return "stagger_complete"

                stagger_task = asyncio.create_task(_start_remaining_tiers())

            while pending_tasks or (stagger_task and not stagger_task.done()):
                wait_set = set(pending_tasks.keys())
                if stagger_task and not stagger_task.done():
                    wait_set.add(stagger_task)

                if not wait_set:
                    break

                done, _ = await asyncio.wait(
                    wait_set, return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    if task is stagger_task:
                        if not browser_tiers_started:
                            browser_tiers_started = True
                            for tier_name, tier_fn, tier_timeout in remaining_tiers:
                                new_task = asyncio.create_task(
                                    _run_tier_with_timeout(
                                        tier_fn, url, mode, tier_name, tier_timeout
                                    )
                                )
                                pending_tasks[new_task] = tier_name
                        continue

                    tier_name = pending_tasks.pop(task)
                    try:
                        attempt = task.result()
                    except Exception as exc:
                        attempt = TierAttempt(
                            tier=tier_name,
                            success=False,
                            error=str(exc)[:200],
                        )

                    result.tier_attempts.append(attempt)

                    if (
                        attempt.success
                        and attempt.content_length >= _SUCCESS_CHAR_THRESHOLD
                    ):
                        for remaining_task in pending_tasks:
                            remaining_task.cancel()
                        if stagger_task and not stagger_task.done():
                            stagger_task.cancel()
                        best_attempt = attempt
                        break

                    if attempt.success and (
                        best_attempt is None
                        or attempt.content_length > best_attempt.content_length
                    ):
                        best_attempt = attempt

                    if (
                        not browser_tiers_started
                        and tier_name == "tier1_curl"
                        and not attempt.success
                    ):
                        browser_tiers_started = True
                        if stagger_task and not stagger_task.done():
                            stagger_task.cancel()
                        for tier_name_r, tier_fn, tier_timeout in remaining_tiers:
                            new_task = asyncio.create_task(
                                _run_tier_with_timeout(
                                    tier_fn, url, mode, tier_name_r, tier_timeout
                                )
                            )
                            pending_tasks[new_task] = tier_name_r

                if (
                    best_attempt
                    and best_attempt.content_length >= _SUCCESS_CHAR_THRESHOLD
                ):
                    break

    except asyncio.TimeoutError:
        for task in list(pending_tasks.keys()):
            task.cancel()
        if stagger_task and not stagger_task.done():
            stagger_task.cancel()
        result.warnings.append(f"Global timeout ({_GLOBAL_TIMEOUT:.1f}s) reached")

    result.total_elapsed_seconds = time.perf_counter() - start_time

    if best_attempt and best_attempt.content:
        result.success = True
        result.content = best_attempt.content
        result.content_length = best_attempt.content_length
        result.winning_tier = best_attempt.tier

        if best_attempt.content_length < _SPARSE_CHAR_THRESHOLD:
            result.sparse_content = True
            result.warnings.append(
                "Sparse content extracted "
                f"({best_attempt.content_length} chars < {_SPARSE_CHAR_THRESHOLD})"
            )

        restricted, signals = _detect_access_restriction(best_attempt.content)
        if restricted:
            result.access_restriction_detected = True
            result.warnings.append(f"Access restriction detected: {', '.join(signals)}")
            result.suggestions.append(f"Try external relays ({_EXTERNAL_RELAY_ENV}=1)")
            result.suggestions.append("Try archive fallback for paywalled content")
    else:
        failed_tiers = [a.tier for a in result.tier_attempts]
        if failed_tiers:
            result.warnings.append(f"All tiers failed: {', '.join(failed_tiers)}")
        else:
            result.warnings.append("All tiers failed")

        if not allow_external_relays:
            result.suggestions.append(
                f"Enable external relays: {_EXTERNAL_RELAY_ENV}=1"
            )
        if not allow_unsafe_tier3:
            result.suggestions.append(f"Enable Tier 3 browser: {_UNSAFE_TIER3_ENV}=1")
        if force_tier is not None:
            result.suggestions.append("Try without force_tier to allow auto-escalation")

    return result


async def scrape(
    url: str,
    force_tier: int | str | None = None,
    mode: str | None = None,
    skip_twitter: bool = False,
    allow_external_relays: bool | None = None,
    allow_unsafe_tier3: bool | None = None,
) -> tuple[str, str] | None:
    """Backward-compatible scrape wrapper. Returns (method, content) or None."""
    normalized_mode = _normalize_mode(mode or _EXTRACT_MODE) or "precision"
    resolved_force_tier, force_tier_error = _coerce_force_tier(force_tier)
    if force_tier_error:
        return None

    result = await scrape_concurrent(
        url=url,
        mode=normalized_mode,
        force_tier=resolved_force_tier,
        skip_twitter=skip_twitter,
        allow_external_relays=(
            _external_relays_enabled()
            if allow_external_relays is None
            else allow_external_relays
        ),
        allow_unsafe_tier3=(
            _unsafe_tier3_enabled()
            if allow_unsafe_tier3 is None
            else allow_unsafe_tier3
        ),
    )

    if result.success and result.content and result.winning_tier:
        return result.winning_tier, result.content
    return None


def _truncate_for_display(text: str) -> tuple[str, bool]:
    if len(text) <= _MAX_RETURN_CHARS:
        return text, False
    return text[:_MAX_RETURN_CHARS], True


def format_scrape_result(result: ScrapeResult) -> str:
    """Human-readable detailed result formatter for CLI usage."""
    if not result.success or not result.content:
        lines = [f"ERROR: Failed to fetch {result.url}", ""]
        if result.tier_attempts:
            lines.append("Tier Results:")
            for attempt in result.tier_attempts:
                status = "OK" if attempt.success else "FAILED"
                error_info = f" ({attempt.error})" if attempt.error else ""
                chars = f", {attempt.content_length} chars" if attempt.success else ""
                lines.append(f"  - {attempt.tier}: {status}{error_info}{chars}")
            lines.append("")
        if result.warnings:
            lines.append("Warnings:")
            for warning in result.warnings:
                lines.append(f"  - {warning}")
            lines.append("")
        if result.suggestions:
            lines.append("Suggestions:")
            for suggestion in result.suggestions:
                lines.append(f"  - {suggestion}")
        return "\n".join(lines)

    output, truncated = _truncate_for_display(result.content)
    tier_info_parts = [f"{result.winning_tier} ({result.total_elapsed_seconds:.1f}s)"]
    other_tiers = [
        f"{a.tier} ({'ok' if a.success else 'fail'}: {a.content_length} chars)"
        for a in result.tier_attempts
        if a.tier != result.winning_tier
    ]
    if other_tiers:
        tier_info_parts.append(f"other: {', '.join(other_tiers)}")

    header_lines = [
        f"SOURCE: {result.url}",
        f"METHOD: {' | '.join(tier_info_parts)}",
        f"MODE: {result.mode}",
        f"CHARS: original={result.content_length:,}; returned={len(output):,}",
    ]

    status_parts: list[str] = []
    if result.sparse_content:
        status_parts.append("SPARSE_CONTENT")
    if result.access_restriction_detected:
        status_parts.append("ACCESS_RESTRICTED")
    if status_parts:
        header_lines.append(f"STATUS: {', '.join(status_parts)}")

    footer_parts: list[str] = []
    if result.warnings:
        footer_parts.append("\nWARNINGS:")
        for warning in result.warnings:
            footer_parts.append(f"  - {warning}")
    if result.suggestions:
        footer_parts.append("\nSUGGESTIONS:")
        for suggestion in result.suggestions:
            footer_parts.append(f"  - {suggestion}")
    footer = "\n".join(footer_parts)

    if truncated:
        output = f"{output}\n\n[TRUNCATED] Output capped at {_MAX_RETURN_CHARS:,} characters."

    header = "\n".join(header_lines)
    if footer:
        return f"{header}\n\n{output}\n{footer}"
    return f"{header}\n\n{output}"


def _cleanup_resources_sync() -> None:
    try:
        asyncio.run(cleanup_http_clients())
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Interactive TUI
# ---------------------------------------------------------------------------

ACCENT = "#00d7af"
DIM_COL = "#555555"
WARN_COL = "#ffaf00"
ERR_COL = "#ff5f5f"
OK_COL = "#00d7af"

console = Console() if Console is not None else None

Q_STYLE = (
    Style(
        [
            ("qmark", "fg:#00d7af bold"),
            ("question", "fg:#ffffff bold"),
            ("answer", "fg:#00d7af bold"),
            ("pointer", "fg:#00d7af bold"),
            ("highlighted", "fg:#00d7af bold"),
            ("selected", "fg:#00d7af"),
            ("separator", "fg:#444444"),
            ("instruction", "fg:#666666"),
            ("text", "fg:#cccccc"),
            ("disabled", "fg:#444444 italic"),
        ]
    )
    if Style is not None
    else None
)

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


def _check_ui_deps() -> None:
    if questionary is None or console is None or Q_STYLE is None:
        missing = []
        try:
            import questionary as _q  # noqa: F401
        except ImportError:
            missing.append("questionary")
        try:
            import rich as _r  # noqa: F401
        except ImportError:
            missing.append("rich")

        print()
        print("Missing UI dependencies:", ", ".join(missing) if missing else "unknown")
        if missing:
            print("Run: uv add", " ".join(missing))
        print()
        sys.exit(1)


def show_banner() -> None:
    assert console is not None
    assert Align is not None
    assert Text is not None
    console.print()
    console.print(Align.center(Text(BANNER, style=f"bold {ACCENT}")))
    console.print(
        Align.center(
            Text(
                "Universal Web Scraper  -  Interactive Mode",
                style=f"dim {ACCENT}",
            )
        )
    )
    console.print()


def _site_hint(site_type: str) -> str:
    return {
        "twitter": "twikit handler runs automatically",
        "medium": "external relay bypass can run when enabled",
        "js-spa": "known JS-heavy domain; browser tiers may be needed",
        "general": "tier 1 fast-path, then staggered browser escalation",
    }.get(site_type, "")


def _save_path(url: str, label: str) -> Path:
    host = re.sub(r"[^\w.-]", "_", _host(url) or "output")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = ".md" if (_normalize_mode(_EXTRACT_MODE) or "precision") == "full" else ".txt"
    return Path(f"{host}_{label}_{ts}{ext}")


def show_summary(url: str, mode: str, tier_label: str, output: str) -> None:
    assert console is not None
    assert Table is not None
    assert Panel is not None
    assert box is not None

    site_type = detect_site_type(url)
    hint = _site_hint(site_type)

    table = Table(
        box=box.ROUNDED,
        border_style=DIM_COL,
        show_header=False,
        padding=(0, 2),
        expand=False,
    )
    table.add_column("key", style="dim", width=12)
    table.add_column("value", style="white")
    table.add_row("URL", f"[bold]{url}[/]")
    table.add_row("Site", f"[{ACCENT}]{site_type}[/]  [dim]{hint}[/]")
    table.add_row("Mode", f"[{ACCENT}]{mode}[/]")
    table.add_row("Tier", f"[{ACCENT}]{tier_label}[/]")
    table.add_row("Output", f"[{ACCENT}]{output}[/]")

    console.print()
    console.print(
        Panel(
            table,
            title="[bold]Scrape Job[/]",
            border_style=ACCENT,
            title_align="left",
            padding=(1, 2),
        )
    )
    console.print()


def show_result(
    result: ScrapeResult, url: str, elapsed: float, output_choice: str
) -> None:
    assert console is not None
    assert Table is not None
    assert Panel is not None
    assert Syntax is not None
    assert Text is not None
    assert Rule is not None

    content = result.content or ""
    label = result.winning_tier or "unknown"
    char_count = len(content)
    line_count = content.count("\n") + (1 if content else 0)

    stats = Table(box=None, show_header=False, padding=(0, 3), expand=False)
    stats.add_column("k", style="dim")
    stats.add_column("v", style=f"bold {ACCENT}")
    stats.add_row("method", label)
    stats.add_row("chars", f"{char_count:,}")
    stats.add_row("lines", f"{line_count:,}")
    stats.add_row("time", f"{elapsed:.1f}s")
    stats.add_row("mode", result.mode)

    console.print(
        Panel(
            stats,
            title=f"[bold {OK_COL}]OK  Succeeded[/]",
            border_style=OK_COL,
            title_align="left",
            padding=(1, 2),
        )
    )
    console.print()

    preview = "\n".join(content.splitlines()[:35])
    if content.count("\n") > 35:
        preview += f"\n\n... ({content.count(chr(10)) - 35} more lines)"

    if result.mode == "full":
        console.print(
            Panel(
                Syntax(preview, "markdown", theme="monokai", word_wrap=True),
                title="[bold]Preview[/] [dim](full/markdown)[/]",
                border_style=DIM_COL,
                padding=(1, 2),
            )
        )
    else:
        console.print(
            Panel(
                Text(preview, style="white"),
                title="[bold]Preview[/] [dim](precision)[/]",
                border_style=DIM_COL,
                padding=(1, 2),
            )
        )
    console.print()

    if output_choice == "Save to file":
        path = _save_path(url, label)
        header = (
            f"URL     : {url}\n"
            f"Method  : {label}\n"
            f"Mode    : {result.mode}\n"
            f"Scraped : {datetime.now().isoformat()}\n"
            f"Chars   : {char_count:,}\n"
            f"{'-' * 60}\n\n"
        )
        path.write_text(header + content, encoding="utf-8")
        console.print(
            f"  [{OK_COL}]OK[/]  Saved -> [bold]{path}[/]  ({char_count:,} chars)"
        )

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
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=content.encode(),
                    check=True,
                )
            console.print(
                f"  [{OK_COL}]OK[/]  Copied {char_count:,} chars to clipboard"
            )
        except Exception as exc:
            fallback = Path("clipboard_output.txt")
            fallback.write_text(content, encoding="utf-8")
            console.print(
                f"  [{WARN_COL}]WARN[/]  Clipboard failed ({exc}) - saved to {fallback}"
            )

    if result.warnings:
        console.print()
        console.print(f"[{WARN_COL}]Warnings:[/]")
        for warning in result.warnings:
            console.print(f"  - {warning}")
    if result.suggestions:
        console.print()
        console.print(f"[{ACCENT}]Suggestions:[/]")
        for suggestion in result.suggestions:
            console.print(f"  - {suggestion}")

    console.print()


def show_failure(result: ScrapeResult | None = None) -> None:
    assert console is not None
    assert Panel is not None
    assert Text is not None

    if result is None:
        message = (
            "All tiers failed.\n\n"
            "Common causes:\n"
            "  - Site requires login/authentication\n"
            "  - Interactive CAPTCHA\n"
            "  - Site blocks known scrapers\n\n"
            "Things to try:\n"
            "  - Switch to full mode and retry\n"
            "  - Force a higher tier\n"
            "  - Enable external relays if needed"
        )
    else:
        lines = [
            "All tiers failed.",
            "",
            "Tier attempts:",
        ]
        if result.tier_attempts:
            for attempt in result.tier_attempts:
                status = "ok" if attempt.success else "failed"
                details = f" ({attempt.error})" if attempt.error else ""
                lines.append(f"  - {attempt.tier}: {status}{details}")
        else:
            lines.append("  - no tier attempts were run")

        if result.warnings:
            lines.append("")
            lines.append("Warnings:")
            for warning in result.warnings:
                lines.append(f"  - {warning}")

        if result.suggestions:
            lines.append("")
            lines.append("Suggestions:")
            for suggestion in result.suggestions:
                lines.append(f"  - {suggestion}")

        message = "\n".join(lines)

    console.print()
    console.print(
        Panel(
            Text(message, style="white"),
            title=f"[bold {ERR_COL}]FAIL  Failed[/]",
            border_style=ERR_COL,
            padding=(1, 2),
        )
    )
    console.print()


def ask_url() -> str:
    assert console is not None
    assert questionary is not None
    assert Q_STYLE is not None

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
            suggested = f"https://{url}"
            fix = questionary.confirm(
                f"  Add https://? ({suggested})", default=True, style=Q_STYLE
            ).ask()
            if fix:
                return suggested
            continue
        return url


def ask_mode() -> str:
    assert console is not None
    assert questionary is not None
    assert Q_STYLE is not None

    console.print()
    choice = questionary.select(
        "  Extraction mode:",
        choices=[
            questionary.Choice(
                "precision  -  trafilatura, main content only", value="precision"
            ),
            questionary.Choice(
                "full       -  markdownify, entire DOM as Markdown", value="full"
            ),
        ],
        style=Q_STYLE,
        use_indicator=True,
    ).ask()
    if choice is None:
        sys.exit(0)
    return choice


def ask_tier(site_type: str) -> tuple[int | None, str]:
    assert console is not None
    assert questionary is not None
    assert Q_STYLE is not None

    console.print()
    if site_type == "twitter":
        console.print(
            f"  [{ACCENT}]INFO[/] Twitter/X -> twikit handler runs automatically"
        )
    elif site_type == "medium":
        console.print(
            f"  [{ACCENT}]INFO[/] Medium -> external relay bypass works when enabled"
        )
    elif site_type == "js-spa":
        console.print(
            f"  [{ACCENT}]INFO[/] Known JS-heavy domain -> browser tiers likely needed"
        )

    if not _unsafe_tier3_enabled():
        console.print(
            f"  [{WARN_COL}]INFO[/] Tier 3 is disabled by default. "
            f"Set {_UNSAFE_TIER3_ENV}=1 to enable it."
        )
    console.print()

    choices = [
        questionary.Choice(
            "Auto  -  concurrent smart escalation (recommended)", value="auto"
        ),
        questionary.Choice("Tier 1  -  curl_cffi (fast HTTP)", value="1"),
        questionary.Choice("Tier 2  -  Camoufox browser", value="2"),
        questionary.Choice("Tier 3  -  Nodriver browser", value="3"),
    ]

    value = questionary.select(
        "  Fetch tier:", choices=choices, style=Q_STYLE, use_indicator=True
    ).ask()
    if value is None:
        sys.exit(0)

    tier_map = {"auto": None, "1": 1, "2": 2, "3": 3}
    label_map = {
        "auto": "Auto",
        "1": "Tier 1 (curl_cffi)",
        "2": "Tier 2 (Camoufox)",
        "3": "Tier 3 (Nodriver)",
    }
    return tier_map[value], label_map[value]


def ask_output() -> str:
    assert console is not None
    assert questionary is not None
    assert Q_STYLE is not None

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
    if "Preview" in choice:
        return "Preview only"
    if "Save" in choice:
        return "Save to file"
    if "Print" in choice:
        return "Print full content"
    if "Copy" in choice:
        return "Copy to clipboard"
    return choice


def ask_confirm() -> bool:
    assert console is not None
    assert questionary is not None
    assert Q_STYLE is not None

    console.print()
    return bool(
        questionary.confirm("  Start scraping?", default=True, style=Q_STYLE).ask()
    )


def ask_again() -> bool:
    assert console is not None
    assert questionary is not None
    assert Q_STYLE is not None

    console.print()
    return bool(
        questionary.confirm("  Scrape another URL?", default=True, style=Q_STYLE).ask()
    )


def run_scrape_interactive(
    url: str, force_tier: int | None, mode: str
) -> ScrapeResult | None:
    assert console is not None
    assert Progress is not None
    assert SpinnerColumn is not None
    assert TextColumn is not None
    assert TimeElapsedColumn is not None

    result_holder: list[ScrapeResult] = []
    error_holder: list[Exception] = []

    async def _run() -> None:
        try:
            validation_error = await _validate_read_website_url_async(url)
            if validation_error:
                failed = ScrapeResult(url=url, mode=mode, success=False)
                failed.warnings.append(validation_error)
                result_holder.append(failed)
                return

            scrape_result = await scrape_concurrent(
                url=url,
                mode=mode,
                force_tier=force_tier,
                skip_twitter=False,
                allow_external_relays=_external_relays_enabled(),
                allow_unsafe_tier3=_unsafe_tier3_enabled(),
            )
            result_holder.append(scrape_result)
        except Exception as exc:
            error_holder.append(exc)
        finally:
            await cleanup_http_clients()

    tier_msgs = {
        None: "Running auto mode...",
        1: "Running Tier 1 (curl_cffi)...",
        2: "Running Tier 2 (Camoufox)...",
        3: "Running Tier 3 (Nodriver)...",
    }

    devnull = io.StringIO()
    with Progress(
        SpinnerColumn(spinner_name="dots", style=f"bold {ACCENT}"),
        TextColumn("[bold white]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task(tier_msgs.get(force_tier, "Scraping..."), total=None)
        with redirect_stderr(devnull):
            asyncio.run(_run())

    if error_holder:
        console.print(f"  [{ERR_COL}]Error: {error_holder[0]}[/]")
        return None
    return result_holder[0] if result_holder else None


def interactive_mode() -> None:
    global _EXTRACT_MODE

    _check_ui_deps()
    assert console is not None
    assert Rule is not None

    show_banner()

    try:
        while True:
            url = ask_url()
            mode = ask_mode()
            _EXTRACT_MODE = mode

            site_type = detect_site_type(url)
            force_tier, tier_label = ask_tier(site_type)
            output_choice = ask_output()

            show_summary(url, mode, tier_label, output_choice)

            if not ask_confirm():
                console.print(f"\n  [{DIM_COL}]Cancelled.[/]\n")
            else:
                console.print()
                start = time.monotonic()
                result = run_scrape_interactive(url, force_tier, mode)
                elapsed = time.monotonic() - start

                if result is None or not result.success:
                    show_failure(result)
                else:
                    show_result(result, url, elapsed, output_choice)

            if not ask_again():
                console.print(f"\n  [{DIM_COL}]Done.[/]\n")
                break

            console.print()
            console.print(Rule(style=DIM_COL))
            console.print()
    finally:
        _cleanup_resources_sync()


def cli_mode(url: str) -> None:
    global _EXTRACT_MODE

    if not url.startswith(("http://", "https://")):
        print("Error: URL must start with http:// or https://")
        sys.exit(1)

    mode = _normalize_mode(_EXTRACT_MODE) or "precision"
    print(f"\nScraping: {url}")
    print(f"Mode: {mode}")

    scrape_result: ScrapeResult | None = None

    async def _run() -> None:
        nonlocal scrape_result
        try:
            validation_error = await _validate_read_website_url_async(url)
            if validation_error:
                failed = ScrapeResult(url=url, mode=mode, success=False)
                failed.warnings.append(validation_error)
                scrape_result = failed
                return

            scrape_result = await scrape_concurrent(
                url=url,
                mode=mode,
                force_tier=None,
                skip_twitter=False,
                allow_external_relays=_external_relays_enabled(),
                allow_unsafe_tier3=_unsafe_tier3_enabled(),
            )
        finally:
            await cleanup_http_clients()

    asyncio.run(_run())

    if scrape_result is None or not scrape_result.success or not scrape_result.content:
        if scrape_result is not None:
            print(format_scrape_result(scrape_result))
        else:
            print("Failed - all tiers exhausted.")
        sys.exit(1)

    print(f"Method : {scrape_result.winning_tier}")
    print(f"Chars  : {len(scrape_result.content):,}")
    print("-" * 60)
    print(scrape_result.content)


def main() -> None:
    try:
        if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
            cli_mode(sys.argv[1])
        else:
            interactive_mode()
    except KeyboardInterrupt:
        if console is not None:
            console.print(f"\n\n  [{DIM_COL}]Interrupted.[/]\n")
        else:
            print("\nInterrupted.\n")
        _cleanup_resources_sync()
        sys.exit(0)


if __name__ == "__main__":
    main()
