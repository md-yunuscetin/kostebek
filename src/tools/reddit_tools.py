# src/tools/reddit_tools.py

import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional

from src.tools.contracts import ToolResult
from src.utils.logger import get_logger

logger = get_logger("reddit_tools")

DEFAULT_KEYWORDS = [
    "wish there was", "app idea", "pain point", "need an app",
    "struggle with", "hate how", "is there an app", "anyone else find",
    "doctors need", "patients struggle", "medical", "clinical",
    "students need", "teachers wish", "education", "learning"
]

_MCP_PROC: Optional[subprocess.Popen] = None
_MCP_LOCK = threading.RLock()
_MCP_ID = 0
_MCP_INITIALIZED = False
_MCP_STDERR_TAIL: List[str] = []
_TOOLS_CACHE: Optional[List[Dict[str, Any]]] = None

if os.name == "nt":
    import msvcrt
    import _winapi


def _next_id() -> int:
    global _MCP_ID
    _MCP_ID += 1
    return _MCP_ID


def _spawn_command() -> List[str]:
    if os.name == "nt":
        cmd = shutil.which("cmd.exe") or os.path.join(
            os.environ.get("SystemRoot", r"C:\Windows"),
            "System32",
            "cmd.exe"
        )
        return [cmd, "/d", "/s", "/c", "npx", "-y", "reddit-mcp-buddy"]

    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx bulunamadı. Node.js / npm kurulu ve PATH içinde olmalı.")
    return [npx, "-y", "reddit-mcp-buddy"]


def _stderr_drain_worker(proc: subprocess.Popen) -> None:
    global _MCP_STDERR_TAIL
    if not proc.stderr:
        return

    while True:
        try:
            line = proc.stderr.readline()
        except Exception:
            break

        if not line:
            break

        if isinstance(line, bytes):
            text = line.decode("utf-8", "replace").strip()
        else:
            text = str(line).strip()

        if text:
            _MCP_STDERR_TAIL.append(text)
            if len(_MCP_STDERR_TAIL) > 200:
                _MCP_STDERR_TAIL = _MCP_STDERR_TAIL[-200:]
            logger.warning(f"[MCP STDERR] {text}")


def _start_mcp_proc() -> subprocess.Popen:
    global _MCP_PROC, _MCP_INITIALIZED, _TOOLS_CACHE

    if _MCP_PROC is not None and _MCP_PROC.poll() is None:
        return _MCP_PROC

    cmd = _spawn_command()
    logger.info(f"[MCP] stdio süreci başlatılıyor: {' '.join(cmd)}")

    _MCP_PROC = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    threading.Thread(
        target=_stderr_drain_worker,
        args=(_MCP_PROC,),
        daemon=True
    ).start()

    _MCP_INITIALIZED = False
    _TOOLS_CACHE = None
    return _MCP_PROC


def _stdout_available(proc: subprocess.Popen) -> int:
    if not proc.stdout:
        return 0

    if os.name == "nt":
        try:
            handle = msvcrt.get_osfhandle(proc.stdout.fileno())
            return _winapi.PeekNamedPipe(handle)[0]
        except Exception:
            return 0

    try:
        import select
        r, _, _ = select.select([proc.stdout], [], [], 0)
        return 1 if r else 0
    except Exception:
        return 0


def _stdout_read_some(proc: subprocess.Popen, size: int) -> bytes:
    if not proc.stdout:
        return b""

    if os.name == "nt":
        handle = msvcrt.get_osfhandle(proc.stdout.fileno())
        try:
            return _winapi.ReadFile(handle, max(1, size))[0]
        except Exception:
            return b""

    try:
        return proc.stdout.read(size)
    except Exception:
        return b""


def _readline_bytes(proc: subprocess.Popen, timeout_sec: float) -> bytes:
    deadline = time.time() + timeout_sec
    buf = bytearray()

    while time.time() < deadline:
        if proc.poll() is not None:
            tail = " | ".join(_MCP_STDERR_TAIL[-20:])
            raise RuntimeError(f"MCP süreci kapandı. exit={proc.returncode} stderr={tail}")

        available = _stdout_available(proc)
        if available <= 0:
            time.sleep(0.02)
            continue

        chunk = _stdout_read_some(proc, 1)
        if not chunk:
            time.sleep(0.02)
            continue

        buf.extend(chunk)
        if chunk == b"\n":
            return bytes(buf)

    tail = " | ".join(_MCP_STDERR_TAIL[-20:])
    raise TimeoutError(f"MCP satır okuma zaman aşımı. stderr={tail}")


def _read_exact(proc: subprocess.Popen, size: int, timeout_sec: float) -> bytes:
    deadline = time.time() + timeout_sec
    buf = bytearray()

    while len(buf) < size and time.time() < deadline:
        if proc.poll() is not None:
            tail = " | ".join(_MCP_STDERR_TAIL[-20:])
            raise RuntimeError(f"MCP süreci kapandı. exit={proc.returncode} stderr={tail}")

        available = _stdout_available(proc)
        if available <= 0:
            time.sleep(0.02)
            continue

        need = min(max(1, available), size - len(buf))
        chunk = _stdout_read_some(proc, need)
        if not chunk:
            time.sleep(0.02)
            continue

        buf.extend(chunk)

    if len(buf) != size:
        tail = " | ".join(_MCP_STDERR_TAIL[-20:])
        raise TimeoutError(
            f"MCP body zaman aşımı. expected={size} got={len(buf)} stderr={tail}"
        )

    return bytes(buf)


def _mcp_send(proc: subprocess.Popen, payload: Dict[str, Any]) -> None:
    if not proc.stdin:
        raise RuntimeError("MCP stdin kullanılamıyor")

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = (
        f"Content-Length: {len(body)}\r\n"
        f"Content-Type: application/json\r\n"
        f"\r\n"
    ).encode("ascii")

    proc.stdin.write(header + body)
    proc.stdin.flush()


def _mcp_recv(proc: subprocess.Popen, timeout_sec: float = 20.0) -> Dict[str, Any]:
    headers: Dict[str, str] = {}

    while True:
        line = _readline_bytes(proc, timeout_sec)
        if line in (b"\n", b"\r\n"):
            break

        text = line.decode("ascii", "replace").strip()
        if ":" in text:
            k, v = text.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    content_length = int(headers.get("content-length", "0"))
    if content_length <= 0:
        raise RuntimeError(f"Geçersiz MCP header: {headers}")

    body = _read_exact(proc, content_length, timeout_sec)

    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception as e:
        raise RuntimeError(f"MCP JSON parse hatası: {e}")


def _ensure_initialized() -> subprocess.Popen:
    global _MCP_INITIALIZED

    proc = _start_mcp_proc()
    if _MCP_INITIALIZED:
        return proc

    init_id = _next_id()
    _mcp_send(proc, {
        "jsonrpc": "2.0",
        "id": init_id,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "kostebek", "version": "1.0"}
        }
    })

    while True:
        msg = _mcp_recv(proc, timeout_sec=30.0)

        if msg.get("method", "").startswith("notifications/"):
            continue

        if msg.get("id") == init_id:
            if "error" in msg:
                raise RuntimeError(f"initialize hatası: {msg['error']}")
            break

    _mcp_send(proc, {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    })

    _MCP_INITIALIZED = True
    logger.info("[MCP] stdio initialize tamam ✅")
    return proc


def _mcp_request(method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    with _MCP_LOCK:
        proc = _ensure_initialized()
        req_id = _next_id()

        _mcp_send(proc, {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {}
        })

        while True:
            msg = _mcp_recv(proc, timeout_sec=30.0)

            if msg.get("method", "").startswith("notifications/"):
                continue

            if msg.get("id") != req_id:
                continue

            if "error" in msg:
                raise RuntimeError(f"MCP {method} hatası: {msg['error']}")

            return msg


def _get_tools() -> List[Dict[str, Any]]:
    global _TOOLS_CACHE

    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE

    res = _mcp_request("tools/list", {})
    tools = res.get("result", {}).get("tools", []) or []
    _TOOLS_CACHE = tools

    names = [t.get("name", "?") for t in tools]
    logger.info(f"[MCP] Tool'lar: {names}")
    return tools


def _get_tool(name: str) -> Optional[Dict[str, Any]]:
    for tool in _get_tools():
        if tool.get("name") == name:
            return tool
    return None


def _tool_properties(tool: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not tool:
        return {}
    schema = tool.get("inputSchema") or tool.get("input_schema") or {}
    return schema.get("properties", {}) or {}


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


def _tool_call(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    logger.info(f"[MCP] tools/call → {name} | args={arguments}")
    return _mcp_request("tools/call", {
        "name": name,
        "arguments": arguments
    })


def _try_json(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_tool_payload(response: Dict[str, Any]) -> Any:
    result = response.get("result", {}) or {}

    if "structuredContent" in result and result["structuredContent"] is not None:
        return result["structuredContent"]

    content = result.get("content", []) or []
    parsed: List[Any] = []

    for item in content:
        if not isinstance(item, dict):
            continue

        if item.get("type") == "text":
            parsed.append(_try_json(item.get("text", "")))
        elif "data" in item:
            parsed.append(item["data"])
        else:
            parsed.append(item)

    if len(parsed) == 1:
        return parsed[0]
    return parsed


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
                "method": "mcp_stdio",
                "tool": "browse_subreddit"
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
                "method": "mcp_stdio",
                "error": str(e)
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
