# Rafiq

An internal assistant for company employees. Rafiq answers questions from the company knowledge base using retrieval-augmented generation (RAG), answers general questions directly, and can answer strictly from a document the user uploads.

- **Chat model:** served through the company AI proxy (OpenAI-compatible endpoint).
- **Embeddings:** computed locally with Chroma's built-in `all-MiniLM-L6-v2` (ONNX, CPU). The proxy serves no embedding models.
- **Vector store:** ChromaDB, persisted in `data/chroma_db/`.
- **Frontend:** React + Vite app in `app/frontend/`.

## How a question is answered

`POST /api/ask` goes through `handle_question()` in `app/core/orchesterator.py`:

| Mode | When | What happens |
|---|---|---|
| `strict_document` | request has a `document_id` (from an upload) | retrieves only from that uploaded document |
| `direct` | the router (`app/core/router.py`) says the question is general knowledge | answered by the model with no retrieval |
| `retrieved` | everything else | retrieves from the company knowledge base (`company_kb` scope) |

If retrieval finds nothing, the response has `needs_upload: true` and asks the user to upload a relevant document.

## Setup

Backend (uses the `rafiq` conda environment):

```bash
conda activate rafiq
pip install -r requirements.txt
cp .env.example .env   # then fill in OPENAI_API_KEY
```

The first ingestion downloads the embedding model (~80 MB) to `~/.cache/chroma/`.

Frontend (needs Node.js; `brew install node` if missing):

```bash
cd app/frontend
npm install
```

## Usage

Put `.md`, `.txt` or `.pdf` files in `data/docs/`, then index them:

```bash
python -m app.ingestion.ingest
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

Start the frontend in a second terminal, then open http://localhost:5173:

```bash
cd app/frontend && npm run dev
```

The frontend calls `http://localhost:8000/api` by default. To point it elsewhere, set `VITE_API_BASE`, e.g. `VITE_API_BASE=http://host:8000/api npm run dev`.

### API

- `GET /health`: status, model and number of indexed chunks
- `POST /api/ask`: `{"question": "...", "document_id": "optional", "session_id": "optional"}`
  Returns `answer`, `mode`, `sources`, `needs_upload`, `usage`, `latency_ms`, `finish_reason`.
- `POST /api/upload`: multipart form with a `file` field (`.md`, `.txt` or `.pdf`, max 10 MB, text files must be UTF-8).
  Returns `document_id`, `filename`, `chunk_count`. Pass `document_id` to `/api/ask` to answer from that file.
- Interactive docs: http://127.0.0.1:8000/docs

## Project layout

```
app/
  main.py                 FastAPI app + CORS
  routes/
    ask_routes.py         /health and /api/ask
    upload_routes.py      /api/upload
  dto/                    request/response models
  core/
    orchesterator.py      picks the mode and answers the question
    router.py             LLM classifier: general question or company-specific?
    direct_agent.py       answers general questions without retrieval
    retrieval.py          embed question -> top-k chunks in a scope
    synthesis.py          builds prompt from chunks, calls chat model
    ingestion.py          chunk + embed + store one text (shared by ingest and upload)
    document_loader.py    extracts text from .md / .txt / .pdf
    chunking.py           token-window chunking (tiktoken cl100k_base)
    llm_client.py         chat via proxy, local embeddings
    vectore_store.py      ChromaDB wrapper
  prompts/system_prompts.py
  ingestion/ingest.py     indexes everything in data/docs
  config/settings.py      all tunables
  frontend/               React + Vite UI
data/docs/                knowledge base source files
```

## Known issues (to fix)

Last reviewed 2026-10-07.

### High priority

- [ ] **1. Retrieval returns every chunk, with no relevance cutoff.**
  `TOP_K = 4`, the knowledge base holds exactly 4 chunks, and `app/core/retrieval.py` doesn't filter by distance. Every `retrieved` answer gets the whole knowledge base as context and lists all 4 files as sources. It also means the "no relevant documents" / `needs_upload` path never triggers for the knowledge base or for a non-empty upload.
  The router now sends general questions to `direct` mode, which hides part of the problem.
  *Fix:* drop chunks whose distance is above a threshold. Measured distances on the current corpus (lower = more relevant):

  | Question | Closest doc | Distance |
  |---|---|---|
  | annual leave days | leave_policy | 0.79 |
  | benefits besides salary | company_benefits | 0.96 |
  | strategic goals 2026 | company_goals | 1.11 |
  | leaving policy | leave_policy | 1.41 |
  | hi / json / RMSprop / Egypt | (any) | 1.77 – 1.86 |

  A cutoff of about **1.5** separates them. Re-calibrate as the corpus grows.

- [ ] **2. RAG answers are truncated.**
  `synthesize()` uses the `chat_completion` default of `max_tokens=200` (`app/core/llm_client.py`). Four of eight test answers hit exactly 200 tokens and were cut off. (`direct` mode uses 500.)
  *Fix:* raise to ~800–1000.

- [ ] **3. System prompt sentences run together.**
  All three prompts in `app/prompts/system_prompts.py` are adjacent string literals with no spaces or periods between them, so the model receives `…company employeesAnswer using ONLY…`. Typos too: "and internal", "Aswer", "polices", "relevent", "rafiq".
  *Fix:* add separators and fix typos.

- [ ] **4. Re-running ingestion never updates documents.**
  `VectoreStore.add` uses `collection.add`, and Chroma silently skips IDs it already has. Edited files keep their old text, and deleted files are never removed.
  *Fix:* use `upsert` and remove chunks whose source no longer exists, or clear the `company_kb` scope before ingesting.

### Medium priority

- [ ] **5. Errors from the proxy become plain 500s.**
  *Fix:* catch `openai.APIError` / `openai.APITimeoutError` in `/api/ask` and return a clean 502/503 with a user-friendly message.

- [ ] **6. Uploaded documents are never cleaned up.**
  Each upload adds chunks under a `session:<id>` scope in the same collection, and nothing deletes them.
  *Fix:* expire or delete session scopes (e.g. on a TTL or an explicit "remove document" call).

- [ ] **7. Every non-upload question costs two model calls.**
  The router call runs before the answer, adding ~2 s (logged latency ~4.2 s).
  *Fix:* accept it, or use a cheaper/faster check (keywords, or embedding distance from issue 1).

### Minor

- [ ] **8.** `session_id` is accepted but unused, so there's no conversation memory between questions.
- [ ] **9.** `GET /` returns 404. Add a simple root route or redirect to `/docs`.
- [ ] **10.** Uploads are read fully into memory before the size check.
- [ ] **11.** `loguru` is in `requirements.txt` but nothing imports it.
- [ ] **12.** Typos in names: `VectoreStore` / `vectore_store.py`, `orchesterator.py`, "Singletone", "lmit", "maybe" (→ "may be") in the truncation note.

### Fixed

- `sources` is now returned by `/api/ask`.
- `ROUTER_MAX_TOKENS` / `ROUTER_TEMPERATURE` are now used by the router.
- Corrupt/encrypted PDFs, non-UTF-8 text files and missing filenames in uploads return a 400 with a clear message instead of a 500.

### Notes

- If the embedding model is ever changed, delete `data/chroma_db/` and re-run ingestion. Vectors from different models can't be compared.
- `cl100k_base` is an OpenAI tokenizer used as an approximation for chunk sizing. Claude's tokenizer counts slightly differently.
