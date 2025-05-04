# Makefile for Transcript Memory Engine

.PHONY: help setup run-dev stop-dev logs init-db lint format test clean ingest

# Default target executed when running `make`
default: help

help:
	@echo "Available commands:"
	@echo "  setup          Install project dependencies using Poetry."
	@echo "  run-dev        Build and start the Docker Compose development environment (foreground)."
	@echo "  run-dev-bg     Build and start the Docker Compose development environment (background)."
	@echo "  stop-dev       Stop and remove the Docker Compose development environment."
	@echo "  logs           Follow logs from the running Docker Compose services."
	@echo "  init-db        Initialize the database schema (runs inside the app container)." # Updated description
	@echo "  ingest         Run the initial transcript ingestion script (runs inside the app container)."
	@echo "  process        Run the transcript chunking and embedding script (runs inside the app container)."
	@echo "  lint           Check code style and quality using Ruff."
	@echo "  format         Format code using Black and Ruff."
	@echo "  test           Run tests using pytest (runs inside the app container)."
	@echo "  clean          Remove cache files, build artifacts, and data volumes."

# Environment Setup
setup:
	@echo "Installing dependencies using Poetry..."
	poetry install

# Docker Environment Management
run-dev:
	@echo "Starting Docker development environment in foreground..."
	COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker-compose up --build

run-dev-bg:
	@echo "Starting Docker development environment in background..."
	COMPOSE_DOCKER_CLI_BUILD=1 DOCKER_BUILDKIT=1 docker-compose up --build -d

stop-dev:
	@echo "Stopping Docker development environment..."
	docker-compose down

logs:
	@echo "Following Docker logs (Ctrl+C to stop)..."
	docker-compose logs -f

# Database and Processing Scripts (Run inside container)
init-db:
	@echo "Initializing database schema..."
	# Run commands within the running service container using exec
	@docker-compose exec app rm -f ./data/transcript_engine.db || true
	@docker-compose exec app poetry run python -c "from transcript_engine.database.crud import initialize_database; from transcript_engine.core.config import get_settings; import sqlite3; import os; project_root='/app'; settings=get_settings(); db_path_relative = settings.database_url.split('///')[-1]; db_path_absolute = os.path.join(project_root, db_path_relative); os.makedirs(os.path.dirname(db_path_absolute), exist_ok=True); conn=sqlite3.connect(db_path_absolute); initialize_database(conn); conn.commit(); conn.close(); print('DB Initialized.')"

ingest: ## Ingest transcripts from the Limitless API
	@echo "Running transcript ingestion script..."
	@poetry run python scripts/ingest.py $(if $(START_DATE),--start-date $(START_DATE)) $(if $(END_DATE),--end-date $(END_DATE)) $(if $(TIMEZONE),--timezone $(TIMEZONE))

process:
	@echo "Running transcript processing script (chunking & embedding)..."
	# Use docker-compose run instead of exec to see if it resolves code update issues
	@docker-compose run --rm app poetry run python scripts/process_transcripts.py

# Code Quality & Testing
lint:
	@echo "Running Ruff linter..."
	poetry run ruff check .

format:
	@echo "Formatting code with Black and Ruff..."
	poetry run black .
	poetry run ruff format .

test:
	@echo "Running tests with pytest..."
	# Use the command that worked previously, including explicit install
	docker-compose exec app /bin/sh -c 'poetry install --no-root --sync && poetry run python -m pytest tests/'

# Cleanup
clean:
	@echo "Cleaning up cache files, build artifacts, and data..."
	find . -type f -name '*.py[co]' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build *.egg-info
	# Remove contents of the data directory
	rm -rf ./data/* 
	# Optionally remove Docker volumes (use with caution!)
	# docker-compose down -v 
	@echo "Cleanup complete. Note: Docker volumes were not removed by default." 