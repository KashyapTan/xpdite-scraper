import trafilatura

url = 'https://docs.openclaw.ai/tools/browser'

# Define a real-looking browser header
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'

# Use the 'config' or 'headers' approach
downloaded = trafilatura.fetch_url(url)

if downloaded:
    result = trafilatura.extract(downloaded)
    # print(result)
    with open("output2.txt", "w", encoding="utf-8") as f:
        f.write(result)

    print("Scraping complete. Check output.txt.")
else:
    print("Blocked or failed to fetch.")
