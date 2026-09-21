"""
Structured logging (Module: observability).

Before this, the only durable "what happened" record was audit_logs - which
answers "which user did what", not "why did this request fail". This module
gives every log line a consistent, machine-parseable shape (JSON in
production, readable text in development) so a real deployment's log
aggregator (CloudWatch, an ELK stack, whatever BOT already runs) can
actually search and alert on them - "grep the container output" does not
scale past a single developer debugging locally.

This is deliberately NOT a Sentry/error-tracking integration: that needs a
real account and DSN this project cannot provision on BOT's behalf. What
this DOES provide is the same optional-activation shape as email_service.py
elsewhere in this codebase - structured logging always works via stdout
(captured by `docker compose logs` / any container platform with zero
extra setup), and a real error tracker can subscribe to it later without
any code here changing.
"""
import logging
import json
import sys
from datetime import datetime, timezone

from app.core.config import settings


class JsonFormatter(logging.Formatter):
    """Renders one log record as one JSON line - the shape most log
    aggregators expect, and trivial to grep/parse even without one."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Any extra=... fields a caller attached (e.g. request_id, user_id)
        reserved = set(vars(logging.makeLogRecord({})).keys()) | {"message"}
        for key, value in vars(record).items():
            if key not in reserved and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """
    Call once, at application startup. JSON lines in production (so a real
    log aggregator can parse them); plain readable text in development
    (so a developer's terminal isn't full of JSON while iterating).
    """
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if settings.ENVIRONMENT == "production":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
        ))
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Uvicorn's own loggers otherwise install a second, differently-formatted
    # handler - route them through this same one instead, so every line in
    # the container's output has one consistent shape.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = True
