import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from twilight_zone.config import Config
from twilight_zone.db import Database, Repository, SCHEMA_VERSION
from twilight_zone.llm import NullLLMProvider
from twilight_zone.search import OfflineSearchProvider
from twilight_zone.service import TwilightZoneService, render_message
from twilight_zone.telegram import TelegramClient, parse_callback_reaction, parse_reaction, reaction_keyboard


class SchemaTests(unittest.TestCase):
    def make_service(self):
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db = Database(Path(tmpdir.name) / "test.sqlite3")
        repo = Repository(db)
        service = TwilightZoneService(
            db=db,
            repo=repo,
            llm=NullLLMProvider(),
            search=OfflineSearchProvider(),
            telegram=TelegramClient("", "", dry_run=True),
        )
        service.initialize()
        return service, db, repo

    def test_schema_initializes_seed_state(self):
        service, db, repo = self.make_service()
        with db.connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)
        self.assertGreaterEqual(len(repo.interests_snapshot()), 6)
        self.assertEqual(repo.day_state()["mode"], "balanced")

    def test_search_queue_deliver_flow(self):
        service, _db, repo = self.make_service()
        saved = service.search_once()
        self.assertGreaterEqual(len(saved), 1)
        delivery_id = service.deliver_once()
        self.assertIsInstance(delivery_id, int)
        self.assertIsNone(repo.next_queued_delivery())

    def test_delivery_slows_to_three_hours_without_reaction(self):
        service, db, _repo = self.make_service()
        service.search_once()
        first_delivery = service.deliver_once()
        self.assertIsInstance(first_delivery, int)
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_materials (title, url, score, status, evaluation_json)
                VALUES ('Second', 'seed://second', 0.9, 'new', '{"score": 0.9, "why": "Ок", "summary_ru": "Ок"}')
                """
            )
        self.assertIsNone(service.deliver_once())

    def test_reaction_allows_hourly_delivery(self):
        service, db, _repo = self.make_service()
        service.search_once()
        first_delivery = service.deliver_once()
        one_hour_ago = (datetime.utcnow() - timedelta(hours=1, minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        with db.connect() as conn:
            conn.execute("UPDATE deliveries SET sent_at = ? WHERE id = ?", (one_hour_ago, first_delivery))
            conn.execute(
                """
                INSERT INTO candidate_materials (title, url, score, status, evaluation_json)
                VALUES ('Second', 'seed://second', 0.9, 'new', '{"score": 0.9, "why": "Ок", "summary_ru": "Ок"}')
                """
            )
        service.handle_telegram_update({"message": {"text": "📌 Интерес"}})
        self.assertIsInstance(service.deliver_once(), int)

    def test_reaction_updates_day_state(self):
        service, _db, repo = self.make_service()
        reaction = service.handle_telegram_update({"message": {"text": "➖ Слишком тяжело"}})
        self.assertEqual(reaction, "too_heavy")
        state = repo.day_state()
        self.assertEqual(state["mode"], "twilight")
        self.assertEqual(state["overload"], 1)

    def test_parse_reaction_aliases(self):
        self.assertEqual(parse_reaction("🧠 Глубже"), "go_deeper")
        self.assertEqual(parse_reaction("больше практики"), "more_practice")

    def test_callback_reaction_updates_day_state(self):
        service, _db, repo = self.make_service()
        service.search_once()
        delivery_id = service.queue_best_once()
        update = {"callback_query": {"id": "callback-1", "data": f"react:{delivery_id}:more_practice"}}
        reaction = service.handle_telegram_update(update)
        self.assertEqual(reaction, "more_practice")
        self.assertEqual(repo.day_state()["mode"], "practice")

    def test_reaction_keyboard_uses_callback_data(self):
        keyboard = reaction_keyboard(7)
        first_button = keyboard["inline_keyboard"][0][0]
        twilight_button = keyboard["inline_keyboard"][3][0]
        self.assertEqual(first_button["callback_data"], "react:7:more_like_this")
        self.assertEqual(twilight_button["text"], "🎲 Twilight")
        self.assertEqual(parse_callback_reaction("react:7:more_like_this")["delivery_id"], 7)

    def test_render_message_links_http_sources(self):
        message = render_message(
            {"title": "Title", "url": "https://example.com/a?x=1&y=2", "snippet": "Snippet"},
            {"why": "Почему. Лишнее.", "summary_ru": "Первое. Второе. Третье. Четвертое.", "tags": []},
        )
        self.assertIn('<a href="https://example.com/a?x=1&amp;y=2">открыть</a>', message)
        self.assertNotIn("Четвертое", message)

    def test_help_command_sends_guide(self):
        service, _db, _repo = self.make_service()
        reaction = service.handle_telegram_update({"message": {"text": "/help"}})
        self.assertEqual(reaction, "help")


class ConfigTests(unittest.TestCase):
    def test_config_defaults_are_offline_safe(self):
        config = Config.from_env()
        self.assertIn(config.llm_provider, {"null", "openai", "gemini"})


if __name__ == "__main__":
    unittest.main()
