.PHONY: up down logs api-test web-test

up:
	docker compose up --build

down:
	docker compose down -v

logs:
	docker compose logs -f

api-test:
	docker compose run --rm api pytest -q

web-test:
	docker compose run --rm web npx playwright test
