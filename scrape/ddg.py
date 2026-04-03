from typing import Dict
import pandas as pd
from ddgs import DDGS
import json

query = "What is the capital of France?"

def search_web_pages(query:str) -> Dict[str, str]:
    """
    Use this tool to fetch website urls and titles
    
    Also use this tool when the user asks you to search the web
    """
    results = DDGS().text(
        query=query,
        region='wt-wt', # us-en for US
        safesearch='off',
        max_results=10
    )

    results_json = json.dumps(results)
    return results_json

result = search_web_pages(query)
print(result)
# results = DDGS().text(
#     query=search_query,
#     region='wt-wt', # us-en for US
#     safesearch='off',
#     max_results=5
# )

# json_output = json.dumps(results)

# print(json_output)