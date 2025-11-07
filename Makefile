PROJECT?=notisnu

.PHONY: dev-up dev-down ingest seed-posts seed-users test fmt lint logs

dev-up:
	docker compose up --build

dev-down:
	docker compose down

ingest:
	docker compose exec api python scripts/run_ingest.py

seed-posts:
	docker compose exec api python scripts/seed_posts.py

seed-users:
	docker compose exec api python scripts/seed_users.py

test:
	docker compose exec api pytest

logs:
	docker compose logs -f api
