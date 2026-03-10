# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running locally (Docker)
```bash
cp .env.example .env          # fill in required values
docker compose up --build     # start all 6 services
docker compose logs -f api    # tail a specific service
```

### Database migrations
```bash
# Run from repo root (PYTHONPATH must include the root)
PYTHONPATH=. alembic upgrade head          # apply all migrations
PYTHONPATH=. alembic revision --autogenerate -m "description"  # generate new migration
PYTHONPATH=. alembic downgrade -1          # roll back one migration
```

### Running tests
```bash
pip install -e ".[dev]" -e shared/ -e api/   # install deps
pytest tests/                                 # all tests
pytest tests/unit/                            # unit tests only
pytest tests/unit/test_recurrence_mapper.py   # single file
pytest -k "test_daily"                        # single test by name
```

### Running services locally (without Docker)
```bash
# API
cd api && uvicorn main:app --reload --port 8000

# Bot
cd bot && python main.py

# Celery worker + beat
cd worker && celery -A celery_config worker --loglevel=info -B
```

## Architecture

### Service layout
The repo is a monorepo with four Python packages, each with its own `pyproject.toml` and `Dockerfile`:

| Package | Role | Entry point |
|---------|------|-------------|
| `api/` | FastAPI backend — all business logic | `uvicorn api.main:app` |
| `bot/` | aiogram 3 Telegram bot — UI only, calls API | `python bot/main.py` |
| `worker/` | Celery + Beat — background jobs | `celery -A celery_config worker -B` |
| `shared/` | Pydantic schemas + enums shared by all services | installed as editable dep |

The bot never touches the database directly — it only calls the API via `bot/services/api_client.py` (`BotClient`, internal `X-Internal-Key` header).

### Request flow
1. Telegram → bot handler (aiogram FSM) → `BotClient.post(...)` → API
2. API router → service layer → Graph API (via `GraphClient`) + DB (SQLAlchemy async)
3. Microsoft Graph change → webhook `POST /api/v1/webhooks/graph` → Celery task → mirror sync

### Key service files
- `api/services/events/event_service.py` — create/delete orchestrator; acquires `redis_lock("sync_group:{user_id}")` before any write, then calls Graph API, then commits DB. On partial mirror failure sets `sync_group.state = DEGRADED`.
- `api/services/events/mirror_service.py` — `sync_mirror_to_primary()` updates all mirror events to match primary; `repair_sync_group()` is called by daily reconciliation.
- `api/services/events/recurrence_mapper.py` — bidirectional Graph `patternedRecurrence` ↔ RRULE. **All recurrence format conversions must go through here.**
- `api/services/graph/client.py` — `GraphClient`: auto-refreshes token 5 min before expiry (with `redis_lock("token_refresh:{account_id}")`), retries 429 with `Retry-After`, raises typed exceptions on 401/403.
- `api/services/llm/parser.py` — calls OpenRouter with `response_format: json_object`, maintains per-user LLM session (up to 4 turns, 30-min TTL in `llm_sessions` table).

### Database / recurrence storage strategy
Only **series masters** are stored in `events` with `is_recurrence_master=True`. Virtual (unmodified) occurrences are computed on the fly via `dateutil.rrulestr(event.recurrence_rule)` and cached in Redis `occurrences:{master_id}:{week_start}` (TTL 30 min). Exception occurrences (moved/cancelled) are materialised as separate rows with `recurrence_master_id` pointing to the master and `recurrence_exception_date` = the original occurrence date.

### Sync group invariant
Every event belongs to a `sync_group`. Each group has exactly one `PRIMARY` event (source of truth) and zero-or-more `MIRROR` events (one per other active calendar). The sync group state is `ACTIVE | DEGRADED | DELETED`. `DEGRADED` means ≥1 mirror failed to sync; the daily `reconcile_sync_groups_task` attempts to repair it.

### Celery Beat schedules
| Task | Schedule |
|------|----------|
| `renew_expiring_subscriptions_task` | every 6 h |
| `reconcile_sync_groups_task` | daily 03:00 UTC |
| `sync_all_contacts_task` | every 12 h |

### Bot FSM
All conversation flows use aiogram FSM backed by `RedisStorage`. State groups live in `bot/states/`. The create flow branches at `choose_mode`: "текстом" calls `POST /api/v1/events/draft/parse` (LLM), "пошагово" collects fields step-by-step. Both paths converge at `choose_calendar` → `confirm` → `POST /api/v1/events`.

### Adding a new API endpoint
1. Add route to the appropriate `api/routers/*.py`
2. Add service logic under `api/services/`
3. If the bot needs to call it, add a method/call in `bot/services/api_client.py` and a handler in `bot/handlers/`

### Environment variables
All required variables are documented in `.env.example`. The API reads them via `api/config.py` (`pydantic-settings`); the bot via `bot/config.py`. Generate `ENCRYPTION_KEY` with:
```python
from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())
```
