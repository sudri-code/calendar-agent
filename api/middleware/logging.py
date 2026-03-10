import time
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        start_time = time.time()

        with structlog.contextvars.bound_contextvars(request_id=request_id):
            logger.info(
                "Request started",
                method=request.method,
                path=request.url.path,
            )

            response = await call_next(request)

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )

            return response
