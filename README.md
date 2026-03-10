# Telegram Calendar Sync Bot

Telegram-бот для управления несколькими Exchange / Outlook-календарями через единый интерфейс.

**Ключевые возможности:**
- Подключение нескольких Exchange-аккаунтов через Microsoft OAuth
- Создание встреч из свободного текста на русском языке (LLM через OpenRouter)
- Автоматическое зеркалирование занятого слота во все остальные активные календари
- Проверка занятости участников через Microsoft Graph `getSchedule`
- Поддержка рекуррентных событий (ежедневно, еженедельно, ежемесячно, ежегодно) с режимами редактирования «только это / это и следующие / все»
- Реального времени синхронизация изменений из Outlook через Graph webhooks
- Поиск свободного слота с учётом участников встречи

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Бот | Python 3.12, aiogram 3.x |
| Backend API | FastAPI, SQLAlchemy 2 (async), asyncpg |
| Фоновые задачи | Celery 5 + Celery Beat, Redis |
| База данных | PostgreSQL 16 |
| Кеш / очередь / FSM | Redis 7 |
| Calendar API | Microsoft Graph API (delegated permissions) |
| LLM | OpenRouter (настраиваемая модель, по умолчанию Claude Haiku) |
| Шифрование токенов | Fernet (библиотека `cryptography`) |

---

## Быстрый старт

### Предварительные требования

- Docker и Docker Compose
- Зарегистрированное приложение в [Azure Portal](https://portal.azure.com) с permissions: `User.Read`, `offline_access`, `Calendars.ReadWrite`, `Calendars.ReadWrite.Shared`, `Contacts.Read`
- Telegram-бот, созданный через [@BotFather](https://t.me/BotFather)
- API-ключ [OpenRouter](https://openrouter.ai)

### 1. Клонирование и настройка окружения

```bash
git clone <repo-url>
cd calendar-agent
cp .env.example .env
```

Откройте `.env` и заполните обязательные переменные:

```bash
# Telegram
BOT_TOKEN=                    # токен от BotFather
BOT_WEBHOOK_SECRET=           # произвольная строка для верификации webhook

# Microsoft OAuth (из Azure Portal → App Registration)
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_REDIRECT_URI=https://yourdomain.com/api/v1/accounts/oauth/callback

# OpenRouter
OPENROUTER_API_KEY=

# Генерируется один раз, не меняется после первого запуска:
ENCRYPTION_KEY=               # см. раздел ниже
INTERNAL_API_KEY=             # произвольная строка
```

**Генерация ENCRYPTION\_KEY:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Запуск

```bash
docker compose up --build
```

При первом запуске Alembic автоматически применяет миграции. Все сервисы поднимаются в правильном порядке благодаря healthcheck-зависимостям.

Проверка работоспособности:
```bash
curl http://localhost/health
# {"status": "ok", "service": "calendar-agent-api"}
```

---

## Архитектура

```
Telegram
   │
   ▼
┌─────────┐   HTTP + X-Internal-Key   ┌─────────────┐
│   bot   │ ──────────────────────── ▶ │     api     │
│ aiogram │                            │   FastAPI   │
└─────────┘                            └──────┬──────┘
                                              │
                              ┌───────────────┼────────────────┐
                              ▼               ▼                ▼
                         PostgreSQL        Redis         Microsoft
                                                        Graph API
                              ▲               ▲
                              │               │
                         ┌────┴──────────┐    │
                         │    worker     │────┘
                         │  Celery+Beat  │
                         └───────────────┘
                              ▲
                              │ webhook notifications
                         Microsoft Graph
```

**Бот** никогда не обращается к базе данных напрямую — только через HTTP к API с заголовком `X-Internal-Key`.

**Worker** обрабатывает:
- Graph webhook-уведомления (обновление зеркал при изменении в Outlook)
- Продление Graph-подписок (каждые 6 ч)
- Ежедневная реконсиляция sync-групп (03:00 UTC)
- Фоновая синхронизация контактов (каждые 12 ч)

---

## Команды бота

| Команда | Действие |
|---------|---------|
| `/start` | Главное меню |
| `/today` | События на сегодня |
| `/week` | События на неделю |
| `/create` | Создать встречу (текстом или пошагово) |
| `/find_slot` | Найти свободный слот |
| `/reschedule` | Перенести встречу |
| `/delete` | Удалить встречу |
| `/accounts` | Управление Exchange-аккаунтами |
| `/settings` | Настройки зеркалирования по календарям |

**Пример текстовых команд** (LLM-парсинг):
```
Поставь встречу с Иваном завтра в 15:00 на час
Встреча с командой каждый понедельник в 10:00
Найди окно на этой неделе на 30 минут с Олей
```

---

## Зеркалирование событий

При создании встречи в календаре A система автоматически создаёт заглушки-блокировки во всех остальных активных календарях пользователя:

```
Тема:    [Занято] Встреча с Иваном
Тело:    Зеркальная блокировка. Основная встреча: «Встреча с Иваном»
         в календаре «Work». Участники: ivan@example.com.
         Sync group: <uuid>.
Статус:  Занят
```

Любое изменение основного события автоматически распространяется на все зеркала. Если зеркало изменено вручную в Outlook — система восстанавливает его из источника истины (основного события).

---

## Разработка

### Установка зависимостей локально

```bash
pip install -e shared/ -e api/ -e bot/ -e worker/ -e ".[dev]"
```

### Запуск отдельных сервисов

```bash
# API (с hot-reload)
PYTHONPATH=. uvicorn api.main:app --reload --port 8000

# Бот
PYTHONPATH=. python bot/main.py

# Celery worker + scheduler
PYTHONPATH=. celery -A worker.celery_config worker --loglevel=info -B
```

### Миграции базы данных

```bash
# Применить все миграции
PYTHONPATH=. alembic upgrade head

# Создать новую миграцию
PYTHONPATH=. alembic revision --autogenerate -m "add_field_x"

# Откатить последнюю
PYTHONPATH=. alembic downgrade -1
```

### Тесты

```bash
pytest tests/                                   # все тесты
pytest tests/unit/                              # только unit
pytest tests/unit/test_recurrence_mapper.py     # один файл
pytest -k "test_weekly"                         # по имени
```

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|------------|:---:|---------|
| `BOT_TOKEN` | ✅ | Токен Telegram-бота |
| `BOT_WEBHOOK_SECRET` | ✅ | Секрет для верификации webhook от Telegram |
| `BOT_WEBHOOK_URL` | | URL для webhook-режима (без — работает polling) |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://...` |
| `POSTGRES_PASSWORD` | ✅ | Пароль PostgreSQL |
| `REDIS_URL` | ✅ | `redis://...` |
| `MS_CLIENT_ID` | ✅ | Azure App Registration Client ID |
| `MS_CLIENT_SECRET` | ✅ | Azure App Registration Client Secret |
| `MS_REDIRECT_URI` | ✅ | OAuth callback URL |
| `MS_TENANT_ID` | | `common` (мульти-тенант) или конкретный tenant ID |
| `OPENROUTER_API_KEY` | ✅ | Ключ OpenRouter |
| `OPENROUTER_MODEL` | | Модель (по умолч. `anthropic/claude-3-haiku`) |
| `ENCRYPTION_KEY` | ✅ | Fernet-ключ для шифрования OAuth-токенов |
| `INTERNAL_API_KEY` | ✅ | Секрет для внутренней аутентификации bot→api |
| `API_BASE_URL` | | `http://api:8000` (внутри Docker) |

---

## Требуемые разрешения Microsoft

Минимальный набор delegated permissions для Azure App Registration:

- `User.Read`
- `offline_access`
- `Calendars.ReadWrite`
- `Calendars.ReadWrite.Shared`
- `Contacts.Read`
