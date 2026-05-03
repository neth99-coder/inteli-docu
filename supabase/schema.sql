create extension if not exists pgcrypto;

create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  user_id text not null default 'default',
  created_at timestamptz not null default now()
);

alter table public.documents
  add column if not exists user_id text not null default 'default';

create table if not exists public.pages (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  page_number integer not null,
  content text not null,
  summary text,
  annotations jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (document_id, page_number)
);

alter table public.pages
  add column if not exists annotations jsonb not null default '[]'::jsonb;

create index if not exists pages_document_id_idx on public.pages (document_id);
create index if not exists pages_document_id_page_number_idx on public.pages (document_id, page_number);
