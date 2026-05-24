# Legal-AI

A chatbot to help you navigate through the complicated paths of the AI regulations inside EU.

Technically it is a RAG system implementation, using:

- **LLM** — Gemini 2.5 Flash
- **VectorDB** — ChromaDB
- **Embedding functions** — Gemini (`gemini-embedding-001`)
- **Agents** — LangChain (history-aware retriever + conversational session store)

Based on [firica/legalai](https://github.com/firica/legalai), extended with Gemini, architecture-aligned gateway/auth stubs, and an updated conversational architecture diagram.

For the purpose of this demo, the context is **The Artificial Intelligence Act**, document adopted by EU Parliament on 13 March 2024. The system could be easily extended to many other legal papers.

## Installing

```bash
pip install -r requirements.txt
```

Set API keys in `.env`:

- `GEMINI_API_KEY` — Gemini LLM and embeddings (see `config.yaml`)

Get a free API key at [Google AI Studio](https://aistudio.google.com/apikey).

For Chroma Cloud, also set `CHROMA_API_KEY`, `CHROMA_TENANT`, and `CHROMA_DATABASE` in `.env`.

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

See [Legal-AI-Architecture.drawio.xml](Legal-AI-Architecture.drawio.xml) — includes Session store and History-aware retriever on the RAG query path.

| Module | Role |
|--------|------|
| `app.py` | Streamlit client |
| `gateway.py` | API gateway stub (JWT routing in production) |
| `auth.py` | Session identity stub (PostgreSQL in production) |
| `agent.py` | Query orchestrator + conversational RAG |
| `embed.py` | Offline ingestion pipeline |

## Demo

https://huggingface.co/spaces/firica/legalai
