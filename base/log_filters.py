"""Filters of the log records (see ``LOGGING`` in the settings)."""

import logging

HEALTH_PATH = "/health"


class SkipHealthChecks(logging.Filter):
    """Drop the uvicorn access lines of the container health check."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access args: client, method, path, HTTP version, status
        args = record.args
        return not (
            isinstance(args, tuple) and len(args) > 2 and args[2] == HEALTH_PATH
        )
