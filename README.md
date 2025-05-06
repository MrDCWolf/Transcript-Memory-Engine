# Transcript Memory Engine

The Transcript Memory Engine is a local-first application designed to help you process, store, and interact with your conversation transcripts. It leverages Retrieval-Augmented Generation (RAG) to allow you to "chat" with your transcripts, asking questions and getting contextually relevant answers. This engine prioritizes local AI models and vector stores for privacy and offline capability, with optional cloud integrations for enhanced features.

## Core Features

*   **Transcript Ingestion:** Supports fetching transcripts from sources (initially configured for Limitless).
*   **Local RAG Pipeline:**
    *   Chunks transcripts into manageable pieces.
    *   Generates embeddings locally using Sentence Transformers (e.g., BGE models).
    *   Stores chunks and embeddings in a local ChromaDB vector store.
    *   Uses a local LLM (via Ollama) for question answering against retrieved context.
*   **Chat Interface:** A web-based UI (FastAPI with HTMX/Streamlit) to interact with your transcripts.
*   **SQLite Database:** For storing transcript metadata, chunks, and chat history.
*   **Configurable Settings:** Manage LLM models, API keys, and other parameters via a UI and `.env` file.
*   **Dockerized:** Easy to set up and run using Docker and Docker Compose.

## ✨ New Feature: Actionable Items from Transcripts

This feature allows you to scan your conversation transcripts to identify potential reminders, calendar events, and tasks.

**How it works:**

1.  **Scan:** Navigate to the "Actionables" section in the UI (usually accessible from the main navigation). Select a date and a timeframe (morning, afternoon, or evening). Click "Scan for Actionables."
2.  **Review & Edit:** The system uses a local Large Language Model (LLM) to identify candidate items. These will be displayed for your review. You can:
    *   Confirm items you want to process further using the checkboxes.
    *   Edit the extracted text snippet directly in the text area.
    *   Change the suggested category (Reminder, Event, Task) using the dropdown.
    *   Edit any auto-detected entities (like names or relative dates mentioned in the snippet).
    *   Discard irrelevant suggestions by clicking the "Discard" button (this visually removes them and unchecks them).
3.  **Prepare for Export:** Once you've curated your list by checking the desired items and making edits, click "Prepare Selected for Export." For each confirmed item, the system uses a powerful cloud-based AI (e.g., OpenAI's GPT models - requires an OpenAI API key to be configured in settings) to extract structured details (e.g., event title, start/end times, task due dates).
4.  **Export to Google:** The prepared items are then displayed with their structured details (or any errors from the extraction process). You can then export individual items to:
    *   **Google Calendar** (for items categorized as "EVENT")
    *   **Google Tasks** (for items categorized as "TASK" or "REMINDER")
    *   *Note: Google Authentication (OAuth 2.0) is required for export. If you haven't authenticated, you'll be prompted or see a link to log in with Google.*

**Key Components for Actionable Items:**
*   **UI for Selection & Review:** New pages/partials in the web interface.
*   **Local LLM Scan:** For initial candidate identification from transcript segments.
*   **Cloud AI API (OpenAI):** For precise structured data extraction from confirmed snippets.
*   **Google Calendar API Integration:** To create calendar events.
*   **Google Tasks API Integration:** To create tasks.
*   **OAuth 2.0 for Google:** For secure authentication with Google services.

## Setup & Running

### 1. Prerequisites

- **Python 3.11+** (if running locally)
- **Docker** and **Docker Compose** (recommended for reproducibility)
- **Ollama** running locally (see below)

### 2. Clone & Setup

```bash
git clone https://github.com/MrDCWolf/Transcript-Memory-Engine.git
cd Transcript-Memory-Engine
cp .env.example .env  # Edit as needed
```

### 3. Start Ollama

Install and run [Ollama](https://ollama.com/) locally. Example (Mac):

```bash
brew install ollama
ollama serve &
ollama pull llama3:latest  # Or your preferred model
```

### 4. Build & Run (Docker)

```bash
docker-compose up --build
```

- The app will be available at [http://localhost:8000](http://localhost:8000)
- Ollama must be running and accessible at the URL specified in your `.env` (default: `http://localhost:11434`)

### 5. Ingest & Process Transcripts

- Navigate to the **Ingest** page ([http://localhost:8000/ingest/](http://localhost:8000/ingest/)) in the web UI.
- Click "Start Ingestion" to fetch and process new transcripts.
- The UI will show the progress through Fetch, DB Load, and Process stages using polling.
- Alternatively, use the provided scripts:

```bash
# These might be deprecated or used for specific needs
# poetry run python scripts/ingest.py 
# poetry run python scripts/chunk_transcripts.py
# poetry run python scripts/embed_chunks.py
```

See the `scripts/` directory for more utilities.

## Feature: Actionable Items - Google Integration Setup

To enable the "Export to Google" functionality for actionable items (Events to Calendar, Tasks to Tasks), you need to set up a Google Cloud Project and configure OAuth 2.0 credentials.

1.  **Create or Select a Google Cloud Project:**
    *   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    *   Create a new project or select an existing one.

2.  **Enable APIs:**
    *   In your project, navigate to "APIs & Services" > "Library".
    *   Search for and enable the following APIs:
        *   **Google Calendar API**
        *   **Google Tasks API**

3.  **Configure OAuth Consent Screen:**
    *   Navigate to "APIs & Services" > "OAuth consent screen".
    *   Choose "External" user type (unless you have a Google Workspace organization and want to limit it internally).
    *   Fill in the required application details:
        *   App name (e.g., "Transcript Memory Engine - Actionables")
        *   User support email
        *   Developer contact information
    *   **Scopes:** Click "Add or Remove Scopes". Add the following scopes:
        *   `https://www.googleapis.com/auth/calendar.events` (for Google Calendar)
        *   `https://www.googleapis.com/auth/tasks` (for Google Tasks)
    *   Add test users (your Google account(s)) during development. While the app is in "testing" mode, only these users can grant consent.

4.  **Create OAuth 2.0 Credentials:**
    *   Navigate to "APIs & Services" > "Credentials".
    *   Click "+ CREATE CREDENTIALS" > "OAuth client ID".
    *   Select "Web application" as the application type.
    *   Give it a name (e.g., "Transcript Engine Web Client").
    *   Under "Authorized redirect URIs", add the following (adjust port if your local server runs differently, though `http://localhost:8000` is common for this app):
        *   `http://localhost:8000/auth/google/callback`
        *   `http://127.0.0.1:8000/auth/google/callback`
    *   Click "Create".

5.  **Download Client Secret JSON:**
    *   After creation, a dialog will show your "Client ID" and "Client Secret".
    *   Click "DOWNLOAD JSON" to get the `client_secret.json` file.
    *   **Important:**
        *   Store this file securely. For this project, place it in the project's root directory (alongside `pyproject.toml`).
        *   The file `client_secret.json` is already included in `.gitignore` to prevent committing it to version control.

6.  **Environment Variables & Configuration:**
    *   The application expects `client_secret.json` to be in the project root by default (configurable via `GOOGLE_CLIENT_SECRET_JSON_PATH` in `core/config.py` or `.env`).
    *   User OAuth tokens will be stored locally in `data/google_oauth_tokens.json` by default (configurable via `GOOGLE_OAUTH_TOKENS_PATH`). This path is also in `.gitignore`.
    *   Ensure your OpenAI API key (`OPENAI_API_KEY`) is set in your `.env` file for the structured data extraction step.

## RAG Architecture

A **local-first**, high-performance RAG (Retrieval-Augmented Generation) system for querying and analyzing transcripts using local LLMs (Ollama), local embeddings, and a modern FastAPI/HTMX web UI. Designed for privacy, speed, and extensibility.

## Features

- **Local-First:** All core processing (embedding, storage, querying, LLM inference) runs locally. No cloud required.
- **RAG Pipeline:** Combines vector search (ChromaDB) with LLMs (Ollama) for context-aware Q&A over your transcript corpus.
- **Traceable Answers:** Every AI answer is linked to the exact transcript segments used as context.
- **Modern UI:** Chat-style web interface (FastAPI + HTMX + Jinja2) and CLI tools.
- **Modular Architecture:** Swap LLMs, embedding models, and vector stores via clean interfaces.
- **Efficient Storage:** Uses SQLite for structured data and ChromaDB for vector search.
- **Extensible:** Add new models, backends, or features with minimal changes.

## Project Structure

```
.
├── transcript_engine/         # Main application package
│   ├── api/routers/          # FastAPI routers (chat, settings, transcripts)
│   ├── core/                 # Config, dependency injection, logging
│   ├── database/             # SQLite schema, models, CRUD
│   ├── embeddings/           # Embedding model implementations
│   ├── interfaces/           # Protocols for LLM, embeddings, vector store
│   ├── llms/                 # LLM client implementations (Ollama)
│   ├── processing/           # Chunking and text processing
│   ├── query/                # RAG pipeline, retrieval, generation
│   ├── ui/                   # Web UI logic (HTMX, Jinja2)
│   ├── vector_stores/        # Vector DB implementations (Chroma)
│   └── main.py               # FastAPI app entrypoint
├── scripts/                  # CLI tools for ingestion, chunking, embedding
├── templates/                # Jinja2 HTML templates
├── static/                   # CSS and static assets
├── data/                     # Local data (DBs, embeddings)
├── tests/                    # Pytest-based tests
├── Dockerfile                # Container build
├── docker-compose.yml        # Service orchestration
├── Makefile                  # Common dev commands
├── pyproject.toml            # Poetry dependencies
└── README.md                 # This file
```

## Build Pipeline

- **Dependency Management:** [Poetry](https://python-poetry.org/)
- **Linting/Formatting:** [Ruff](https://docs.astral.sh/ruff/) (enforces Black style)
- **Testing:** [pytest](https://docs.pytest.org/)
- **Containerization:** Docker, Docker Compose
- **Dev Commands:** See `Makefile` for `make run`, `make test`, `make lint`, etc.

## Configuration

All configuration is managed via environment variables and loaded using `pydantic-settings`. See `.env.example` for required/optional settings:

- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `DEFAULT_MODEL` (e.g., `llama3:latest`)
- `CHROMA_DB_PATH` (default: `data/chroma_db`)
- `SQLITE_DB_PATH` (default: `data/transcripts.db`)
- ...and more

## Core Components

- **LLM:** Local LLMs via [Ollama](https://ollama.com/) (`transcript_engine/llms/ollama_client.py`)
- **Embeddings:** Local models via [sentence-transformers](https://www.sbert.net/) (`transcript_engine/embeddings/bge_local.py`)
- **Vector Store:** [ChromaDB](https://www.trychroma.com/) for fast vector search (`transcript_engine/vector_stores/chroma_store.py`)
- **Database:** SQLite for transcripts, chunks, and chat history (`transcript_engine/database/`)
- **Web UI:** FastAPI, HTMX, Jinja2 templates (`transcript_engine/ui/`, `templates/`)
    - Chat interface (`/chat/`)
    - Settings management (`/settings/`)
    - Ingestion control with status polling (`/ingest/`)
- **APIs:** Modular routers for chat, settings, transcripts, ingestion (`transcript_engine/api/routers/`)
- **Processing:** Chunking, embedding, and retrieval logic (`transcript_engine/processing/`, `transcript_engine/query/`)

## Usage

- **Web UI:** Chat with your transcript data, see traceable answers, manage settings, and trigger/monitor ingestion via the dedicated page.
- **CLI Tools:** Ingest, process, and query transcripts from the command line (check `scripts/` for availability).
- **Tracebacks:** Every answer links to the exact transcript segment(s) used.

## Development

- **Run locally:** `poetry install && poetry run uvicorn transcript_engine.main:app --reload`
- **Run tests:** `poetry run pytest`
- **Lint/format:** `poetry run ruff check . && poetry run ruff format .`
- **Add dependencies:** `poetry add <package>`

## Testing

- **Framework:** pytest
- **Coverage:** Core logic (ingestion, chunking, retrieval, generation) is covered.
- **Mocking:** Uses `pytest-mock` for external dependencies.
- **Fixtures:** For DB, service instances, etc.

## Security & Privacy

- **Local-First:** No transcript data leaves your machine unless you configure a cloud LLM.
- **Secrets:** Never hardcoded; always loaded from environment.
- **Input Validation:** All API and DB inputs validated via Pydantic.

## Roadmap

- [x] Local RAG pipeline (ingest, chunk, embed, retrieve, generate)
- [x] FastAPI + HTMX web UI
- [x] Ollama LLM integration
- [x] ChromaDB vector search
- [x] SQLite structured storage
- [x] Modular, interface-driven architecture
- [x] Basic Ingestion page with status polling
- [ ] Summarization, trend tracking, task extraction (see PRD)
- [ ] Audio integration, visualization (future phases)

## License

MIT License. See [LICENSE](LICENSE).

## Acknowledgments

- [Ollama](https://ollama.com/)
- [ChromaDB](https://www.trychroma.com/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Sentence Transformers](https://www.sbert.net/)
- [HTMX](https://htmx.org/)
- [Jinja2](https://jinja.palletsprojects.com/)

## For more details, see the [Product Requirements Document](transcript_memory_engine_prd.md). 