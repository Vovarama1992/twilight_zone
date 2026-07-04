from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Protocol

from .config import Config


class LLMProvider(Protocol):
    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        ...


@dataclass
class NullLLMProvider:
    """Deterministic offline provider for local development and tests."""

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        if "strategy" in user.lower() or "queries" in user.lower():
            return {
                "summary": "Искать узко: мосты между темами, странные сильные идеи, без новостного шума.",
                "queries": [
                    "category theory software architecture LLM agents",
                    "homotopy type theory formal verification engineering",
                    "research agents personal knowledge graph unusual ideas",
                    "p-adic geometry cryptography zero knowledge bridge",
                ],
                "rationale": "Ценнее короткие находки, после которых хочется открыть источник и подумать самому.",
            }
        return {
            "score": 0.72,
            "language": "en",
            "why": "Хороший мост между агентами и личной картой знания.",
            "summary_ru": "Короткая тестовая находка про память исследовательских агентов и персональные графы знаний.",
            "tags": ["bridge", "research", "twilight-zone"],
        }


@dataclass
class OpenAIProvider:
    api_key: str
    model: str

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": {"type": "json_object"},
        }
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        return json.loads(data["choices"][0]["message"]["content"])


@dataclass
class GeminiProvider:
    api_key: str
    model: str

    def complete_json(self, system: str, user: str) -> Dict[str, Any]:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        prompt = f"{system}\n\nReturn only JSON.\n\n{user}"
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.removeprefix("json").strip()
        return json.loads(text)


def build_llm(config: Config) -> LLMProvider:
    if config.llm_provider == "openai" and config.openai_api_key:
        return OpenAIProvider(config.openai_api_key, config.openai_model)
    if config.llm_provider == "gemini" and config.gemini_api_key:
        return GeminiProvider(config.gemini_api_key, config.gemini_model)
    return NullLLMProvider()


def strategy_prompt(interests: List[Dict[str, Any]], day_state: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Create a search strategy for a personal research agent.",
            "language_policy": "All user-facing prose must be in Russian. Search queries may be in English or Russian.",
            "rules": [
                "Prefer surprising bridges over ordinary news.",
                "Better no item than a weak item.",
                "Use both English and Russian queries when useful.",
                "Account for current day state and cognitive energy.",
            ],
            "interests": interests,
            "day_state": day_state,
            "expected_json": {
                "summary": "short diagnosis in Russian",
                "queries": ["query 1", "query 2"],
                "rationale": "why these searches now, in Russian",
            },
        },
        ensure_ascii=False,
    )


def evaluation_prompt(item: Dict[str, Any], interests: List[Dict[str, Any]], day_state: Dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Evaluate whether this material deserves one Telegram message.",
            "language_policy": "Return every user-facing field in Russian. Keep only URLs and original titles unchanged.",
            "style": "Short, literary, human. No academic throat-clearing, no grant-proposal prose, no long justification.",
            "hard_filter": "Reject ordinary news, thin SEO, and generic productivity content.",
            "score_meaning": "0.0 useless, 0.68 minimum for queueing, 0.85 rare excellent.",
            "item": item,
            "interests": interests,
            "day_state": day_state,
            "expected_json": {
                "score": 0.0,
                "language": "en|ru|unknown",
                "why": "one short Russian sentence, vivid but not hype",
                "summary_ru": "1-3 short Russian sentences; enough to decide whether to open the source",
                "tags": ["tag"],
            },
        },
        ensure_ascii=False,
    )
