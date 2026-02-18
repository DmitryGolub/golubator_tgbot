# Опрос после созвона

## Что добавлено
- После завершения созвона встреча помечается как завершенная (`meetings.completed_at`).
- Для завершенного созвона открывается доступ к опросу (`meetings.survey_available_at`).
- Ответы опроса сохраняются в `survey_responses` и привязываются к `call_id`.
- Повторная отправка по тому же `call_id` идемпотентна: возвращается уже сохраненный ответ.

## API
- `GET /calls/{call_id}/survey` — получить структуру вопросов и статус (`not_available|available|completed`)
- `POST /calls/{call_id}/survey` — отправить ответы

Пример `POST` body:
```json
{
  "duration_option": "45_60",
  "mentor_style": 5,
  "knowledge_depth": 4,
  "understanding": 5,
  "comment": "Отличный разбор"
}
```

## Как проверить локально
1. Применить миграции:
```bash
alembic upgrade head
```
2. Запустить API:
```bash
python -m src.scripts.api_server
```
3. Открыть документацию:
- `http://localhost:8000/docs`

## Тесты
```bash
pytest -q tests/test_call_survey_api.py
```
