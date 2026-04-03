#!/usr/bin/env python3
"""
vision_scraper.py — Playwright screenshot + OCR scraper

Two modes (auto-selected, or force with --mode):
  surya    Free, local, layout-aware OCR via Surya (default)
  claude   Paid, Claude Vision API (~$0.01-0.05/page), most accurate

Usage:
    python vision_scraper.py <url>
    python vision_scraper.py                 # interactive prompts
    python vision_scraper.py --interactive   # force interactive prompts
    python vision_scraper.py <url> --out output.txt
    python vision_scraper.py <url> --mode claude   # force Claude Vision
    python vision_scraper.py <url> --mode surya    # force Surya OCR
    python vision_scraper.py <url> --save-screenshot  # also save the PNG

Install:
    pip install playwright surya-ocr pillow curl_cffi
    playwright install chromium

For Claude Vision mode, set your API key:
    export ANTHROPIC_API_KEY=sk-ant-...   (Linux/Mac)
    set ANTHROPIC_API_KEY=sk-ant-...      (Windows)
"""

import sys
import platform
import warnings
import atexit
import os

if platform.system() == "Windows":
    warnings.filterwarnings("ignore", category=ResourceWarning)
    def _silence():
        try:
            devnull = open(os.devnull, 'w')
            sys.stderr.flush()
            os.dup2(devnull.fileno(), sys.stderr.fileno())
        except Exception:
            pass
    atexit.register(_silence)

import argparse
import asyncio
import re
import io
import base64
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# ── Colours ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def log(msg, c=RESET):  print(f"{c}{msg}{RESET}", file=sys.stderr)
def ok(msg):            log(f"  ✅  {msg}", GREEN)
def warn(msg):          log(f"  ⚠️   {msg}", YELLOW)
def fail(msg):          log(f"  ❌  {msg}", RED)
def info(msg):          log(f"  ℹ️   {msg}", CYAN)
def dim_log(msg):       log(f"  {msg}", DIM)


def dependency_help(packages: str, extra_uv_cmd: str | None = None, extra_py_module_cmd: str | None = None):
    fail(f"  Current Python: {sys.executable}")
    fail("  If you use uv, run:")
    fail(f"    uv pip install {packages}")
    if extra_uv_cmd:
        fail(f"    uv run {extra_uv_cmd}")
    fail("  Or install into this interpreter:")
    fail(f"    \"{sys.executable}\" -m pip install {packages}")
    if extra_py_module_cmd:
        fail(f"    \"{sys.executable}\" -m {extra_py_module_cmd}")


def warn_if_outside_project_venv():
    if platform.system() != "Windows":
        return
    venv_python = Path(".venv") / "Scripts" / "python.exe"
    if not venv_python.exists():
        return

    current = Path(sys.executable)
    try:
        if current.resolve() != venv_python.resolve():
            warn("Current interpreter is not the project's .venv")
            warn(f"  Using: {current}")
            warn("  Use: uv run python play.py")
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: RENDER — Playwright takes a full-page screenshot
# ═══════════════════════════════════════════════════════════════════════════════

async def render_screenshot(url: str) -> bytes | None:
    """
    Launches a headless Chromium browser, navigates to the URL,
    waits for JS to fully render, and returns a full-page PNG screenshot.
    """
    info("Render → Playwright (headless Chromium, full JS execution)")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        fail("playwright not installed in current Python environment")
        dependency_help(
            "playwright",
            extra_uv_cmd="playwright install chromium",
            extra_py_module_cmd="playwright install chromium",
        )
        return None

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                java_script_enabled=True,
            )
            page = await ctx.new_page()

            info(f"  Navigating to {url}…")
            await page.goto(url, wait_until="networkidle", timeout=45_000)

            # Extra wait for lazy-loaded content, React hydration, etc.
            await asyncio.sleep(3)

            # Scroll to bottom to trigger any scroll-based lazy loading
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(0.5)

            info("  Taking full-page screenshot…")
            screenshot_bytes = await page.screenshot(
                full_page=True,
                type="png",
            )
            await browser.close()

        ok(f"Screenshot captured ({len(screenshot_bytes) / 1024:.1f} KB)")
        return screenshot_bytes

    except Exception as e:
        fail(f"Playwright render failed: {type(e).__name__}: {e}")
        return None


def resize_for_ocr(screenshot_bytes: bytes, max_width: int = 1568) -> bytes:
    """
    Resize screenshot to a sensible max width.
    - Surya: larger = more accurate but slower; 1280px is the sweet spot
    - Claude Vision: 1568px is Claude's internal processing max
    Sending larger just wastes time/tokens with no accuracy gain.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")
        if img.width > max_width:
            ratio = max_width / img.width
            new_size = (max_width, int(img.height * ratio))
            resampling = getattr(Image, "Resampling", Image)
            img = img.resize(new_size, resampling.LANCZOS)
            dim_log(f"  Resized screenshot: {img.width}×{img.height}px")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        warn("Pillow not installed (pip install pillow) — sending original screenshot size")
        return screenshot_bytes

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2A: EXTRACT — Surya OCR (free, local, layout-aware)
# ═══════════════════════════════════════════════════════════════════════════════

# Surya models are expensive to load (~2-3s, ~1GB RAM).
# Cache them as module-level globals so they're only loaded once per process.
_surya_models = None

def _load_surya_models():
    global _surya_models
    if _surya_models is not None:
        return _surya_models

    info("  Loading Surya models (first run — ~2-3s)…")
    modern_error = None

    # Surya >=0.16 API
    try:
        from surya.detection import DetectionPredictor
        from surya.foundation import FoundationPredictor
        from surya.recognition import RecognitionPredictor

        foundation_predictor = FoundationPredictor()
        det_predictor = DetectionPredictor()
        rec_predictor = RecognitionPredictor(foundation_predictor)

        _surya_models = ("modern", det_predictor, rec_predictor)
        ok("Surya models loaded (modern API)")
        return _surya_models
    except Exception as e:
        modern_error = f"{type(e).__name__}: {e}"
        dim_log(f"  Modern Surya API unavailable: {modern_error}")

    # Legacy API fallback
    try:
        from surya.model.detection.model import load_model as load_det
        from surya.model.detection.processor import load_processor as load_det_proc
        from surya.model.recognition.model import load_model as load_rec
        from surya.model.recognition.processor import load_processor as load_rec_proc

        _surya_models = (
            "legacy",
            load_det(), load_det_proc(),
            load_rec(), load_rec_proc(),
        )
        ok("Surya models loaded (legacy API)")
        return _surya_models
    except Exception as e:
        fail("Failed to initialize Surya OCR models")
        if modern_error:
            fail(f"  Modern API error: {modern_error}")
        fail(f"  Legacy API error: {type(e).__name__}: {e}")
        raise


def extract_surya(screenshot_bytes: bytes) -> str | None:
    """
    Runs Surya OCR on the screenshot.
    Unlike Tesseract, Surya understands page layout — it correctly handles
    multi-column pages, sidebars, and tables without garbling the reading order.
    Supports 90+ languages, runs fully offline.
    """
    info("Extract → Surya OCR (local, layout-aware)")
    try:
        from PIL import Image
    except ImportError:
        fail("surya-ocr or pillow not installed in current Python environment")
        dependency_help("surya-ocr pillow")
        return None

    try:
        screenshot_bytes = resize_for_ocr(screenshot_bytes, max_width=1280)
        image = Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")

        surya_models = _load_surya_models()

        if surya_models[0] == "modern":
            _, det_predictor, rec_predictor = surya_models
            try:
                from surya.common.surya.schema import TaskNames
                task_names = [TaskNames.ocr_with_boxes]
            except Exception:
                task_names = ["ocr_with_boxes"]

            results = rec_predictor(
                [image],
                task_names=task_names,
                det_predictor=det_predictor,
                highres_images=[image],
                sort_lines=True,
                math_mode=True,
            )
        else:
            from surya.ocr import run_ocr

            _, det_model, det_processor, rec_model, rec_processor = surya_models
            results = run_ocr(
                [image],
                [["en"]],
                det_model, det_processor,
                rec_model, rec_processor,
            )

        # results is a list of OCRResult (one per image).
        # Each has .text_lines, each line has .text and .confidence.
        lines = []
        for page_result in results:
            for line in page_result.text_lines:
                # Skip very low confidence noise (< 40%)
                if hasattr(line, 'confidence') and line.confidence < 0.4:
                    continue
                if line.text.strip():
                    lines.append(line.text.strip())

        text = "\n".join(lines)
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        if len(text) < 50:
            warn("Surya extracted very little text — page may be mostly images or canvas")
            return None

        ok(f"Surya OCR complete ({len(text):,} chars from {len(lines)} text lines)")
        return text

    except Exception as e:
        fail(f"Surya OCR failed: {type(e).__name__}: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2B: EXTRACT — Claude Vision API (paid, most accurate)
# ═══════════════════════════════════════════════════════════════════════════════

async def extract_claude_vision(screenshot_bytes: bytes) -> str | None:
    """
    Sends the screenshot to Claude Vision API.
    Claude understands layout, tables, charts, and spatial relationships —
    not just raw character recognition.
    Costs ~$0.01-0.05 per page depending on screenshot size.
    Requires ANTHROPIC_API_KEY environment variable.
    """
    info("Extract → Claude Vision API")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        fail("ANTHROPIC_API_KEY not set in environment")
        fail("  Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
        return None

    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        fail("curl_cffi not installed in current Python environment")
        dependency_help("curl_cffi")
        return None

    screenshot_bytes = resize_for_ocr(screenshot_bytes, max_width=1568)
    b64 = base64.b64encode(screenshot_bytes).decode()

    # Estimate cost for user awareness
    size_kb = len(screenshot_bytes) / 1024
    dim_log(f"  Image size: {size_kb:.1f} KB — estimated cost: ~${size_kb * 0.00003:.4f}")

    try:
        async with AsyncSession() as s:
            resp = await s.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 4096,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": b64,
                                },
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Extract all readable text content from this webpage screenshot. "
                                    "Preserve the logical reading order. "
                                    "Include all visible text: headings, body text, navigation labels, "
                                    "prices, statistics, table data, captions, buttons. "
                                    "For tables, preserve the row/column structure using plain text alignment. "
                                    "Output plain text only — no markdown formatting, no commentary, "
                                    "no explanation. Just the extracted text."
                                ),
                            },
                        ],
                    }],
                },
                timeout=60,
            )

        data = resp.json()
        if "error" in data:
            fail(f"Claude API error: {data['error'].get('message', data['error'])}")
            return None

        if "content" in data and data["content"]:
            text = data["content"][0].get("text", "").strip()
            if len(text) > 50:
                ok(f"Claude Vision complete ({len(text):,} chars)")
                return text

        warn("Claude Vision returned empty response")
        return None

    except Exception as e:
        fail(f"Claude Vision API call failed: {type(e).__name__}: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATION
# ═══════════════════════════════════════════════════════════════════════════════

async def scrape(url: str, mode: str = "surya") -> tuple[str, str] | None:
    """
    Render with Playwright, then extract with the chosen OCR method.
    mode: "surya" | "claude" | "both" (tries surya first, claude as fallback)
    Returns (method_label, extracted_text) or None.
    """
    # Step 1: render
    screenshot_bytes = await render_screenshot(url)
    if not screenshot_bytes:
        return None

    # Step 2: extract
    if mode == "surya":
        text = extract_surya(screenshot_bytes)
        if text:
            return ("playwright_surya", text)
        fail("Surya OCR failed — try --mode claude (requires ANTHROPIC_API_KEY)")
        return None

    elif mode == "claude":
        text = await extract_claude_vision(screenshot_bytes)
        if text:
            return ("playwright_claude", text)
        return None

    elif mode == "both":
        # Try Surya first (free), fall back to Claude
        info("Mode: both — trying Surya first, Claude Vision as fallback")
        text = extract_surya(screenshot_bytes)
        if text:
            return ("playwright_surya", text)
        warn("Surya failed — falling back to Claude Vision…")
        text = await extract_claude_vision(screenshot_bytes)
        if text:
            return ("playwright_claude_fallback", text)
        return None

    fail(f"Unknown mode: {mode}")
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

def build_path(url: str, label: str, out: str | None) -> Path:
    if out: return Path(out)
    host = re.sub(r'[^\w.-]', '_', urlparse(url).hostname or "output")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"{host}_{label}_{ts}.txt")

def build_screenshot_path(url: str) -> Path:
    host = re.sub(r'[^\w.-]', '_', urlparse(url).hostname or "output")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(f"{host}_screenshot_{ts}.png")

def write_output(path: Path, url: str, label: str, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"URL     : {url}\n"
        f"Method  : {label}\n"
        f"Scraped : {datetime.now().isoformat()}\n"
        f"{'─' * 60}\n\n"
    )
    path.write_text(header + content, encoding="utf-8")
    ok(f"Saved → {path}  ({len(content):,} chars)")


def prompt_text(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default not in (None, "") else ""
    while True:
        try:
            raw = input(f"{BOLD}{prompt}{suffix}:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            fail("Interactive input cancelled by user")
            sys.exit(1)

        if raw:
            return raw
        if default is not None:
            return default
        return ""


def prompt_yes_no(prompt: str, default: bool = False) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = prompt_text(f"{prompt} ({hint})", "").strip().lower()
        if raw == "":
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        warn("Please enter y or n")


def prompt_url(default: str | None = None) -> str:
    while True:
        url = prompt_text("URL", default)
        if url.startswith(("http://", "https://")):
            return url
        warn("URL must start with http:// or https://")


def prompt_mode(default: str = "surya") -> str:
    choice_to_mode = {
        "1": "surya",
        "2": "claude",
        "3": "both",
        "surya": "surya",
        "claude": "claude",
        "both": "both",
    }
    mode_to_choice = {"surya": "1", "claude": "2", "both": "3"}

    print(f"{BOLD}Choose OCR mode:{RESET}")
    print("  1) surya  - Free local OCR")
    print("  2) claude - Claude Vision API (paid)")
    print("  3) both   - Surya first, Claude fallback")

    while True:
        raw = prompt_text("Mode (1/2/3 or name)", mode_to_choice.get(default, "1")).lower()
        mode = choice_to_mode.get(raw)
        if mode:
            return mode
        warn("Invalid mode. Enter 1, 2, 3, surya, claude, or both")


def collect_interactive_inputs(
    url: str | None,
    mode: str,
    out: str | None,
    save_screenshot: bool,
) -> tuple[str, str, str | None, bool]:
    print(f"\n{BOLD}{CYAN}{'─' * 58}{RESET}")
    print(f"{BOLD}{CYAN}  🧭  Interactive setup{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 58}{RESET}")

    picked_url = prompt_url(default=url)
    picked_mode = prompt_mode(default=mode)
    out_default = out if out else ""
    picked_out = prompt_text("Output file path (blank = auto)", out_default).strip() or None
    picked_save_screenshot = prompt_yes_no("Save raw screenshot PNG too", default=save_screenshot)

    print()
    info("Using interactive selections")
    info(f"Target : {picked_url}")
    info(f"Mode   : {picked_mode}")
    info(f"Out    : {picked_out or '(auto)'}")
    info(f"PNG    : {'yes' if picked_save_screenshot else 'no'}")
    print()

    return picked_url, picked_mode, picked_out, picked_save_screenshot

# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    warn_if_outside_project_venv()

    parser = argparse.ArgumentParser(
        prog="vision_scraper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            "Playwright screenshot + OCR scraper.\n\n"
            "Works on ANY website — renders full JS, then reads the pixels.\n"
            "No DOM parsing, no bot-detection bypass needed.\n\n"
            "If URL is omitted, interactive prompts are shown in terminal.\n\n"
            "Modes:\n"
            "  surya   Free, local, layout-aware OCR (default)\n"
            "  claude  Paid Claude Vision API, most accurate (~$0.01-0.05/page)\n"
            "  both    Surya first, Claude as fallback\n\n"
            "Install:\n"
            "  pip install playwright surya-ocr pillow curl_cffi\n"
            "  playwright install chromium\n"
        ),
    )
    parser.add_argument("url",
                        nargs="?",
                        help="URL to scrape (omit for interactive mode)")
    parser.add_argument("--out", "-o",
                        help="Output file path (default: auto-named)")
    parser.add_argument("--mode", "-m",
                        choices=["surya", "claude", "both"],
                        default="surya",
                        help="OCR backend (default: surya)")
    parser.add_argument("--save-screenshot", "-s",
                        action="store_true",
                        help="Also save the raw PNG screenshot")
    parser.add_argument("--interactive", "-i",
                        action="store_true",
                        help="Ask for URL/mode/output interactively")
    args = parser.parse_args()

    if args.interactive or not args.url:
        args.url, args.mode, args.out, args.save_screenshot = collect_interactive_inputs(
            url=args.url,
            mode=args.mode,
            out=args.out,
            save_screenshot=args.save_screenshot,
        )

    if not args.url.startswith(("http://", "https://")):
        fail("URL must start with http:// or https://")
        sys.exit(1)

    print(f"\n{BOLD}{CYAN}{'═' * 58}{RESET}")
    print(f"{BOLD}{CYAN}  📸  Vision Scraper (Playwright + OCR){RESET}")
    print(f"{BOLD}{CYAN}{'═' * 58}{RESET}")
    info(f"Target : {args.url}")
    info(f"Mode   : {args.mode}")
    if args.mode in ("claude", "both"):
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        info(f"API Key: {'✅ set' if has_key else '❌ not set (export ANTHROPIC_API_KEY=...)'}")
    print()

    # Run the scrape
    if args.save_screenshot:
        # We need the raw screenshot bytes to save, so do it manually
        async def run_with_screenshot():
            screenshot_bytes = await render_screenshot(args.url)
            if not screenshot_bytes:
                return None, None

            # Save screenshot
            ss_path = build_screenshot_path(args.url)
            ss_path.write_bytes(screenshot_bytes)
            ok(f"Screenshot saved → {ss_path}")

            # Extract
            if args.mode == "surya":
                text = extract_surya(screenshot_bytes)
                label = "playwright_surya"
            elif args.mode == "claude":
                text = await extract_claude_vision(screenshot_bytes)
                label = "playwright_claude"
            else:  # both
                text = extract_surya(screenshot_bytes)
                label = "playwright_surya"
                if not text:
                    text = await extract_claude_vision(screenshot_bytes)
                    label = "playwright_claude_fallback"

            return (label, text) if text else (None, None)

        label, content = asyncio.run(run_with_screenshot())
    else:
        outcome = asyncio.run(scrape(args.url, mode=args.mode))
        if outcome:
            label, content = outcome
        else:
            label, content = None, None

    if not content:
        fail("Extraction failed. No output written.")
        sys.exit(1)
    if label is None:
        fail("Extraction failed: missing extraction method label.")
        sys.exit(1)

    path = build_path(args.url, label, args.out)
    write_output(path, args.url, label, content)
    print()

if __name__ == "__main__":
    main()