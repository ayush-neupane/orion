.PHONY: install migrate run test security-check lint down logs clean help

# Default: bring the entire ecosystem online
run:
	docker compose up --build

install:
	docker compose build
	@echo "Setup complete. Run 'make migrate' then 'make run'."

# Idempotent schema migration (creates tables + TimescaleDB hypertables)
migrate:
	docker compose run --rm backend python -m app.db_migrate

test:
	cd backend && python -m pytest --cov=app --cov-fail-under=85 -q

lint:
	cd backend && python -m flake8 app tests
	cd frontend && npm run lint

security-check:
	gitleaks detect --source . --no-git -v || true
	docker compose run --rm --no-deps backend sh -c "pip install pip-audit && pip-audit --strict -r requirements.txt"
	cd frontend && npm audit --audit-level=critical

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

clean:
	docker compose down -v --remove-orphans

help:
	@echo "make run            - build & start the full stack (http://localhost:8080)"
	@echo "make install        - build all images"
	@echo "make migrate        - apply database schema (idempotent)"
	@echo "make test           - run backend test suite with coverage gate"
	@echo "make security-check - run secret scanner + dependency audits"
	@echo "make lint           - run flake8 + eslint"
	@echo "make down / clean   - stop stack / stop and wipe volumes"