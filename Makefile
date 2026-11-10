SHELL := /bin/sh
PNPM ?= pnpm
UV ?= uv

.PHONY: up down migrate seed test lint gen:api

up:
	docker compose up --build --detach

down:
	docker compose down

migrate:
	$(UV) run --directory backend alembic upgrade head

seed:
	$(UV) run --directory backend python scripts/seed_dev.py

test:
	$(UV) run --directory backend pytest
	$(PNPM) --recursive --if-present test

lint:
	$(UV) run --directory backend ruff check .
	$(UV) run --directory backend ruff format --check .
	$(UV) run --directory backend mypy
	$(PNPM) --recursive --if-present lint

gen:api:
	$(PNPM) gen:api
