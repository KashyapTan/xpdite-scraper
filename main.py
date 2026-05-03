# FastAPI backend for XpditeS Scraper
# V2 Rebuild
"""
FastAPI backend for XpditeS Scraper
Replaces Streamlit with a lightweight REST API

Vercel Deployment:
  - Vercel auto-detects this file (main.py) and the `app` ASGI object.
  - Static files are served from the /public directory by Vercel's CDN,
    but we also mount /static for local dev compatibility.
  - maxDuration is set to 60s in vercel.json (Hobby plan max with Fluid Compute).
  - Browser-based tiers (Camoufox, Nodriver) are disabled in serverless;
    only Tier 1 (HTTP) works on Vercel.
"""

import time
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, Field

import scrape.scraper as scraper

api_description = """
<div style="font-family: 'Montserrat', sans-serif;">

## Defensive Web Scraping Engine
XpditeS is a high-performance web scraper designed for modern, JS-heavy applications. It bypasses bot protections by employing a **Concurrent Tiered Escalation Strategy**.

---

### Architecture Overview

**1. Fast HTTP Impersonation (Tier 1)**
The engine initiates standard HTTP requests using `curl_cffi` to mimic real browser TLS handshakes (JA3/HTTP2 fingerprints). For 80% of targets, this provides sub-second extraction without ever instantiating a browser.

**2. Jina AI Relay (Tier 1.5)**
If Tier 1 encounters a JS-wall, we leverage the Jina AI reader relay. This serves as an extremely fast and lightweight alternative to spinning up our own headless browsers.

**3. Headless Browser Escalation (Tier 2 / 3)**
When endpoints strictly demand local Javascript rendering, XpditeS escalates to headless browsers:
* **Tier 2 (Camoufox)**: A stealthy Firefox build customized to defeat fingerprinting.
* **Tier 3 (Nodriver)**: Undetected Chromium automation for the most stubborn protections.

---

### Vercel Serverless Limitations
This API is deployed on Vercel's serverless platform. Vercel functions are constrained to 500MB of ephemeral storage, meaning **local browser binaries cannot be packaged**.

**Impact**: Only Tier 1 (HTTP) and Tier 1.5 (Jina) are available in this specific cloud deployment. If a site requires local JS rendering, this API deployment will gracefully fail and return `vercel_limited=true`. 

For full-tier scraping capabilities, please run the engine locally or deploy the provided Docker container.

</div>
"""

app = FastAPI(
    title="XpditeS API", 
    version="1.0.0",
    description=api_description,
    docs_url=None,  # We serve a custom Swagger UI below
    redoc_url=None
)

# Mount static files (for local dev; Vercel serves /public via CDN)
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


class ScrapeRequest(BaseModel):
    url: str = Field(..., description="The target URL to scrape. Must start with http:// or https://", examples=["https://example.com/article"])
    mode: str = Field("precision", description="Extraction mode. 'precision' extracts main article content. 'full' returns raw Markdown of the entire page.", examples=["precision"])
    tier: str = Field("Auto", description="Scraping tier to use. 'Auto' starts at 1 and escalates. '1' is HTTP-only. '2' uses Camoufox. '3' uses Nodriver.", examples=["Auto"])


class ScrapeResponse(BaseModel):
    success: bool = Field(..., description="Whether the scrape was successful")
    tier_used: str | None = Field(None, description="The tier that successfully extracted the content")
    content: str | None = Field(None, description="The extracted text or markdown content")
    char_count: int = Field(0, description="Number of characters extracted")
    elapsed_time: float = Field(0.0, description="Total time taken for the extraction in seconds")
    error: str | None = Field(None, description="Error message if the extraction failed")
    vercel_limited: bool = Field(False, description="True if the scrape failed due to Vercel serverless environment limitations")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """Serve custom Swagger UI matching the main app's dark theme"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Documentation",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-dark.css?v=2",
        swagger_favicon_url="/api/logo",
    )


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the main HTML frontend"""
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return HTMLResponse("<h1>Frontend not found</h1>", status_code=404)


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    # Detect if running on Vercel
    is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))

    # Check for core dependency availability without crashing
    try:
        import playwright

        playwright_ok = True
    except ImportError:
        playwright_ok = False

    return {
        "status": "ok",
        "service": "xpdites-scraper",
        "playwright_installed": playwright_ok,
        "port_configuration": os.environ.get("PORT", "7860"),
        "environment": "vercel" if is_vercel else "local",
    }


@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_url(request: ScrapeRequest):
    """
    Scrape a URL and return the extracted content.

    On Vercel Hobby plan (Fluid Compute):
      - maxDuration is 60s (configured in vercel.json)
      - Only Tier 1 (HTTP-based scraping) is available
      - Browser tiers are auto-disabled in serverless
    """
    # Validate URL
    url = request.url.strip()
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400, detail="Invalid URL. Must start with http:// or https://"
        )

    # Validate mode
    mode = request.mode.strip().lower()
    if mode not in {"precision", "full"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Must be 'precision' or 'full'.",
        )

    # Determine tier
    force_tier = None if request.tier == "Auto" else int(request.tier)

    try:
        start_time = time.time()
        result = await scraper.scrape(url, force_tier=force_tier, mode=mode)
        elapsed_time = time.time() - start_time

        if result:
            tier_used, content = result
            return ScrapeResponse(
                success=True,
                tier_used=tier_used,
                content=content,
                char_count=len(content),
                elapsed_time=round(elapsed_time, 2),
            )
        else:
            is_vercel = bool(os.environ.get("VERCEL") or os.environ.get("VERCEL_ENV"))
            return ScrapeResponse(
                success=False,
                error="All scraping tiers exhausted. Could not extract content.",
                elapsed_time=round(elapsed_time, 2),
                vercel_limited=is_vercel,
            )

    except Exception as e:
        return ScrapeResponse(success=False, error=str(e))


@app.get("/api/logo")
async def get_logo():
    """Serve the logo image"""
    logo_path = Path(__file__).parent / "assets" / "logo.svg"
    if logo_path.exists():
        return FileResponse(logo_path, media_type="image/svg+xml")
    raise HTTPException(status_code=404, detail="Logo not found")


if __name__ == "__main__":
    import uvicorn
    import os

    # Force port to be an integer to avoid Node-style string/socket path pitfalls
    # Hosting platforms often provide PORT as an environment variable
    port_env = os.environ.get("PORT", "7860")
    try:
        port = int(port_env)
    except ValueError:
        print(f"Warning: Invalid PORT '{port_env}', falling back to 7860")
        port = 7860

    print(f"Starting server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
