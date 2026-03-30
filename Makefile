DC_FILE := docker-compose.yaml

.PHONY: init up up-prod down logs ps test migrate reset clean restart cert-init cert-renew nginx-deploy backfill-transitions

init: up logs

up:
	docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --profile dev up -d --build

up-prod:
	docker compose up -d --build

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
	docker compose --profile dev down -v --remove-orphans

restart: reset up

clean:
	docker compose --profile dev down -v --rmi local --remove-orphans

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
