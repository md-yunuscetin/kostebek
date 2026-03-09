from typing import List, Dict, Any, Tuple
from langchain_core.tools import tool
from src.tools.contracts import ToolResult
from src.utils.logger import get_logger

logger = get_logger("appstore_tools")

# Varsayılan hedefler (Uygulama Adı, slug, ID)
DEFAULT_TARGET_APPS = [
    ("Notion", "notion", "1232780281"),
    ("Todoist", "todoist", "572688855"),
    ("Calendly", "calendly", "1361335903"),
]

@tool
def as_scrape_negative_reviews(target_apps: List[Tuple[str, str, str]] = None) -> ToolResult:
    """App Store'daki hedef uygulamaların düşük yıldızlı (1-2) eleştirel yorumlarını çeker."""
    try:
        from app_store_scraper import AppStore
    except ImportError:
        logger.warning("app-store-scraper kütüphanesi yüklü değil, App Store araması atlanıyor.")
        return ToolResult(success=False, source="AppStore", error_type="dependency", error_msg="app-store-scraper missing", had_errors=True)

    if target_apps is None:
        target_apps = DEFAULT_TARGET_APPS
        
    collected = []
    logger.info(f"App Store taranıyor... Hedef Uygulamalar: {[t[0] for t in target_apps]}")
    
    had_errors = False
    
    for app_name, app_slug, numeric_id in target_apps:
        try:
            app = AppStore(country="us", app_name=app_slug, app_id=numeric_id)
            app.review(how_many=50)
            
            for review in app.reviews:
                rating = review.get("rating", 5)
                if rating <= 2:
                    collected.append({
                        "source": f"AppStore/{app_name}",
                        "id": f"{app_name}-{review.get('date', '')}",
                        "title": review.get("title", ""),
                        "score": (3 - rating) * 30,
                        "text": review.get("review", "")[:1000],
                        "url": f"https://apps.apple.com/app/{numeric_id}",
                        "signal": f"{app_name} kullanıcısı şikayeti ({rating} Yıldız)",
                        "top_comments": []
                    })
        except Exception as e:
            logger.error(f"App Store arama hatası ({app_name}): {e}")
            had_errors = True
            
    return ToolResult(
        success=len(collected) > 0,
        source="AppStore",
        items=collected,
        had_errors=had_errors,
        provenance={"targets": target_apps}
    )
