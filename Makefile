DC_FILE := docker-compose.yaml
BOT_SERVICE := tg_bot

.PHONY: init build up logs down ps test

init: build up logs

build:
	docker compose -f $(DC_FILE) build

up:
	docker compose -f $(DC_FILE) up -d

logs:
	docker compose -f $(DC_FILE) logs -f

down:
	docker compose -f $(DC_FILE) down

ps:
	docker compose -f $(DC_FILE) ps

test:
	pytest -q

migrate:
	alembic upgrade head