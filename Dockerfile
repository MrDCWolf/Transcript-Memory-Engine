# Use the official Python 3.11 slim image as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/opt/poetry"

# Install pipx and poetry
RUN apt-get update && apt-get install -y --no-install-recommends pipx && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pipx install poetry==1.8.3
RUN pipx ensurepath

# Adding poetry to PATH explicitly (needed for subsequent RUN commands)
ENV PATH="/root/.local/bin:$PATH"

# Set the working directory in the container
WORKDIR /app

# Copy the dependency files
COPY pyproject.toml poetry.lock* /app/

# Install project dependencies into the virtual environment managed by Poetry
RUN poetry install --no-interaction --no-ansi --no-root --sync

# Copy the rest of the application code
COPY ./transcript_engine /app/transcript_engine

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable (optional, can be set in docker-compose)
# ENV NAME World

# Define the command to run the application using poetry run
CMD ["poetry", "run", "uvicorn", "transcript_engine.main:app", "--host", "0.0.0.0", "--port", "8000"] 