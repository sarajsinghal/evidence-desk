from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import requests


class ProviderError(RuntimeError):
    def __init__(self, provider: str, message: str, status_code: int | None = None):
        super().__init__(message)
        self.provider, self.status_code = provider, status_code


@dataclass
class SearchHit:
    provider: str
    url: str
    title: str
    snippet: str
    published_date: str | None = None
    raw_content: str | None = None
    score: float | None = None


def _post(provider: str, url: str, headers: dict[str, str], payload: dict[str, Any], timeout: int, retries: int) -> dict[str, Any]:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < retries:
                    import time
                    time.sleep(min(2 ** attempt, 4))
                    continue
            if not response.ok:
                detail = response.text[:300].replace("\n", " ")
                raise ProviderError(provider, f"HTTP {response.status_code}: {detail}", response.status_code)
            return response.json()
        except ProviderError:
            raise
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt < retries:
                import time
                time.sleep(min(2 ** attempt, 4))
    raise ProviderError(provider, f"Request failed after {retries + 1} attempt(s): {last}")


def parallel_search(api_key: str, question: str, limit: int = 8, timeout: int = 25, retries: int = 2) -> list[SearchHit]:
    data = _post("Parallel", "https://api.parallel.ai/v1/search", {
        "x-api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"
    }, {"objective": question, "search_queries": [question], "advanced_settings": {"max_results": limit}}, timeout, retries)
    hits = []
    for item in data.get("results", [])[:limit]:
        excerpts = item.get("excerpts") or []
        hits.append(SearchHit("Parallel", item.get("url", ""), item.get("title", "Untitled"),
                              "\n\n".join(str(x) for x in excerpts), item.get("publish_date")))
    return hits


def tavily_search(api_key: str, question: str, limit: int = 8, depth: str = "basic", timeout: int = 25, retries: int = 2) -> list[SearchHit]:
    data = _post("Tavily", "https://api.tavily.com/search", {
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"
    }, {"query": question, "search_depth": depth, "max_results": limit,
        "include_answer": False, "include_raw_content": True}, timeout, retries)
    return [SearchHit("Tavily", x.get("url", ""), x.get("title", "Untitled"),
                      x.get("content", ""), x.get("published_date"), x.get("raw_content"), x.get("score"))
            for x in data.get("results", [])[:limit]]


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_") and k.lower() not in {"ref", "fbclid", "gclid"}])
    return urlunsplit((parts.scheme.lower() or "https", host, path, query, ""))
