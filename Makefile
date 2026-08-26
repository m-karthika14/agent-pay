# AgentPay convenience commands.
# Wraps frontend (npm) and backend (uv) tooling so contributors don't need to
# remember two different package managers. Requires GNU make (available via
# Git Bash / WSL on Windows).

.PHONY: install install-frontend install-backend dev-frontend dev-backend \
        test test-frontend test-backend test-backend-real-llm db-up db-down migrate seed

## Install both frontend and backend dependencies.
install: install-frontend install-backend

install-frontend:
	cd frontend && npm install

install-backend:
	cd backend && uv sync

## Run the frontend dev server (Vite).
dev-frontend:
	cd frontend && npm run dev

## Run the backend dev server (FastAPI/uvicorn with reload).
dev-backend:
	cd backend && uv run uvicorn app.main:app --reload

## Run all tests.
test: test-frontend test-backend

test-frontend:
	cd frontend && npm test

## Normal development: LLM calls are mocked (fast, deterministic, no Groq key needed).
test-backend:
	cd backend && uv run pytest

## Before a demo: same suite, against real Groq -- confirms the live LLM integration works.
test-backend-real-llm:
	cd backend && REAL_LLM_TESTS=1 uv run pytest

## Start local PostgreSQL via docker-compose.
db-up:
	docker compose up -d

## Stop local PostgreSQL.
db-down:
	docker compose down

## Run Alembic migrations against DATABASE_URL.
migrate:
	cd backend && uv run alembic upgrade head

## Seed the database with the UrbanNest demo merchant/catalog.
seed:
	cd backend && uv run python ../scripts/seed_database.py
