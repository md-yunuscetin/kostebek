import requests
from typing import List, Dict, Any
from langchain_core.tools import tool
from src.tools.contracts import ToolResult
from src.utils.logger import get_logger

logger = get_logger("hackernews_tools")

@tool
def hn_search_ask_posts(query: str = "tool for", hits_per_page: int = 20) -> ToolResult:
    """Hacker News 'Ask HN' gönderilerinde yazılım taleplerini arar"""
    
    url = "https://hn.algolia.com/api/v1/search_by_date"
    params = {
        "tags": "ask_hn",
        "query": query,
        "hitsPerPage": hits_per_page
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for hit in data.get("hits", []):
            results.append({
                "source": "HackerNews",
                "id": str(hit.get("objectID")),
                "title": hit.get("title"),
                "score": hit.get("points", 0),
                "upvote_ratio": None,
                "text": hit.get("story_text") or "",
                "url": f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "top_comments": [] # İstenirse yorumlar ayrı çekilebilir
            })
            
        logger.info(f"HN Araması tamamlandı, {len(results)} hit bulundu.")
        return ToolResult(
            success=True, 
            source="HackerNews", 
            items=results, 
            provenance={"query": query, "hits": hits_per_page}
        )
        
    except requests.exceptions.Timeout:
        logger.warning("HN API Timeout.")
        return ToolResult(success=False, source="HackerNews", error_type="timeout", error_msg="Zaman aşımı")
    except Exception as e:
        logger.error(f"HN Arama Hatası: {e}")
        return ToolResult(success=False, source="HackerNews", error_type="network", error_msg=str(e), had_errors=True)
