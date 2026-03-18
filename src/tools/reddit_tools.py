# src/tools/reddit_tools.py
# MCP Server üzerinden Reddit verisi çeker (API key gerektirmez)
# Çalışması için: npx -y reddit-mcp-buddy --http (ayrı terminalde)

import asyncio
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

# ──────────────────────────────────────────────
# MCP Client — Tek Seferlik Session Yönetimi
# ──────────────────────────────────────────────

async def _mcp_call(tool_name: str, arguments: dict) -> dict:
    """MCP server'a initialize → tool çağrısı yapar."""
    async with httpx.AsyncClient(timeout=30) as client:

        # 1. Session başlat
        init_payload = {
            "jsonrpc": "2.0", "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kostebek", "version": "1.0"}
            }
        }
        init_res = await client.post(MCP_URL, json=init_payload)
        session_id = init_res.headers.get("mcp-session-id", "")

        headers = {"mcp-session-id": session_id} if session_id else {}

        # 2. initialized bildirimi gönder
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        await client.post(MCP_URL, json=notif, headers=headers)

        # 3. Tool çağrısı yap
        tool_payload = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        }
        res = await client.post(MCP_URL, json=tool_payload, headers=headers)
        return res.json()


def _run_mcp(tool_name: str, arguments: dict) -> dict:
    """Async MCP çağrısını sync ortamda çalıştırır."""
    try:
        return asyncio.run(_mcp_call(tool_name, arguments))
    except Exception as e:
        logger.error(f"[MCP] Bağlantı hatası: {e}")
        return {}


# ──────────────────────────────────────────────
# MCP Tool'larını Keşfet (debug için)
# ──────────────────────────────────────────────

def list_mcp_tools() -> list:
    """MCP server'daki mevcut tool'ları listeler."""
    try:
        result = _run_mcp("tools/list", {})
        tools = result.get("result", {}).get("tools", [])
        logger.info(f"[MCP] Mevcut tool'lar: {[t['name'] for t in tools]}")
        return tools
    except Exception as e:
        logger.error(f"[MCP] Tool listesi alınamadı: {e}")
        return []


# ──────────────────────────────────────────────
# Ana Fonksiyonlar
# ──────────────────────────────────────────────

def reddit_search_posts(
    subreddit: str,
    keywords: List[str] = None,
    limit: int = 25,
    min_score: int = 10,
    min_comments: int = 5,
    min_upvote_ratio: float = 0.70
) -> ToolResult:
    """MCP server üzerinden subreddit post'larını çeker."""
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    logger.info(f"[MCP] r/{subreddit} çekiliyor...")

    # MCP tool çağrısı — reddit-mcp-buddy'nin sunduğu tool isimleri
    result = _run_mcp("get_subreddit_posts", {
        "subreddit": subreddit,
        "limit": limit,
        "sort": "hot"
    })

    # MCP'den gelen veriyi parse et
    raw_posts = []
    try:
        content = result.get("result", {}).get("content", [])
        for item in content:
            if item.get("type") == "text":
                import json
                data = json.loads(item["text"])
                if isinstance(data, list):
                    raw_posts = data
                elif isinstance(data, dict) and "posts" in data:
                    raw_posts = data["posts"]
                break
    except Exception as e:
        logger.error(f"[MCP] Parse hatası: {e}")

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
        text_l = p.get("selftext", p.get("text", "")).lower()

        if not any(kw.lower() in title_l or kw.lower() in text_l for kw in keywords):
            continue

        collected.append({
            "id": p.get("id", ""),
            "subreddit": subreddit,
            "title": p.get("title", ""),
            "score": score,
            "upvote_ratio": upvote_ratio,
            "text": text_l[:1000],
            "url": p.get("url", f"https://reddit.com/r/{subreddit}"),
            "top_comments": p.get("comments", [])
        })

    # MCP başarısızsa public JSON fallback
    if not collected:
        logger.warning(f"[MCP] r/{subreddit} boş döndü → Public JSON fallback")
        return _fallback_json(subreddit, keywords, limit, min_score, min_upvote_ratio)

    logger.info(f"[MCP] r/{subreddit} → {len(collected)} geçerli post")
    return ToolResult(
        success=True,
        source=f"Reddit/r/{subreddit} (MCP)",
        items=collected,
        had_errors=False,
        provenance={"subreddit": subreddit, "method": "mcp"}
    )


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
        ratio = d.get("upvote_ratio", 0.0)
        if score < min_score or ratio < min_upvote_ratio:
            continue
        title_l = d.get("title", "").lower()
        text_l = d.get("selftext", "").lower()
        if not any(kw.lower() in title_l or kw.lower() in text_l for kw in keywords):
            continue
        collected.append({
            "id": d["id"], "subreddit": subreddit,
            "title": d["title"], "score": score,
            "upvote_ratio": ratio,
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
    result = _run_mcp("get_post_comments", {
        "post_id": post_id,
        "limit": max_comments
    })
    try:
        content = result.get("result", {}).get("content", [])
        for item in content:
            if item.get("type") == "text":
                import json
                data = json.loads(item["text"])
                if isinstance(data, list):
                    return [c.get("body", "") for c in data if c.get("body")]
    except Exception as e:
        logger.error(f"[MCP] Yorum parse hatası: {e}")
    return []
