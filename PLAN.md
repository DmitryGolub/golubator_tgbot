# План E2E-тестирования golubator_tgbot

## Выбор MTProto-библиотеки

### Сравнение

| Критерий | Telethon | Pyrogram | tgintegration |
|--------|----------|----------|---------------|
| Отправка команд боту | `conv.send_message("/start")` — встроенный `Conversation` API | `app.send_message(bot, "/start")` — нужно вручную ждать ответ | Обёртка над Pyrogram, добавляет `await client.send_command_and_wait()` |
| Inline-кнопки | `message.click(index)` / `message.click(text=...)` — нативно | `app.request_callback_answer(chat_id, msg_id, callback_data)` — нужно знать callback_data | Наследует Pyrogram API |
| FSM-диалоги | `conv.send_message()` → `conv.get_response()` — последовательно, как тест | Ручная реализация через `app.get_history()` + sleep | Есть `await_response()` |
| Два аккаунта | Два `TelegramClient` — легко | Два `Client` — легко | Один клиент на тест |
| pytest-asyncio | Полная совместимость (`asyncio_mode="auto"`) | Полная совместимость | Зависит от Pyrogram |
| Зрелость | 7+ лет, 9k+ stars, активная разработка | 4k+ stars, менее активна | ~200 stars, нишевый проект |

### Решение: **Telethon**

**Причины:**
1. `Conversation` API идеально ложится на паттерн E2E-тестов: send → wait → assert → send → wait → assert
2. `message.click()` позволяет кликать inline-кнопки по тексту или индексу — не нужно знать callback_data
3. `conv.get_edit()` отслеживает edit сообщений (бот часто редактирует при клике inline-кнопок)
4. Наиболее зрелая библиотека с лучшей документацией

### Пример использования

```python
from telethon import TelegramClient

async def test_start_command(user_client: TelegramClient, bot_username: str):
    async with user_client.conversation(bot_username) as conv:
        await conv.send_message("/start")
        response = await conv.get_response()
        assert "Привет" in response.text or "Добро пожаловать" in response.text

        # Если бот отправляет меню вторым сообщением
        menu_msg = await conv.get_response()
        assert menu_msg.reply_markup is not None
```

---

## Глобальные чекбоксы

- [ ] **1. Инфраструктура** — Docker Compose test profile, `.env.test`, MTProto sessions
- [ ] **2. MTProto-клиент** — `TelegramTestClient` обёртка над Telethon
- [ ] **3. DB assertions** — read-only проверки PostgreSQL
- [ ] **4. Notion assertions** — read-only проверки Notion API
- [ ] **5. Setup helpers** — предустановка ролей (единственный write в БД)
- [ ] **6. Тесты: регистрация и авторизация**
- [ ] **7. Тесты: меню и RBAC**
- [ ] **8. Тесты: управление ролями**
- [ ] **9. Тесты: когорты**
- [ ] **10. Тесты: созвоны (Meetings)**
- [ ] **11. Тесты: опросы (Surveys)**
- [ ] **12. Тесты: триггеры и уведомления**
- [ ] **13. Тесты: синхронизация с Notion**
- [ ] **14. Тесты: статистика и отчёты**
- [ ] **15. Тесты: обновление пользователей**

---

## 1. Инфраструктура

### 1.1 Docker Compose profile `test`

Добавить profile `test` в существующий `docker-compose.yaml`. Тестовый стек использует **отдельную БД** (`botdb_test`), но **тот же dev BOT_TOKEN**.

```yaml
# docker-compose.yaml — дополнения
  db_test:
    image: postgres:16-alpine
    container_name: tg_bot.db_test
    environment:
      POSTGRES_DB: botdb_test
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "127.0.0.1:5433:5432"
    volumes:
      - db_test_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d botdb_test"]
      interval: 10s
      timeout: 5s
      retries: 5
    profiles:
      - test

  redis_test:
    image: redis:7-alpine
    container_name: tg_bot.redis_test
    ports:
      - "127.0.0.1:6381:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    profiles:
      - test

  migrations_test:
    <<: *app-base
    container_name: tg_bot.migrations_test
    command: ["alembic", "upgrade", "head"]
    env_file:
      - .env.test
    environment:
      DB_HOST: db_test
      REDIS_HOST: redis_test
    restart: "no"
    depends_on:
      db_test:
        condition: service_healthy
    profiles:
      - test

  bot_test:
    <<: *app-base
    container_name: tg_bot.bot_test
    env_file:
      - .env.test
    environment:
      DB_HOST: db_test
      REDIS_HOST: redis_test
    depends_on:
      migrations_test:
        condition: service_completed_successfully
      redis_test:
        condition: service_healthy
    profiles:
      - test

  celery_worker_test:
    <<: *app-base
    container_name: tg_bot.celery_worker_test
    command: ["python", "-m", "src.scripts.celery_worker"]
    env_file:
      - .env.test
    environment:
      DB_HOST: db_test
      REDIS_HOST: redis_test
    depends_on:
      migrations_test:
        condition: service_completed_successfully
      redis_test:
        condition: service_healthy
    profiles:
      - test

  celery_beat_test:
    <<: *app-base
    container_name: tg_bot.celery_beat_test
    command: ["python", "-m", "src.scripts.celery_beat"]
    env_file:
      - .env.test
    environment:
      DB_HOST: db_test
      REDIS_HOST: redis_test
    depends_on:
      migrations_test:
        condition: service_completed_successfully
      redis_test:
        condition: service_healthy
    profiles:
      - test

volumes:
  db_test_data:
```

- [ ] Добавить test-сервисы в `docker-compose.yaml`
- [ ] Добавить volume `db_test_data`

### 1.2 Файл `.env.test`

```env
BOT_TOKEN=<dev-bot-token>

LOG_LEVEL=DEBUG
LOG_FORMAT=dev

DB_NAME=botdb_test
DB_USER=postgres
DB_PASS=postgres
DB_HOST=localhost
DB_PORT=5433

REDIS_HOST=localhost
REDIS_PORT=6381

ADMIN_IDS=<account_1_telegram_id>

# Notion — тестовые базы данных (дубликаты prod баз)
NOTION_TOKEN=<test-notion-token>
NOTION_DATABASE_ID=<test-mentee-db-id>
NOTION_MENTOR_DB_ID=<test-mentor-db-id>
NOTION_MENTEE_DB_ID=<test-mentee-db-id>
NOTION_EVENT_DB_ID=<test-event-db-id>
NOTION_MENTEE_TEMPLATE_PAGE_ID=
NOTION_WEBHOOK_SECRET=<test-webhook-secret>

NOTION_PUSH_INTERVAL=10
NOTION_BACKUP_POLL_USERS_INTERVAL=300
NOTION_BACKUP_POLL_EVENTS_INTERVAL=300

# MTProto — два тестовых аккаунта
TELEGRAM_API_ID=<api-id>
TELEGRAM_API_HASH=<api-hash>
TEST_ACCOUNT_1_SESSION=account1
TEST_ACCOUNT_1_PHONE=+7XXXXXXXXXX
TEST_ACCOUNT_2_SESSION=account2
TEST_ACCOUNT_2_PHONE=+7XXXXXXXXXX

# Username dev-бота (без @)
TEST_BOT_USERNAME=<dev_bot_username>
```

- [ ] Создать `.env.test` с реальными credentials
- [ ] Добавить `.env.test` в `.gitignore`

### 1.3 MTProto session files

Telethon хранит авторизацию в `.session` файлах. Нужно один раз авторизовать оба аккаунта:

```python
# scripts/create_test_sessions.py
import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv
import os

load_dotenv(".env.test")

async def main():
    api_id = int(os.environ["TELEGRAM_API_ID"])
    api_hash = os.environ["TELEGRAM_API_HASH"]

    for name, phone_key in [
        ("account1", "TEST_ACCOUNT_1_PHONE"),
        ("account2", "TEST_ACCOUNT_2_PHONE"),
    ]:
        client = TelegramClient(f"tests/e2e/sessions/{name}", api_id, api_hash)
        await client.start(phone=os.environ[phone_key])
        print(f"Session {name} created for {os.environ[phone_key]}")
        await client.disconnect()

asyncio.run(main())
```

- [ ] Создать скрипт `scripts/create_test_sessions.py`
- [ ] Авторизовать два аккаунта, сохранить session-файлы в `tests/e2e/sessions/`
- [ ] Добавить `tests/e2e/sessions/*.session` в `.gitignore`

### 1.4 Makefile

```makefile
test-e2e-up:
	docker compose --profile test up -d --build

test-e2e-down:
	docker compose --profile test down

test-e2e-reset:
	docker compose --profile test down -v --remove-orphans

test-e2e:
	docker compose --profile test up -d --build
	uv run pytest tests/e2e/ -v --timeout=120
	docker compose --profile test down
```

- [ ] Добавить команды в Makefile

### 1.5 pyproject.toml

```toml
[tool.pytest.ini_options]
markers = [
    "e2e: End-to-end tests via MTProto (require running bot + DB)",
]

# Исключить e2e из обычного прогона
addopts = "--ignore=tests/e2e"
```

Зависимости:

```
uv add --dev telethon cryptg python-dotenv
```

- `telethon` — MTProto клиент
- `cryptg` — ускорение шифрования для Telethon
- `python-dotenv` — загрузка `.env.test`

- [ ] Обновить `pyproject.toml` (markers, addopts)
- [ ] Установить зависимости

### 1.6 Fixture lifecycle — очистка между тест-сьютами

Между тестовыми сьютами (модулями) выполняется TRUNCATE всех таблиц + FLUSH Redis. Это делается **в conftest.py через fixture**, не внутри тестов.

Notion-страницы очищаются через архивацию (Notion API `PATCH /pages/{id}` с `archived: true`).

- [ ] Реализовать cleanup в conftest.py

---

## 2. MTProto-клиент (`TelegramTestClient`)

### Файл: `tests/e2e/helpers/telegram_client.py`

```python
from __future__ import annotations

import asyncio
from telethon import TelegramClient
from telethon.tl.custom import Message


class TelegramTestClient:
    """Обёртка над Telethon для удобства E2E-тестов."""

    def __init__(self, client: TelegramClient, bot_username: str):
        self._client = client
        self._bot = bot_username
        self._conv = None

    async def send_command(self, command: str, timeout: float = 15) -> Message:
        """Отправить команду боту и получить первый ответ."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await conv.send_message(command)
            return await conv.get_response()

    async def send_command_multi(
        self, command: str, count: int = 2, timeout: float = 15
    ) -> list[Message]:
        """Отправить команду и получить несколько ответов (напр. welcome + menu)."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await conv.send_message(command)
            responses = []
            for _ in range(count):
                try:
                    responses.append(await conv.get_response())
                except asyncio.TimeoutError:
                    break
            return responses

    async def click_button(
        self, message: Message, text: str | None = None, index: int | None = None,
        timeout: float = 15,
    ) -> Message:
        """Кликнуть inline-кнопку и получить отредактированное сообщение."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            if text is not None:
                await message.click(text=text)
            elif index is not None:
                await message.click(index)
            else:
                raise ValueError("Specify text or index")
            return await conv.get_edit()

    async def send_text_in_fsm(self, text: str, timeout: float = 15) -> Message:
        """Отправить текст в FSM-диалоге и получить следующий вопрос/подтверждение."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            await conv.send_message(text)
            return await conv.get_response()

    async def fsm_dialog(
        self, steps: list[str], timeout: float = 15
    ) -> list[Message]:
        """Провести FSM-диалог: отправить серию сообщений, собрать все ответы."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            responses = []
            for step in steps:
                await conv.send_message(step)
                responses.append(await conv.get_response())
            return responses

    async def wait_for_message(self, timeout: float = 30) -> Message:
        """Ждать входящего сообщения от бота (для уведомлений/триггеров)."""
        async with self._client.conversation(self._bot, timeout=timeout) as conv:
            return await conv.get_response()

    async def get_last_messages(self, limit: int = 5) -> list[Message]:
        """Получить последние сообщения из чата с ботом."""
        return await self._client.get_messages(self._bot, limit=limit)

    @property
    def raw(self) -> TelegramClient:
        return self._client
```

**Методы:**

| Метод | Назначение | Используется в |
|-------|-----------|----------------|
| `send_command(cmd)` | Отправить `/start`, `/menu` и т.д. | Все тесты |
| `send_command_multi(cmd, n)` | Получить N ответов (welcome + menu) | Регистрация |
| `click_button(msg, text=)` | Кликнуть inline-кнопку по тексту | Навигация по меню, RBAC |
| `send_text_in_fsm(text)` | Ответить в FSM-диалоге | Создание созвонов, опросов |
| `fsm_dialog(steps)` | Последовательный FSM-диалог | Длинные формы |
| `wait_for_message(timeout)` | Ждать уведомление от бота | Триггеры |
| `get_last_messages(limit)` | Проверить историю чата | Отладка |

- [ ] Создать `tests/e2e/helpers/telegram_client.py`
- [ ] Написать unit-тесты на `TelegramTestClient` (опционально)

---

## 3. DB assertions (read-only)

### Файл: `tests/e2e/helpers/db_assertions.py`

Прямое подключение к тестовой PostgreSQL через `asyncpg` (не через ORM — чтобы не тянуть зависимости приложения). Все запросы — SELECT only.

```python
import asyncpg
from typing import Any


class DBAssertions:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM iam.users WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None

    async def assert_user_exists(self, telegram_id: int) -> dict[str, Any]:
        user = await self.get_user(telegram_id)
        assert user is not None, f"User {telegram_id} not found in DB"
        return user

    async def assert_user_has_role(self, telegram_id: int, role_name: str):
        row = await self._pool.fetchrow(
            """
            SELECT r.name FROM iam.users u
            JOIN iam.roles r ON u.role_id = r.id
            WHERE u.telegram_id = $1
            """,
            telegram_id,
        )
        assert row is not None, f"User {telegram_id} has no role"
        assert row["name"] == role_name, f"Expected role {role_name}, got {row['name']}"

    async def get_meeting(self, meeting_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM meetings.meetings WHERE id = $1", meeting_id
        )
        return dict(row) if row else None

    async def get_meetings_for_mentor(self, mentor_telegram_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM meetings.meetings WHERE mentor_telegram_id = $1 ORDER BY created_at DESC",
            mentor_telegram_id,
        )
        return [dict(r) for r in rows]

    async def assert_meeting_exists(
        self, mentor_id: int, student_id: int
    ) -> dict[str, Any]:
        row = await self._pool.fetchrow(
            """
            SELECT * FROM meetings.meetings
            WHERE mentor_telegram_id = $1 AND student_telegram_id = $2
            ORDER BY created_at DESC LIMIT 1
            """,
            mentor_id, student_id,
        )
        assert row is not None, f"Meeting not found for mentor={mentor_id}, student={student_id}"
        return dict(row)

    async def assert_meeting_call_status(self, meeting_id: int, expected_status: str):
        row = await self._pool.fetchrow(
            "SELECT call_status FROM meetings.meetings WHERE id = $1", meeting_id
        )
        assert row is not None, f"Meeting {meeting_id} not found"
        assert row["call_status"] == expected_status

    async def get_survey_session(self, session_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM surveys.survey_sessions WHERE id = $1", session_id
        )
        return dict(row) if row else None

    async def assert_survey_completed(self, user_telegram_id: int) -> dict[str, Any]:
        row = await self._pool.fetchrow(
            """
            SELECT * FROM surveys.survey_sessions
            WHERE respondent_telegram_id = $1 AND status = 'completed'
            ORDER BY created_at DESC LIMIT 1
            """,
            user_telegram_id,
        )
        assert row is not None, f"No completed survey for user {user_telegram_id}"
        return dict(row)

    async def get_survey_answers(self, session_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM surveys.survey_answers WHERE session_id = $1",
            session_id,
        )
        return [dict(r) for r in rows]

    async def get_trigger_rule(self, rule_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM triggers.trigger_rules WHERE id = $1", rule_id
        )
        return dict(row) if row else None

    async def get_trigger_executions(self, rule_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            "SELECT * FROM triggers.trigger_executions WHERE rule_id = $1 ORDER BY created_at DESC",
            rule_id,
        )
        return [dict(r) for r in rows]

    async def get_user_cohorts(self, telegram_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            """
            SELECT uc.*, c.type, c.value FROM integrations.user_cohorts uc
            JOIN integrations.cohorts c ON uc.cohort_id = c.id
            WHERE uc.user_telegram_id = $1
            """,
            telegram_id,
        )
        return [dict(r) for r in rows]

    async def get_mentee(self, telegram_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM iam.mentees WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None

    async def get_mentor(self, telegram_id: int) -> dict[str, Any] | None:
        row = await self._pool.fetchrow(
            "SELECT * FROM iam.mentors WHERE telegram_id = $1", telegram_id
        )
        return dict(row) if row else None

    async def get_roles(self) -> list[dict]:
        rows = await self._pool.fetch("SELECT * FROM iam.roles ORDER BY name")
        return [dict(r) for r in rows]

    async def get_role_permissions(self, role_id: int) -> list[dict]:
        rows = await self._pool.fetch(
            """
            SELECT p.* FROM iam.permissions p
            JOIN iam.role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = $1
            """,
            role_id,
        )
        return [dict(r) for r in rows]
```

- [ ] Создать `tests/e2e/helpers/db_assertions.py`

---

## 4. Notion assertions (read-only)

### Файл: `tests/e2e/helpers/notion_assertions.py`

```python
from notion_client import AsyncClient


class NotionAssertions:
    def __init__(self, client: AsyncClient):
        self._client = client

    async def get_page(self, page_id: str) -> dict:
        return await self._client.pages.retrieve(page_id=page_id)

    async def assert_page_property(
        self, page_id: str, property_name: str, expected_value: str
    ):
        page = await self.get_page(page_id)
        props = page["properties"]
        assert property_name in props, f"Property {property_name} not found"
        # Извлечение значения зависит от типа property
        prop = props[property_name]
        actual = self._extract_value(prop)
        assert actual == expected_value, f"Expected {expected_value}, got {actual}"

    async def find_page_by_telegram_id(
        self, database_id: str, telegram_id: int
    ) -> dict | None:
        result = await self._client.databases.query(
            database_id=database_id,
            filter={"property": "Telegram ID", "number": {"equals": telegram_id}},
        )
        pages = result.get("results", [])
        return pages[0] if pages else None

    async def assert_page_exists_for_user(
        self, database_id: str, telegram_id: int
    ) -> dict:
        page = await self.find_page_by_telegram_id(database_id, telegram_id)
        assert page is not None, f"Notion page not found for telegram_id={telegram_id}"
        return page

    async def cleanup_test_pages(self, database_id: str, telegram_ids: list[int]):
        """Архивировать тестовые страницы по telegram_id."""
        for tid in telegram_ids:
            page = await self.find_page_by_telegram_id(database_id, tid)
            if page:
                await self._client.pages.update(page_id=page["id"], archived=True)

    @staticmethod
    def _extract_value(prop: dict) -> str:
        """Извлечь текстовое значение из Notion property."""
        t = prop["type"]
        if t == "title":
            return prop["title"][0]["plain_text"] if prop["title"] else ""
        elif t == "rich_text":
            return prop["rich_text"][0]["plain_text"] if prop["rich_text"] else ""
        elif t == "number":
            return str(prop["number"]) if prop["number"] is not None else ""
        elif t == "select":
            return prop["select"]["name"] if prop["select"] else ""
        elif t == "multi_select":
            return ", ".join(o["name"] for o in prop["multi_select"])
        return str(prop.get(t, ""))
```

- [ ] Создать `tests/e2e/helpers/notion_assertions.py`

---

## 5. Setup helpers

### Файл: `tests/e2e/helpers/setup.py`

Единственные write-операции в БД — только в fixtures. Минимальный набор.

```python
import asyncpg


class TestSetup:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def set_user_role(self, telegram_id: int, role_name: str):
        """Назначить роль пользователю. Используется ТОЛЬКО в fixture setup."""
        await self._pool.execute(
            """
            UPDATE iam.users SET role_id = (
                SELECT id FROM iam.roles WHERE name = $1
            ) WHERE telegram_id = $2
            """,
            role_name, telegram_id,
        )

    async def ensure_mentor_record(self, telegram_id: int):
        """Создать запись Mentor, если не существует."""
        existing = await self._pool.fetchrow(
            "SELECT id FROM iam.mentors WHERE telegram_id = $1", telegram_id
        )
        if not existing:
            await self._pool.execute(
                "INSERT INTO iam.mentors (telegram_id) VALUES ($1)", telegram_id
            )

    async def ensure_mentee_record(self, telegram_id: int, mentor_telegram_id: int | None = None):
        """Создать запись Mentee, если не существует."""
        existing = await self._pool.fetchrow(
            "SELECT id FROM iam.mentees WHERE telegram_id = $1", telegram_id
        )
        if not existing:
            mentor_id = None
            if mentor_telegram_id:
                row = await self._pool.fetchrow(
                    "SELECT id FROM iam.mentors WHERE telegram_id = $1",
                    mentor_telegram_id,
                )
                mentor_id = row["id"] if row else None
            await self._pool.execute(
                "INSERT INTO iam.mentees (telegram_id, mentor_id) VALUES ($1, $2)",
                telegram_id, mentor_id,
            )

    async def truncate_all(self):
        """Очистить все таблицы между тест-сьютами."""
        schemas = ["triggers", "surveys", "meetings", "integrations", "iam", "public"]
        for schema in schemas:
            tables = await self._pool.fetch(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname = $1 AND tablename != 'alembic_version'
                """,
                schema,
            )
            for table in tables:
                await self._pool.execute(
                    f'TRUNCATE TABLE {schema}."{table["tablename"]}" CASCADE'
                )

    async def flush_redis(self, redis_url: str):
        """Сбросить Redis (FSM state, permission cache)."""
        import redis.asyncio as aioredis
        r = aioredis.from_url(redis_url)
        await r.flushall()
        await r.aclose()
```

- [ ] Создать `tests/e2e/helpers/setup.py`

---

## 6. conftest.py

### Файл: `tests/e2e/conftest.py`

```python
import asyncio
import os
import pytest
import asyncpg
from telethon import TelegramClient
from notion_client import AsyncClient as NotionAsyncClient
from dotenv import load_dotenv

from tests.e2e.helpers.telegram_client import TelegramTestClient
from tests.e2e.helpers.db_assertions import DBAssertions
from tests.e2e.helpers.notion_assertions import NotionAssertions
from tests.e2e.helpers.setup import TestSetup

load_dotenv(".env.test")

# ── Telegram config ──
API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
BOT_USERNAME = os.environ["TEST_BOT_USERNAME"]
SESSION_DIR = "tests/e2e/sessions"

ACCOUNT_1_SESSION = os.environ["TEST_ACCOUNT_1_SESSION"]
ACCOUNT_2_SESSION = os.environ["TEST_ACCOUNT_2_SESSION"]

# ── DB config ──
DB_DSN = (
    f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASS']}"
    f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
)

REDIS_URL = f"redis://{os.environ['REDIS_HOST']}:{os.environ['REDIS_PORT']}/0"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def db_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(DB_DSN)
    yield pool
    await pool.close()


@pytest.fixture(scope="session")
async def db(db_pool) -> DBAssertions:
    return DBAssertions(db_pool)


@pytest.fixture(scope="session")
async def setup(db_pool) -> TestSetup:
    return TestSetup(db_pool)


@pytest.fixture(scope="session")
async def notion() -> NotionAssertions:
    client = NotionAsyncClient(auth=os.environ["NOTION_TOKEN"])
    yield NotionAssertions(client)
    await client.aclose()


@pytest.fixture(scope="session")
async def account1() -> TelegramTestClient:
    client = TelegramClient(
        f"{SESSION_DIR}/{ACCOUNT_1_SESSION}", API_ID, API_HASH
    )
    await client.connect()
    yield TelegramTestClient(client, BOT_USERNAME)
    await client.disconnect()


@pytest.fixture(scope="session")
async def account2() -> TelegramTestClient:
    client = TelegramClient(
        f"{SESSION_DIR}/{ACCOUNT_2_SESSION}", API_ID, API_HASH
    )
    await client.connect()
    yield TelegramTestClient(client, BOT_USERNAME)
    await client.disconnect()


@pytest.fixture(autouse=True, scope="module")
async def cleanup_between_modules(setup):
    """Очистка БД и Redis между модулями тестов."""
    yield
    await setup.truncate_all()
    await setup.flush_redis(REDIS_URL)
```

- [ ] Создать `tests/e2e/conftest.py`

---

## 7. Структура файлов

```
tests/
  e2e/
    conftest.py
    sessions/                    # .gitignore'd
      account1.session
      account2.session
    helpers/
      __init__.py
      telegram_client.py         # TelegramTestClient
      db_assertions.py           # DBAssertions (read-only)
      notion_assertions.py       # NotionAssertions (read-only)
      setup.py                   # TestSetup (write в fixtures)
    test_01_registration.py
    test_02_menu_rbac.py
    test_03_roles.py
    test_04_cohorts.py
    test_05_meetings.py
    test_06_surveys.py
    test_07_triggers.py
    test_08_notion_sync.py
    test_09_statistics.py
    test_10_user_updates.py
scripts/
  create_test_sessions.py
```

Нумерация файлов гарантирует порядок выполнения (pytest запускает модули по алфавиту).

---

## 8. Тестовые сценарии — детальные шаги

### 8.1 Регистрация и авторизация (`test_01_registration.py`)

- [ ] `test_start_account1` — `/start` первым аккаунтом
  - [ ] Шаг: `account1.send_command_multi("/start", count=2)`
  - [ ] Assert bot: первый ответ содержит приветствие (UiText `start.welcome`)
  - [ ] Assert bot: второй ответ — меню с inline-кнопками (если есть права)
  - [ ] DB check: `db.assert_user_exists(ACCOUNT_1_TG_ID)` — user записан
  - [ ] DB check: `user["username"]` совпадает с Telegram username
- [ ] `test_start_account2` — `/start` вторым аккаунтом
  - [ ] Шаг: `account2.send_command_multi("/start", count=2)`
  - [ ] Assert bot: приветствие получено
  - [ ] DB check: `db.assert_user_exists(ACCOUNT_2_TG_ID)`
- [ ] `test_notion_link_on_start` — связывание с Notion при `/start`
  - [ ] DB check: `db.get_mentee(ACCOUNT_2_TG_ID)` → `notion_page_id` не None (если placeholder был)
  - [ ] Notion check: `notion.assert_page_exists_for_user(MENTEE_DB_ID, ACCOUNT_2_TG_ID)`

### 8.2 Меню и RBAC (`test_02_menu_rbac.py`)

- [ ] **Setup fixture**: `setup.set_user_role(ACCOUNT_1_TG_ID, "admin")`
- [ ] `test_admin_full_menu` — admin видит все кнопки
  - [ ] Шаг: `account1.send_command("/menu")`
  - [ ] Assert bot: сообщение содержит reply_markup
  - [ ] Assert bot: кнопки включают "Пользователи", "Когорты", "Опросы", "Триггеры", "Роли"
- [ ] `test_student_limited_menu` — student видит ограниченное меню
  - [ ] Шаг: `account2.send_command("/menu")`
  - [ ] Assert bot: reply_markup содержит только student-кнопки ("Обо мне", "Мои созвоны")
  - [ ] Assert bot: НЕ содержит "Пользователи", "Когорты", "Роли"
- [ ] `test_student_cannot_access_admin` — student не может выполнить admin-действие
  - [ ] Шаг: account2 кликает на callback_data админской кнопки (если каким-то образом получил)
  - [ ] Assert bot: PermissionFilter отклоняет — бот не отвечает или отвечает ошибкой

### 8.3 Управление ролями (`test_03_roles.py`)

- [ ] **Setup fixture**: account1 — admin
- [ ] `test_create_role_via_bot` — создать роль через бота
  - [ ] Шаг: account1 → `/menu` → кнопка "Роли" → "Создать роль"
  - [ ] Шаг: FSM-диалог — ввести имя `test_role`, display_name `Тестовая роль`
  - [ ] DB check: `SELECT * FROM iam.roles WHERE name = 'test_role'` — запись есть
- [ ] `test_assign_permissions_to_role` — назначить пермишены
  - [ ] Шаг: account1 → выбрать роль `test_role` → "Пермишены" → выбрать `view_own_info`
  - [ ] DB check: `role_permissions` содержит запись
- [ ] `test_assign_role_to_user` — назначить роль аккаунту 2
  - [ ] Шаг: account1 → "Пользователи" → найти account2 → "Изменить роль" → выбрать `test_role`
  - [ ] DB check: `db.assert_user_has_role(ACCOUNT_2_TG_ID, "test_role")`
- [ ] `test_menu_updates_after_role_change` — меню обновилось
  - [ ] Шаг: `account2.send_command("/menu")`
  - [ ] Assert bot: кнопки соответствуют пермишенам `test_role`

### 8.4 Когорты (`test_04_cohorts.py`)

- [ ] **Setup fixture**: account1 — admin
- [ ] `test_create_cohort_type` — создать тип когорты
  - [ ] Шаг: account1 → `/menu` → "Когорты" → "Создать тип" → FSM: ввести тип и опции
  - [ ] DB check: `SELECT * FROM integrations.cohorts WHERE type = '...'` — записи есть
- [ ] `test_assign_user_to_cohort` — назначить аккаунт 2 в когорту
  - [ ] Шаг: account1 → "Пользователи" → account2 → "Когорта" → выбрать значение
  - [ ] DB check: `db.get_user_cohorts(ACCOUNT_2_TG_ID)` — содержит когорту
- [ ] `test_cohort_synced_to_notion` — синхронизация с Notion
  - [ ] Ожидание: подождать push interval (~10 сек в тесте)
  - [ ] Notion check: страница пользователя содержит обновлённую когорту
- [ ] `test_stage_transition_created` — StageTransition записан при смене когорты
  - [ ] DB check: `SELECT * FROM integrations.stage_transitions WHERE user_telegram_id = $1`

### 8.5 Созвоны (`test_05_meetings.py`)

- [ ] **Setup fixture**: account1 — mentor (роль + запись в `iam.mentors`), account2 — mentee
- [ ] `test_create_meeting_fsm` — FSM-диалог создания созвона
  - [ ] Шаг: account1 → `/menu` → "Созвоны" → "Создать" → FSM:
    - Выбрать ученика (account2)
    - Выбрать тип созвона
    - Ввести описание
    - Ввести дату
    - Ввести время
    - Ввести ссылку
  - [ ] Assert bot: подтверждение "Созвон создан"
  - [ ] DB check: `db.assert_meeting_exists(ACCOUNT_1_TG_ID, ACCOUNT_2_TG_ID)`
  - [ ] DB check: meeting.call_status = `'запланирован'`
- [ ] `test_start_call` — начать звонок
  - [ ] Шаг: account1 → выбрать созвон → "Начать звонок"
  - [ ] DB check: meeting.call_status = `'идёт'`
- [ ] `test_end_call` — завершить звонок
  - [ ] Шаг: account1 → "Завершить звонок" (или `/end_call`)
  - [ ] DB check: `db.assert_meeting_call_status(meeting_id, 'завершён')`
  - [ ] DB check: `completed_at` is not None
- [ ] `test_meeting_synced_to_notion` — синхронизация с Notion
  - [ ] Ожидание: push interval
  - [ ] Notion check: `notion.assert_page_exists_for_user(EVENT_DB_ID, ...)` — meeting в Notion

### 8.6 Опросы (`test_06_surveys.py`)

- [ ] **Setup fixture**: account1 — admin
- [ ] `test_create_survey_template` — создать шаблон опроса
  - [ ] Шаг: account1 → `/menu` → "Опросы" → "Создать шаблон" → FSM:
    - Ввести название
    - Добавить вопрос (текстовый)
    - Добавить вопрос (шкала)
    - Добавить вопрос (выбор из вариантов + ввести варианты)
    - Подтвердить
  - [ ] DB check: `SELECT * FROM surveys.survey_templates WHERE name = '...'`
  - [ ] DB check: `SELECT * FROM surveys.survey_questions WHERE template_id = ...` — 3 вопроса
  - [ ] DB check: `SELECT * FROM surveys.survey_question_options` — варианты для 3-го вопроса
- [ ] `test_student_takes_survey` — ученик проходит опрос
  - [ ] **Предусловие**: отправить опрос аккаунту 2 (через триггер или ручной вызов)
  - [ ] Шаг: account2 получает сообщение с опросом → кликает "Начать"
  - [ ] Шаг: FSM-диалог — отвечает на каждый вопрос
  - [ ] Assert bot: "Спасибо, опрос завершён" (или аналогичное)
  - [ ] DB check: `db.assert_survey_completed(ACCOUNT_2_TG_ID)`
  - [ ] DB check: `db.get_survey_answers(session_id)` — 3 ответа

### 8.7 Триггеры и уведомления (`test_07_triggers.py`)

- [ ] **Setup fixture**: account1 — admin
- [ ] `test_create_trigger_rule` — создать триггер
  - [ ] Шаг: account1 → `/menu` → "Триггеры" → "Создать" → FSM:
    - Тип: `manual`
    - Действие: `send_message` / `send_survey`
    - Текст сообщения
    - Получатели (все / по когорте / конкретный пользователь)
  - [ ] DB check: `SELECT * FROM triggers.trigger_rules` — запись создана
- [ ] `test_manual_trigger_sends_message` — ручная отправка
  - [ ] Шаг: account1 → триггер → "Отправить вручную"
  - [ ] Assert bot (account2): `account2.wait_for_message()` — получает сообщение
  - [ ] DB check: `db.get_trigger_executions(rule_id)` — status = `'sent'`
- [ ] `test_trigger_call_ended_sends_survey` — триггер по завершению звонка
  - [ ] Предусловие: создать триггер типа `call_ended` → действие `send_survey`
  - [ ] Шаг: account1 завершает звонок
  - [ ] Assert bot (account2): получает опрос
  - [ ] DB check: trigger_executions записан
- [ ] `test_trigger_with_delay` — отложенная отправка
  - [ ] Создать триггер с `delay_seconds = 15`
  - [ ] Шаг: сработать триггер
  - [ ] Assert: account2 НЕ получает сообщение сразу (timeout 5 сек — TimeoutError)
  - [ ] Assert: account2 получает сообщение через ~15 сек

### 8.8 Синхронизация с Notion (`test_08_notion_sync.py`)

- [ ] `test_push_user_to_notion` — данные пользователя в Notion
  - [ ] Предусловие: user создан через `/start`
  - [ ] Ожидание: push interval
  - [ ] Notion check: страница существует, telegram_id совпадает
- [ ] `test_webhook_updates_db` — webhook → обновление БД
  - [ ] Шаг: отправить HTTP POST на `http://localhost:8080/api/webhooks/notion/mentors` с телом Notion page
  - [ ] DB check: данные обновились в `iam.mentors`
- [ ] `test_anti_echo` — push не вызывает циклический webhook
  - [ ] Шаг: обновить данные через бота → push в Notion
  - [ ] Проверка: `synced_at >= last_edited_time` → повторный webhook скипнут
  - [ ] DB check: данные не перезаписаны повторно (проверить `updated_at` не изменился)
- [ ] `test_backup_pull` — backup polling обновляет данные
  - [ ] Шаг: вручную изменить страницу в Notion (через API)
  - [ ] Ожидание: backup poll interval
  - [ ] DB check: данные обновились

### 8.9 Статистика и отчёты (`test_09_statistics.py`)

- [ ] **Setup fixture**: account1 — mentor с несколькими завершёнными созвонами
- [ ] `test_mentor_stats_display` — просмотр статистики
  - [ ] Шаг: account1 → `/menu` → "Обо мне"
  - [ ] Assert bot: сообщение содержит "Созвоны: N", "Опросы заполнено: N"
  - [ ] DB cross-check: `SELECT COUNT(*) FROM meetings.meetings WHERE mentor_telegram_id = $1` совпадает с отображаемым
- [ ] `test_admin_mentor_stats` — admin просматривает статистику менторов
  - [ ] Шаг: account1 (admin) → "Статистика менторов"
  - [ ] Assert bot: список менторов со статистикой

### 8.10 Обновление пользователей (`test_10_user_updates.py`)

- [ ] **Setup fixture**: account1 — admin/mentor, account2 — mentee
- [ ] `test_change_mentee_mentor` — сменить ментора у ученика
  - [ ] Шаг: account1 → "Пользователи" → account2 → "Изменить ментора" → выбрать другого
  - [ ] DB check: `db.get_mentee(ACCOUNT_2_TG_ID)["mentor_id"]` обновлён
- [ ] `test_mentee_change_synced_to_notion` — изменение ментора синхронизировано
  - [ ] Ожидание: push interval
  - [ ] Notion check: страница mentee обновлена
- [ ] `test_update_user_info` — изменить информацию о пользователе
  - [ ] Шаг: account1 → "Пользователи" → account2 → FSM-диалог обновления
  - [ ] DB check: данные обновились

---

## 9. Proof of Concept — полный пример одного теста

```python
# tests/e2e/test_01_registration.py

import os
import pytest
from tests.e2e.helpers.telegram_client import TelegramTestClient
from tests.e2e.helpers.db_assertions import DBAssertions

ACCOUNT_1_TG_ID = int(os.environ.get("TEST_ACCOUNT_1_TG_ID", "0"))


async def test_start_command_registers_user(
    account1: TelegramTestClient,
    db: DBAssertions,
):
    """
    /start → бот отвечает приветствием → User записан в БД.
    Все действия через бота, БД только для проверки.
    """
    # 1. Отправить /start через MTProto
    responses = await account1.send_command_multi("/start", count=2)

    # 2. Проверить ответ бота
    assert len(responses) >= 1, "Bot did not respond to /start"
    welcome = responses[0]
    assert welcome.text is not None
    # Бот использует UiText start.welcome — содержит имя пользователя
    assert len(welcome.text) > 0

    # 3. Если есть права — второе сообщение с меню
    if len(responses) >= 2:
        menu_msg = responses[1]
        assert menu_msg.reply_markup is not None, "Menu should have inline keyboard"

    # 4. Read-only проверка БД
    user = await db.assert_user_exists(ACCOUNT_1_TG_ID)
    assert user["telegram_id"] == ACCOUNT_1_TG_ID
    assert user["username"] is not None
```

---

## 10. Зависимости

```bash
uv add --dev telethon cryptg python-dotenv asyncpg
```

| Пакет | Назначение |
|-------|-----------|
| `telethon` | MTProto-клиент для отправки команд и чтения ответов |
| `cryptg` | Ускорение шифрования Telethon (опционально, но рекомендуется) |
| `python-dotenv` | Загрузка `.env.test` в conftest |
| `asyncpg` | Прямое подключение к PostgreSQL для read-only проверок |

`notion-client` уже есть в основных зависимостях.

---

## 11. Порядок реализации

1. **Инфраструктура** (docker-compose test profile, .env.test, sessions) — фундамент
2. **Хелперы** (TelegramTestClient, DBAssertions, NotionAssertions, TestSetup) — инструменты
3. **conftest.py** — связка всех хелперов через fixtures
4. **PoC**: `test_01_registration.py` — один рабочий тест от начала до конца
5. **Остальные тесты** — по порядку нумерации файлов (02→10)
6. **CI-конфигурация** — Makefile, pyproject.toml markers

---

## Verification checklist

- [x] Покрывает все 10 групп сценариев (8.1–8.10)
- [x] Все действия через бота, БД только read-only (кроме setup ролей в fixtures)
- [x] Каждый сценарий: шаги через бота → expected bot response → DB SELECT check → Notion GET check
- [x] Описана инфраструктура: docker-compose test profile, .env.test, session files
- [x] Список зависимостей: telethon, cryptg, python-dotenv, asyncpg
- [x] Makefile команды: `test-e2e-up`, `test-e2e-down`, `test-e2e-reset`, `test-e2e`
- [x] Proof of concept: полный пример `test_start_command_registers_user`
- [x] Двухуровневые чекбоксы: глобальные этапы (раздел "Глобальные чекбоксы") + локальные шаги внутри каждого раздела
