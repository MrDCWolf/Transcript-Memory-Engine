# Product Requirements Document (PRD)
**Project Name:** Transcript Memory Engine
**Version:** 1.0
**Date:** 2025-05-03
**Owner:** Daniel Wolf

---

## 1. Overview

The **Transcript Memory Engine** is a **local-first**, high-performance desktop application designed for MacOS (targeting modern versions like Sonoma 14.x and above). It enables users to ingest, explore, and query large volumes of personal transcription data using natural language. The core functionality revolves around providing fast, context-aware Q&A, detailed recall, and thematic analysis across potentially weeks or months of conversations, all while prioritizing user privacy and local data control.

The system will feature a chat-style interface (both CLI and Web UI via HTMX) mimicking modern LLM interactions (e.g., ChatGPT, Claude), but grounded in the user's actual transcript data. Crucially, it will provide clear, clickable **tracebacks** linking AI-generated answers directly to the relevant segments within the source transcripts.

Development will leverage AI coding assistants (Cursor/Windsurf) within a containerized Docker environment managed by Poetry for dependency handling.

---

## 2. Goals

* **🎯 Local-First Operation:** All core processing (embedding, storage, querying, LLM inference) should run locally on the user's machine (Mac Studio target) without mandatory cloud dependencies.
* **⚡ High Performance:** Deliver near-instantaneous (< 3 seconds) responses to natural language queries over the transcript corpus. Ensure efficient ingestion and embedding.
* **🧠 Accurate & Relevant Recall:** Provide contextually accurate answers based *only* on the ingested transcript data.
* **🔗 Traceability:** Every generated answer must allow the user to easily trace back to the specific source transcript segment(s) (e.g., via session ID and timestamp) used as context.
* **🗣️ Conversational Interface:** Offer an intuitive chat-like UI (CLI and Web) for querying and exploring transcripts, maintaining conversation history per session.
* **🧩 Modularity & Extensibility:** Design the system with clearly defined interfaces for core components (LLM, Embeddings, Vector Store) to allow for easy experimentation, upgrades, or swapping of models/backends.
* **📈 Scalability (Local):** Handle a growing corpus of transcripts (potentially 1+ year's worth) efficiently within the constraints of a local desktop environment.
* **🔒 Privacy:** Ensure transcript data remains local and is not sent to external services unless explicitly configured (e.g., using OpenAI fallback).

---

## 3. Key Features & Functionality

### 3.1. Development Environment & Setup (Phase 1)
* **Containerized Environment:** Utilize Docker and Docker Compose for a reproducible local development and runtime environment.
* **Dependency Management:** Use Poetry for managing Python dependencies.
* **Configuration:** Load sensitive keys and configuration parameters (paths, URLs, model names) via environment variables (`.env` file) using `pydantic-settings`.
* **Project Structure:** Maintain a clean, modular project structure with distinct directories for interfaces, services, data models, API, scripts, etc.
* **Makefile:** Provide simple `make` commands for common development tasks (setup, run, test, lint, format, db init).

### 3.2. Ingestion & Processing Pipeline (Phase 2)
* **API Ingestion:** Fetch structured transcript data (text, timestamps, speaker tags, session metadata) from a specified external API.
* **Incremental Fetching:** Only fetch transcripts newer than the latest one already stored.
* **Data Validation:** Use Pydantic models (`Transcript`) to validate incoming data structure.
* **Structured Storage (SQLite):** Store normalized transcript metadata and text reliably in a local SQLite database (`transcripts.db`). Manage schema via code (`database/schema.py`). Implement CRUD operations (`database/crud.py`).
* **Deduplication:** Prevent duplicate transcript entries based on source hash or unique ID during ingestion.
* **Chunking:** Split transcripts into smaller, semantically meaningful chunks (e.g., < 300 tokens) suitable for embedding, using methods like `RecursiveCharacterTextSplitter`. Store chunk data (including `transcript_id` and offsets/timestamps) in SQLite.
* **Embedding:**
    * Utilize a pluggable `EmbeddingInterface`.
    * Default to a high-performance local embedding model (e.g., `BAAI/bge-small-en-v1.5`) via `sentence-transformers`.
    * Generate embeddings for new/updated chunks.
    * Track embedding status in the SQLite database.
* **Vector Storage (Chroma):**
    * Utilize a pluggable `VectorStoreInterface`.
    * Default implementation using `chromadb` with persistent local storage (`data/chroma_db`).
    * Store chunk embeddings along with their corresponding text and queryable metadata (chunk ID, transcript ID, timestamps, speaker).

### 3.3. Query & Response Generation (RAG Core) (Phase 3)
* **Query Embedding:** Embed user's natural language query using the *same* model defined by the `EmbeddingInterface`.
* **Vector Retrieval:**
    * Implement retrieval logic via `SimilarityRetriever` class.
    * Query the `VectorStoreInterface` (Chroma) to find top-K most similar chunks based on vector similarity to the query embedding.
    * Retrieve chunk text and associated metadata.
* **LLM Interaction:**
    * Utilize a pluggable `LLMInterface`.
    * Default implementation using `OllamaClient` to interact with a locally running Ollama service (e.g., serving Mistral, LLaMA 3).
    * Support optional fallback to OpenAI API if configured.
* **Prompt Engineering:** Construct a clear prompt for the LLM, including:
    * Optional chat history from the current session.
    * Retrieved context chunks (formatted clearly).
    * The user's current query.
* **Response Generation:**
    * Implement generation logic via `ResponseGenerator` class.
    * Send the constructed prompt to the `LLMInterface`.
    * Receive the LLM's generated text response.
* **Traceback Generation:** Associate the generated response with the specific `Chunk` objects used as context, enabling UI links.

### 3.4. User Interfaces (Phase 3 & 4)
* **CLI Interface (`ask.py`):**
    * Provide a command-line tool for single-shot or conversational queries.
    * Accept query text and optional session ID.
    * Display LLM response and formatted traceback links (e.g., "🔗 Session Y, Timestamp ZZZ").
    * Persist conversation history (user query, assistant response, source chunks) per session ID in the SQLite database (`chat_sessions` table).
* **Web Interface (FastAPI + HTMX):**
    * Serve a dynamic, single-page chat application using FastAPI.
    * Utilize Jinja2 for templating and HTMX for dynamic updates without full page reloads.
    * Maintain session context (via hidden fields or cookies).
    * Handle user queries via POST requests to a `/ask` endpoint.
    * Display chat history, streaming LLM responses (optional), and clickable traceback links.

### 3.5. Advanced Features (Phase 5 - Stretch Goals)
* **Smart Summarization:** Generate summaries of transcripts based on date ranges (daily/weekly) using the `LLMInterface`. Provide via CLI script initially.
* **Trend & Topic Tracking:** Use NER (e.g., spaCy) to identify and track frequency of named entities (People, Orgs, Projects) over time. Provide via CLI script initially.
* **Task Extraction & Export:** Identify potential action items/reminders using regex/LLM. Provide CLI tool to confirm and export tasks to Google Calendar/Tasks via Google API client libraries (requires user OAuth).

### 3.6. Audio Integration (Phase 6 - Optional Stretch Goal)
* **Audio File Storage:** Assume audio files corresponding to transcripts can be stored locally (e.g., `data/audio/{session_id}.mp3`).
* **Timestamp Linking:** If precise timings are available, link transcript chunks to `start_seconds`/`end_seconds` in the audio file (requires schema/ingestion update).
* **Web UI Playback:** Implement clickable links in the web UI tracebacks that trigger playback of the relevant audio segment using an HTML5 `<audio>` player.

### 3.7. Visualization (Phase 6 - Optional Stretch Goal)
* **Timeline/Heatmap:** Provide a simple visualization (e.g., using Plotly) showing transcript activity density over time, potentially integrated into the web UI.

---

## 4. Technical Architecture & Stack

| Layer/Component         | Tool/Technology                                 | Rationale / Notes                                                                 |
| :---------------------- | :---------------------------------------------- | :-------------------------------------------------------------------------------- |
| **Language** | Python 3.11+                                    | Strong AI/ML ecosystem, excellent libraries, good AI coder support.               |
| **Web Framework** | FastAPI                                         | High performance, async support, auto-docs, Pydantic integration.                 |
| **Web Frontend** | HTMX + Jinja2                                   | Lightweight dynamic UI without heavy JS framework, server-side rendering focus.   |
| **ASGI Server** | Uvicorn                                         | Standard, high-performance ASGI server for FastAPI.                               |
| **Local LLM Service** | Ollama                                          | Easy local hosting of various quantized LLMs (Mistral, LLaMA 3, etc.) on MacOS.     |
| **LLM Interface** | `LLMInterface` (Protocol/ABC)                   | Allows swapping Ollama, OpenAI, or other backends.                                |
| **Embedding Model** | `sentence-transformers` (e.g., BAAI/bge-small)  | High-quality local embeddings, runs efficiently on CPU/MPS.                       |
| **Embedding Interface** | `EmbeddingInterface` (Protocol/ABC)             | Allows swapping local models or cloud APIs (e.g., OpenAI).                        |
| **Vector Database** | ChromaDB                                        | Open-source, Python-native, designed for RAG, persistent local storage.           |
| **Vector DB Interface** | `VectorStoreInterface` (Protocol/ABC)           | Allows swapping Chroma or other vector stores.                                    |
| **Structured Storage** | SQLite                                          | Simple, file-based, performant for single-user local data (transcripts, chunks, sessions). |
| **Data Validation** | Pydantic                                        | Core data models, API request/response validation, settings management.           |
| **Chunking Strategy** | `langchain-text-splitters` or similar           | Robust text splitting respecting semantic boundaries.                             |
| **NER (Trends)** | spaCy (`en_core_web_sm`)                        | Efficient local named entity recognition.                                         |
| **Task Export** | `google-api-python-client`                      | Standard library for Google Calendar/Tasks integration.                           |
| **Dev Environment** | Docker / Docker Compose                         | Reproducible environment, service orchestration.                                  |
| **Dependency Mgmt** | Poetry                                          | Robust dependency locking and packaging.                                          |
| **AI Coding Assistant** | Cursor / Windsurf                               | Leverage AI for faster development, refactoring, and debugging.                   |
| **Target Platform** | MacOS (Sonoma 14.x+)                            | Optimized for local execution on modern Mac hardware (Mac Studio).                |

---

## 5. Performance Targets

| Task                          | Target Time       | Notes                                     |
| :---------------------------- | :---------------- | :---------------------------------------- |
| Query Retrieval (Vector)      | < 0.5 seconds     | Time to get top-K chunks from Chroma.     |
| LLM Inference (Local Ollama)  | < 2 seconds       | Time for LLM to generate response text.   |
| **End-to-End Query Response** | **< 3 seconds** | Total time from query submission to display. |
| Traceback Link Generation     | Instant (< 0.1s)  | Should be immediate based on retrieved metadata. |
| Transcript Ingestion          | Variable          | Depends on API speed and volume.          |
| Chunking/Embedding            | Offline/Batched   | Can run as background/scripted process.   |

---

## 6. User Flow (Core RAG Cycle)

1.  **(Offline Prep):** User runs ingestion (`ingest_transcripts.py`) and processing (`process_transcripts.py`) scripts to populate SQLite and ChromaDB.
2.  **Query Input:** User enters a natural language question via the CLI (`ask.py`) or the Web UI.
3.  **Query Embedding:** The system embeds the user's query using the configured `EmbeddingInterface`.
4.  **Chunk Retrieval:** The system queries the `VectorStoreInterface` (Chroma) using the query embedding to retrieve the top-K most relevant transcript `Chunk` objects.
5.  **Prompt Assembly:** The system constructs a prompt for the LLM, including chat history (if applicable), the retrieved context chunks, and the user's query.
6.  **LLM Generation:** The system sends the prompt to the configured `LLMInterface` (Ollama).
7.  **Response & Traceback:** The LLM generates an answer. The system displays the answer to the user along with clickable traceback links derived from the metadata of the source `Chunk` objects used in the prompt.
8.  **History Logging:** The user's query and the assistant's response (including source chunk references) are saved to the session history in the SQLite database.

---

## 7. Non-Goals (Out of Scope for v1.0 unless explicitly in Stretch Goals)

* Real-time transcription.
* Multi-user support or collaboration features.
* Cloud-hosted deployment (focus is local-first).
* Advanced agentic behavior beyond RAG.
* Complex data visualization beyond basic timelines/heatmaps (Phase 6).
* Automatic audio alignment (assumes timestamps or separate process).
* Support for operating systems other than MacOS.

---

## 8. Open Questions / Considerations

* Specific format and content of the external transcript API? (Assume structured JSON/Text with timestamps/speakers).
* Exact schema/granularity of timestamps provided by the source API? (Affects chunking and traceback precision).
* Optimal chunking strategy (size, overlap, splitting method) for the specific transcript data? (Requires experimentation).
* Performance of different local embedding models (`bge-small` vs. others) on the target hardware?
* Performance of different Ollama-served LLMs (Mistral vs. LLaMA 3 vs. others) for response quality vs. speed?
* Scalability limits of SQLite and Chroma with very large datasets on the target hardware? (Monitor over time).
* Details of the OAuth flow and token management for Google API integration.
