from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Iterable, List, Protocol

from .config import Config


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


def build_search(config: Config) -> SearchProvider:
    if config.search_endpoint:
        return JsonEndpointSearchProvider(config.search_endpoint, config.search_api_key)
    return OfflineSearchProvider()
