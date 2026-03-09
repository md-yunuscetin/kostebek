import os
import requests
from typing import List, Dict, Any
from langchain_core.tools import tool
from src.tools.contracts import ToolResult
from src.utils.logger import get_logger

logger = get_logger("producthunt_tools")

PRODUCTHUNT_GRAPHQL = """
query {{
  posts(order: VOTES, first: 20, topic: "{topic}") {{
    edges {{
      node {{
        name
        tagline
        votesCount
        commentsCount
        url
        reviewsRating
        topics {{ edges {{ node {{ name }} }} }}
      }}
    }}
  }}
}}
"""

@tool
def ph_search_gap_products(topics: List[str] = None) -> ToolResult:
    """Product Hunt API'sinden yüksek oylu ancak düşük puanlı ürünleri bularak piyasa boşluklarını tespit eder."""
    token = os.getenv("PH_API_TOKEN")
    if not token:
        logger.warning("PH_API_TOKEN tanımlanmamış, Product Hunt atlanıyor.")
        return ToolResult(success=False, source="ProductHunt", error_type="auth", error_msg="Missing PH_API_TOKEN")
        
    if not topics:
        topics = ["productivity", "developer-tools", "ai"]
        
    headers = {"Authorization": f"Bearer {token}"}
    collected = []
    logger.info(f"Product Hunt taranıyor... Kategoriler: {topics}")
    
    had_errors = False
    
    for topic in topics:
        try:
            res = requests.post(
                "https://api.producthunt.com/v2/api/graphql",
                json={"query": PRODUCTHUNT_GRAPHQL.format(topic=topic)},
                headers=headers,
                timeout=10
            )
            res.raise_for_status()
            data = res.json()
            
            for edge in data.get("data", {}).get("posts", {}).get("edges", []):
                node = edge.get("node", {})
                
                votes = node.get("votesCount", 0)
                rating = node.get("reviewsRating", 5)
                
                if votes > 200 and rating < 3.5:
                    collected.append({
                        "source": "ProductHunt",
                        "id": node.get("url"),
                        "title": node.get("name", ""),
                        "score": votes,
                        "signal": f"Yüksek talep ({votes} oy), düşük memnuniyet ({rating} yıldız) — boşluk var!",
                        "url": node.get("url", ""),
                        "text": node.get("tagline", ""),
                        "top_comments": []
                    })
        except Exception as e:
            logger.error(f"ProductHunt arama hatası ({topic}): {e}")
            had_errors = True
            
    return ToolResult(
        success=len(collected) > 0,
        source="ProductHunt",
        items=collected,
        had_errors=had_errors,
        provenance={"topics": topics}
    )
