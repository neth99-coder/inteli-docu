# Document Intelligence for Accountants

Stage 1 MVP for uploading long PDFs, extracting text page-by-page, and lazily generating accountant-focused summaries on demand.

## Project structure

```text
.
├── backend
│   ├── app
│   │   ├── config.py
│   │   ├── db.py
│   │   ├── main.py
│   │   ├── schemas.py
│   │   └── services
│   │       ├── gemini.py
│   │       └── pdf.py
│   ├── .env.example
│   └── requirements.txt
├── frontend
│   ├── app
│   │   ├── globals.css
│   │   ├── layout.tsx
│   │   └── page.tsx
│   ├── components
│   │   └── document-intelligence-app.tsx
│   ├── lib
│   │   ├── api.ts
│   │   └── types.ts
│   ├── .env.example
│   ├── eslint.config.mjs
│   ├── next.config.ts
│   ├── package.json
│   └── tsconfig.json
└── supabase
    └── schema.sql
```

## Architecture

- `Next.js` frontend for upload, navigation, and page viewing.
- `FastAPI` backend for PDF parsing, Supabase I/O, and Gemini summarization.
- `Supabase Postgres` for `documents` and `pages`.
- `Supabase Storage` for original PDFs.
- `PyMuPDF` for page extraction.
- `Gemini Flash` for lazy page summaries.

## API surface

- `POST /upload`
- `GET /documents`
- `GET /document/{id}/pages`
- `GET /page/{id}`

`GET /documents` is a small convenience endpoint for the UI. The three endpoints in your MVP spec are implemented exactly as required.

## Supabase setup

1. Create a new Supabase project.
2. In the SQL editor, run [schema.sql](/Users/nethmijayakody/Desktop/N3TH/My Projects/intelligent-base/supabase/schema.sql).
3. In Storage, create a bucket named `documents`.
4. Copy your project URL and service role key from Supabase settings.
5. For an MVP without auth, keep the backend on the service role key and do not expose that key to the frontend.

## Environment variables

### Backend

Create `backend/.env` first:

```bash
cd backend
cp .env.example .env
```

Then fill in:

```bash
FRONTEND_ORIGIN=http://localhost:3000
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_STORAGE_BUCKET=documents
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your-openrouter-api-key
OPENROUTER_MODEL=openrouter/free
OPENROUTER_FALLBACK_MODELS=
OPENROUTER_SITE_URL=http://localhost:3000
OPENROUTER_APP_NAME=Document Intelligence API
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODELS=gemini-2.5-flash-lite,gemini-2.0-flash
```

`LLM_PROVIDER` can be `openrouter` or `gemini`. The example above uses `openrouter`, and `OPENROUTER_MODEL=openrouter/free` uses OpenRouter's current free-model router.

### Frontend

Create `frontend/.env.local`:

```bash
cd frontend
cp .env.example .env.local
```

Then set:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_APP_USERNAME=Shenu@difa
NEXT_PUBLIC_APP_PASSWORD=difa@2026
```

## Run locally

1. Install backend dependencies:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Start the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

3. In a second terminal, install frontend dependencies:

```bash
cd frontend
npm install
```

4. Start the frontend:

```bash
npm run dev
```

5. Open `http://localhost:3000`.

## How the lazy summarization works

1. Upload sends the PDF to `POST /upload`.
2. The backend stores the original PDF in Supabase Storage.
3. The backend extracts text page-by-page with PyMuPDF.
4. Each page is inserted into the `pages` table with `summary = null`.
5. When the UI opens a page, it calls `GET /page/{id}`.
6. If the page already has a summary, the backend returns it immediately.
7. If not, the backend calls Gemini, stores the summary in `pages.summary`, and returns it.

## Notes

- This MVP does not run OCR. Pages with scanned images but no embedded text will return little or no content.
- Large PDFs are handled page-by-page for extraction, but summarization stays strictly on demand.
- The code is intentionally clean and narrow so Stage 2 can add retrieval or OCR without rewriting the flow.
