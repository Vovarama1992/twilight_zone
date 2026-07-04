from __future__ import annotations

import json
import re
from typing import Any, Dict, List

from .llm import LLMProvider, evaluation_prompt


SYSTEM_PROMPT = (
    "You are Twilight Zone, a personal research scout. "
    "You prefer durable, strange, rigorous materials and useful bridges. "
    "All user-facing prose must be in Russian. Return compact JSON only."
)


def evaluate_material(
    llm: LLMProvider,
    item: Dict[str, Any],
    interests: List[Dict[str, Any]],
    day_state: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        evaluation = llm.complete_json(SYSTEM_PROMPT, evaluation_prompt(item, interests, day_state))
    except Exception as exc:
        evaluation = {"score": 0.0, "language": "unknown", "why": f"evaluation_error: {exc}", "tags": []}

    score = float(evaluation.get("score", 0.0))
    if day_state.get("overload") and "twilight" not in json.dumps(evaluation).lower():
        score -= 0.08
    if day_state.get("mode") == "practice" and "engineering" in item.get("snippet", "").lower():
        score += 0.05
    score = _penalize_foreign_dense_math(item, evaluation, score)
    evaluation["score"] = max(0.0, min(1.0, score))
    return evaluation


CORE_DEPTH_TERMS = {
    "algebraic geometry",
    "scheme",
    "schemes",
    "sheaf",
    "sheaves",
    "category theory",
    "higher category",
    "homotopy type theory",
    "hott",
    "dependent type",
    "dependent types",
    "type theory",
    "topos",
    "toposes",
    "p-adic",
    "perfectoid",
    "formal verification",
    "zero knowledge",
    "zk",
    "cryptography",
    "llm",
    "agent",
    "agents",
    "rag",
    "software architecture",
}

FOREIGN_DENSE_TERMS = {
    "lattice gauge",
    "potts",
    "ising",
    "wilson loop",
    "statistical mechanics",
    "spin glass",
    "quantum field",
    "correlation length",
    "plaquette",
    "random cluster",
}


def _penalize_foreign_dense_math(item: Dict[str, Any], evaluation: Dict[str, Any], score: float) -> float:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("snippet", "")),
        ]
    ).lower()
    if not any(term in haystack for term in FOREIGN_DENSE_TERMS):
        return score
    if any(term in haystack for term in CORE_DEPTH_TERMS):
        return score
    bridge_terms = re.findall(r"\b(bridge|verification|cryptography|agent|architecture|software|programming|foundation)\b", haystack)
    if bridge_terms:
        return min(score, 0.62)
    return min(score, 0.34)
