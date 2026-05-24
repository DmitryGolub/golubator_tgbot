# Техническая справка по проекту

Эта страница — короткая техническая выжимка для разработчиков и операторов. Пользовательские сценарии описаны в соседних документах из `docs/user/`.

## Как устроен сервис

- **Telegram-бот** запускается из `src/main.py` на `aiogram 3`: там создаются `Bot`, `Dispatcher`, Redis FSM storage, подключаются middleware и все feature-router'ы.
- **Состояние диалогов** хранится в Redis через `RedisStorage`; Redis также используется Celery как broker/backend и для отдельных lock/cursor-сценариев.
- **Данные** лежат в PostgreSQL. Доступ к БД построен на async SQLAlchemy 2.x и DAO-слое (`src/core/database.py`, `src/core/dao.py`, `src/dao/`).
- **Бизнес-логика** вынесена в `src/services/`: Notion sync, CalDAV, trigger-правила, опросы, отчеты и вспомогательные доменные операции.
- **Фоновые задачи** выполняются Celery (`src/celery_app.py`, `src/tasks/`): синхронизация Notion, автостарт/автозавершение созвонов, триггеры, регулярные опросы, CalDAV sync.
- **Доступы** строятся вокруг permissions: `PermissionFilter` проверяет права пользователя, а главное меню собирается динамически по доступным permissions.
- **Наблюдаемость** вынесена в compose-профиль `monitoring`: Prometheus, Loki, Promtail, Grafana, Blackbox exporter и cAdvisor. Сам бот отдает `/health` и `/metrics`.

## Что сделано хорошо

- **Централизованный bootstrap бота.** В `src/main.py` в одном месте видны создание бота, Redis FSM storage, middleware, routers, health server и polling. Это упрощает первичную навигацию по проекту.
- **Понятная модель доступа.** Меню и handlers завязаны на permissions, а не на жестко прошитые роли. Это удобнее расширять при появлении новых ролей и разделов.
- **Разделение синхронных пользовательских действий и фоновой работы.** Долгие операции — Notion, CalDAV, регулярные опросы, trigger rules — вынесены в Celery, поэтому bot layer не должен держать тяжелую работу в обработчиках Telegram-событий.
- **Async DB stack и миграции.** PostgreSQL используется через async SQLAlchemy, а схема управляется Alembic-миграциями; модели дополнительно разнесены по доменным схемам (`iam`, `meetings`, `surveys`, `triggers`, `integrations`).
- **Production-like инфраструктура.** В Dockerfile есть non-root runtime user, в compose описаны healthchecks, resource limits и отдельные профили `app`, `dev`, `monitoring`, `test`.
- **Есть покрытие тестами разных уровней.** В `tests/` есть проверки bot/filter layer, services, tasks и отдельный набор e2e-тестов через compose-профиль `test`.

## Что сделано плохо или требует внимания

- **Документация была слишком пользовательской.** До этой страницы `docs/` хорошо описывал Telegram/Grafana-сценарии, но почти не объяснял архитектуру, фоновые задачи, мониторинг и технические риски.
- **Dev defaults нельзя переносить в production.** В `.env.sample` есть удобные локальные значения (`DB_PASS=postgres`, пустой `REDIS_PASSWORD`, `GRAFANA_ADMIN_PASSWORD=admin`). Перед production-запуском их обязательно нужно заменить.
- **Много широких `except Exception`.** В handlers/tasks/services встречаются broad catch-блоки. Это защищает UX от падений, но усложняет диагностику инцидентов: лучше постепенно вводить типизированные ошибки, контекст в логах и более узкую обработку.
- **Есть крупные модули-сценарии.** `src/bot/handlers/meeting.py`, `src/bot/handlers/survey_builder.py`, `src/bot/handlers/trigger_rules.py` и `src/services/notion_sync_v2.py` содержат много логики. Их сложнее ревьюить и тестировать; при развитии проекта стоит дробить их на use-case/service-компоненты.
- **Блокировка при незаполненном опросе — сильное UX-ограничение.** `SurveyBlockMiddleware` намеренно блокирует почти все действия пользователя, пока есть pending survey. Это важно явно учитывать в поддержке и мониторинге, иначе поведение может выглядеть как «сломанное меню».
- **E2E не запускаются по умолчанию.** `pytest` игнорирует `tests/e2e`; перед релизами нужно отдельно запускать `make test-e2e` или поднимать test-профиль compose.

## Что проверять перед релизом

```bash
uv run pytest
make test-e2e
make monitoring
```

Минимально также стоит проверить, что `/health` возвращает успешный статус, Prometheus видит `/metrics`, а Grafana открывается с недефолтным паролем администратора.
