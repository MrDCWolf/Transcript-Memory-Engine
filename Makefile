# Makefile for Transcript Memory Engine

.PHONY: help setup run-dev stop-dev logs init-db lint format test clean

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
	# Ensure the app service is running or start it temporarily
	docker-compose run --rm app poetry run python -c "from transcript_engine.database.crud import initialize_database; from transcript_engine.core.dependencies import get_db; from transcript_engine.core.config import get_settings; settings = get_settings(); conn = next(get_db(settings)); initialize_database(conn); print('DB Initialized.')"

ingest:
	@echo "Running transcript ingestion script..."
	docker-compose exec app poetry run python scripts/ingest_transcripts.py

process:
	@echo "Running transcript processing script (chunking & embedding)..."
	docker-compose exec app poetry run python scripts/process_transcripts.py

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
	@echo "Cleaning up cache files, build artifacts, and Docker volumes..."
	find . -type f -name '*.py[co]' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov dist build *.egg-info
	# Optionally remove Docker volumes (use with caution!)
	# docker-compose down -v 
	@echo "Cleanup complete. Note: Docker volumes were not removed by default." 