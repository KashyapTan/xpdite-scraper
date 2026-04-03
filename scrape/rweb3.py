import asyncio
import re
import random
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig, CacheMode

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
]

def clean_markdown(md_text: str) -> str:
    if not md_text: return ""
    md_text = re.sub(r'!\[.*?\]\(.*?\)', '', md_text)
    md_text = re.sub(r'\[([^\]]*)\]\(.*?\)', r'\1', md_text)
    md_text = re.sub(r'\n{3,}', '\n\n', md_text)
    return md_text.strip()

async def read_website(url: str) -> str:
    print(f"🚀 Initializing Stealth Crawl for: {url}...")
    
    # FIX: In recent versions, stealth is often handled by 'extra_args' 
    # or specific flags depending on your Crawl4AI version.
    # If 'use_stealth_js' is missing, we use the automation bypass flag.
    browser_config = BrowserConfig(
        headless=True,
        extra_args=["--disable-blink-features=AutomationControlled"],
        # Note: headers are sometimes moved to CrawlerRunConfig in newer versions
    )
    
    noise_selector = ['.nav', '.navbar', '.footer', '.header', '.ad-container']
    random_wait = random.uniform(1.0, 3.0)
    
    # NEW: Most stealth/identity settings now live in CrawlerRunConfig
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        excluded_selector=", ".join(noise_selector),
        excluded_tags=['nav', 'header', 'footer', 'aside', 'form', 'svg', 'noscript'],
        wait_for="networkidle",
        # We pass the JS stealth logic and headers here if BrowserConfig rejected them
        js_code=f"await new Promise(r => setTimeout(r, {random_wait * 1000}));",
        user_agent=random.choice(USER_AGENTS)
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)
            
            if result.success:
                print(f"✅ Successfully crawled: {url}")
                return clean_markdown(result.markdown)
            else:
                return f"❌ Failed. Status: {result.status_code} | Error: {result.error_message}"
                
    except Exception as e:
        return f"⚠️ Error: {str(e)}"

async def main():
    target_url = "https://docs.openclaw.ai/tools/browser" 
    result = await read_website(target_url)
    with open("output_stealth.txt", "w", encoding="utf-8") as f:
        f.write(result)
    print("📝 Results written to output_stealth.txt")

if __name__ == "__main__":
    asyncio.run(main())