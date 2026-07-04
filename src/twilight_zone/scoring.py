from __future__ import annotations

import json
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
    evaluation["score"] = max(0.0, min(1.0, score))
    return evaluation
