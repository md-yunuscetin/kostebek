# src/tools/reddit_tools.py

import asyncio
import json
import os
import shutil
import threading
from typing import Any, Dict, List, Optional

from src.tools.contracts import ToolResult
from src.utils.logger import get_logger

logger = get_logger("reddit_tools")

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError as e:
    raise RuntimeError(
        "mcp paketi kurulu değil. Önce şunu çalıştır: pip install mcp"
    ) from e


DEFAULT_KEYWORDS = [
    "wish there was", "app idea", "pain point", "need an app",
    "struggle with", "hate how", "is there an app", "anyone else find",
    "doctors need", "patients struggle", "medical", "clinical",
    "students need", "teachers wish", "education", "learning"
]


def _server_command():
    if os.name == "nt":
        cmd = shutil.which("cmd.exe") or os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "cmd.exe",
        )
        args = ["/d", "/s", "/c", "npx", "-y", "reddit-mcp-buddy"]
        return cmd, args

    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx bulunamadı. Node.js/npm PATH içinde olmalı.")
    return npx, ["-y", "reddit-mcp-buddy"]


def _to_plain(obj: Any) -> Any:
    if obj is None:
        return None

    if hasattr(obj, "model_dump"):
        try:
            return _to_plain(obj.model_dump())
        except Exception:
            pass

    if isinstance(obj, dict):
        return {k: _to_plain(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_to_plain(x) for x in obj]

    if hasattr(obj, "__dict__"):
        try:
            return _to_plain(vars(obj))
        except Exception:
            pass

    return obj


class _MCPBridge:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._session: Optional[ClientSession] = None
        self._ready = threading.Event()
        self._start_error: Optional[Exception] = None
        self._stop_event = None
        self._lock = threading.RLock()

    async def _runner(self):
        cmd, args = _server_command()
        logger.info(f"[MCP] stdio süreci başlatılıyor: {cmd} {' '.join(args)}")

        server_params = StdioServerParameters(
            command=cmd,
            args=args,
            env=os.environ.copy(),
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._loop = asyncio.get_running_loop()
                self._session = session
                self._stop_event = asyncio.Event()
                logger.info("[MCP] stdio initialize tamam ✅")
                self._ready.set()
                await self._stop_event.wait()

    def _thread_main(self):
        try:
            asyncio.run(self._runner())
        except Exception as e:
            self._start_error = e
            self._ready.set()
            logger.error(f"[MCP] bridge hata: {e}")
        finally:
            self._session = None
            self._loop = None
            self._stop_event = None

    def ensure_started(self):
        with self._lock:
            if self._session is not None and self._loop is not None:
                return

            self._ready = threading.Event()
            self._start_error = None
            self._thread = threading.Thread(target=self._thread_main, daemon=True)
            self._thread.start()

        if not self._ready.wait(timeout=60):
            raise TimeoutError("MCP başlatma zaman aşımı")

        if self._start_error is not None:
            raise RuntimeError(f"MCP başlatılamadı: {self._start_error}")

        if self._session is None or self._loop is None:
            raise RuntimeError("MCP session oluşturulamadı")

    def _run(self, coro_factory, timeout=120):
        self.ensure_started()
        if self._session is None or self._loop is None:
            raise RuntimeError("MCP session hazır değil")
        future = asyncio.run_coroutine_threadsafe(
            coro_factory(self._session),
            self._loop
        )
        return future.result(timeout=timeout)

    def list_tools(self):
        return self._run(lambda session: session.list_tools(), timeout=60)

    def call_tool(self, name: str, arguments: Dict[str, Any]):
        return self._run(
            lambda session: session.call_tool(name, arguments=arguments),
            timeout=180
        )


_MCP = _MCPBridge()
_TOOLS_CACHE: Optional[List[Dict[str, Any]]] = None


def _get_tools() -> List[Dict[str, Any]]:
    global _TOOLS_CACHE

    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE

    resp = _MCP.list_tools()
    plain = _to_plain(resp)

    tools = plain.get("tools", []) if isinstance(plain, dict) else []
    if not isinstance(tools, list):
        tools = []

    _TOOLS_CACHE = tools
    logger.info(f"[MCP] Tool'lar: {[t.get('name') for t in tools if isinstance(t, dict)]}")
    return tools


def _get_tool(name: str) -> Optional[Dict[str, Any]]:
    for tool in _get_tools():
        if isinstance(tool, dict) and tool.get("name") == name:
            return tool
    return None


def _tool_properties(tool: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not tool:
        return {}
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    props = schema.get("properties", {})
    return props if isinstance(props, dict) else {}


def _pick_key(props: Dict[str, Any], candidates: List[str]) -> Optional[str]:
    for key in candidates:
        if key in props:
            return key
    return None


def _build_args(tool: Optional[Dict[str, Any]], values: List[tuple]) -> Dict[str, Any]:
    props = _tool_properties(tool)
    args: Dict[str, Any] = {}

    for candidate_keys, value in values:
        if value is None:
            continue
        key = _pick_key(props, candidate_keys)
        if key:
            args[key] = value

    if not args:
        for candidate_keys, value in values:
            if value is None:
                continue
            args[candidate_keys[0]] = value

    return args


def _tool_call(name: str, arguments: Dict[str, Any]) -> Any:
    logger.info(f"[MCP] tools/call → {name} | args={arguments}")
    resp = _MCP.call_tool(name, arguments)
    return _to_plain(resp)


def _try_json(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return v
    return v


def _extract_tool_payload(response: Any) -> Any:
    if not isinstance(response, dict):
        return response

    if "structuredContent" in response:
        return response["structuredContent"]

    result = response.get("result", response)

    if isinstance(result, dict):
        if "structuredContent" in result and result["structuredContent"] is not None:
            return result["structuredContent"]

        content = result.get("content")
        if isinstance(content, list):
            parsed = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parsed.append(_try_json(item.get("text", "")))
                else:
                    parsed.append(item)
            if len(parsed) == 1:
                return parsed[0]
            return parsed

    return result


def _collect_posts(obj: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    if isinstance(obj, list):
        for item in obj:
            out.extend(_collect_posts(item))
        return out

    if isinstance(obj, dict):
        if any(k in obj for k in ("title", "selftext", "permalink", "num_comments", "score", "url")):
            out.append(obj)
            return out

        for key in ("posts", "items", "results", "children", "data"):
            if key in obj:
                out.extend(_collect_posts(obj[key]))
        return out

    return out


def _normalize_post(p: Dict[str, Any], subreddit: str) -> Dict[str, Any]:
    score = p.get("score", 0) or 0
    num_comments = p.get("num_comments", p.get("comments_count", 0)) or 0
    upvote_ratio = p.get("upvote_ratio", 0.0)
    title = p.get("title", "") or ""
    text = p.get("selftext", p.get("text", p.get("body", ""))) or ""
    post_id = p.get("id", p.get("post_id", "")) or ""
    permalink = p.get("permalink", "") or ""
    url = p.get("url_overridden_by_dest", p.get("url", "")) or ""

    if permalink and not str(permalink).startswith("http"):
        permalink = f"https://reddit.com{permalink}"

    final_url = permalink or url or f"https://reddit.com/r/{subreddit}"

    comments = p.get("comments", p.get("top_comments", []))
    if not isinstance(comments, list):
        comments = []

    try:
        score = int(score)
    except Exception:
        score = 0

    try:
        num_comments = int(num_comments)
    except Exception:
        num_comments = 0

    try:
        upvote_ratio = float(upvote_ratio)
    except Exception:
        upvote_ratio = 0.0

    return {
        "id": str(post_id),
        "subreddit": subreddit,
        "title": str(title),
        "score": score,
        "upvote_ratio": upvote_ratio,
        "text": str(text)[:1000],
        "url": str(final_url),
        "num_comments": num_comments,
        "top_comments": comments[:5] if comments else [],
    }


def _keyword_match(text: str, keywords: List[str]) -> bool:
    if not keywords:
        return True
    hay = (text or "").lower()
    return any(kw.lower() in hay for kw in keywords)


def reddit_search_posts(
    subreddit: str,
    keywords: List[str] = None,
    limit: int = 25,
    min_score: int = 5,
    min_comments: int = 2,
    min_upvote_ratio: float = 0.60
) -> ToolResult:
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    logger.info(f"[MCP] r/{subreddit} çekiliyor...")

    try:
        tool = _get_tool("browse_subreddit")
        if not tool:
            raise RuntimeError("browse_subreddit tool'u bulunamadı")

        args = _build_args(tool, [
            (["subreddit", "subreddit_name", "name"], subreddit),
            (["limit", "count", "page_size"], limit),
            (["sort", "sorting"], "hot"),
        ])

        response = _tool_call("browse_subreddit", args)
        payload = _extract_tool_payload(response)
        raw_posts = _collect_posts(payload)

        logger.info(f"[MCP] r/{subreddit} → {len(raw_posts)} ham post")

        filtered_engagement: List[Dict[str, Any]] = []
        filtered_keyword: List[Dict[str, Any]] = []

        for raw in raw_posts:
            post = _normalize_post(raw, subreddit)

            if post["score"] < min_score:
                continue
            if post["num_comments"] < min_comments:
                continue
            if post["upvote_ratio"] and post["upvote_ratio"] < min_upvote_ratio:
                continue

            filtered_engagement.append(post)

            combined = f"{post['title']} {post['text']}"
            if _keyword_match(combined, keywords):
                filtered_keyword.append(post)

        collected = filtered_keyword if filtered_keyword else filtered_engagement

        logger.info(
            f"[MCP] r/{subreddit} → {len(collected)} post "
            f"(keyword={len(filtered_keyword)}, engagement={len(filtered_engagement)})"
        )

        return ToolResult(
            success=len(collected) > 0,
            source=f"Reddit/r/{subreddit} (MCP)",
            items=collected,
            had_errors=False,
            provenance={
                "subreddit": subreddit,
                "method": "mcp_sdk_stdio",
                "tool": "browse_subreddit",
            }
        )

    except Exception as e:
        logger.error(f"[MCP] r/{subreddit} hata: {e}")
        return ToolResult(
            success=False,
            source=f"Reddit/r/{subreddit} (MCP)",
            items=[],
            had_errors=True,
            provenance={
                "subreddit": subreddit,
                "method": "mcp_sdk_stdio",
                "error": str(e),
            }
        )


def _collect_comments(obj: Any, limit: int) -> List[str]:
    out: List[str] = []

    if isinstance(obj, dict):
        for key in ("comments", "top_comments", "data", "items", "results"):
            if key in obj:
                out.extend(_collect_comments(obj[key], limit))
                if len(out) >= limit:
                    return out[:limit]

        body = obj.get("body", obj.get("text", obj.get("content")))
        if isinstance(body, str) and body.strip():
            out.append(body.strip())
            return out[:limit]

    elif isinstance(obj, list):
        for item in obj:
            out.extend(_collect_comments(item, limit))
            if len(out) >= limit:
                return out[:limit]

    return out[:limit]


def reddit_fetch_comments(
    post_id: str,
    max_comments: int = 5,
    subreddit: Optional[str] = None,
    post_url: Optional[str] = None
) -> List[str]:
    try:
        tool = _get_tool("get_post_details")
        if not tool:
            raise RuntimeError("get_post_details tool'u bulunamadı")

        args = _build_args(tool, [
            (["url", "post_url", "link"], post_url),
            (["post_id", "id"], post_id),
            (["subreddit", "subreddit_name"], subreddit),
            (["limit", "comment_limit", "max_comments"], max_comments),
        ])

        response = _tool_call("get_post_details", args)
        payload = _extract_tool_payload(response)
        comments = _collect_comments(payload, max_comments)

        logger.info(f"[MCP] Yorumlar ({post_id}) → {len(comments)} adet")
        return comments

    except Exception as e:
        logger.error(f"[MCP] Yorum hatası ({post_id}): {e}")
        return []
