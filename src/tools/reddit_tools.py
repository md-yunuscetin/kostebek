# src/tools/reddit_tools.py

import os
import requests
from typing import List, Optional
from src.tools.contracts import ToolResult
from src.utils.logger import get_logger

logger = get_logger("reddit_tools")

DEFAULT_KEYWORDS = [
    "wish there was", "app idea", "pain point", "need an app",
    "struggle with", "hate how", "is there an app", "anyone else find"
]

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "application/json"
}


def _scrape_reddit_json(subreddit: str, limit: int = 50, keywords: List[str] = None,
                        min_score: int = 10, min_upvote_ratio: float = 0.70) -> List[dict]:
    """
    Reddit public JSON endpoint kullanır — PRAW / API key gerektirmez.
    Rate limit: dakikada ~60 istek (IP bazlı).
    """
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    try:
        res = requests.get(url, headers=_HEADERS, timeout=8)
        res.raise_for_status()
        children = res.json()["data"]["children"]
    except Exception as e:
        logger.warning(f"[JSON] r/{subreddit} isteği başarısız: {e}")
        return []

    collected = []
    for p in children:
        d = p["data"]
        if d.get("stickied"):
            continue
        score = d.get("score", 0)
        upvote_ratio = d.get("upvote_ratio", 0.0)
        if score < min_score or upvote_ratio < min_upvote_ratio:
            continue
        title_l = d.get("title", "").lower()
        text_l  = d.get("selftext", "").lower()
        if not any(kw in title_l or kw in text_l for kw in keywords):
            continue
        collected.append({
            "id":           d["id"],
            "subreddit":    subreddit,
            "title":        d["title"],
            "score":        score,
            "upvote_ratio": upvote_ratio,
            "text":         d.get("selftext", "")[:1000],
            "url":          f"https://reddit.com{d['permalink']}",
            "top_comments": []
        })

    logger.info(f"[JSON] r/{subreddit} → {len(collected)} eşleşen post")
    return collected


# --- PRAW Singleton (opsiyonel, credentials varsa kullanılır) ---

_reddit_instance = None

def get_reddit_instance():
    global _reddit_instance
    if _reddit_instance is not None:
        return _reddit_instance

    client_id     = os.getenv("PRAW_CLIENT_ID")
    client_secret = os.getenv("PRAW_CLIENT_SECRET")
    user_agent    = os.getenv("PRAW_USER_AGENT", "reddit-miner/1.0")

    if not client_id or not client_secret:
        return None

    try:
        import praw
        _reddit_instance = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            ratelimit_seconds=300
        )
        logger.info("✅ PRAW instance hazır (authenticated).")
        return _reddit_instance
    except Exception as e:
        logger.error(f"PRAW bağlantı hatası: {e}")
        return None


def reddit_search_posts(
    subreddit:        str,
    keywords:         List[str] = None,
    limit:            int = 50,
    min_score:        int = 10,
    min_comments:     int = 5,
    min_upvote_ratio: float = 0.70
) -> ToolResult:
    """
    Önce Reddit public JSON (API key yok) dener.
    PRAW credentials varsa onlara düşer, yoksa mock data döner.
    """
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    # --- Yol 1: Public JSON API (API key gerektirmez) ---
    items = _scrape_reddit_json(subreddit, limit=limit, keywords=keywords,
                                min_score=min_score, min_upvote_ratio=min_upvote_ratio)
    if items:
        return ToolResult(
            success=True,
            source=f"Reddit/r/{subreddit} (JSON)",
            items=items,
            had_errors=False,
            provenance={"subreddit": subreddit, "method": "json", "count": len(items)}
        )

    # --- Yol 2: PRAW (credentials .env'de tanımlıysa) ---
    reddit = get_reddit_instance()
    if reddit:
        collected = []
        try:
            for post in reddit.subreddit(subreddit).hot(limit=limit):
                if post.stickied:
                    continue
                title_l = post.title.lower()
                text_l  = post.selftext.lower() if post.selftext else ""
                if (any(kw in title_l or kw in text_l for kw in keywords) and
                    post.score >= min_score and
                    post.num_comments >= min_comments and
                    post.upvote_ratio >= min_upvote_ratio):
                    collected.append({
                        "id":           post.id,
                        "title":        post.title,
                        "score":        post.score,
                        "upvote_ratio": post.upvote_ratio,
                        "subreddit":    subreddit,
                        "text":         post.selftext[:1000] if post.selftext else "",
                        "url":          f"https://reddit.com{post.permalink}",
                        "top_comments": []
                    })
            if collected:
                return ToolResult(success=True, source=f"Reddit/r/{subreddit} (PRAW)",
                                  items=collected, had_errors=False,
                                  provenance={"subreddit": subreddit, "method": "praw"})
        except Exception as e:
            logger.error(f"[PRAW] r/{subreddit}: {e}")

    # --- Yol 3: Mock fallback ---
    logger.warning(f"[MOCK] r/{subreddit} — JSON ve PRAW başarısız, mock kullanılıyor.")
    return ToolResult(
        success=True,
        source=f"Reddit/r/{subreddit} (Mock)",
        items=[{
            "id": "mock_1",
            "title": f"I wish there was an app for managing invoices in r/{subreddit}",
            "score": 150, "upvote_ratio": 0.95, "subreddit": subreddit,
            "text": "Struggle with managing invoices every month.",
            "url": f"https://reddit.com/r/{subreddit}/mock_1",
            "top_comments": ["Same here, I'd pay for this", "Need this!"]
        }],
        had_errors=False,
        provenance={"subreddit": subreddit, "mocked": True}
    )


def reddit_fetch_comments(post_id: str, max_comments: int = 5) -> List[str]:
    """PRAW varsa yorumları çeker, yoksa boş liste döner."""
    reddit = get_reddit_instance()
    if not reddit:
        return []
    try:
        submission = reddit.submission(id=post_id)
        submission.comments.replace_more(limit=0)
        return [
            c.body for c in submission.comments[:max_comments]
            if c.body and c.body != "[deleted]"
        ]
    except Exception as e:
        logger.error(f"[TOOL] Yorum hatası ({post_id}): {e}")
        return []
