# Legal-AI

A conversational AI chatbot to help navigate the EU Artificial Intelligence Act and other legal frameworks. Built as a production-ready RAG (Retrieval-Augmented Generation) system with session management, authentication, and comprehensive tracing.

## Technology Stack

Technically it is a RAG system implementation, using:

- **LLM** — Gemini 2.5 Flash (with streaming support)
- **Vector Database** — ChromaDB (with Cloud support)
- **Embeddings** — HuggingFace (all-mpnet-base-v2) & Gemini
- **Orchestration** — LangChain with history-aware retriever
- **Frontend** — Streamlit with session persistence
- **Authentication** — JWT-based with PostgreSQL session store
- **Database** — PostgreSQL with SQLAlchemy ORM
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
- `DATABASE_URL` — PostgreSQL connection string (e.g., `postgresql://user:password@localhost/legal_ai`)

**Optional (for cloud deployment):**
- `CHROMA_API_KEY` — Chroma Cloud API key
- `CHROMA_TENANT` — Chroma Cloud tenant name
- `CHROMA_DATABASE` — Chroma Cloud database name
- `JWT_SECRET` — Secret key for JWT token signing
- `SENDGRID_API_KEY` — SendGrid API key for email authentication
- `EMAIL_FROM` — Sender email address
- `LANGFUSE_PUBLIC_KEY` — Langfuse public key for tracing
- `LANGFUSE_SECRET_KEY` — Langfuse secret key

**Example `.env`:**
```bash
GEMINI_API_KEY=your_api_key_here
DATABASE_URL=postgresql://localhost/legal_ai
JWT_SECRET=your_secret_key
SENDGRID_API_KEY=your_sendgrid_key
EMAIL_FROM=noreply@legal-ai.app
LANGFUSE_PUBLIC_KEY=your_public_key
LANGFUSE_SECRET_KEY=your_secret_key
```

### Database Setup

For local development with PostgreSQL:

```bash
# Create database
createdb legal_ai

# The application will create tables automatically on first run
```

### Ingest the EU AI Act (required before first chat)

Download the PDF and embed it into Chroma **offline** (not at app startup):

```bash
python embed.py
```

This caches the PDF at `data/eu_ai_act.pdf` (gitignored) and writes embeddings to local `chroma_storage/` or Chroma Cloud, depending on your `.env`. Expect several minutes on first run.

To re-ingest after changing the embedding model:

```bash
python embed.py --force
```

For local-only setups, you can also delete `chroma_storage/` and re-run `python embed.py`.

### Run the app

```bash
streamlit run app.py
```

## Architecture

![Legal AI Architecture Diagram](Legal-AI-Architecture.drawio.png)

The system implements a comprehensive RAG pipeline with the following components:

| Module | Role |
|--------|------|
| `app.py` | Streamlit client with chat UI and session management |
| `gateway.py` | API gateway with JWT validation and request routing |
| `auth.py` | Session identity management (PostgreSQL in production) |
| `agent.py` | Query orchestrator + conversational RAG with history awareness |
| `embed.py` | Offline document ingestion and embedding pipeline |
| `db.py` | Database abstraction for session and message storage |
| `utils.py` | Configuration loading and utility functions |

**Key Features:**
- History-aware retriever for context-aware responses
- Session store for persistent conversation management
- JWT-based authentication for production deployments
- Support for multiple document ingestion sources
- Integration with Langfuse for tracing and monitoring

## Deployment

The application is deployed and accessible at:
🚀 **[https://legal-ai-anjhwkwci9gqrofvqkueks.streamlit.app/](https://legal-ai-anjhwkwci9gqrofvqkueks.streamlit.app/)**

Deployed on Streamlit Cloud for easy access and scalability.

## Demo

Original base project: https://huggingface.co/spaces/firica/legalai
