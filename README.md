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
- `FastAPI` backend for PDF parsing, Supabase Postgres I/O, Supabase-authenticated access, S3-backed document storage, and Gemini summarization.
- `Supabase Postgres` for `documents` and `pages`.
- `Supabase Auth` for login and signup.
- `AWS S3` for original PDFs.
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
3. Copy your project URL and service role key from Supabase settings.
4. Create an S3 bucket for PDFs.
5. Copy your Supabase anon key for the frontend auth flow.
6. Keep the backend on the service role key and never expose that key to the frontend.

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
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key-id
AWS_SECRET_ACCESS_KEY=your-secret-access-key
AWS_S3_BUCKET=your-s3-bucket-name
AWS_S3_ENDPOINT_URL=
DEFAULT_USER_ID=Shenu@difa
ALLOW_LEGACY_AUTH_FALLBACK=true
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
NEXT_PUBLIC_SUPABASE_URL=https://your-project-id.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-supabase-anon-key
NEXT_PUBLIC_APP_USERNAME=Shenu@difa
NEXT_PUBLIC_APP_PASSWORD=difa@2026
```

`NEXT_PUBLIC_APP_USERNAME` and `NEXT_PUBLIC_APP_PASSWORD` are only for the temporary legacy fallback. Once Supabase Auth is fully in use, you can remove them and set `ALLOW_LEGACY_AUTH_FALLBACK=false` in the backend.

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

## Existing user bootstrap

Create the existing Supabase auth user, update document ownership, back up the legacy PDFs locally, and upload them into S3:

```bash
cd backend
source .venv/bin/activate
python scripts/bootstrap_existing_user.py \
  --email existing.user@example.com \
  --password 'choose-a-strong-password' \
  --app-user-id Shenu@difa
```

This script is idempotent for the common cases:
- It reuses the auth user if the email already exists.
- It updates `documents.user_id` to the chosen app user id.
- It skips files already present in S3.
- It writes a local backup under `backend/backups/existing-user/` before uploading legacy Supabase files to S3.

## How the lazy summarization works

1. Upload sends the PDF to `POST /upload`.
2. The backend stores the original PDF in S3 under `{user_id}/files/{document_id}/original.pdf`.
3. The backend extracts text page-by-page with PyMuPDF.
4. Each page is inserted into the `pages` table with `summary = null`.
5. When the UI opens a page, it calls `GET /page/{id}`.
6. If the page already has a summary, the backend returns it immediately.
7. If not, the backend calls Gemini, stores the summary in `pages.summary`, and returns it.

## Notes

- This MVP does not run OCR. Pages with scanned images but no embedded text will return little or no content.
- Large PDFs are handled page-by-page for extraction, but summarization stays strictly on demand.
- The code is intentionally clean and narrow so Stage 2 can add retrieval or OCR without rewriting the flow.
- Legacy PDFs already in Supabase Storage still resolve through a fallback path, so the existing system keeps working while you migrate.
