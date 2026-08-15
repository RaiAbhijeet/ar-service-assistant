"""Structured logging configuration.

Renders JSON to stdout via `structlog`, with a `trace_id` attached to every
log line for the lifetime of a request. The trace_id is stored in a
`ContextVar` so it survives across `await` points without being passed
explicitly through every function call.
"""

import logging
import sys
import uuid
from contextvars import ContextVar

import structlog

_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)


def new_trace_id() -> str:
    """Generate and bind a fresh trace_id for the current context, returning it."""
    trace_id = uuid.uuid4().hex
    _trace_id.set(trace_id)
    return trace_id


def get_trace_id() -> str | None:
    """Return the trace_id bound to the current context, if any."""
    return _trace_id.get()


def _add_trace_id(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """structlog processor: inject the current trace_id into every event."""
    trace_id = _trace_id.get()
    if trace_id is not None:
        event_dict["trace_id"] = trace_id
    return event_dict


def configure_logging(*, level: int = logging.INFO) -> None:
    """Configure structlog + stdlib logging for JSON output. Call once at startup."""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_trace_id,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(**initial_values: object) -> structlog.typing.FilteringBoundLogger:
    """Return a structlog logger, optionally bound with initial key/value pairs."""
    return structlog.get_logger(**initial_values)  # type: ignore[no-any-return]
