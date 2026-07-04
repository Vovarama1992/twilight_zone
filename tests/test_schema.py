import tempfile
import unittest
from pathlib import Path

from twilight_zone.config import Config
from twilight_zone.db import Database, Repository, SCHEMA_VERSION
from twilight_zone.llm import NullLLMProvider
from twilight_zone.search import OfflineSearchProvider
from twilight_zone.service import TwilightZoneService
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
        self.assertEqual(first_button["callback_data"], "react:7:more_like_this")
        self.assertEqual(parse_callback_reaction("react:7:more_like_this")["delivery_id"], 7)


class ConfigTests(unittest.TestCase):
    def test_config_defaults_are_offline_safe(self):
        config = Config.from_env()
        self.assertIn(config.llm_provider, {"null", "openai", "gemini"})


if __name__ == "__main__":
    unittest.main()
