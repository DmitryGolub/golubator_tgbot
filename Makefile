DC_FILE := docker-compose.yaml

.PHONY: init build up up-prod down logs ps test migrate clean

init: build up logs

build:
	docker compose -f $(DC_FILE) build

up:
	docker compose up -d

up-prod:
	docker compose -f $(DC_FILE) up -d

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
