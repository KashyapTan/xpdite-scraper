# FastAPI backend for XpditeS Scraper
# V2 Rebuild
"""
FastAPI backend for XpditeS Scraper
Replaces Streamlit with a lightweight REST API
"""

import time
import os
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

import scrape.scraper as scraper

app = FastAPI(title="XpditeS Scraper API", version="1.0.0")

# Mount static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


class ScrapeRequest(BaseModel):
    url: str
    mode: str = "precision"  # "precision" or "full"
    tier: str = "Auto"  # "Auto", "1", "2", or "3"


class ScrapeResponse(BaseModel):
    success: bool
    tier_used: str | None = None
    content: str | None = None
    char_count: int = 0
    elapsed_time: float = 0.0
    error: str | None = None


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
    }


@app.post("/api/scrape", response_model=ScrapeResponse)
async def scrape_url(request: ScrapeRequest):
    """
    Scrape a URL and return the extracted content
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
            return ScrapeResponse(
                success=False,
                error="All scraping tiers exhausted. Could not extract content.",
                elapsed_time=round(elapsed_time, 2),
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
    # Hugging Face usually provides PORT as an environment variable
    port_env = os.environ.get("PORT", "7860")
    try:
        port = int(port_env)
    except ValueError:
        print(f"Warning: Invalid PORT '{port_env}', falling back to 7860")
        port = 7860

    print(f"Starting server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
