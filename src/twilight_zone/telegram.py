from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import escape
from typing import Any, Dict, Optional

from .config import Config


REACTION_COMMANDS = {
    "👍": "more_like_this",
    "🧠": "go_deeper",
    "↔": "connect_topic",
    "👎": "miss",
    "📌": "new_interest",
    "➖": "too_heavy",
    "🎲": "more_twilight",
    "⚒": "more_practice",
}

REACTION_LABELS = {
    "more_like_this": "👍 Еще",
    "go_deeper": "🧠 Глубже",
    "connect_topic": "↔ Связать",
    "miss": "👎 Мимо",
    "new_interest": "📌 Интерес",
    "too_heavy": "➖ Тяжело",
    "more_twilight": "🎲 Twilight",
    "more_practice": "⚒ Практика",
}

HELP_TEXT = """Как пользоваться кнопками:

👍 Еще — это попало в тему. Усиль похожие материалы и попробуй прислать продолжение прямо сейчас.
🧠 Глубже — тема интересна, но хочется серьезнее/труднее/ближе к первоисточникам. Тоже пробует продолжить прямо сейчас.
↔ Связать — хочется мост к другой области: математика ↔ инженерия, агенты ↔ продукт, HoTT ↔ verification и так далее.
👎 Мимо — не тот вкус. Ослабить такие материалы.
📌 Интерес — зафиксировать как новый или более важный интерес.
➖ Тяжело — сейчас перегруз; лучше легче, короче, прогулочнее.
🎲 Twilight — больше странного, глубокого, необычных мыслителей и идей с послевкусием.
⚒ Практика — больше применимого: архитектура, код, продукты, инструменты.

Ритм: если ты реагируешь, но не просишь продолжение, бот пишет не чаще раза в час. Если молчишь — не чаще раза в три часа. Только 👍 Еще и 🧠 Глубже пробуют принести что-то сразу.

Источник в обычных материалах будет кликабельным. Если видишь seed:// — это тестовая заглушка, она не открывается."""


@dataclass
class TelegramClient:
    token: str
    user_id: str
    dry_run: bool = True

    def send_message(
        self,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        if self.dry_run or not self.token or not self.user_id:
            print("\n--- TELEGRAM DRY RUN ---")
            print(text)
            if reply_markup:
                print(json.dumps(reply_markup, ensure_ascii=False))
            print("--- END ---\n")
            return {"ok": True, "dry_run": True, "result": {"message_id": 0}}

        payload_data = {
            "chat_id": self.user_id,
            "text": text,
            "disable_web_page_preview": "false",
        }
        if parse_mode:
            payload_data["parse_mode"] = parse_mode
        if reply_markup:
            payload_data["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        payload = urllib.parse.urlencode(payload_data).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def answer_callback_query(self, callback_query_id: str, text: str = "Принял") -> Dict[str, Any]:
        if self.dry_run or not self.token:
            return {"ok": True, "dry_run": True}
        payload = urllib.parse.urlencode({"callback_query_id": callback_query_id, "text": text}).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/answerCallbackQuery",
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def get_updates(self, offset: Optional[int] = None) -> Dict[str, Any]:
        if not self.token:
            return {"ok": True, "result": []}
        params = {"timeout": 20}
        if offset is not None:
            params["offset"] = offset
        url = f"https://api.telegram.org/bot{self.token}/getUpdates?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))


def build_telegram(config: Config) -> TelegramClient:
    return TelegramClient(
        token=config.telegram_bot_token,
        user_id=config.telegram_user_id,
        dry_run=config.telegram_dry_run,
    )


def parse_reaction(text: str) -> Optional[str]:
    text = text.strip()
    for marker, reaction in REACTION_COMMANDS.items():
        if text.startswith(marker):
            return reaction
    lowered = text.lower()
    if "twilight" in lowered:
        return "more_twilight"
    if "практи" in lowered:
        return "more_practice"
    if "глуб" in lowered:
        return "go_deeper"
    return None


def is_help_request(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered in {"/help", "help", "помощь", "кнопки", "что значит кнопки"}


def reaction_keyboard(delivery_id: int) -> Dict[str, Any]:
    rows = [
        ["more_like_this", "go_deeper"],
        ["connect_topic", "miss"],
        ["new_interest", "too_heavy"],
        ["more_twilight", "more_practice"],
    ]
    return {
        "inline_keyboard": [
            [
                {"text": REACTION_LABELS[reaction], "callback_data": f"react:{delivery_id}:{reaction}"}
                for reaction in row
            ]
            for row in rows
        ]
    }


def parse_callback_reaction(data: str) -> Optional[Dict[str, Any]]:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "react":
        return None
    try:
        delivery_id = int(parts[1])
    except ValueError:
        return None
    reaction = parts[2]
    if reaction not in REACTION_LABELS:
        return None
    return {"delivery_id": delivery_id, "reaction": reaction}


def html_escape(value: object) -> str:
    return escape(str(value), quote=False)
