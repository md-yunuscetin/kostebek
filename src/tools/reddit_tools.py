# src/tools/reddit_tools.py
# Reddit MCP Buddy Server üzerinden veri çeker (http://localhost:3000)

import json
import httpx
from typing import List
from src.tools.contracts import ToolResult
from src.utils.logger import get_logger

logger = get_logger("reddit_tools")

MCP_URL = "http://localhost:3000/mcp"

DEFAULT_KEYWORDS = [
    "wish there was", "app idea", "pain point", "need an app",
    "struggle with", "hate how", "is there an app", "anyone else find",
    "doctors need", "patients struggle", "medical", "clinical",
    "students need", "teachers wish", "education", "learning"
]


def _mcp_call_sync(tool_name: str, arguments: dict) -> dict:
    """Synchronous MCP çağrısı — asyncio gerektirmez."""
    with httpx.Client(timeout=30) as client:
        # 1. Initialize
        init_res = client.post(MCP_URL, json={
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kostebek", "version": "1.0"}
            }
        })
        session_id = init_res.headers.get("mcp-session-id", "")
        headers = {"mcp-session-id": session_id} if session_id else {}

        # 2. Initialized bildirimi
        client.post(MCP_URL, json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }, headers=headers)

        # 3. Tool çağrısı
        res = client.post(MCP_URL, json={
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }, headers=headers)

        return res.json()


def _parse_mcp_posts(result: dict) -> list:
    """MCP response'undan post listesini çıkarır."""
    try:
        content = result.get("result", {}).get("content", [])
        for item in content:
            if item.get("type") == "text":
                data = json.loads(item["text"])
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    for key in ("posts", "data", "children", "results"):
                        if key in data and isinstance(data[key], list):
                            return data[key]
    except Exception as e:
        logger.error(f"[MCP] Parse hatası: {e}")
    return []


def reddit_search_posts(
    subreddit: str,
    keywords: List[str] = None,
    limit: int = 25,
    min_score: int = 5,
    min_comments: int = 2,
    min_upvote_ratio: float = 0.60
) -> ToolResult:
    """MCP Server üzerinden subreddit post'larını çeker."""
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    logger.info(f"[MCP] r/{subreddit} çekiliyor...")

    # MCP tool listesini al (ilk çağrıda hangi tool ismi kullanıldığını öğren)
    try:
        tools_res = _mcp_call_sync("tools/list", {})
        available = [t["name"] for t in tools_res.get("result", {}).get("tools", [])]
        logger.info(f"[MCP] Mevcut tool'lar: {available}")
    except Exception as e:
        logger.error(f"[MCP] Tool listesi alınamadı: {e}")
        available = []

    # Doğru tool adını bul
    post_tool = None
    for candidate in ["get_subreddit_posts", "getSubredditPosts", "search_posts",
                       "reddit_posts", "get_posts", "hot_posts"]:
        if candidate in available:
            post_tool = candidate
            break

    if not post_tool and available:
        post_tool = available[0]  # İlk mevcut tool'u dene

    raw_posts = []
    if post_tool:
        try:
            result = _mcp_call_sync(post_tool, {
                "subreddit": subreddit,
                "limit": limit,
                "sort": "hot"
            })
            raw_posts = _parse_mcp_posts(result)
            logger.info(f"[MCP] r/{subreddit} → {len(raw_posts)} ham post")
        except Exception as e:
            logger.error(f"[MCP] r/{subreddit} tool çağrısı başarısız: {e}")
    else:
        logger.warning(f"[MCP] Hiç tool bulunamadı!")

    # Filtrele
    collected = []
    for p in raw_posts:
        score = p.get("score", 0)
        upvote_ratio = p.get("upvote_ratio", 0.0)
        num_comments = p.get("num_comments", 0)
        if score < min_score or upvote_ratio < min_upvote_ratio:
            continue
        if num_comments < min_comments:
            continue
        title_l = p.get("title", "").lower()
        text_l = p.get("selftext", p.get("text", p.get("body", ""))).lower()
        if not any(kw.lower() in title_l or kw.lower() in text_l for kw in keywords):
            continue
        collected.append({
            "id": p.get("id", ""),
            "subreddit": subreddit,
            "title": p.get("title", ""),
            "score": score,
            "upvote_ratio": upvote_ratio,
            "text": text_l[:1000],
            "url": p.get("url", p.get("permalink", f"https://reddit.com/r/{subreddit}")),
            "top_comments": p.get("comments", [])
        })

    if collected:
        logger.info(f"[MCP] r/{subreddit} → {len(collected)} geçerli post ✅")
        return ToolResult(
            success=True,
            source=f"Reddit/r/{subreddit} (MCP)",
            items=collected,
            had_errors=False,
            provenance={"subreddit": subreddit, "method": "mcp"}
        )

    logger.warning(f"[MCP] r/{subreddit} boş → JSON fallback")
    return _fallback_json(subreddit, keywords, limit, min_score, min_upvote_ratio)


def _fallback_json(subreddit, keywords, limit, min_score, min_upvote_ratio) -> ToolResult:
    """MCP çalışmazsa Public JSON API kullanır."""
    import requests
    headers = {"User-Agent": "Mozilla/5.0 kostebek/1.0"}
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    try:
        res = requests.get(url, headers=headers, timeout=8)
        res.raise_for_status()
        children = res.json()["data"]["children"]
    except Exception as e:
        logger.error(f"[JSON] r/{subreddit}: {e}")
        return ToolResult(success=False, source=f"Reddit/r/{subreddit}", items=[], had_errors=True)

    collected = []
    for p in children:
        d = p["data"]
        if d.get("stickied"):
            continue
        score = d.get("score", 0)
        if score < min_score:
            continue
        title_l = d.get("title", "").lower()
        text_l = d.get("selftext", "").lower()
        if not any(kw.lower() in title_l or kw.lower() in text_l for kw in keywords):
            continue
        collected.append({
            "id": d["id"], "subreddit": subreddit,
            "title": d["title"], "score": score,
            "upvote_ratio": d.get("upvote_ratio", 0.0),
            "text": d.get("selftext", "")[:1000],
            "url": f"https://reddit.com{d['permalink']}",
            "top_comments": []
        })

    logger.info(f"[JSON Fallback] r/{subreddit} → {len(collected)} post")
    return ToolResult(
        success=len(collected) > 0,
        source=f"Reddit/r/{subreddit} (JSON)",
        items=collected,
        had_errors=False,
        provenance={"subreddit": subreddit, "method": "json_fallback"}
    )


def reddit_fetch_comments(post_id: str, max_comments: int = 5) -> List[str]:
    """MCP üzerinden post yorumlarını çeker."""
    try:
        result = _mcp_call_sync("get_post_comments", {
            "post_id": post_id,
            "limit": max_comments
        })
        content = result.get("result", {}).get("content", [])
        for item in content:
            if item.get("type") == "text":
                data = json.loads(item["text"])
                if isinstance(data, list):
                    return [c.get("body", "") for c in data if c.get("body")]
    except Exception as e:
        logger.error(f"[MCP] Yorum hatası ({post_id}): {e}")
    return []
