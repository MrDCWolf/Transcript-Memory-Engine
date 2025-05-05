# Use the official Python 3.11 slim image as a parent image
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry and add to PATH
ENV POETRY_HOME=/opt/poetry
RUN curl -sSL https://install.python-poetry.org | python3 - \
    && ln -s /opt/poetry/bin/poetry /usr/local/bin/poetry

# Set working directory
WORKDIR /app

# Copy Poetry configuration and install dependencies
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --no-root

# Copy application code
COPY . .

# Define the command to run the application
CMD ["poetry", "run", "uvicorn", "transcript_engine.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variable (optional, can be set in docker-compose)
# ENV NAME World

# Define the command to run the application using poetry run
CMD ["poetry", "run", "uvicorn", "transcript_engine.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set working directory
WORKDIR /app

# Copy Poetry configuration
COPY pyproject.toml poetry.lock ./

# Install dependencies
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi

# Copy application code
COPY . .

# Install the package in development mode
RUN poetry install --no-interaction --no-ansi 