"""
The background monitor: every MONITOR_INTERVAL_MINUTES the checks run and the System Administrators are told in the application about
anything that needs attention. Off when the interval is 0 (development and the tests). A failing run is logged and tried again later; it
never stops the application.
"""
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from app.core.config import settings

logger = logging.getLogger("cdr.monitor")
FIRST_RUN_DELAY_SECONDS = 60.0      # let the application finish starting before the first check
SECONDS_PER_MINUTE = 60.0


def run_once() -> int:
    """One run: the checks, then the notifications. Returns how many notifications were created."""
    from app.core.database import SessionLocal
    from app.services import monitoring_service as monitoring
    db = SessionLocal()
    try:
        return monitoring.notify_admins(db, monitoring.run_checks(db))
    finally:
        db.close()


async def _loop():
    await asyncio.sleep(FIRST_RUN_DELAY_SECONDS)
    while True:
        try:
            told = await asyncio.to_thread(run_once)
            if told:
                logger.info("Monitoring: %s notification(s) sent to the System Administrators.", told)
        except Exception:
            logger.exception("The monitoring run failed; it will try again at the next interval.")
        await asyncio.sleep(max(1, settings.MONITOR_INTERVAL_MINUTES) * SECONDS_PER_MINUTE)


@asynccontextmanager
async def monitoring_lifespan(app):
    task = asyncio.create_task(_loop()) if settings.MONITOR_INTERVAL_MINUTES > 0 else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
