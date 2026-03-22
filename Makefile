DC_FILE := docker-compose.yaml

.PHONY: init build up up-prod down logs ps test migrate clean ssl

init: build up logs

build:
	docker compose -f $(DC_FILE) build

up:
	docker compose --profile dev up -d

up-prod: ssl
	docker compose --profile prod up -d

ssl:
	docker compose --profile prod run --rm certbot

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
