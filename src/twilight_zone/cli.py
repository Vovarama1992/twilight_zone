from __future__ import annotations

import argparse
import logging
from typing import Optional

from .config import Config
from .db import Database, Repository
from .llm import build_llm
from .scheduler import Scheduler
from .search import build_search
from .service import TwilightZoneService
from .telegram import build_telegram


def build_service(config: Optional[Config] = None) -> TwilightZoneService:
    config = config or Config.from_env()
    db = Database(config.db_path)
    repo = Repository(db)
    return TwilightZoneService(
        db=db,
        repo=repo,
        llm=build_llm(config),
        search=build_search(config),
        telegram=build_telegram(config),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Personal Research Agent / Twilight Zone")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("analyze-once")
    sub.add_parser("search-once")
    sub.add_parser("deliver-once")
    sub.add_parser("poll-telegram")
    day = sub.add_parser("day-state")
    day.add_argument("--energy", choices=["low", "normal", "high"])
    day.add_argument("--overload", choices=["true", "false"])
    day.add_argument("--mode", choices=["balanced", "twilight", "practice", "deep", "walk"])
    day.add_argument("--notes")
    sub.add_parser("run")

    args = parser.parse_args()
    config = Config.from_env()
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    service = build_service(config)
    service.initialize()

    if args.command == "init-db":
        print(f"Initialized {config.db_path}")
    elif args.command == "analyze-once":
        print(service.analyze_once())
    elif args.command == "search-once":
        print(service.search_once())
    elif args.command == "deliver-once":
        print(service.deliver_once())
    elif args.command == "poll-telegram":
        print(service.poll_telegram_once())
    elif args.command == "day-state":
        overload = None
        if args.overload is not None:
            overload = args.overload == "true"
        print(service.set_day_state(args.energy, overload, args.mode, args.notes))
    elif args.command == "run":
        Scheduler(service, config).run_forever()


if __name__ == "__main__":
    main()
