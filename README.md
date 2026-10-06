# Rafiq

An internal assistant for company employees. Rafiq answers questions from the company knowledge base using retrieval-augmented generation (RAG), and can also answer general questions.

- **Chat model:** served through the company AI proxy (OpenAI-compatible endpoint).
- **Embeddings:** computed locally with Chroma's built-in `all-MiniLM-L6-v2` (ONNX, CPU). The proxy serves no embedding models.
- **Vector store:** ChromaDB, persisted in `data/chroma_db/`.

## Setup

Uses the `rafiq` conda environment.

```bash
conda activate rafiq
pip install -r requirements.txt
cp .env.example .env   # then fill in OPENAI_API_KEY
```

The first ingestion downloads the embedding model (~80 MB) to `~/.cache/chroma/`.

## Usage

Put `.md`, `.txt` or `.pdf` files in `data/docs/`, then index them:

```bash
python -m app.ingestion.ingest
```

Start the API:

```bash
uvicorn app.main:app --reload --port 8000
```

- `GET /health`: status, model and number of indexed chunks
- `POST /api/ask`: `{"question": "...", "session_id": "optional"}`
- Interactive docs: http://127.0.0.1:8000/docs

## Project layout

```
app/
  main.py                 FastAPI app + CORS
  routes/ask_routes.py    /health and /api/ask
  core/
    document_loader.py    reads files from data/docs
    chunking.py           token-window chunking (tiktoken cl100k_base)
    llm_client.py         chat via proxy, local embeddings
    vectore_store.py      ChromaDB wrapper
    retrieval.py          embed question -> top-k chunks
    synthesis.py          builds prompt, calls chat model
  prompts/system_prompts.py
  ingestion/ingest.py     indexing script
  config/settings.py      all tunables
data/docs/                knowledge base source files
```

## Known issues (to fix)

Found while reviewing the first end-to-end run (2026-10-07).

### High priority

- [ ] **1. Retrieval returns every document for every question.**
  `TOP_K = 4` and the store holds exactly 4 chunks, and there is no relevance cutoff in `app/core/retrieval.py`. Even "what is json?" gets the whole knowledge base as context, and every response lists all 4 files as sources.
  *Fix:* drop chunks whose distance is above a threshold. Measured distances on the current corpus (lower = more relevant):

  | Question | Closest doc | Distance |
  |---|---|---|
  | annual leave days | leave_policy | 0.79 |
  | benefits besides salary | company_benefits | 0.96 |
  | strategic goals 2026 | company_goals | 1.11 |
  | leaving policy | leave_policy | 1.41 |
  | hi / json / RMSprop / Egypt | (any) | 1.77 – 1.86 |

  A cutoff of about **1.5** separates them. Re-calibrate as the corpus grows.

- [ ] **2. Answers are truncated.**
  `max_tokens=200` (default in `chat_completion`, `app/core/llm_client.py`). Four of the eight test answers used exactly 200 completion tokens and were cut off mid-answer.
  *Fix:* raise to ~800–1000.

- [ ] **3. The system prompt sentences run together.**
  The adjacent string literals in `app/prompts/system_prompts.py` have no spaces or periods between them, so the model receives `…company employeesYou can answer…and moreif the user asked…`. It also has typos ("and internal", "sience", "relevent").
  *Fix:* add separators, fix typos, and tell the model what to do when the context doesn't contain the answer (say so instead of guessing at company policy).

- [ ] **4. Re-running ingestion never updates documents.**
  `app/ingestion/ingest.py` uses `collection.add`, and Chroma silently skips IDs it already has. Edited files keep their old text in the index, and deleted files are never removed.
  *Fix:* use `upsert` and remove chunks whose source file no longer exists, or clear the collection before ingesting.

- [ ] **5. `sources` is not returned to the client.**
  It is computed in `synthesize()` and logged, but `AskResponse` (`app/dto/ask.py`) has no `sources` field, so the frontend can't show citations.
  *Fix:* add `sources: list[str]` to `AskResponse` and pass it through in the route.

### Medium priority

- [ ] **6. Errors from the proxy become plain 500s.**
  A timeout or error from the proxy surfaces as an unhandled 500.
  *Fix:* catch `openai.APIError` / `openai.APITimeoutError` in `/api/ask` and return a clean 502/503 with a user-friendly message.

### Minor

- [ ] **7.** `session_id` is accepted but unused, so there's no conversation memory between questions.
- [ ] **8.** `ROUTER_MAX_TOKENS` and `ROUTER_TEMPERATURE` in `app/config/settings.py` are unused (unfinished router, or dead config).
- [ ] **9.** `GET /` returns 404. Add a simple root route or redirect to `/docs`.
- [ ] **10.** Typos in names: `VectoreStore` / `vectore_store.py`, "Singletone", "lmit", "maybe" (→ "may be") in the truncation note.

### Notes

- If the embedding model is ever changed, delete `data/chroma_db/` and re-run ingestion. Vectors from different models can't be compared.
- `cl100k_base` is an OpenAI tokenizer used as an approximation for chunk sizing. Claude's tokenizer counts slightly differently.
