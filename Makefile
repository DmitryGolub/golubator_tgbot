DC_FILE := docker-compose.yaml

.PHONY: init up up-prod down logs ps test migrate clean

init: up logs

up:
	docker compose --profile dev up -d --build

up-prod:
	docker compose --profile prod up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

ps:
	docker compose ps

test:
	uv run pytest -q

migrate:
	uv run alembic upgrade head

clean:
	docker compose down -v --rmi local
