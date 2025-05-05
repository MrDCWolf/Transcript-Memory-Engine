# Transcript Memory Engine

A **local-first**, high-performance RAG (Retrieval-Augmented Generation) system for querying and analyzing transcripts using local LLMs (Ollama), local embeddings, and a modern FastAPI/HTMX web UI. Designed for privacy, speed, and extensibility.

---

## Features

- **Local-First:** All core processing (embedding, storage, querying, LLM inference) runs locally. No cloud required.
- **RAG Pipeline:** Combines vector search (ChromaDB) with LLMs (Ollama) for context-aware Q&A over your transcript corpus.
- **Traceable Answers:** Every AI answer is linked to the exact transcript segments used as context.
- **Modern UI:** Chat-style web interface (FastAPI + HTMX + Jinja2) and CLI tools.
- **Modular Architecture:** Swap LLMs, embedding models, and vector stores via clean interfaces.
- **Efficient Storage:** Uses SQLite for structured data and ChromaDB for vector search.
- **Extensible:** Add new models, backends, or features with minimal changes.

---

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

---

## Quickstart

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

Use the provided scripts to fetch, chunk, and embed your transcripts:

```bash
poetry run python scripts/ingest.py
poetry run python scripts/chunk_transcripts.py
poetry run python scripts/embed_chunks.py
```

See the `scripts/` directory for more utilities.

---

## Build Pipeline

- **Dependency Management:** [Poetry](https://python-poetry.org/)
- **Linting/Formatting:** [Ruff](https://docs.astral.sh/ruff/) (enforces Black style)
- **Testing:** [pytest](https://docs.pytest.org/)
- **Containerization:** Docker, Docker Compose
- **Dev Commands:** See `Makefile` for `make run`, `make test`, `make lint`, etc.

---

## Configuration

All configuration is managed via environment variables and loaded using `pydantic-settings`. See `.env.example` for required/optional settings:

- `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- `DEFAULT_MODEL` (e.g., `llama3:latest`)
- `CHROMA_DB_PATH` (default: `data/chroma_db`)
- `SQLITE_DB_PATH` (default: `data/transcripts.db`)
- ...and more

---

## Core Components

- **LLM:** Local LLMs via [Ollama](https://ollama.com/) (`transcript_engine/llms/ollama_client.py`)
- **Embeddings:** Local models via [sentence-transformers](https://www.sbert.net/) (`transcript_engine/embeddings/bge_local.py`)
- **Vector Store:** [ChromaDB](https://www.trychroma.com/) for fast vector search (`transcript_engine/vector_stores/chroma_store.py`)
- **Database:** SQLite for transcripts, chunks, and chat history (`transcript_engine/database/`)
- **Web UI:** FastAPI, HTMX, Jinja2 templates (`transcript_engine/ui/`, `templates/`)
- **APIs:** Modular routers for chat, settings, transcripts (`transcript_engine/api/routers/`)
- **Processing:** Chunking, embedding, and retrieval logic (`transcript_engine/processing/`, `transcript_engine/query/`)

---

## Usage

- **Web UI:** Chat with your transcript data, see traceable answers, manage settings.
- **CLI Tools:** Ingest, process, and query transcripts from the command line.
- **Tracebacks:** Every answer links to the exact transcript segment(s) used.

---

## Development

- **Run locally:** `poetry install && poetry run uvicorn transcript_engine.main:app --reload`
- **Run tests:** `poetry run pytest`
- **Lint/format:** `poetry run ruff check . && poetry run ruff format .`
- **Add dependencies:** `poetry add <package>`

---

## Testing

- **Framework:** pytest
- **Coverage:** Core logic (ingestion, chunking, retrieval, generation) is covered.
- **Mocking:** Uses `pytest-mock` for external dependencies.
- **Fixtures:** For DB, service instances, etc.

---

## Security & Privacy

- **Local-First:** No transcript data leaves your machine unless you configure a cloud LLM.
- **Secrets:** Never hardcoded; always loaded from environment.
- **Input Validation:** All API and DB inputs validated via Pydantic.

---

## Roadmap

- [x] Local RAG pipeline (ingest, chunk, embed, retrieve, generate)
- [x] FastAPI + HTMX web UI
- [x] Ollama LLM integration
- [x] ChromaDB vector search
- [x] SQLite structured storage
- [x] Modular, interface-driven architecture
- [ ] Summarization, trend tracking, task extraction (see PRD)
- [ ] Audio integration, visualization (future phases)

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Acknowledgments

- [Ollama](https://ollama.com/)
- [ChromaDB](https://www.trychroma.com/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Sentence Transformers](https://www.sbert.net/)
- [HTMX](https://htmx.org/)
- [Jinja2](https://jinja.palletsprojects.com/)

---

**For more details, see the [Product Requirements Document](transcript_memory_engine_prd.md).** 