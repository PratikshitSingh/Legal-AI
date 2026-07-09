# Legal-AI

A conversational AI chatbot to help navigate the EU Artificial Intelligence Act and other legal frameworks. Built as a production-ready RAG (Retrieval-Augmented Generation) system with session management, authentication, and comprehensive tracing.

## Technology Stack

Technically it is a RAG system implementation, using:

- **LLM** — Gemini 2.5 Flash (with streaming support)
- **Vector Database** — ChromaDB (with Cloud support)
- **Embeddings** — HuggingFace sentence-transformers (all-mpnet-base-v2)
- **Orchestration** — LangChain with history-aware retriever
- **Frontend** — Streamlit with session persistence
- **Authentication** — Magic links + JWT with PostgreSQL session store
- **Database** — PostgreSQL (Neon) via SQLAlchemy Core
- **Monitoring** — Langfuse for tracing and observability
- **Email** — SendGrid for magic link authentication

Based on [firica/legalai](https://github.com/firica/legalai), extended with production-grade authentication, session management, architecture-aligned gateway, and an updated conversational architecture.

For the purpose of this demo, the context is **The Artificial Intelligence Act**, document adopted by EU Parliament on 13 March 2024. The system can be easily extended to many other legal documents and use cases.

## Installing

```bash
pip install -r requirements.txt
```

### Environment Configuration

Create a `.env` file in the project root with the following variables:

**Required:**
- `GEMINI_API_KEY` — Google Gemini API key (get free key at [Google AI Studio](https://aistudio.google.com/apikey))
- `NEON_DB_DATABASE_URL` — PostgreSQL connection string (e.g., `postgresql://user:password@host/legal_ai`)
- `JWT_SECRET` — Secret key for JWT token signing

**Optional (for cloud deployment):**
- `CHROMA_API_KEY` — Chroma Cloud API key
- `CHROMA_TENANT` — Chroma Cloud tenant name
- `CHROMA_DATABASE` — Chroma Cloud database name
- `SENDGRID_API_KEY` — SendGrid API key for email authentication (or set `EMAIL_PROVIDER=local` to print magic links to the console)
- `EMAIL_FROM` — Sender email address
- `APP_BASE_URL` — Overrides the magic-link base URL from `config.yaml`
- `LANGFUSE_PUBLIC_KEY` — Langfuse public key for tracing
- `LANGFUSE_SECRET_KEY` — Langfuse secret key
- `LOG_LEVEL` — Application log level (default `INFO`)

**Example `.env`:**
```bash
GEMINI_API_KEY=your_api_key_here
NEON_DB_DATABASE_URL=postgresql://user:password@host/legal_ai
JWT_SECRET=your_secret_key
SENDGRID_API_KEY=your_sendgrid_key
EMAIL_FROM=noreply@legal-ai.app
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
```

### Database Setup

Two mechanisms create the schema, and **both are required**:

1. Auth/session tables (`users`, `magic_links`, `refresh_tokens`, `sessions`, `audit_log`, roles) are created lazily by the app on first use (`db.init_db()`).
2. Document/jurisdiction tables come from the SQL migrations:

```bash
python scripts/run_migrations.py
python -m legal_ai.scripts.seed_jurisdictions   # loads the jurisdiction hierarchy
```

There is no migration version tracking yet — every migration is idempotent and safe to re-run.

### Ingest the EU AI Act (required before first chat)

Download the PDF and embed it into Chroma **offline** (not at app startup):

```bash
python scripts/ingest.py            # or: python -m legal_ai.services.embed
```

This caches the PDF at `data/eu_ai_act.pdf` (gitignored) and writes embeddings to local `chroma_storage/` or Chroma Cloud, depending on your `.env`. Expect several minutes on first run.

To re-ingest after changing the embedding model:

```bash
python scripts/ingest.py --force
```

For local-only setups, you can also delete `chroma_storage/` and re-run the ingest.

### Run the app

```bash
streamlit run app.py
```

## Architecture

![Legal AI Architecture Diagram](Legal-AI-Architecture.drawio.png)

The system is a layered RAG pipeline — UI → services → auth/db → core:

| Module | Role |
|--------|------|
| `app.py`, `pages/` | Streamlit UI: chat, profile, admin, jurisdiction comparison |
| `legal_ai/services/chat_service.py` | Query routing: JWT validation, session ownership, agent cache, message persistence |
| `legal_ai/services/document_service.py` | Admin upload orchestration: preflight, ingestion, CSV bulk import |
| `legal_ai/services/embed.py` | Offline document ingestion and embedding pipeline (CLI: `python -m legal_ai.services.embed`) |
| `legal_ai/services/vector_store.py` | Single home for the Chroma client, collection, and embedding function |
| `legal_ai/agent/agent.py` | Conversational RAG agent (history-aware retriever, Gemini) |
| `legal_ai/auth/` | Magic-link auth, JWT/session state, browser-cookie persistence, RBAC |
| `legal_ai/db/` | Postgres access split by domain (users, tokens, sessions, documents, jurisdictions) behind one facade |
| `legal_ai/core/` | Settings (single dotenv entry), logging, constants, Langfuse tracing |
| `scripts/` | Operational entry points: `ingest.py`, `run_migrations.py` |

**Key Features:**
- History-aware retriever for context-aware responses
- Session store for persistent conversation management
- JWT-based authentication for production deployments
- Support for multiple document ingestion sources
- Integration with Langfuse for tracing and monitoring

### Development

```bash
pip install ruff pytest
ruff check .                          # lint (CI-gated)
pytest tests/ -m "not integration"    # unit suite (CI-gated); integration tests need live services
```

## Deployment

The application is deployed and accessible at:
🚀 **[https://legal-ai-anjhwkwci9gqrofvqkueks.streamlit.app/](https://legal-ai-anjhwkwci9gqrofvqkueks.streamlit.app/)**

Deployed on Streamlit Cloud for easy access and scalability.

## Demo

Original base project: https://huggingface.co/spaces/firica/legalai
