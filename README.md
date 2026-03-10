# Telegram Calendar Sync Bot

Telegram-бот для управления несколькими Exchange-календарями через единый интерфейс.

**Ключевые возможности:**
- Подключение нескольких корпоративных Exchange-аккаунтов (on-premises Exchange Server)
- Создание встреч из свободного текста на русском языке (LLM через OpenRouter)
- Автоматическое зеркалирование занятого слота во все остальные активные календари
- Проверка занятости участников через EWS GetUserAvailability
- Поддержка рекуррентных событий (ежедневно, еженедельно, ежемесячно, ежегодно) с режимами редактирования «только это / это и следующие / все»
- Отслеживание изменений из Outlook через периодический EWS-опрос (Celery Beat)
- Поиск свободного слота с учётом участников встречи

---

## Стек

| Компонент | Технология |
|-----------|-----------|
| Бот | Python 3.12, aiogram 3.x |
| Backend API | FastAPI, SQLAlchemy 2 (async), asyncpg |
| Exchange | `exchangelib` (EWS — Exchange Web Services) |
| Фоновые задачи | Celery 5 + Celery Beat, Redis |
| База данных | PostgreSQL 16 |
| Кеш / очередь / FSM | Redis 7 |
| LLM | OpenRouter (настраиваемая модель, по умолчанию Claude Haiku) |
| Шифрование credentials | Fernet (библиотека `cryptography`) |

---

## Быстрый старт

### Предварительные требования

- Docker и Docker Compose
- Доступ к on-premises Exchange Server (NTLM или Basic Auth через HTTPS)
- Telegram-бот, созданный через [@BotFather](https://t.me/BotFather)
- API-ключ [OpenRouter](https://openrouter.ai)

**Azure и регистрация приложения не требуются.**

### 1. Клонирование и настройка окружения

```bash
git clone <repo-url>
cd calendar-agent
cp .env.example .env
```

Заполните в `.env`:

```bash
BOT_TOKEN=                   # токен от BotFather
BOT_WEBHOOK_SECRET=          # произвольная строка
OPENROUTER_API_KEY=          # ключ OpenRouter
ENCRYPTION_KEY=              # см. ниже
INTERNAL_API_KEY=            # произвольная строка
```

**Генерация ENCRYPTION\_KEY:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Если Exchange использует самоподписанный сертификат, добавьте:
```bash
EWS_VERIFY_SSL=false
```

### 2. Запуск

```bash
docker compose up --build
```

При первом запуске применяются все Alembic-миграции.

```bash
curl http://localhost/health
# {"status": "ok", "service": "calendar-agent-api"}
```

### 3. Подключение Exchange-аккаунта

Exchange-реквизиты вводятся через бота, **не через .env**:

```
/accounts → Подключить аккаунт

Сервер:   mail.company.ru
Email:    ivanov@company.ru
Логин:    CORP\ivanov  (или ivanov@company.ru)
Пароль:   ••••••
```

Бот проверяет подключение через EWS и сохраняет пароль в зашифрованном виде (Fernet). Сообщение с паролем немедленно удаляется из чата.

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
                                              │ exchangelib (EWS)
                              ┌───────────────┼────────────────┐
                              ▼               ▼                ▼
                         PostgreSQL        Redis         Exchange
                                                         Server
                              ▲               ▲         (on-prem)
                              │               │              ▲
                         ┌────┴──────────┐    │              │
                         │    worker     │────┘    EWS polling│
                         │  Celery+Beat  │─────────────────── ┘
                         └───────────────┘
```

**Обнаружение изменений** (вместо webhooks):
Celery Beat каждые 5 минут опрашивает Exchange через EWS, сравнивает `changeKey` событий с БД и синхронизирует зеркала при расхождении.

**Бот** никогда не обращается к БД напрямую — только через HTTP к API с заголовком `X-Internal-Key`.

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
         в календаре «Work». Участники: ivan@company.ru.
         Sync group: <uuid>.
Статус:  Занят
```

Любое изменение основного события автоматически распространяется на все зеркала. Если зеркало изменено вручную в Outlook — при следующем опросе система восстанавливает его из источника истины.

---

## Разработка

### Установка зависимостей

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
PYTHONPATH=. alembic upgrade head          # применить все
PYTHONPATH=. alembic revision --autogenerate -m "описание"
PYTHONPATH=. alembic downgrade -1          # откатить последнюю
```

### Тесты

```bash
pytest tests/
pytest tests/unit/test_recurrence_mapper.py
pytest -k "test_weekly"
```

---

## Переменные окружения

| Переменная | Обязательная | Описание |
|------------|:---:|---------|
| `BOT_TOKEN` | ✅ | Токен Telegram-бота |
| `BOT_WEBHOOK_SECRET` | ✅ | Секрет для верификации webhook от Telegram |
| `BOT_WEBHOOK_URL` | | URL для webhook-режима (без — polling) |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://...` |
| `POSTGRES_PASSWORD` | ✅ | Пароль PostgreSQL |
| `REDIS_URL` | ✅ | `redis://...` |
| `OPENROUTER_API_KEY` | ✅ | Ключ OpenRouter |
| `OPENROUTER_MODEL` | | Модель LLM (по умолч. `anthropic/claude-3-haiku`) |
| `ENCRYPTION_KEY` | ✅ | Fernet-ключ для шифрования паролей Exchange |
| `INTERNAL_API_KEY` | ✅ | Секрет для внутренней аутентификации bot→api |
| `EWS_VERIFY_SSL` | | `false` для самоподписанных сертификатов |
| `API_BASE_URL` | | `http://api:8000` (внутри Docker) |

Exchange-реквизиты (сервер, логин, пароль) **хранятся в БД в зашифрованном виде** и вводятся через бот, а не через переменные окружения.

---

## Фоновые задачи (Celery Beat)

| Задача | Расписание | Описание |
|--------|-----------|---------|
| `poll_calendar_changes_task` | каждые 5 минут | Опрос EWS на изменения событий, синхронизация зеркал |
| `sync_all_calendars_task` | каждые 12 часов | Обновление списка подключённых календарей |
| `sync_all_contacts_task` | каждые 12 часов | Обновление списка контактов из Exchange |
| `reconcile_sync_groups_task` | ежедневно в 03:00 UTC | Проверка и восстановление консистентности зеркал |

При подключении нового аккаунта синхронизация календарей запускается немедленно автоматически.