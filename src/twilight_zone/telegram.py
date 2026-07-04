from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
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


@dataclass
class TelegramClient:
    token: str
    user_id: str
    dry_run: bool = True

    def send_message(self, text: str) -> Dict[str, Any]:
        if self.dry_run or not self.token or not self.user_id:
            print("\n--- TELEGRAM DRY RUN ---")
            print(text)
            print("--- END ---\n")
            return {"ok": True, "dry_run": True}

        payload = urllib.parse.urlencode(
            {"chat_id": self.user_id, "text": text, "disable_web_page_preview": "false"}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/sendMessage",
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
