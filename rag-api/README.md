# rag-api

Standalone FastAPI backend scaffold for the RAG service. This is designed to live beside the existing MVP backend without breaking it.

## Included

- Supabase-authenticated FastAPI API
- Supabase Storage upload orchestration
- Redis-backed document processing queue
- Worker pipeline for Unstructured PDF extraction, LlamaParse Office parsing, embeddings, and chunk storage
- Query endpoint with flags for multi-query, hybrid retrieval, reranking, and source citations
- Supabase schema with pgvector, RLS, and retrieval SQL functions
- Local development setup via Docker Compose

## Structure

```text
rag-api/
  app/
    api/
    core/
    db/
    schemas/
    services/
    workers/
  supabase/
    schema.sql
  Dockerfile
  docker-compose.yml
  requirements.txt
```

## Local development

1. Copy the env file:

```bash
cd rag-api
cp .env.example .env
```

2. Fill in your Supabase, Redis, and model provider values.
3. Add `UNSTRUCTURED_API_KEY` if you want to use Unstructured Cloud for PDFs. If you leave it blank, the worker falls back to local `unstructured[pdf]` parsing.
4. Add `LLAMA_PARSE_API_KEY` for `.xlsx` and `.pptx` ingestion.

5. Run the service stack:

```bash
docker compose up --build
```

6. Apply [supabase/schema.sql](/Users/nethmijayakody/Desktop/N3TH/My Projects/intelligent-base/rag-api/supabase/schema.sql) in your Supabase project.

## Notes

- PDF extraction uses Unstructured with `by_title` chunking semantics, and Office parsing uses LlamaParse markdown output normalized into internal chunks.
- Embeddings use `sentence-transformers` with the configured HuggingFace model, and reranking uses a CrossEncoder model.
- Hybrid retrieval merging uses reciprocal rank fusion, which matches your request for `rrfs` merging.
- The query endpoint saves chat history when a `session_id` is supplied.
