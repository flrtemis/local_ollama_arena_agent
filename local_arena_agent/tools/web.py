from __future__ import annotations

import base64
import html
import json
import mimetypes
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from .base import Tool, ToolRegistry
from ..workspace import Workspace


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0
        self.links: list[tuple[str, str]] = []
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_d = {k.lower(): v for k, v in attrs if k}
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if tag in {"p", "div", "section", "article", "header", "footer", "br", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")
        if tag == "a":
            self._link_href = attrs_d.get("href")
            self._link_text = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"} and self.skip:
            self.skip -= 1
        if tag == "a" and self._link_href:
            text = " ".join("".join(self._link_text).split())
            if text:
                self.links.append((text, self._link_href))
            self._link_href = None
            self._link_text = []
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        if self._link_href is not None:
            self._link_text.append(data)
        self.parts.append(data)

    def text(self) -> str:
        raw = html.unescape("".join(self.parts))
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n\s*\n+", "\n\n", raw)
        return raw.strip()


def fetch_url(url: str, timeout: int, max_bytes: int) -> tuple[bytes, str, str]:
    req = Request(url, headers={"User-Agent": "LocalArenaOllamaAgent/0.1 (+localhost)"})
    with urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        final_url = resp.geturl()
        data = resp.read(max_bytes + 1)
    return data[:max_bytes], content_type, final_url


def register_web_tools(reg: ToolRegistry, ws: Workspace, config: dict[str, Any]) -> None:
    web_cfg = config.get("web", {})
    timeout = int(web_cfg.get("timeout_seconds", 15))
    max_bytes = int(web_cfg.get("max_bytes", 2_000_000))
    searxng_url = str(web_cfg.get("searxng_url", "")).rstrip("/")

    def fetch_page(args: dict[str, Any]) -> dict[str, Any]:
        url = str(args.get("url", ""))
        if not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "Only http:// and https:// URLs are supported."}
        start = time.time()
        try:
            data, content_type, final_url = fetch_url(url, timeout, max_bytes)
            if "text/html" in content_type.lower() or final_url.lower().endswith((".html", "/")):
                parser = TextExtractor()
                parser.feed(data.decode("utf-8", errors="replace"))
                links = [(text, urljoin(final_url, href)) for text, href in parser.links[:100]]
                return {
                    "ok": True,
                    "url": url,
                    "final_url": final_url,
                    "content_type": content_type,
                    "seconds": round(time.time() - start, 3),
                    "text": parser.text()[: int(args.get("max_chars", 50000))],
                    "links": [{"text": t, "url": u} for t, u in links],
                    "truncated": len(data) > max_bytes,
                }
            text_like = content_type.startswith("text/") or any(final_url.lower().endswith(ext) for ext in [".txt", ".md", ".json", ".csv", ".xml"])
            if text_like:
                return {
                    "ok": True,
                    "url": url,
                    "final_url": final_url,
                    "content_type": content_type,
                    "seconds": round(time.time() - start, 3),
                    "text": data.decode("utf-8", errors="replace")[: int(args.get("max_chars", 50000))],
                    "truncated": len(data) > max_bytes,
                }
            return {
                "ok": True,
                "url": url,
                "final_url": final_url,
                "content_type": content_type,
                "seconds": round(time.time() - start, 3),
                "base64": base64.b64encode(data).decode("ascii"),
                "truncated": len(data) > max_bytes,
            }
        except Exception as e:
            return {"ok": False, "url": url, "error": repr(e)}

    def web_search(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", ""))
        limit = min(max(int(args.get("limit", 5)), 1), 10)
        if not query.strip():
            return {"ok": False, "error": "query is empty"}
        try:
            if searxng_url:
                url = searxng_url + "/search?" + urlencode({"q": query, "format": "json", "language": "en"})
                data, _, _ = fetch_url(url, timeout, max_bytes)
                parsed = json.loads(data.decode("utf-8", errors="replace"))
                results = []
                for r in parsed.get("results", [])[:limit]:
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", "") or r.get("snippet", ""),
                    })
                return {"ok": True, "backend": "searxng", "query": query, "results": results}

            # No API key fallback: DuckDuckGo HTML. This is best-effort and may break.
            url = "https://duckduckgo.com/html/?" + urlencode({"q": query})
            data, _, final_url = fetch_url(url, timeout, max_bytes)
            page = data.decode("utf-8", errors="replace")
            results = []
            # DuckDuckGo result anchors often use class result__a.
            for m in re.finditer(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, flags=re.I | re.S):
                href = html.unescape(m.group(1))
                title = re.sub(r"<.*?>", "", m.group(2), flags=re.S)
                title = html.unescape(" ".join(title.split()))
                if href.startswith("//duckduckgo.com/l/?"):
                    # leave redirect URL; it still opens in browser
                    href = "https:" + href
                results.append({"title": title, "url": href, "snippet": ""})
                if len(results) >= limit:
                    break
            return {"ok": True, "backend": "duckduckgo-html", "query": query, "results": results, "note": "Fallback HTML search is best-effort. Configure SearXNG for reliability."}
        except Exception as e:
            return {"ok": False, "query": query, "error": repr(e), "hint": "Configure web.searxng_url for reliable local/metasearch."}

    def image_search(args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query", ""))
        count = min(max(int(args.get("count", 3)), 1), 5)
        if not query.strip():
            return {"ok": False, "error": "query is empty"}
        if not searxng_url:
            return {"ok": False, "error": "image_search requires a SearXNG URL in config.json under web.searxng_url."}
        try:
            url = searxng_url + "/search?" + urlencode({"q": query, "format": "json", "categories": "images", "language": "en"})
            data, _, _ = fetch_url(url, timeout, max_bytes)
            parsed = json.loads(data.decode("utf-8", errors="replace"))
            saved = []
            for i, r in enumerate(parsed.get("results", [])[:count], 1):
                img_url = r.get("img_src") or r.get("thumbnail") or r.get("url")
                if not img_url:
                    continue
                try:
                    img_data, content_type, final_url = fetch_url(img_url, timeout, max_bytes)
                    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) or Path(urlparse(final_url).path).suffix or ".img"
                    out = ws.safe_path(f"image_search/{int(time.time())}_{i}{ext}")
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(img_data)
                    saved.append({"title": r.get("title", ""), "source_url": r.get("url", ""), "image_url": final_url, "file": ws.meta(out)})
                except Exception as e:
                    saved.append({"title": r.get("title", ""), "image_url": img_url, "error": repr(e)})
            return {"ok": True, "backend": "searxng", "query": query, "results": saved}
        except Exception as e:
            return {"ok": False, "query": query, "error": repr(e)}

    reg.add(Tool(
        "fetch_page",
        "Fetch a web page or URL and return cleaned text, links, or base64 for binary content.",
        {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer"}}, "required": ["url"]},
        fetch_page,
        category="web",
    ))
    reg.add(Tool(
        "web_search",
        "Search the web. Uses SearXNG if configured, otherwise a best-effort DuckDuckGo HTML fallback.",
        {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]},
        web_search,
        category="web",
    ))
    reg.add(Tool(
        "image_search",
        "Search for images and save up to 5 images into the workspace. Requires SearXNG configured with image search.",
        {"type": "object", "properties": {"query": {"type": "string"}, "count": {"type": "integer"}}, "required": ["query"]},
        image_search,
        requires_approval=True,
        category="web",
    ))
