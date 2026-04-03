import requests
from bs4 import BeautifulSoup
import re

def clean_website_text(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status() # Check for HTTP errors
        
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 1. Remove non-content elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'form', 'noscript']):
            element.decompose()

        # 2. Target the main content area (common for most news/blogs)
        # If 'article' or 'main' tags exist, we prioritize those
        content_area = soup.find('article') or soup.find('main') or soup.body
        
        if not content_area:
            return "Could not find main content."

        # 3. Extract text with controlled spacing
        chunks = (phrase.strip() for line in content_area.get_text(separator='\n').splitlines() for phrase in line.split('  '))
        
        # 4. Remove empty lines and join with a single newline
        text = '\n'.join(chunk for chunk in chunks if chunk)

        # 5. Final Regex cleanup: limit consecutive newlines to two
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    except Exception as e:
        return f"Error scraping {url}: {e}"

# Execution
url = 'https://www.cbsnews.com/news/winter-olympic-games-schedule-2026/'
website_text = clean_website_text(url)

with open("output.txt", "w", encoding="utf-8") as f:
    f.write(website_text)

print("Scraping complete. Check output.txt.")