create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  file_name text not null,
  file_type text not null,
  storage_path text not null,
  status text not null default 'uploaded',
  page_count integer,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.document_processing_jobs (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  user_id uuid not null,
  status text not null default 'queued',
  current_step text,
  progress integer not null default 0,
  total_pages integer not null default 0,
  processed_pages integer not null default 0,
  total_chunks integer not null default 0,
  embedded_chunks integer not null default 0,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  user_id uuid not null,
  chunk_index integer not null,
  content text not null,
  content_tsv tsvector generated always as (to_tsvector('english', content)) stored,
  page_number integer,
  section_title text,
  has_image boolean not null default false,
  has_table boolean not null default false,
  image_summary text,
  table_summary text,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(384),
  created_at timestamptz not null default now()
);

create table if not exists public.chat_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  title text,
  created_at timestamptz not null default now()
);

create table if not exists public.chat_messages (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.chat_sessions(id) on delete cascade,
  user_id uuid not null,
  role text not null,
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists documents_user_id_idx on public.documents (user_id);
create index if not exists jobs_user_id_idx on public.document_processing_jobs (user_id);
create index if not exists jobs_document_id_idx on public.document_processing_jobs (document_id);
create index if not exists chunks_document_user_idx on public.document_chunks (document_id, user_id);
create index if not exists chunks_tsv_idx on public.document_chunks using gin (content_tsv);
create index if not exists chunks_embedding_idx on public.document_chunks using ivfflat (embedding vector_cosine_ops);
create index if not exists chat_sessions_user_id_idx on public.chat_sessions (user_id);
create index if not exists chat_messages_session_id_idx on public.chat_messages (session_id);

create or replace function public.handle_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists documents_handle_updated_at on public.documents;
create trigger documents_handle_updated_at
before update on public.documents
for each row execute procedure public.handle_updated_at();

drop trigger if exists jobs_handle_updated_at on public.document_processing_jobs;
create trigger jobs_handle_updated_at
before update on public.document_processing_jobs
for each row execute procedure public.handle_updated_at();

create or replace function public.match_document_chunks(
  filter_user_id uuid,
  filter_document_ids uuid[],
  query_embedding vector(384),
  match_count integer
)
returns table (
  id uuid,
  document_id uuid,
  user_id uuid,
  content text,
  page_number integer,
  section_title text,
  metadata jsonb,
  score double precision
)
language sql
as $$
  select
    document_chunks.id,
    document_chunks.document_id,
    document_chunks.user_id,
    document_chunks.content,
    document_chunks.page_number,
    document_chunks.section_title,
    document_chunks.metadata,
    1 - (document_chunks.embedding <=> query_embedding) as score
  from public.document_chunks
  where document_chunks.user_id = filter_user_id
    and document_chunks.document_id = any(filter_document_ids)
  order by document_chunks.embedding <=> query_embedding
  limit match_count;
$$;

create or replace function public.keyword_search_document_chunks(
  filter_user_id uuid,
  filter_document_ids uuid[],
  search_query text,
  match_count integer
)
returns table (
  id uuid,
  document_id uuid,
  user_id uuid,
  content text,
  page_number integer,
  section_title text,
  metadata jsonb,
  score double precision
)
language sql
as $$
  select
    document_chunks.id,
    document_chunks.document_id,
    document_chunks.user_id,
    document_chunks.content,
    document_chunks.page_number,
    document_chunks.section_title,
    document_chunks.metadata,
    ts_rank(document_chunks.content_tsv, plainto_tsquery('english', search_query))::double precision as score
  from public.document_chunks
  where document_chunks.user_id = filter_user_id
    and document_chunks.document_id = any(filter_document_ids)
    and document_chunks.content_tsv @@ plainto_tsquery('english', search_query)
  order by score desc
  limit match_count;
$$;

alter table public.documents enable row level security;
alter table public.document_processing_jobs enable row level security;
alter table public.document_chunks enable row level security;
alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

drop policy if exists "Users can access own documents" on public.documents;
create policy "Users can access own documents"
on public.documents
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can access own jobs" on public.document_processing_jobs;
create policy "Users can access own jobs"
on public.document_processing_jobs
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can access own chunks" on public.document_chunks;
create policy "Users can access own chunks"
on public.document_chunks
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can access own sessions" on public.chat_sessions;
create policy "Users can access own sessions"
on public.chat_sessions
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can access own messages" on public.chat_messages;
create policy "Users can access own messages"
on public.chat_messages
for all
using (auth.uid() = user_id)
with check (auth.uid() = user_id);
