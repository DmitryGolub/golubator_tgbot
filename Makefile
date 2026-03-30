DC_FILE := docker-compose.yaml

.PHONY: init up up-prod down logs ps test migrate reset clean restart cert-init cert-renew

init: up logs

up:
	docker compose -f docker-compose.yaml -f docker-compose.dev.yaml --profile dev up -d --build

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

restart: reset up

clean:
	docker compose --profile dev --profile prod down -v --rmi local --remove-orphans

cert-init:
	@echo "==> Switching to initial nginx config (HTTP only)..."
	cp nginx/default.conf.initial nginx/default.conf.tmp
	cp nginx/default.conf nginx/default.conf.bak
	cp nginx/default.conf.initial nginx/default.conf
	docker compose --profile prod up -d nginx
	@echo "==> Requesting certificate from Let's Encrypt..."
	docker compose --profile prod run --rm certbot certonly \
		--webroot -w /var/www/certbot \
		--register-unsafely-without-email \
		--agree-tos \
		-d notion.pigeon.careers \
		-d grafana.pigeon.careers
	@echo "==> Restoring HTTPS nginx config..."
	cp nginx/default.conf.bak nginx/default.conf
	rm -f nginx/default.conf.tmp nginx/default.conf.bak
	docker compose --profile prod exec nginx nginx -s reload
	@echo "==> Done! HTTPS is active."

cert-renew:
	docker compose --profile prod run --rm certbot renew
	docker compose --profile prod exec nginx nginx -s reload
