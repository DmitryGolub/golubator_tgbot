# Golubator TG Bot

Телеграм-бот для работы с учениками, менторами, созвонами, опросами и регулярными уведомлениями.

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

## Запуск

### Бот

```bash
uv run python -m src.main
```

Для локального запуска значения из `.env.sample` подходят как есть: `DB_HOST=localhost`, `REDIS_HOST=localhost`.

### Celery (фоновые задачи)

```bash
uv run python -m src.scripts.celery_worker   # worker
uv run python -m src.scripts.celery_beat      # beat (периодические задачи)
```

### Миграции

```bash
uv run alembic upgrade head                           # применить
uv run alembic revision --autogenerate -m "описание"  # создать новую
```

## Docker Compose

```bash
cp .env.sample .env   # заполнить BOT_TOKEN
make init             # build + up + logs
```

Или напрямую:

```bash
docker compose up --build
```

`docker-compose.yaml` переопределяет `DB_HOST=db` и `REDIS_HOST=redis` внутри контейнеров, поэтому `.env` не нужно менять под compose.

Другие команды:

```bash
make up        # запустить контейнеры
make down      # остановить
make logs      # логи
make test      # pytest -q
make migrate   # alembic upgrade head
make clean     # down + удалить volumes и образы
```

## Тесты

```bash
uv run pytest                              # все тесты
uv run pytest tests/test_file.py -v        # один файл
uv run pytest -k "test_name" -v            # по имени
```

Тесты используют моки — реальная БД не нужна.

## Линтинг

```bash
uv run ruff check src/
uv run ruff format src/
```

## Основной сценарий

1. Пользователь проходит `/start` — регистрация в системе.
2. Ментор создаёт созвон через меню «Созвоны».
3. Ментор нажимает «Начать созвон» в списке созвонов.
4. После завершения — кнопка «Завершить активный созвон» или команда `/end_call`.
5. По завершению созвона срабатывают trigger-правила (отправка опроса ученику, уведомления и т.д.).
6. Ученик заполняет опрос через динамическую форму в боте.
7. Результаты можно экспортировать в xlsx на Яндекс.Диск.
