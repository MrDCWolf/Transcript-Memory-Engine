# Revised Build Plan: Transcript Memory Engine

## **Phase 1.0 — Environment Setup & Core Interfaces**

### 🌟 **Goal:**
Establish a clean, reproducible local development environment with core data models, service interfaces, and connections to essential services (DB, Vector Store, LLM) verified early.

---

### **Phase 1.1 — Dockerized Local Dev Environment**

**🔺 Target:**
Run a local FastAPI + Chroma + SQLite environment inside Docker with volume mounting and hot-reloading enabled.

**🖊️ Description:**
Lay the groundwork for local service orchestration. Ensure DBs and data persist.

**🔧 AI Coder Instructions (Cursor):**
1.  Initialize project with `poetry init`. Add `fastapi`, `uvicorn`, `python-dotenv`, `jinja2`, `pydantic-settings`. Add dev dependencies `pytest`, `black`, `ruff`, `httpx`, `ollama` (or `httpx` if calling API directly), `chromadb`, `sentence-transformers`, `langchain-text-splitters`, `spacy`, `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib`. (*Note: Add dependencies as needed per phase*). Run `poetry lock`.
2.  Create `Dockerfile` using `python:3.11-slim`.
    * Install `poetry`.
    * Copy `pyproject.toml`, `poetry.lock`.
    * Run `poetry install --no-root --only main` (adjust if dev tools needed in container).
    * Copy application code (e.g., `COPY ./transcript_engine /app/transcript_engine`).
    * Optionally add `curl` for debugging: `RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*`.
3.  Create `docker-compose.yml`:
    * Define `app` service building from `Dockerfile`.
    * Expose port `8000`.
    * Mount `./:/app` volume (ensure correct mapping).
    * Set working dir `/app`.
    * Command: `uvicorn transcript_engine.main:app --host 0.0.0.0 --port 8000 --reload` (Create dummy `transcript_engine/main.py` initially).
    * Define volume for SQLite DB (e.g., `db_data:/app/data`). Map `data` dir.
4.  Create `data/` folder locally (will be mounted).
5.  Add `.env.example` with placeholders (`OPENAI_API_KEY=`, `TRANSCRIPT_API_URL=`, `CHROMA_PATH=./data/chroma_db`, `DB_PATH=./data/transcripts.db`, etc.). Add `.env` to `.gitignore`.
6.  Create `.dockerignore` file (include `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `*.pyc`, `*.tmp`, `.env`, `data/`, `docs/`).

**✅ Acceptance Criteria:**
* `docker-compose up --build` starts FastAPI on [http://localhost:8000](http://localhost:8000).
* Project files editable on host reflect in container.
* `data/` directory persists.

---

### **Phase 1.2 — Project Structure, Config & Core Models**

**🔺 Target:**
Establish project structure, configuration loading, core data models, and basic database setup.

**🖊️ Description:**
Define how data will be represented and stored foundationally.

**🔧 AI Coder Instructions (Cursor):**
1.  Create main package folder: `transcript_engine/`.
2.  Add sub-folders inside `transcript_engine/`: `api/`, `core/`, `database/`, `embeddings/`, `features/`, `ingest/`, `interfaces/`, `llms/`, `models/`, `query/`, `vector_stores/`.
3.  Add top-level folders: `data/`, `scripts/`, `tests/`, `templates/`, `static/`.
4.  Create `transcript_engine/core/config.py`: Use `pydantic-settings`' `BaseSettings` to load config from `.env` file (define variables like `DB_PATH`, `CHROMA_PATH`, `CHROMA_COLLECTION`, `OLLAMA_BASE_URL`, etc.).
5.  Create `transcript_engine/models/data_models.py`: Define Pydantic models for `Transcript`, `Chunk`, `ChatMessage`. Include relevant fields (IDs, text, timestamps, speaker, metadata, source_hash, embedded_flag).
6.  Create `transcript_engine/database/schema.py`: Define functions using `sqlite3` to create initial tables (e.g., `transcripts`, `chunks`, `chat_sessions`) based on Pydantic models. Use `config` for DB path.
7.  Create `transcript_engine/database/crud.py`: Add basic functions (stubs initially) for inserting/querying data using Pydantic models for validation/serialization.
8.  Create `scripts/initialize_db.py` that imports and calls the schema creation function from `schema.py`.
9.  Create `Makefile` with targets: `setup` (poetry install), `run-dev` (docker-compose up --build), `stop-dev` (docker-compose down), `init-db` (docker-compose run app python scripts/initialize_db.py), `lint` (poetry run ruff check .), `format` (poetry run black . ; poetry run ruff format .), `test` (poetry run pytest).
10. Add dummy test in `tests/test_config.py` ensuring config loads.

**✅ Acceptance Criteria:**
* `make setup` installs dependencies.
* `make init-db` creates `data/transcripts.db` file with tables inside the container volume.
* `poetry run pytest` passes.
* Project structure navigable in Cursor.

---

### **Phase 1.3 — Interfaces & Local LLM Verification**

**🔺 Target:**
Define core service interfaces and verify local Ollama connection.

**🖊️ Description:**
Establish contracts for swappable components and test the LLM connection early.

**🔧 AI Coder Instructions (Cursor):**
1.  Create `transcript_engine/interfaces/llm_interface.py`: Define a `Protocol` (from `typing`) named `LLMInterface` with methods like `generate(prompt: str) -> str` and `chat(messages: list[ChatMessage]) -> ChatMessage`.
2.  Create `transcript_engine/llms/ollama_client.py`: Implement `LLMInterface`. Use `ollama` library or `httpx` to call Ollama API (`config.OLLAMA_BASE_URL`). Add basic error handling (e.g., connection errors, timeouts) and logging.
3.  Ensure Ollama installation (`brew install ollama`), pull a model (`ollama pull mistral`), and ensure it's running.
4.  Create `tests/test_ollama_client.py`: Write a test that instantiates `OllamaClient` and makes a successful call to the running Ollama service. Use `@pytest.mark.skipif(not is_ollama_running(), reason='Ollama not running')` or similar.

**✅ Acceptance Criteria:**
* `LLMInterface` protocol defined.
* `OllamaClient` implementation exists.
* `pytest tests/test_ollama_client.py` passes against running Ollama service (<3s response).
* Ollama setup documented in `README.md`.

---

### **Phase 1.4 — Vector DB Interface & Setup (Chroma)**

**🔺 Target:**
Define vector store interface and verify local Chroma DB setup and persistence.

**🖊️ Description:**
Establish contract for vector storage and ensure Chroma is operational.

**🔧 AI Coder Instructions (Cursor):**
1.  Create `transcript_engine/interfaces/vector_store_interface.py`: Define `Protocol` `VectorStoreInterface` with methods like `add(chunks: list[Chunk], embeddings: list[list[float]])` and `query(query_embedding: list[float], k: int, filter_metadata: dict | None = None) -> list[Chunk]`.
2.  Create `transcript_engine/vector_stores/chroma_store.py`: Implement `VectorStoreInterface` using `chromadb`.
    * Initialize client: `chromadb.PersistentClient(path=config.CHROMA_PATH)`.
    * Use `config.CHROMA_COLLECTION` name. Use `get_or_create_collection`.
    * Implement `add`: Use `chunk.id` for Chroma IDs. Store `chunk.text` and relevant fields from `chunk.metadata` in Chroma metadata. Handle potential ID conflicts if needed.
    * Implement `query`: Retrieve results including text and metadata. Convert Chroma results back to `Chunk` Pydantic models (or add necessary info). Add basic error handling.
3.  Add `data/chroma_db/` path (from config) to `.gitignore`.
4.  Create `tests/test_chroma_store.py`: Write tests to initialize `ChromaStore`, add dummy `Chunk` objects with fake embeddings, query them, verify metadata, and test persistence.

**✅ Acceptance Criteria:**
* `VectorStoreInterface` defined.
* `ChromaStore` implementation exists.
* `pytest tests/test_chroma_store.py` passes.
* `data/chroma_db/` directory created and persists data.

---

### **Phase 1.5 — Embedding Interface Setup**

**🔺 Target:**
Define embedding interface and basic implementation stub.

**🖊️ Description:**
Establish contract for generating embeddings.

**🔧 AI Coder Instructions (Cursor):**
1.  Create `transcript_engine/interfaces/embedding_interface.py`: Define `Protocol` `EmbeddingInterface` with methods `embed_documents(texts: list[str]) -> list[list[float]]` and `embed_query(text: str) -> list[float]`.
2.  Create `transcript_engine/embeddings/stub_embedding.py`: Implement `EmbeddingInterface` returning fixed-size lists of zeros (e.g., dimension 384 for BGE-small).
3.  Create `tests/test_embedding_interface.py` using the stub implementation.

**✅ Acceptance Criteria:**
* `EmbeddingInterface` defined.
* Stub implementation exists and is testable.

---

**Phase Completion Result:**
* Fully working, reproducible local environment via Docker.
* Clean project structure with configuration, core data models, and DB schema.
* Core service interfaces defined (`LLM`, `VectorStore`, `Embedding`).
* Local Ollama and Chroma services verified and accessible via interface implementations.
* Project ready for Phase 2: building the ingestion pipeline.

---

## **Phase 2.0 — Ingestion & Embedding Pipeline**

### 🌟 **Goal:**
Build a modular pipeline that pulls transcripts, normalizes/chunks them using defined models, stores them in SQLite, generates embeddings via the embedding interface, and stores vectors in Chroma via its interface.

---

### **Phase 2.1 — Transcript Fetching & Initial Storage**

**🔺 Target:**
Ingest transcript data from external API, validate with Pydantic models, and store raw/structured data in SQLite.

**🖊️ Description:**
Implement the fetcher, ensuring deduplication and using the database layer.

**🔧 AI Coder Instructions (Cursor):**
1.  Implement `transcript_engine/ingest/fetcher.py`:
    * Add function `fetch_transcripts(api_url: str, api_key: str | None, since_date: date | None) -> list[Transcript]`.
    * Use `httpx.Client` for API calls. Add robust error handling (timeouts, status codes, retries) and logging.
    * Parse response, validate/transform data into `Transcript` Pydantic models. Handle potential parsing errors.
2.  Implement required functions in `transcript_engine/database/crud.py`:
    * `add_transcript(db: sqlite3.Connection, transcript: Transcript)`: Checks for existence (e.g., by source hash or a unique external ID) before inserting. Returns bool indicating if added.
    * `get_latest_transcript_timestamp(db: sqlite3.Connection) -> date | None`.
    * Add helper function in `database/db_utils.py` for getting DB connection.
3.  Create `scripts/ingest_transcripts.py`:
    * Uses `config` for API details. Gets DB connection.
    * Calls `get_latest_transcript_timestamp` to determine `since_date`.
    * Calls `fetch_transcripts`.
    * Iterates results, calls `add_transcript`. Logs success/skips/errors.
4.  Write tests `tests/ingest/test_fetcher.py` (use `httpx` mocking like `respx`).
5.  Write tests `tests/database/test_crud_transcripts.py`.

**✅ Acceptance Criteria:**
* `python scripts/ingest_transcripts.py` (run inside container or with local venv pointing to DB volume) fetches data and stores unique transcripts in SQLite.
* Re-running fetches only newer transcripts based on timestamp logic.
* Errors during fetching/parsing/saving are logged appropriately.

---

### **Phase 2.2 — Chunking & Embedding Pipeline**

**🔺 Target:**
Process stored transcripts: chunk them, generate embeddings, store chunks in SQLite, and store embeddings in Chroma.

**🖊️ Description:**
Create a script that coordinates chunking, embedding, and storage using the defined interfaces and DB layer.

**🔧 AI Coder Instructions (Cursor):**
1.  Add embedding model dependencies: `poetry add sentence-transformers langchain-text-splitters` (add `nltk` if using that for chunking).
2.  Implement `transcript_engine/embeddings/bge_local.py` (or similar) fully implementing `EmbeddingInterface`. Load model specified in `config` (e.g., `BAAI/bge-small-en-v1.5`). Add error handling for model loading and embedding process. Handle device placement (CPU/GPU/MPS).
3.  Implement `transcript_engine/ingest/chunker.py`:
    * Function `chunk_transcript(transcript: Transcript, chunk_size: int, chunk_overlap: int) -> list[Chunk]`.
    * Use `RecursiveCharacterTextSplitter` (configure `length_function=len`, `chunk_size`, `chunk_overlap`).
    * Populate `Chunk` models, ensuring metadata includes `transcript_id` and ideally character offsets or precise timestamps if available from source. Generate unique `chunk.id` (e.g., UUID).
4.  Implement required functions in `transcript_engine/database/crud.py`:
    * `get_transcripts_needing_chunking(db: sqlite3.Connection) -> list[Transcript]`.
    * `add_chunks(db: sqlite3.Connection, chunks: list[Chunk])`.
    * `get_chunks_needing_embedding(db: sqlite3.Connection, limit: int = 100) -> list[Chunk]`.
    * `mark_transcript_chunked(db: sqlite3.Connection, transcript_id: str)`.
    * `mark_chunks_embedded(db: sqlite3.Connection, chunk_ids: list[str])`.
5.  Create `scripts/process_transcripts.py`:
    * Initialize DB connection, `EmbeddingInterface` (concrete), `VectorStoreInterface` (concrete).
    * **Chunking Step:** Get transcripts (`get_transcripts_needing_chunking`), loop through, chunk (`chunk_transcript`), save chunks (`add_chunks`), mark transcript processed (`mark_transcript_chunked`). Add logging/error handling.
    * **Embedding Step:** Loop while True: Get batch of chunks (`get_chunks_needing_embedding`), if no chunks break loop. Embed chunk texts (`embed_documents`), add to vector store (`vector_store.add` with chunks and embeddings), mark chunks embedded (`mark_chunks_embedded`). Add batching, logging, error handling.
6.  Write tests for `ingest/chunker.py`, `embeddings/bge_local.py`.
7.  Update `tests/database/test_crud_chunks.py`.

**✅ Acceptance Criteria:**
* Running `python scripts/process_transcripts.py` chunks transcripts, saves chunks to SQLite, generates embeddings using the specified local model, stores them in Chroma, and updates status flags in SQLite.
* Re-running processes only new/unprocessed data.
* Embeddings and metadata are searchable in Chroma via `test_chroma_store.py` or a dedicated test script.

---

**Phase Completion Result:**
* Robust ingestion and embedding pipeline using modular interfaces.
* Transcript data chunked, stored, embedded, and indexed.
* Ready for Phase 3: implementing the query logic.

---

## **Phase 3.0 — Query Interface + LLM Response Generation**

### 🌟 **Goal:**
Implement the core RAG query flow: embed user query, retrieve relevant chunks from Chroma, use LLM via interface to synthesize an answer, and provide a CLI interface.

---

### **Phase 3.1 — Query Retrieval Logic**

**🔺 Target:**
Implement the logic to retrieve relevant chunks based on a user query.

**🖊️ Description:**
Use the embedding and vector store interfaces to perform similarity search.

**🔧 AI Coder Instructions (Cursor):**
1.  Implement `transcript_engine/query/retriever.py`:
    * Create class `SimilarityRetriever`. Constructor takes `embedding_service: EmbeddingInterface` and `vector_store: VectorStoreInterface`.
    * Implement method `retrieve(query_text: str, k: int, filter_metadata: dict | None = None) -> list[Chunk]`.
    * Inside `retrieve`: Embed the query (`embedding_service.embed_query`), query the vector store (`vector_store.query` with embedding, k, filter). Add logging and error handling (e.g., if vector store fails).
2.  Write tests `tests/query/test_retriever.py` using stub/mock interfaces.

**✅ Acceptance Criteria:**
* `SimilarityRetriever` class implemented and tested.
* Can retrieve relevant `Chunk` objects (containing text and metadata) for a given query text.

---

### **Phase 3.2 — LLM Response Generation Logic**

**🔺 Target:**
Implement logic to generate a response using retrieved context and the LLM interface.

**🖊️ Description:**
Assemble context, formulate a prompt, and call the LLM.

**🔧 AI Coder Instructions (Cursor):**
1.  Implement `transcript_engine/query/generator.py`:
    * Create class `ResponseGenerator`. Constructor takes `llm_service: LLMInterface`.
    * Implement method `generate_response(query: str, retrieved_chunks: list[Chunk], chat_history: list[ChatMessage] | None = None) -> tuple[str, list[Chunk]]`.
    * Inside `generate_response`:
        * Format `retrieved_chunks` into a context string (e.g., join `chunk.text` with metadata hints).
        * Format optional `chat_history` into a history string.
        * Construct a clear prompt including history (if any), context, and the query. (e.g., "Chat History:\n{history}\n\nContext from transcripts:\n{context}\n\nQuestion:\n{query}\n\nAnswer:").
        * Call the LLM interface (`llm_service.generate(prompt)` or `llm_service.chat(...)` if using chat endpoint). Add logging and error handling (e.g., if LLM fails).
        * Return the LLM's text response *and* the `retrieved_chunks` used.
2.  Write tests `tests/query/test_generator.py` using a stub LLM interface.

**✅ Acceptance Criteria:**
* `ResponseGenerator` implemented and tested.
* Generates a string response and returns the source chunks used.
* Handles optional chat history in prompt construction.

---

### **Phase 3.3 — CLI Chat Interface with History**

**🔺 Target:**
Create the `ask.py` CLI tool integrating retrieval and generation, with session history stored in SQLite.

**🖊️ Description:**
Provide a command-line entry point for users to query transcripts conversationally.

**🔧 AI Coder Instructions (Cursor):**
1.  Implement `scripts/ask.py`:
    * Use `typer` for a cleaner CLI interface (`poetry add typer`). Define commands/arguments (e.g., `main(query: str, session_id: str | None = None)`).
    * In `main`: Initialize DB connection, concrete interfaces (`BGELocalEmbeddings`, `ChromaStore`, `OllamaClient`).
    * Instantiate `SimilarityRetriever` and `ResponseGenerator`.
    * Implement chat loop or single-shot query logic:
        * Load chat history for `session_id` using `crud.get_chat_history` (if `session_id` provided).
        * Retrieve relevant chunks (`retriever.retrieve`).
        * Generate response (`generator.generate_response`, passing query, chunks, history). Returns `(answer_text, source_chunks)`.
        * Format tracebacks from `source_chunks` metadata (e.g., "🔗 Session Y, Timestamp ZZZ").
        * Print the `answer_text` and formatted tracebacks.
        * Create new `ChatMessage` objects for user query and assistant response.
        * Save query and response messages to chat history using `crud.add_chat_message` (pass `session_id`).
2.  Implement `database/crud.py` functions `add_chat_message(db, message: ChatMessage)` and `get_chat_history(db, session_id: str) -> list[ChatMessage]`. Define `chat_sessions` table schema in `schema.py` (columns: `session_id`, `timestamp`, `role` (`user`/`assistant`), `content`, maybe `source_chunk_ids`).
3.  Update `tests/database/test_crud_chat.py`.
4.  Add basic instructions on how to run `ask.py` to `README.md`.

**✅ Acceptance Criteria:**
* `python scripts/ask.py --query "..."` returns LLM answer with tracebacks.
* `python scripts/ask.py --query "..." --session-id my_session` maintains conversation history across runs in SQLite.
* Tracebacks link clearly to source metadata (session/timestamp).

---

**Phase Completion Result:**
* Core RAG pipeline operational via CLI.
* Answers grounded in retrieved context with tracebacks.
* Conversational history persisted in SQLite.
* Ready for Phase 4: Building the Web UI.

---

## **Phase 4.0 — Web UI + Session Management**

### 🌟 **Goal:**
Provide a lightweight, chat-style web interface using FastAPI and HTMX.

---

### **Phase 4.1 — FastAPI Server + HTMX Frontend**

**🔺 Target:**
Serve a dynamic chat frontend, handle user queries via POST requests using HTMX.

**🖊️ Description:**
Set up FastAPI routes, Jinja2 templates, and HTMX interactions for a basic chat UI.

**🔧 AI Coder Instructions (Cursor):**
1.  Implement `transcript_engine/api/routers/chat.py`:
    * Create FastAPI `APIRouter`. Use FastAPI's `Depends` for dependency injection of services (Retriever, Generator, DB connection/session).
    * Add GET `/` endpoint: Renders `templates/chat.html`. Generate a unique session ID (e.g., `uuid.uuid4()`) if none exists (e.g., in cookie) and pass it to template.
    * Add POST `/ask` endpoint (triggered by HTMX):
        * Accept form data (user query, session ID). Use Pydantic model for validation if preferred over form data.
        * Get/validate `session_id`.
        * Load chat history (`crud.get_chat_history`).
        * Run retrieval (`retriever.retrieve`).
        * Run generation (`generator.generate_response`, passing history). Returns `(answer_text, source_chunks)`.
        * Save user query and assistant response messages (`crud.add_chat_message`).
        * Format tracebacks from `source_chunks`.
        * Render an HTML fragment using `templates/_chat_message.html` (pass `answer_text`, `tracebacks`, `role='assistant'`). Return `HTMLResponse`.
2.  Implement dependency injection setup in `main.py` or `core/dependencies.py` to provide instances of services (Retriever, Generator, etc.).
3.  Create `transcript_engine/main.py`: Initialize FastAPI app, include chat router, mount `/static` directory.
4.  Create `templates/base.html` (include HTMX script).
5.  Create `templates/chat.html`: Basic chat layout, includes form with `hx-post="/ask"`, `hx-target="#chat-history"`, `hx-swap="beforeend"`. Include hidden input for `session_id`. Display initial chat history if needed. Div with `id="chat-history"`.
6.  Create `templates/_chat_message.html`: Renders a single chat message (user or assistant), including formatted tracebacks for assistant messages.
7.  Add basic CSS in `static/style.css`.

**✅ Acceptance Criteria:**
* Web app accessible at `http://localhost:8000`.
* Chat interface loads, user can submit questions.
* Assistant responses appear dynamically below the user query via HTMX.
* Responses include formatted tracebacks.
* Session ID is maintained across requests (e.g., via hidden form field).

---

### **Phase 4.2 — Streaming Responses & UI Polish**

**🔺 Target:**
Implement streaming responses for LLM generation and improve UI feedback.

**🖊️ Description:**
Use FastAPI's streaming capabilities and HTMX extensions for a more responsive chat experience.

**🔧 AI Coder Instructions (Cursor):**
1.  Refactor `LLMInterface` and `OllamaClient`: Add a `stream()` method that yields response chunks (e.g., `async def stream(...) -> AsyncIterator[str]:`). Modify Ollama client to use `stream=True` and yield content parts.
2.  Refactor `ResponseGenerator`: Add a `stream_response()` method that calls `llm_service.stream()` and yields chunks. Decide how/when to return source chunk info (e.g., yield it first or last, or return separately).
3.  Refactor POST `/ask` endpoint in `chat.py`:
    * Make the endpoint `async`.
    * Call `generator.stream_response()`.
    * Return FastAPI's `StreamingResponse` yielding the chunks from the generator. (This simple streaming won't easily interleave tracebacks - consider alternative UI pattern or separate endpoint for tracebacks if needed, or use WebSockets later).
    * *Simpler non-streaming alternative:* Keep `/ask` synchronous but add UI indicator during processing.
4.  (Optional UI Polish): Add loading indicator triggered by HTMX `htmx:beforeRequest` event. Use HTMX Server-Sent Events extension (`hx-ext="sse"`) for cleaner streaming if implementing SSE on the server.

**✅ Acceptance Criteria:**
* (If Streaming Implemented): LLM response streams into the web UI token by token.
* (If Non-Streaming): UI provides feedback (e.g., loading indicator) while waiting for response.
* Chat history saving still occurs correctly.

---

**Phase Completion Result:**
* Functional web chat UI with conversational context and tracebacks.
* Improved responsiveness through streaming or loading indicators.
* Ready for Phase 5: Advanced Features.

---

## **Phase 5.0 — Smart Summarization, Trends, and Task Extraction**

### 🌟 **Goal:**
Add high-value summarization, tracking, and task export features accessible via CLI or potentially new API endpoints.

---

### **Phase 5.1 — Daily/Weekly Transcript Summaries**

**🔺 Target:**
Generate summaries for conversations over specific date ranges using the LLM.

**🖊️ Description:**
Create a feature module and script to handle summarization.

**🔧 AI Coder Instructions (Cursor):**
1.  Implement `transcript_engine/features/summarizer.py`:
    * Function `summarize_transcripts(db: sqlite3.Connection, llm: LLMInterface, start_date: date, end_date: date) -> dict[str, str]`.
    * Query `crud.get_chunks_by_date_range` (implement this in `crud.py`).
    * Group chunks (e.g., by day or session ID within the range).
    * For each group: Format context, create a specific summarization prompt, call `llm.generate()`. Add error handling. Store results in a dictionary (e.g., `{day_or_session: summary}`).
2.  Create `scripts/summarize.py` CLI tool (using `typer`): Takes date range arguments, initializes DB/LLM, calls `summarize_transcripts`, prints results.
3.  Write tests for `summarizer.py` and `crud.get_chunks_by_date_range`.

**✅ Acceptance Criteria:**
* `python scripts/summarize.py --start=YYYY-MM-DD --end=YYYY-MM-DD` generates and prints coherent summaries.

---

### **Phase 5.2 — Trend + Topic Tracker (NER)**

**🔺 Target:**
Track recurring named entities using spaCy.

**🖊️ Description:**
Create feature module and script for NER-based trend tracking.

**🔧 AI Coder Instructions (Cursor):**
1.  Run `poetry run python -m spacy download en_core_web_sm`.
2.  Implement `transcript_engine/features/tracker.py`:
    * Function `track_trends(db: sqlite3.Connection, start_date: date, end_date: date, top_n: int = 10) -> dict[str, list[tuple[str, int]]]`.
    * Load spaCy model (`spacy.load("en_core_web_sm")`).
    * Get chunk texts via `crud.get_chunks_by_date_range`.
    * Process texts using `nlp.pipe()` for efficiency. Extract relevant entities (PERSON, ORG, maybe custom rules for PROJECT).
    * Aggregate entity frequencies (case-insensitive).
    * Return dictionary of top N entities per category (e.g., `{'PERSON': [('Alice', 5), ...], 'ORG': [...]}`). Add error handling.
3.  Create `scripts/track_trends.py` CLI tool using `typer`.
4.  Write tests for `tracker.py`.

**✅ Acceptance Criteria:**
* `python scripts/track_trends.py --start=YYYY-MM-DD --end=YYYY-MM-DD` outputs list of trending entities and frequencies.

---

### **Phase 5.3 — Reminder / Task Detection + Export**

**🔺 Target:**
Extract actionable items and optionally export to Google Calendar/Tasks.

**🖊️ Description:**
Implement task extraction logic and Google API integration.

**🔧 AI Coder Instructions (Cursor):**
1.  Implement `transcript_engine/features/task_extractor.py`:
    * Function `extract_potential_tasks(text: str) -> list[str]`: Use regex/keywords first for simplicity (e.g., match patterns like "follow up on", "remind me to", "action item:", "schedule meeting with"). Return list of matching sentences/phrases.
    * (Optional Later): Enhance `extract_potential_tasks` using `LLMInterface` with a specific prompt to identify tasks, assignees, and deadlines.
    * Function `export_to_google(task_details: dict, service_name: str)`: Implement Google API interaction using `googleapiclient.discovery.build` for 'calendar' (v3) or 'tasks' (v1). Handle OAuth2 flow for user authentication (store/refresh tokens securely). See Google API Python Quickstarts. Add robust error handling for API calls.
2.  Create `scripts/extract_tasks.py` CLI tool:
    * Takes date range or session ID. Gets relevant transcript/chunk text.
    * Calls `extract_potential_tasks`.
    * Presents potential tasks to user.
    * If user confirms: Prompts for details (if needed, e.g., due date). Initiates OAuth flow if first time. Calls `export_to_google`.
3.  Add detailed Google Cloud Project setup and OAuth instructions to `README.md`.
4.  Write tests for extraction logic and mock Google API interactions for `export_to_google`.

**✅ Acceptance Criteria:**
* `scripts/extract_tasks.py` identifies potential action items from transcripts.
* User interaction allows confirming and exporting tasks to Google Calendar or Tasks after successful authentication.

---

**Phase Completion Result:**
* Advanced summarization, trend tracking, task extraction features added via CLI tools.
* Ready for Phase 6 (Optional).

---

## **Phase 6.0 — Audio Sync + Timeline Visualization (Optional Stretch)**

### 🌟 **Goal:**
Link transcript segments to audio files and add timeline visualization.

---

### **Phase 6.1 — Audio Linking**

**🔺 Target:**
Support clickable links in UI that jump to timestamped audio playback.

**🖊️ Description:**
Assume audio files exist locally; link transcript chunk metadata to audio time offsets.

**🔧 AI Coder Instructions (Cursor):**
1.  Modify `Transcript` and `Chunk` models/schema: Add optional fields for `audio_file_path` (on Transcript) and `start_seconds`, `end_seconds` (on Chunk).
2.  Update ingestion/chunking logic (Phase 2) to populate these fields if the source API provides precise word timings or if alignment can be done separately. Assume manual linking or separate alignment process for now.
3.  Modify `/ask` endpoint response/HTML fragments (`_chat_message.html`): If `start_seconds` exists in chunk metadata used for traceback, render a link/button like `<button hx-get="/play_audio?session_id=...&start=...">Play @ {timestamp}</button>`.
4.  Add FastAPI endpoint `GET /play_audio`: Takes `session_id`, `start_seconds`. Finds audio file path from `crud`. Returns JavaScript/HTMX response to control an HTML5 `<audio>` player on the page (e.g., set `audio.src` and `audio.currentTime`, then `audio.play()`).
5.  Add `<audio controls id="audio-player">` element to `chat.html`.

**✅ Acceptance Criteria:**
* Traceback links in UI, when clicked, trigger audio playback from the correct time in the associated audio file.

---

### **Phase 6.2 — Timeline UI + Heatmap**

**🔺 Target:**
Render a simple timeline/heatmap visualization of conversation activity.

**🖊️ Description:**
Aggregate chunk timestamps and use a charting library.

**🔧 AI Coder Instructions (Cursor):**
1.  Add dependency: e.g., `plotly` (`poetry add plotly`).
2.  Implement `transcript_engine/features/visualizer.py`:
    * Function `generate_timeline_data(db: sqlite3.Connection, start_date: date, end_date: date) -> list[dict]`: Query chunks/transcripts in date range, aggregate data suitable for plotting (e.g., count per day/hour, session durations).
    * Function `create_timeline_plot(data)`: Use Plotly Express or similar to generate chart definition (e.g., histogram, heatmap) as JSON or HTML div.
3.  Add FastAPI endpoint (e.g., GET `/timeline`): Calls `generate_timeline_data`, `create_timeline_plot`, renders template displaying the plot.
4.  Alternatively, create endpoint returning JSON data and use a frontend JS charting library (Plotly.js, Chart.js) integrated via script tag in `chat.html` or a dedicated dashboard page.

**✅ Acceptance Criteria:**
* A new page or section in the web UI displays a visualization (e.g., bar chart of activity per day) based on transcript timestamps.

---

**Phase Completion Result:**
* Optional visual/audio extensions implemented.
* Transcript engine supports semantic and auditory navigation with UI overlays.
* Project is feature-complete based on PRD and stretch goals.
