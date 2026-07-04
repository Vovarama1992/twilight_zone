from __future__ import annotations

from html.parser import HTMLParser
import json
import re
import base64
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import unescape
from typing import Dict, Iterable, List, Optional, Protocol

from .config import Config


BLOCKED_DOMAINS = {
    "dictionary.cambridge.org",
    "www.merriam-webster.com",
    "merriam-webster.com",
    "smallpdf.com",
    "www.smallpdf.com",
    "tratu.soha.vn",
    "communaute.orange.fr",
}

BLOCKED_TITLE_TERMS = {
    "definition",
    "meaning",
    "dictionary",
    "định nghĩa",
    "từ điển",
}

QUERY_STOPWORDS = {
    "and",
    "or",
    "the",
    "with",
    "for",
    "to",
    "in",
    "of",
    "on",
    "latest",
    "recent",
    "advanced",
    "strong",
    "small",
    "unusual",
    "rigorous",
    "experimental",
    "2026",
}


class SearchProvider(Protocol):
    def search(self, queries: Iterable[str], limit_per_query: int = 3) -> List[Dict[str, str]]:
        ...


SEED_RESULTS = [
    {
        "title": "Research agent memory architectures and personal knowledge graphs",
        "url": "seed://research-agent-memory-architectures",
        "source": "offline-seed",
        "snippet": "A seed candidate for testing bridge-heavy agent strategy without network access.",
    },
    {
        "title": "Homotopy type theory as a practical language for verified systems",
        "url": "seed://hott-practical-verified-systems",
        "source": "offline-seed",
        "snippet": "A seed candidate connecting foundations, PL, and engineering practice.",
    },
    {
        "title": "p-adic intuitions, zero knowledge, and finite field engineering",
        "url": "seed://padic-zk-finite-field-engineering",
        "source": "offline-seed",
        "snippet": "A seed candidate for math-to-cryptography bridges.",
    },
]


@dataclass
class OfflineSearchProvider:
    def search(self, queries: Iterable[str], limit_per_query: int = 3) -> List[Dict[str, str]]:
        return SEED_RESULTS[: max(1, limit_per_query)]


@dataclass
class JsonEndpointSearchProvider:
    endpoint: str
    api_key: str = ""

    def search(self, queries: Iterable[str], limit_per_query: int = 3) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        for query in queries:
            url = self.endpoint
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urllib.parse.urlencode({'q': query, 'limit': limit_per_query})}"
            headers = {"Accept": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
            for item in data.get("results", [])[:limit_per_query]:
                if item.get("url"):
                    results.append(
                        {
                            "title": item.get("title", ""),
                            "url": item["url"],
                            "source": item.get("source", ""),
                            "snippet": item.get("snippet", ""),
                        }
                    )
        return results


class _DuckDuckGoHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: List[Dict[str, str]] = []
        self._current: Optional[Dict[str, str]] = None
        self._field: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[tuple]) -> None:
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in class_name:
            href = attrs_dict.get("href", "")
            self._current = {"title": "", "url": _normalize_duckduckgo_url(href), "source": "duckduckgo", "snippet": ""}
            self._field = "title"
        elif self._current is not None and tag in {"a", "div"} and "result__snippet" in class_name:
            self._field = "snippet"

    def handle_data(self, data: str) -> None:
        if self._current is None or self._field is None:
            return
        text = " ".join(data.split())
        if not text:
            return
        existing = self._current.get(self._field, "")
        self._current[self._field] = f"{existing} {text}".strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None and self._field == "title":
            if self._current.get("title") and self._current.get("url"):
                self.results.append(self._current)
            self._current = None
            self._field = None
        elif tag in {"a", "div"} and self._field == "snippet":
            self._field = None


@dataclass
class DuckDuckGoSearchProvider:
    def search(self, queries: Iterable[str], limit_per_query: int = 3) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        seen = set()
        for query in list(queries):
            url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 TwilightZoneBot/0.1",
                    "Accept": "text/html",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    html = response.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            parser = _DuckDuckGoHTMLParser()
            parser.feed(html)
            added_for_query = 0
            for item in parser.results:
                item_url = item["url"]
                if item_url in seen:
                    continue
                seen.add(item_url)
                results.append(item)
                added_for_query += 1
                if added_for_query >= limit_per_query:
                    break
        return results


@dataclass
class BingSearchProvider:
    def search(self, queries: Iterable[str], limit_per_query: int = 3) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        seen = set()
        for query in list(queries):
            search_query = _research_query(query)
            url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": search_query})
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 TwilightZoneBot/0.1",
                    "Accept": "text/html",
                    "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    html = response.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            added_for_query = 0
            for item in _parse_bing_results(html):
                item_url = item["url"]
                if _is_blocked_result(item):
                    continue
                if item_url in seen:
                    continue
                seen.add(item_url)
                results.append(item)
                added_for_query += 1
                if added_for_query >= limit_per_query:
                    break
        return results


@dataclass
class ArxivSearchProvider:
    def search(self, queries: Iterable[str], limit_per_query: int = 3) -> List[Dict[str, str]]:
        results: List[Dict[str, str]] = []
        seen = set()
        for query in list(queries):
            url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
                {
                    "search_query": _arxiv_search_query(query),
                    "start": 0,
                    "max_results": limit_per_query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                }
            )
            request = urllib.request.Request(url, headers={"User-Agent": "TwilightZoneBot/0.1"})
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    xml = response.read().decode("utf-8", errors="replace")
            except Exception:
                continue
            for item in _parse_arxiv_results(xml):
                if item["url"] in seen:
                    continue
                seen.add(item["url"])
                results.append(item)
        return results


def _parse_arxiv_results(xml: str) -> List[Dict[str, str]]:
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    items: List[Dict[str, str]] = []
    for entry in root.findall("atom:entry", namespace):
        title = _clean_xml_text(entry.findtext("atom:title", "", namespace))
        summary = _clean_xml_text(entry.findtext("atom:summary", "", namespace))
        url = entry.findtext("atom:id", "", namespace).strip()
        if title and url:
            items.append({"title": title, "url": url, "source": "arxiv", "snippet": summary})
    return items


def _arxiv_search_query(query: str) -> str:
    tokens = [
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", query)
        if token.lower() not in QUERY_STOPWORDS
    ]
    if not tokens:
        return f'all:"{query}"'
    selected = tokens[:5]
    return " AND ".join(f"all:{token}" for token in selected)


def _clean_xml_text(value: str) -> str:
    return " ".join(value.split())


def _parse_bing_results(html: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    blocks = re.findall(r'<li[^>]+class="[^"]*\bb_algo\b[^"]*"[^>]*>(.*?)</li>', html, flags=re.DOTALL)
    for block in blocks:
        link = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>.*?</h2>', block, flags=re.DOTALL)
        if not link:
            continue
        url = _normalize_bing_url(unescape(link.group(1)))
        title = _strip_html(link.group(2))
        snippet_match = re.search(r'<p[^>]*>(.*?)</p>', block, flags=re.DOTALL)
        snippet = _strip_html(snippet_match.group(1)) if snippet_match else ""
        if title and url.startswith(("http://", "https://")):
            items.append({"title": title, "url": url, "source": "bing", "snippet": snippet})
    return items


def _research_query(query: str) -> str:
    negative = "-dictionary -definition -meaning -translate -translation"
    return f"{query} research paper blog arxiv github longform {negative}"


def _normalize_bing_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qs(parsed.query)
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/") and query.get("u"):
        encoded = query["u"][0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
        padded = encoded + "=" * (-len(encoded) % 4)
        try:
            return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        except Exception:
            return url
    return url


def _is_blocked_result(item: Dict[str, str]) -> bool:
    parsed = urllib.parse.urlparse(item.get("url", ""))
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain in BLOCKED_DOMAINS:
        return True
    title = item.get("title", "").lower()
    return any(term in title for term in BLOCKED_TITLE_TERMS)


def _strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    return " ".join(unescape(value).split())


def _normalize_duckduckgo_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.path == "/l/":
        query = urllib.parse.parse_qs(parsed.query)
        if "uddg" in query and query["uddg"]:
            return urllib.parse.unquote(query["uddg"][0])
    return url


def build_search(config: Config) -> SearchProvider:
    if config.search_endpoint:
        return JsonEndpointSearchProvider(config.search_endpoint, config.search_api_key)
    if config.search_provider == "offline":
        return OfflineSearchProvider()
    if config.search_provider == "bing":
        return BingSearchProvider()
    if config.search_provider == "duckduckgo":
        return DuckDuckGoSearchProvider()
    return ArxivSearchProvider()
