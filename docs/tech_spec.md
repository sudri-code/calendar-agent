# Техническое задание — Telegram-бот синхронизации Exchange-календарей

## 1. Технический стек

- Python 3.12
- FastAPI
- aiogram 3.x
- PostgreSQL 16
- Redis
- Celery или ARQ/RQ для фоновых задач
- SQLAlchemy 2.x + Alembic
- httpx
- Pydantic v2
- Docker
- Docker Compose
- Microsoft Graph API
- OpenRouter API

---

## 2. Архитектура

Система состоит из следующих компонентов:

1. **telegram-bot**
   - принимает сообщения и callback'и из Telegram;
   - управляет сценариями диалога;
   - вызывает backend API.

2. **backend-api**
   - бизнес-логика;
   - работа с пользователями, аккаунтами, календарями, контактами, событиями;
   - orchestration вызовов Graph и LLM.

3. **sync-worker**
   - обработка webhook-событий от Microsoft Graph;
   - продление подписок;
   - фоновая синхронизация контактов;
   - восстановление консистентности;
   - подбор альтернативных слотов.

4. **postgres**
   - основная БД.

5. **redis**
   - кеш;
   - distributed locks;
   - очередь задач;
   - FSM / transient state по Telegram-сценариям.

6. **nginx / reverse proxy**
   - TLS termination;
   - проксирование webhook'ов.

---

## 3. Схема взаимодействия

### 3.1 Создание встречи через текст

1. Пользователь отправляет текст в Telegram.
2. Bot передаёт текст в backend.
3. Backend вызывает LLM parser.
4. LLM возвращает JSON intent + entities.
5. Backend:
   - определяет календарь или спрашивает его;
   - ищет участников;
   - запрашивает свободность календарей и участников;
   - при необходимости вычисляет альтернативы;
   - после подтверждения создаёт основное событие;
   - создаёт зеркальные события;
   - сохраняет mapping.
6. Bot отправляет пользователю результат.

### 3.2 Синхронизация внешних изменений

1. Microsoft Graph отправляет webhook о создании / изменении / удалении события.
2. Webhook endpoint валидирует запрос.
3. Worker получает событие.
4. Worker загружает актуальное состояние события из Graph.
5. Worker находит sync-group.
6. Worker:
   - обновляет зеркала;
   - или удаляет зеркала;
   - или помечает конфликт.
7. Пользователь получает уведомление, если нужна реакция.

Microsoft Graph change notifications поддерживают модель подписок на изменения ресурсов, а подписки имеют ограниченный срок действия и должны обновляться. :contentReference[oaicite:7]{index=7}

---

## 4. Роли и модель доступа

### 4.1 Пользователь

- Telegram-пользователь, привязанный к одной учётной записи приложения.
- Может подключить несколько Exchange-аккаунтов.
- Работает только со своими данными.

### 4.2 Сервис

- Хранит refresh tokens.
- Доступ к Microsoft Graph выполняется от имени пользователя через delegated permissions.

---

## 5. Интеграция с Microsoft Graph

## 5.1 Основные сценарии API

Нужны операции:

- OAuth sign-in + token refresh;
- list calendars;
- list events;
- create event;
- update event;
- delete event;
- get contacts;
- get free/busy schedule;
- webhook subscriptions.

Microsoft Graph поддерживает:

- создание события в календаре пользователя;
- чтение/запись shared/delegated calendars при соответствующих разрешениях;
- работу с контактами;
- change notifications;
- scheduling/free-busy APIs. :contentReference[oaicite:8]{index=8}

## 5.2 Рекомендуемые permissions

Минимально рассмотреть:

- `User.Read`
- `offline_access`
- `Calendars.Read`
- `Calendars.ReadWrite`
- при необходимости для shared/delegated сценариев: `Calendars.Read.Shared`, `Calendars.ReadWrite.Shared`
- `Contacts.Read`

Набор прав нужно уточнить по фактической модели доступа Exchange в вашей организации. Microsoft Graph разделяет delegated permissions и permissions для shared calendars. :contentReference[oaicite:9]{index=9}

## 5.3 Выбор стратегии занятости

Для проверки доступности использовать:

- `getSchedule` как базовый источник free/busy;
- алгоритм приложения для построения альтернативных слотов;
- `findMeetingTimes` не делать единственным источником логики, потому что приложению нужна более строгая собственная логика зеркалирования и консистентности.

---

## 6. Интеграция с OpenRouter

## 6.1 Назначение

LLM используется только для:

- классификации намерения;
- извлечения параметров встречи;
- нормализации запроса;
- генерации коротких уточняющих вопросов.

LLM не должен:

- самостоятельно выполнять действия;
- принимать окончательное решение без backend-валидации;
- обходить проверки занятости.

## 6.2 Формат запроса

Backend отправляет в OpenRouter:

- system prompt;
- краткую историю текущей задачи;
- текущее сообщение пользователя;
- список допустимых интентов.

## 6.3 Формат ответа

LLM должен возвращать только JSON по схеме:

```json
{
  "intent": "create_event",
  "confidence": 0.93,
  "title": "Встреча с Ваней Ивановым",
  "date_range": {
    "from": "2026-03-10",
    "to": "2026-03-15"
  },
  "start_time": null,
  "duration_minutes": 60,
  "participants": [
    {
      "name": "Ваня Иванов",
      "email": null
    }
  ],
  "description": null,
  "target_calendar_hint": null,
  "missing_fields": ["start_time", "target_calendar"],
  "needs_confirmation": true
}
```

OpenRouter предоставляет совместимый chat completions API, который можно вызывать через Bearer token.
6.4 Политика контекста
Контекст LLM хранить кратко, в пределах атомарной задачи:
последнее сообщение пользователя;
предыдущее уточнение бота;
собранные поля текущего draft-события.
Полный долгий чат в prompt не передавать. 7. Бизнес-правила
7.1 Основное и зеркальные события
Для каждой sync-группы есть:
одно основное событие;
N зеркальных событий в других календарях.
7.2 Основное событие
Основное событие:
создаётся в календаре, выбранном пользователем;
содержит участников;
содержит полное описание;
является источником истины.
7.3 Зеркальное событие
Зеркальное событие:
создаётся в остальных активных календарях;
не содержит участников;
содержит пометку, что это синхронизированная блокировка;
содержит ссылочные метаданные на primary event.
7.4 Приоритет изменений
Приоритет:
пользовательское действие через бота;
изменение primary event в Outlook;
ручное изменение mirror event — нежелательный случай, приводящий к восстановлению состояния по primary.
7.5 Проверка доступности
Перед созданием или переносом события обязательна проверка:
выбранного календаря;
всех активных зеркалируемых календарей;
всех участников.
Если слот недоступен:
событие не создаётся;
пользователь получает список альтернатив.
7.6 Альтернативные слоты
Алгоритм должен уметь:
искать окна в заданном диапазоне;
учитывать длительность;
учитывать рабочие часы, если они доступны;
сортировать слоты по близости к пожеланию пользователя;
возвращать не менее 3 и не более 10 вариантов. 8. Сценарии Telegram UX
8.1 Главное меню
Кнопки:
Создать встречу
Найти слот
Мой день
Моя неделя
Перенести встречу
Удалить встречу
Аккаунты
Календари
Контакты
Настройки
8.2 Сценарий "Создать встречу"
Шаги:
выбор способа:
текстом;
пошагово;
выбор календаря;
выбор даты через inline-календарь;
выбор времени;
выбор длительности;
выбор участников;
ввод названия;
ввод описания;
превью;
подтверждение.
8.3 Сценарий "Найти слот"
Пользователь указывает:
участников;
диапазон дат;
длительность.
Бот:
ищет общие окна;
показывает варианты кнопками;
после выбора предлагает создать событие.
8.4 Сценарий "Аккаунты"
Раздел:
Подключить аккаунт
Отключить аккаунт
Список аккаунтов
Синхронизировать контакты
Выбрать активные календари
Проверить статус подписок 9. Модель данных
9.1 users
id UUID PK
telegram_user_id BIGINT UNIQUE NOT NULL
telegram_username TEXT NULL
is_active BOOLEAN NOT NULL DEFAULT TRUE
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
9.2 exchange_accounts
id UUID PK
user_id UUID FK users(id)
tenant_id TEXT NULL
email TEXT NOT NULL
display_name TEXT NULL
access_token_encrypted TEXT NOT NULL
refresh_token_encrypted TEXT NOT NULL
token_expires_at TIMESTAMP NOT NULL
status TEXT NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
9.3 calendars
id UUID PK
user_id UUID FK users(id)
account_id UUID FK exchange_accounts(id)
external_calendar_id TEXT NOT NULL
name TEXT NOT NULL
is_active BOOLEAN NOT NULL DEFAULT TRUE
is_default BOOLEAN NOT NULL DEFAULT FALSE
is_mirror_enabled BOOLEAN NOT NULL DEFAULT TRUE
timezone TEXT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
9.4 contacts
id UUID PK
user_id UUID FK users(id)
account_id UUID FK exchange_accounts(id)
external_contact_id TEXT NULL
name TEXT NOT NULL
normalized_name TEXT NOT NULL
email TEXT NULL
phone TEXT NULL
source TEXT NOT NULL
merged_contact_key TEXT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
9.5 events
id UUID PK
user_id UUID FK users(id)
calendar_id UUID FK calendars(id)
external_event_id TEXT NOT NULL
sync_group_id UUID NOT NULL
role TEXT NOT NULL
status TEXT NOT NULL
title TEXT NOT NULL
description TEXT NULL
start_at TIMESTAMP NOT NULL
end_at TIMESTAMP NOT NULL
timezone TEXT NOT NULL
attendees_json JSONB NOT NULL DEFAULT '[]'
source_event_id UUID NULL
etag TEXT NULL
last_seen_change_key TEXT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
deleted_at TIMESTAMP NULL
role:
primary
mirror
9.6 sync_groups
id UUID PK
user_id UUID FK users(id)
primary_event_id UUID NULL
state TEXT NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
9.7 graph_subscriptions
id UUID PK
user_id UUID FK users(id)
account_id UUID FK exchange_accounts(id)
resource TEXT NOT NULL
external_subscription_id TEXT NOT NULL
expires_at TIMESTAMP NOT NULL
status TEXT NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
9.8 llm_sessions
id UUID PK
user_id UUID FK users(id)
task_type TEXT NOT NULL
context_json JSONB NOT NULL
expires_at TIMESTAMP NOT NULL
created_at TIMESTAMP NOT NULL
updated_at TIMESTAMP NOT NULL
9.9 operation_logs
id UUID PK
user_id UUID FK users(id)
entity_type TEXT NOT NULL
entity_id UUID NULL
operation TEXT NOT NULL
status TEXT NOT NULL
request_json JSONB NULL
response_json JSONB NULL
error_text TEXT NULL
created_at TIMESTAMP NOT NULL 10. API backend
10.1 Auth / Accounts
POST /api/v1/accounts/oauth/start
GET /api/v1/accounts/oauth/callback
GET /api/v1/accounts
POST /api/v1/accounts/{id}/refresh
DELETE /api/v1/accounts/{id}
10.2 Calendars
GET /api/v1/calendars
PATCH /api/v1/calendars/{id}
POST /api/v1/calendars/sync
10.3 Contacts
GET /api/v1/contacts
GET /api/v1/contacts/search?q=...
POST /api/v1/contacts/sync
10.4 Events
POST /api/v1/events/draft/parse
POST /api/v1/events/check-availability
POST /api/v1/events
PATCH /api/v1/events/{id}
DELETE /api/v1/events/{id}
GET /api/v1/events/day
GET /api/v1/events/week
POST /api/v1/events/find-slots
10.5 Webhooks
GET /api/v1/webhooks/graph — validation handshake
POST /api/v1/webhooks/graph — notifications
POST /api/v1/internal/subscriptions/renew 11. Алгоритмы
11.1 Алгоритм создания события
Получить draft из Telegram / LLM.
Проверить полноту обязательных полей.
Разрешить участников:
contact match;
fallback на ручной email.
Проверить доступность:
primary calendar;
all mirror calendars;
all attendees.
Если конфликт:
вычислить альтернативы;
показать варианты.
Если слот подтверждён:
создать primary event;
создать mirror events;
сохранить mapping;
записать лог операции.
11.2 Алгоритм переноса
Получить новый слот.
Проверить доступность всех сущностей.
Обновить primary event.
Обновить mirror events.
При частичной ошибке:
retry;
если неуспех, перевести sync_group в degraded;
уведомить пользователя.
11.3 Алгоритм удаления
Найти sync_group.
Удалить primary event.
Удалить mirror events.
Пометить записи deleted.
Записать лог.
11.4 Алгоритм подбора слотов
Вход:
participants;
date range;
duration;
optional preferred times.
Шаги:
Получить free/busy по всем объектам.
Построить временную сетку.
Исключить занятые интервалы.
Найти пересечения свободных окон нужной длины.
Отсортировать:
сначала ближайшие к пожеланию пользователя;
затем по рабочим часам;
затем по минимальному числу пограничных пересечений.
Вернуть набор предложений. 12. Обработка ошибок
12.1 Типы ошибок
AuthExpiredError
InsufficientPermissionsError
CalendarConflictError
AttendeeBusyError
ContactNotFoundError
AmbiguousContactError
MirrorSyncError
WebhookValidationError
SubscriptionExpiredError
LLMParsingError
ExternalRateLimitError
12.2 Правила реакции
ошибки Graph 401/403 → предложить переподключить аккаунт;
конфликт слота → показать альтернативы;
неоднозначный контакт → попросить выбрать из списка;
неполный разбор LLM → добрать поля через диалог;
ошибка зеркалирования → статус degraded + уведомление.
Microsoft Graph рекомендует учитывать ограничения, жизненный цикл подписок и корректную обработку ошибок/повторов. 13. Логирование и наблюдаемость
Логировать:
входящие Telegram update;
вызовы LLM;
вызовы Graph API;
webhook notifications;
операции создания/обновления/удаления;
конфликты слотов;
ошибки авторизации;
попытки восстановления sync-group.
Метрики:
число подключённых аккаунтов;
число активных календарей;
число созданных событий;
число конфликтов;
число деградированных sync-group;
latency Graph / LLM;
процент успешных renew webhook subscriptions. 14. Безопасность
Все секреты только через env / secret store.
Токены Exchange шифровать на уровне приложения.
OpenRouter API key хранить отдельно.
Ограничить доступ к боту по whitelist или по self-registration с подтверждением.
Webhook endpoint только по HTTPS.
CSRF для OAuth state обязателен.
Не логировать access token, refresh token и полный PII без маскирования. 15. Docker Compose
Пример состава:
version: "3.9"

services:
bot:
build: ./bot
env_file: .env
depends_on: - api - redis

api:
build: ./api
env_file: .env
depends_on: - postgres - redis

worker:
build: ./worker
env_file: .env
depends_on: - postgres - redis

postgres:
image: postgres:16
environment:
POSTGRES_DB: calendar_bot
POSTGRES_USER: calendar_bot
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
volumes: - postgres_data:/var/lib/postgresql/data

redis:
image: redis:7

nginx:
image: nginx:stable
depends_on: - api - bot
ports: - "80:80" - "443:443"

volumes:
postgres_data: 16. FSM Telegram-сценариев
Состояния для create flow:
idle
create.choose_mode
create.choose_calendar
create.choose_date
create.choose_time
create.choose_duration
create.choose_attendees
create.enter_title
create.enter_description
create.confirm
create.completed
Состояния для slot finding:
slot.enter_people
slot.enter_range
slot.enter_duration
slot.review_options 17. Acceptance Criteria
17.1 Аккаунты
пользователь может подключить минимум 2 Exchange-аккаунта;
токены успешно обновляются без ручного вмешательства до истечения refresh policy;
пользователь может отключить аккаунт.
17.2 Календари
пользователь видит список календарей из каждого аккаунта;
может выбрать, какие календари участвуют в зеркалировании.
17.3 Контакты
контакты подтягиваются из всех подключённых аккаунтов;
дубли по email объединяются;
поиск по имени и email работает.
17.4 Создание встреч
бот может создать primary event в выбранном календаре;
в остальных активных календарях создаются mirror events;
при конфликте показываются альтернативы;
участники учитываются при подборе слота.
17.5 Синхронизация
изменение primary event приводит к обновлению mirrors;
удаление primary event удаляет mirrors;
webhook renewal работает автоматически.
17.6 LLM
текстовые команды на русском корректно разбираются;
при нехватке данных бот задаёт уточнение;
backend не выполняет действие без валидации структуры и доступности слота.
