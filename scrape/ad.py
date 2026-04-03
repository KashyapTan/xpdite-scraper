from mcp.server.fastmcp import FastMCP
from ddgs import DDGS
from typing import Any, Dict, List
import re
import random
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode

# A list of modern, common User-Agents to rotate
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
]

def clean_markdown(md_text: str) -> str:
    """
    Strips Markdown links and images to return pure text.
    """
    if not md_text:
        return ""
    # Remove images
    md_text = re.sub(r'!\[.*?\]\(.*?\)', '', md_text)
    # Remove links, keep text
    md_text = re.sub(r'\[([^\]]*)\]\(.*?\)', r'\1', md_text)
    # Clean up excessive newlines
    md_text = re.sub(r'\n{3,}', '\n\n', md_text)
    return md_text.strip()

async def read_website(url: str) -> str:
    print(f"🚀 Initializing Stealth Crawl for: {url}...")
    
    # --- 1. ENHANCED BROWSER CONFIG ---
    # enable_stealth=True is the heavy lifter here. 
    # It masks 'navigator.webdriver' and other bot signatures.
    browser_config = BrowserConfig(
        headless=True,
        enable_stealth=True,  # ✅ FIXED: Changed from use_stealth_js to enable_stealth
        headers={
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"  # Makes it look like you came from a search
        },
        # Specifically disables the "AutomationControlled" flag in Blink browsers
        extra_args=["--disable-blink-features=AutomationControlled"]
    )
    
    # --- 2. NOISE REDUCTION ---
    noise_selector = [
        '.nav', '.navbar', '.menu', '.sidebar', '.footer', '.header',
        '#nav', '#header', '#footer', '.topbar', '.navigation',
        '.ad-container', '.social-share', '.cookie-banner', '.modal'
    ]
    
    # --- 3. RANDOMIZED HUMAN TIMING ---
    # We use a random wait between 1-3 seconds to break rhythmic detection
    random_wait = random.uniform(1.0, 3.0)
    
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        excluded_selector=", ".join(noise_selector),
        excluded_tags=['nav', 'header', 'footer', 'aside', 'form', 'svg', 'noscript', 'script', 'style'],
        # Wait for the page to be idle (all network requests finished)
        js_code=f"await new Promise(r => setTimeout(r, {random_wait * 1000}));"
    )
    
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            
            if result.success:
                print(f"✅ Successfully crawled: {url}")
                return clean_markdown(result.markdown)
            else:
                # Log specific status codes (e.g., 403 Forbidden)
                return f"❌ Failed to crawl. Status: {result.status_code} | Error: {result.error_message}"
                
    except Exception as e:
        return f"⚠️ An unexpected error occurred: {str(e)}"

# --- EXECUTION ---
async def main():
    # Testing on a slightly more complex target or your choice
    target_url = "https://www.nba.com/schedule" 
    result = await read_website(target_url)
    
    with open("output_stealth.txt", "w", encoding="utf-8") as f:
        f.write(result)
    print("📝 Results written to output_stealth.txt")

if __name__ == "__main__":
    asyncio.run(main())