import time
import asyncio
from typing import Dict, Any, List
from src.state import AgentState
from src.tools.contracts import ToolResult
from src.tools.reddit_tools import reddit_search_posts, reddit_fetch_comments
from src.tools.hackernews_tools import hn_search_ask_posts
from src.tools.producthunt_tools import ph_search_gap_products
from src.tools.appstore_tools import as_scrape_negative_reviews
from src.utils.logger import get_logger
from src.utils.config_loader import config

logger = get_logger("collector")

def _scrape_reddit(reddit_config: dict, rate_limit_sleep: int) -> ToolResult:
    subs = reddit_config.get("subreddits", ["SaaS"])
    kws = reddit_config.get("keywords", ["app idea"])
    filters = reddit_config.get("filters", {})
    
    collected_data = []
    had_errors = False
    
    for sub in subs:
        try:
            result = reddit_search_posts(
                subreddit=sub,
                keywords=kws,
                limit=filters.get("posts_per_sub", 50),
                min_score=filters.get("min_score", 10),
                min_comments=filters.get("min_comments", 5),
                min_upvote_ratio=filters.get("min_upvote_ratio", 0.70)
            )
            
            if not result.success:
                had_errors = True
                continue
                
            for p in result.items:
                # Mock veya önceden çekilmiş yorumlar var mı kontrolü
                comments = p.get("top_comments", [])
                if not comments and not p.get("mocked", False):
                    comments = reddit_fetch_comments(post_id=p["id"], max_comments=5)
                    
                collected_data.append({
                    "source": f"Reddit/r/{sub}",
                    "id": p["id"],
                    "title": p["title"],
                    "score": p["score"],
                    "upvote_ratio": p["upvote_ratio"],
                    "text": p["text"],
                    "url": p["url"],
                    "top_comments": comments
                })
                    
        except Exception as e:
            logger.error(f"[AGENT] Collector Reddit hata (r/{sub}): {e}")
            had_errors = True
            
    return ToolResult(
        success=len(collected_data) > 0,
        source="Reddit/MultiSub",
        items=collected_data,
        had_errors=had_errors
    )


def run_collector_agent(state: AgentState) -> Dict[str, Any]:
    """Çoklu kaynaklardan (Reddit, HN, PH, App Store) veri toplar (Subagent Node)"""
    logger.info("[AGENT] Collector: Multi-Source Scraper başlatılıyor...")
    
    reddit_config = config.get("reddit", {})
    rate_limit_sleep = config.get("pipeline", {}).get("rate_limit_sleep", 7)
    
    collected_data = state.get("raw_data", [])
    
    # Zaten veri varsa (döngü durumu vs.) tekrar çekme
    if collected_data:
        logger.info("[AGENT] Collector: Bellekte zaten data var, atlanıyor.")
        return {"raw_data": collected_data}
    
    tool_errors = state.get("tool_errors", [])
    
    # Kaynak Kazıma (Sıralı veya paralel)
    scrapers = {
        "Reddit": lambda: _scrape_reddit(reddit_config, rate_limit_sleep),
        "HackerNews": lambda: hn_search_ask_posts.invoke({}),  # Default parametreler
        "ProductHunt": lambda: ph_search_gap_products.invoke({}),
        "AppStore": lambda: as_scrape_negative_reviews.invoke({})
    }
    
    new_data: List[Dict[str, Any]] = []
    for source_name, scraper_fn in scrapers.items():
        try:
            logger.info(f"[AGENT] Collector: {source_name} başlatıldı...")
            result: ToolResult = scraper_fn()
            
            if result.had_errors or not result.success:
                 tool_errors.append({
                     "source": source_name,
                     "error_type": result.error_type or "unknown",
                     "error_msg": result.error_msg
                 })
                 
            # Veri standardizasyonu sağlama
            for item in result.items:
                if "source" not in item:
                    item["source"] = source_name
                new_data.append(item)
                
            logger.info(f"  ✅ {source_name}: {len(result.items)} kayıt")
            
        except ImportError as ie:
            logger.warning(f"  ⚠️ {source_name} modülü eksik: {ie} — atlanıyor")
        except Exception as e:
            logger.warning(f"  ⚠️ {source_name} başarısız: {e} — atlanıyor")
            
    # Skora göre sırala ve en iyi sonuçları al (Örn: En fazla 50 tane)
    new_data.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    logger.info(f"[AGENT] Collector: Toplam {len(new_data)} kayıt toplandı ({len(scrapers)} kaynak)")
    
    return {
        "raw_data": new_data[:50],
        "tool_errors": tool_errors
    }
