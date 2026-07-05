from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .db import Database, Repository
from .llm import LLMProvider, strategy_prompt
from .scoring import SYSTEM_PROMPT, evaluate_material
from .search import SearchProvider
from .telegram import (
    HELP_TEXT,
    TelegramClient,
    html_escape,
    is_help_request,
    parse_callback_reaction,
    parse_reaction,
    reaction_keyboard,
)


LOGGER = logging.getLogger(__name__)


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

    def deliver_once(self, force: bool = False) -> Optional[int]:
        if not force and not self._delivery_allowed():
            return None
        delivery = self.repo.next_queued_delivery()
        if not delivery:
            queued = self.queue_best_once()
            if queued is None:
                return None
            delivery = self.repo.next_queued_delivery()
            if not delivery:
                return None
        return self._send_delivery(delivery)

    def _send_delivery(self, delivery: Dict[str, Any]) -> int:
        delivery_id = int(delivery["id"])
        result = self.telegram.send_message(
            delivery["message"],
            reply_markup=reaction_keyboard(delivery_id),
            parse_mode="HTML",
        )
        message_id = (result.get("result") or {}).get("message_id")
        if message_id is not None:
            self.repo.set_kv(f"telegram_message:{message_id}", delivery_id)
        self.repo.mark_delivery_sent(delivery_id)
        return delivery_id

    def _delivery_allowed(self) -> bool:
        last_sent = _parse_sqlite_timestamp(self.repo.latest_sent_delivery_at())
        if last_sent is None:
            return True
        last_reaction = _parse_sqlite_timestamp(self.repo.latest_reaction_at())
        now = datetime.utcnow()
        interval = timedelta(hours=1) if last_reaction and last_reaction > last_sent else timedelta(hours=3)
        return now - last_sent >= interval

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
            self._mark_callback_reaction(callback_query, parsed["delivery_id"], reaction)
            callback_id = callback_query.get("id")
            if callback_id:
                self._answer_callback(callback_id, reaction)
            if reaction in {"more_like_this", "go_deeper", "more_twilight"}:
                self._send_immediate_followup(reaction, parsed["delivery_id"])
            return reaction

        message = update.get("message") or update.get("edited_message") or {}
        text = message.get("text", "")
        if is_help_request(text):
            self.telegram.send_message(HELP_TEXT)
            return "help"
        reaction = parse_reaction(text)
        if not reaction:
            return None
        delivery_id = None
        reply = message.get("reply_to_message") or {}
        if reply.get("text"):
            delivery_id = self.repo.get_kv(f"telegram_message:{reply.get('message_id')}", None)
        self.repo.record_reaction(delivery_id, reaction, update)
        self._apply_reaction_to_day_state(reaction)
        if reaction in {"more_like_this", "go_deeper", "more_twilight"}:
            self._send_immediate_followup(reaction, delivery_id)
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
            self.repo.update_day_state(
                energy="low",
                overload=True,
                mode="twilight",
                notes=(
                    "Если материал из чужой области, нужен человеческий мостик и легкий вход. "
                    "Плотную техническую жесткость оставлять для ядерных тем пользователя."
                ),
            )
        elif reaction == "more_like_this":
            self.repo.update_day_state(notes="Пользователь попросил больше похожего прямо сейчас.")
        elif reaction == "miss":
            self.repo.update_day_state(
                notes=(
                    "Последний материал был мимо. Особенно осторожно с чужой тяжелой математикой: "
                    "без сильного моста или человеческой подачи лучше не слать."
                )
            )
        elif reaction == "more_practice":
            self.repo.update_day_state(mode="practice", overload=False)
        elif reaction == "more_twilight":
            self.repo.update_day_state(
                mode="twilight",
                notes="Пользователь сказал: направление хорошее, но нужно страннее.",
            )
        elif reaction == "go_deeper":
            self.repo.update_day_state(mode="deep")

    def _send_immediate_followup(self, reaction: str, delivery_id: Optional[int] = None) -> None:
        source_item = self.repo.material_for_delivery(int(delivery_id)) if delivery_id else None
        if reaction == "go_deeper":
            self.repo.update_day_state(mode="deep", notes="Пользователь попросил углубиться прямо сейчас.")
        elif reaction == "more_like_this":
            self.repo.update_day_state(
                notes="Пользователь попросил похожее продолжение именно к последнему материалу, не просто еще один хороший общий пост."
            )
        elif reaction == "more_twilight":
            self.repo.update_day_state(
                mode="twilight",
                notes="Пользователь попросил продолжение в том же направлении, но страннее.",
            )
        if source_item:
            delivered = self._deliver_followup_for_source(reaction, source_item)
        else:
            self.search_once()
            delivered = self.deliver_once(force=True)
        if delivered is None:
            self.telegram.send_message(
                "Принял сигнал. Прямо сейчас сильного продолжения не нашел; лучше ничего, чем слабая догонялка."
            )

    def _deliver_followup_for_source(self, reaction: str, source_item: Dict[str, Any]) -> Optional[int]:
        queries = followup_queries(reaction, source_item)
        items = self.search.search(queries, limit_per_query=3)
        interests = self.repo.interests_snapshot()
        day_state = self.repo.day_state()
        saved: List[int] = []
        for item in items:
            evaluation = evaluate_material(self.llm, item, interests, day_state)
            saved.append(self.repo.add_candidate(item, evaluation))
        best = self.repo.best_candidate_from_ids(saved, exclude_id=int(source_item["id"]))
        if not best:
            return None
        evaluation = json.loads(best["evaluation_json"])
        message = render_message(best, evaluation)
        delivery_id = self.repo.queue_delivery(best["id"], message)
        self.repo.mark_candidate(best["id"], "queued")
        delivery = self.repo.delivery_by_id(delivery_id)
        if not delivery:
            return None
        return self._send_delivery(delivery)

    def _callback_ack(self, reaction: str) -> str:
        if reaction == "more_like_this":
            return "Ищу похожее"
        if reaction == "go_deeper":
            return "Ищу глубже"
        if reaction == "more_twilight":
            return "Ищу страннее"
        return "Принял"

    def _answer_callback(self, callback_id: str, reaction: str) -> None:
        try:
            self.telegram.answer_callback_query(callback_id, self._callback_ack(reaction))
        except Exception:
            LOGGER.warning("failed to answer callback query", exc_info=True)

    def _mark_callback_reaction(self, callback_query: Dict[str, Any], delivery_id: int, reaction: str) -> None:
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        message_id = message.get("message_id")
        if chat_id is None or message_id is None:
            return
        try:
            self.telegram.edit_message_reply_markup(
                chat_id,
                message_id,
                reply_markup=reaction_keyboard(delivery_id, selected=reaction),
            )
        except Exception:
            LOGGER.warning("failed to mark callback reaction", exc_info=True)
            return


def render_message(item: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
    title = html_escape(item["title"].strip() or "Untitled")
    why = html_escape(_compact_text(evaluation.get("why", "Похоже на хорошую находку."), max_sentences=1, max_chars=180))
    summary = _compact_text(evaluation.get("summary_ru") or item.get("snippet", "").strip(), max_sentences=3, max_chars=420)
    url = item["url"]
    label = _message_label(evaluation)
    parts = [
        f"{label}: {title}",
        "",
        f"Почему показать: {why}",
    ]
    if summary:
        parts.append(html_escape(summary))
    parts.extend(
        [
            "",
            f"Источник: {_render_source(url)}",
        ]
    )
    return "\n".join(parts)


def followup_queries(reaction: str, source_item: Dict[str, Any]) -> List[str]:
    title = _query_text(source_item.get("title", ""), max_chars=120)
    snippet = _query_text(source_item.get("snippet", ""), max_chars=220)
    base = f"{title} {snippet}".strip()
    if not base:
        return []
    if reaction == "go_deeper":
        return [
            f"{base} technical follow-up related work",
            f"{title} deeper methods limitations source code",
        ]
    if reaction == "more_twilight":
        return [
            f"{base} unusual adjacent ideas research blog",
            f"{title} strange implications adjacent fields",
        ]
    return [
        f"{base} similar research related work",
        f"{title} related paper blog github",
    ]


def _query_text(value: object, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    text = text.replace('"', " ")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip()


def _render_source(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        safe_url = escape_url(url)
        return f'<a href="{safe_url}">открыть</a>'
    return f"{html_escape(url)} (тестовый источник, не открывается)"


def escape_url(url: str) -> str:
    return str(url).replace("&", "&amp;").replace('"', "%22")


def _compact_text(value: object, max_sentences: int, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    sentences = []
    current = ""
    for char in text:
        current += char
        if char in ".!?":
            sentence = current.strip()
            if sentence:
                sentences.append(sentence)
            current = ""
            if len(sentences) >= max_sentences:
                break
    if len(sentences) < max_sentences and current.strip():
        sentences.append(current.strip())
    compact = " ".join(sentences) if sentences else text
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 1].rstrip() + "..."


def _parse_sqlite_timestamp(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def _message_label(evaluation: Dict[str, Any]) -> str:
    tags = {str(tag).lower() for tag in evaluation.get("tags", [])}
    if "startup" in tags:
        return "Startup"
    if "math" in tags or "mathematics" in tags:
        return "Математика"
    if "practice" in tags or "engineering" in tags:
        return "Практика"
    return "Twilight Zone"
