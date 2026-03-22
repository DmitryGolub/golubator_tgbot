# Golubator TG Bot

Телеграм-бот для работы с учениками, менторами, созвонами и регулярными уведомлениями.

## Зависимости

- Python 3.14
- uv
- PostgreSQL 16
- Redis

## Установка

1. Скопируйте `.env.sample` в `.env`.
2. Заполните `BOT_TOKEN`.
3. Установите зависимости:

```bash
uv sync
```

## Запуск проекта

Запуск бота:

```bash
uv run python -m src.main
```

Для локального запуска значения из `.env.sample` подходят как есть: `DB_HOST=localhost`, `REDIS_HOST=localhost`.

## Миграции

Применить миграции:

```bash
uv run alembic upgrade head
```

## Celery

Запуск worker:

```bash
uv run python -m src.scripts.celery_worker
```

Запуск beat:

```bash
uv run python -m src.scripts.celery_beat
```

## Docker Compose

1. Скопируйте `.env.sample` в `.env`.
2. Проверьте `BOT_TOKEN`.
3. Запустите:

```bash
docker compose up --build
```

`docker-compose.yaml` сам переопределяет `DB_HOST=db` и `REDIS_HOST=redis` внутри контейнеров, поэтому `.env` не нужно переписывать под compose.

## Тесты

Полный прогон:

```bash
uv run pytest
```

## Основной сценарий

1. Пользователь проходит `/start`.
2. Ментор создаёт созвон в меню `Созвоны`.
3. Ментор открывает список созвонов и нажимает `Начать созвон #...`.
4. После завершения ментор использует кнопку `Завершить активный созвон` или команду `/end_call`.
5. После завершения в меню созвонов доступна кнопка `Заполнить фидбек`.
