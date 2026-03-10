import structlog
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.config import settings
from api.db.session import engine
from api.middleware.logging import LoggingMiddleware
from api.middleware.rate_limiting import limiter
from api.routers import accounts, calendars, contacts, events, webhooks

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Calendar Agent API", environment=settings.environment)
    yield
    logger.info("Shutting down Calendar Agent API")
    await engine.dispose()


app = FastAPI(
    title="Calendar Agent API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(LoggingMiddleware)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def internal_key_middleware(request: Request, call_next):
    # Only protect internal routes
    if request.url.path.startswith("/api/v1/internal/"):
        api_key = request.headers.get("X-Internal-Key")
        if api_key != settings.internal_api_key:
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
    response = await call_next(request)
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "service": "calendar-agent-api"}


# Register routers
app.include_router(accounts.router)
app.include_router(calendars.router)
app.include_router(contacts.router)
app.include_router(events.router)
app.include_router(webhooks.router)
