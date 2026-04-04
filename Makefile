DC_FILE := docker-compose.yaml

.PHONY: init up up-prod down logs ps test migrate reset clean restart monitoring cert-init cert-renew nginx-deploy backfill-transitions test-e2e-up test-e2e-down test-e2e-reset test-e2e

init: up logs

up:
	docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --profile app --profile dev up -d --build

up-prod:
	docker compose --profile app --profile monitoring up -d --build

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
	docker compose --profile app --profile dev --profile monitoring down -v --remove-orphans

restart: reset up

clean:
	docker compose --profile app --profile dev --profile monitoring down -v --rmi local --remove-orphans

monitoring:
	docker compose --profile monitoring up -d

nginx-deploy:
	sudo cp nginx/notion.pigeon.careers /etc/nginx/sites-available/notion.pigeon.careers
	sudo cp nginx/grafana.pigeon.careers /etc/nginx/sites-available/grafana.pigeon.careers
	sudo ln -sf /etc/nginx/sites-available/notion.pigeon.careers /etc/nginx/sites-enabled/notion.pigeon.careers
	sudo ln -sf /etc/nginx/sites-available/grafana.pigeon.careers /etc/nginx/sites-enabled/grafana.pigeon.careers
	sudo nginx -t
	sudo nginx -s reload

cert-init:
	@echo "==> Stopping nginx to free port 80..."
	sudo nginx -s stop || true
	sudo certbot certonly --standalone \
		--register-unsafely-without-email \
		--agree-tos \
		-d notion.pigeon.careers \
		-d grafana.pigeon.careers
	@echo "==> Starting nginx..."
	sudo nginx
	@echo "==> Done! HTTPS certificates obtained."

cert-renew:
	sudo certbot renew
	sudo nginx -s reload

backfill-transitions:
	docker compose exec bot python -m src.scripts.backfill_stage_transitions

# ── E2E tests ──
test-e2e-up:
	docker compose --env-file .env.test --profile test up -d --build

test-e2e-down:
	docker compose --env-file .env.test --profile test down

test-e2e-reset:
	docker compose --env-file .env.test --profile test down -v --remove-orphans

test-e2e:
	docker compose --env-file .env.test --profile test up -d --build
	uv run pytest tests/e2e/ -v --timeout=120
	docker compose --env-file .env.test --profile test down
