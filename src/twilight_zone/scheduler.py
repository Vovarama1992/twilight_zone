from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict

from .config import Config
from .service import TwilightZoneService


LOGGER = logging.getLogger(__name__)


@dataclass
class PeriodicJob:
    name: str
    interval: timedelta
    action: Callable[[], object]
    next_run: datetime = field(default_factory=datetime.utcnow)

    def maybe_run(self, now: datetime) -> None:
        if now < self.next_run:
            return
        LOGGER.info("running job=%s", self.name)
        try:
            self.action()
        except Exception:
            LOGGER.exception("job failed: %s", self.name)
        self.next_run = now + self.interval


class Scheduler:
    def __init__(self, service: TwilightZoneService, config: Config):
        self.jobs: Dict[str, PeriodicJob] = {
            "analysis": PeriodicJob(
                "analysis",
                timedelta(minutes=config.analysis_interval_minutes),
                service.analyze_once,
            ),
            "search": PeriodicJob(
                "search",
                timedelta(minutes=config.search_interval_minutes),
                service.search_once,
            ),
            "delivery": PeriodicJob(
                "delivery",
                timedelta(minutes=config.delivery_interval_minutes),
                service.deliver_once,
            ),
            "telegram_poll": PeriodicJob(
                "telegram_poll",
                timedelta(seconds=30),
                service.poll_telegram_once,
            ),
        }

    def run_forever(self, tick_seconds: int = 10) -> None:
        while True:
            now = datetime.utcnow()
            for job in self.jobs.values():
                job.maybe_run(now)
            time.sleep(tick_seconds)
