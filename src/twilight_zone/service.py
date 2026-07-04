from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .db import Database, Repository
from .llm import LLMProvider, strategy_prompt
from .scoring import SYSTEM_PROMPT, evaluate_material
from .search import SearchProvider
from .telegram import TelegramClient, parse_callback_reaction, parse_reaction, reaction_keyboard


class TwilightZoneService:
    def __init__(
        self,
        db: Database,
        repo: Repository,
        llm: LLMProvider,
        search: SearchProvider,
        telegram: TelegramClient,
    ):
        self.db = db
        self.repo = repo
        self.llm = llm
        self.search = search
        self.telegram = telegram

    def initialize(self) -> None:
        self.db.initialize()

    def analyze_once(self) -> Dict[str, Any]:
        interests = self.repo.interests_snapshot()
        day_state = self.repo.day_state()
        prompt = strategy_prompt(interests, day_state)
        strategy = self.llm.complete_json(SYSTEM_PROMPT, prompt)
        queries = strategy.get("queries", [])
        self.repo.record_analysis("background", strategy.get("summary", ""), strategy)
        self.repo.save_strategy(queries, strategy.get("rationale", ""))
        return strategy

    def search_once(self) -> List[int]:
        strategy = self.analyze_once()
        queries = strategy.get("queries", [])
        items = self.search.search(queries, limit_per_query=3)
        interests = self.repo.interests_snapshot()
        day_state = self.repo.day_state()
        saved: List[int] = []
        for item in items:
            evaluation = evaluate_material(self.llm, item, interests, day_state)
            saved.append(self.repo.add_candidate(item, evaluation))
        return saved

    def queue_best_once(self) -> Optional[int]:
        item = self.repo.best_candidate()
        if not item:
            return None
        evaluation = json.loads(item["evaluation_json"])
        message = render_message(item, evaluation)
        delivery_id = self.repo.queue_delivery(item["id"], message)
        self.repo.mark_candidate(item["id"], "queued")
        return delivery_id

    def deliver_once(self) -> Optional[int]:
        delivery = self.repo.next_queued_delivery()
        if not delivery:
            queued = self.queue_best_once()
            if queued is None:
                return None
            delivery = self.repo.next_queued_delivery()
            if not delivery:
                return None
        result = self.telegram.send_message(delivery["message"], reply_markup=reaction_keyboard(int(delivery["id"])))
        message_id = (result.get("result") or {}).get("message_id")
        if message_id is not None:
            self.repo.set_kv(f"telegram_message:{message_id}", int(delivery["id"]))
        self.repo.mark_delivery_sent(delivery["id"])
        return int(delivery["id"])

    def set_day_state(
        self,
        energy: Optional[str] = None,
        overload: Optional[bool] = None,
        mode: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        return self.repo.update_day_state(energy=energy, overload=overload, mode=mode, notes=notes)

    def handle_telegram_update(self, update: Dict[str, Any]) -> Optional[str]:
        callback_query = update.get("callback_query")
        if callback_query:
            parsed = parse_callback_reaction(callback_query.get("data", ""))
            if not parsed:
                return None
            reaction = parsed["reaction"]
            self.repo.record_reaction(parsed["delivery_id"], reaction, update)
            self._apply_reaction_to_day_state(reaction)
            callback_id = callback_query.get("id")
            if callback_id:
                self.telegram.answer_callback_query(callback_id, "Принял")
            return reaction

        message = update.get("message") or update.get("edited_message") or {}
        text = message.get("text", "")
        reaction = parse_reaction(text)
        if not reaction:
            return None
        delivery_id = None
        reply = message.get("reply_to_message") or {}
        if reply.get("text"):
            delivery_id = self.repo.get_kv(f"telegram_message:{reply.get('message_id')}", None)
        self.repo.record_reaction(delivery_id, reaction, update)
        self._apply_reaction_to_day_state(reaction)
        return reaction

    def poll_telegram_once(self) -> int:
        offset = self.repo.get_kv("telegram_update_offset", None)
        updates = self.telegram.get_updates(offset=offset)
        processed = 0
        for update in updates.get("result", []):
            self.handle_telegram_update(update)
            self.repo.set_kv("telegram_update_offset", int(update["update_id"]) + 1)
            processed += 1
        return processed

    def _apply_reaction_to_day_state(self, reaction: str) -> None:
        if reaction == "too_heavy":
            self.repo.update_day_state(energy="low", overload=True, mode="twilight")
        elif reaction == "more_practice":
            self.repo.update_day_state(mode="practice", overload=False)
        elif reaction == "more_twilight":
            self.repo.update_day_state(mode="twilight")
        elif reaction == "go_deeper":
            self.repo.update_day_state(mode="deep")


def render_message(item: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
    title = item["title"].strip() or "Untitled"
    why = evaluation.get("why", "Похоже на материал с хорошей связностью с твоей картой интересов.")
    summary = evaluation.get("summary_ru") or item.get("snippet", "").strip()
    url = item["url"]
    label = _message_label(evaluation)
    parts = [
        f"{label}: {title}",
        "",
        f"Почему показать: {why}",
    ]
    if summary:
        parts.append(str(summary))
    parts.extend(
        [
            "",
            f"Источник: {url}",
        ]
    )
    return "\n".join(parts)


def _message_label(evaluation: Dict[str, Any]) -> str:
    tags = {str(tag).lower() for tag in evaluation.get("tags", [])}
    if "startup" in tags:
        return "Startup"
    if "math" in tags or "mathematics" in tags:
        return "Математика"
    if "practice" in tags or "engineering" in tags:
        return "Практика"
    return "Twilight Zone"
