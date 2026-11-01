"""Request IDs, JSON access logs and dependency-free HTTP metrics."""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from threading import Lock

from fastapi import Request

from app.security import decode_token

REQUEST_ID_HEADER = "X-Request-ID"
_logger = logging.getLogger("ashore.http")
_metrics_lock = Lock()
_metrics: dict[tuple[str, str, int], dict[str, float]] = defaultdict(
    lambda: {"count": 0.0, "duration": 0.0}
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "request_id", "method", "path", "status", "latency_ms",
            "client", "user_id",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    if _logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def metrics_text() -> str:
    lines = [
        "# HELP ashore_http_requests_total Total HTTP requests.",
        "# TYPE ashore_http_requests_total counter",
        "# HELP ashore_http_request_duration_seconds HTTP request duration.",
        "# TYPE ashore_http_request_duration_seconds summary",
    ]
    with _metrics_lock:
        items = sorted(_metrics.items())
    for (method, route, status), value in items:
        labels = (
            f'method="{_escape(method)}",route="{_escape(route)}",'
            f'status="{status}"'
        )
        lines.append(f"ashore_http_requests_total{{{labels}}} {int(value['count'])}")
        lines.append(
            f"ashore_http_request_duration_seconds_sum{{{labels}}} "
            f"{value['duration']:.6f}"
        )
        lines.append(
            f"ashore_http_request_duration_seconds_count{{{labels}}} "
            f"{int(value['count'])}"
        )
    return "\n".join(lines) + "\n"


def reset_metrics() -> None:
    with _metrics_lock:
        _metrics.clear()


async def http_middleware(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    request.state.request_id = request_id
    user_id = None
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        payload = decode_token(authorization[7:].strip())
        if payload:
            user_id = payload.get("sub")

    started = time.perf_counter()
    response = None
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _logger.exception(
            "request_failed",
            extra={
                "request_id": request_id, "method": request.method,
                "path": request.url.path, "status": 500,
                "latency_ms": latency_ms,
                "client": request.client.host if request.client else None,
                "user_id": user_id,
            },
        )
        _record(request, status, time.perf_counter() - started)
        raise

    latency = time.perf_counter() - started
    _record(request, status, latency)
    response.headers[REQUEST_ID_HEADER] = request_id
    _logger.info(
        "request",
        extra={
            "request_id": request_id, "method": request.method,
            "path": request.url.path, "status": status,
            "latency_ms": round(latency * 1000, 2),
            "client": request.client.host if request.client else None,
            "user_id": user_id,
        },
    )
    return response


def _record(request: Request, status: int, duration: float) -> None:
    route = getattr(request.scope.get("route"), "path", request.url.path)
    key = (request.method, route, status)
    with _metrics_lock:
        item = _metrics[key]
        item["count"] += 1
        item["duration"] += duration
