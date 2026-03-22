DC_FILE := docker-compose.yaml

.PHONY: init up up-prod down logs ps test migrate reset clean

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

reset:
	docker compose --profile dev --profile prod down -v --remove-orphans

clean:
	docker compose --profile dev --profile prod down -v --rmi local --remove-orphans
