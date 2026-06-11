-- DeepCoffee initial PostgreSQL schema.
-- Markdown files remain the source of truth for public knowledge content.

create extension if not exists pgcrypto;

create table if not exists public.user_profiles (
    id uuid primary key,
    email text unique,
    display_name text,
    plan text not null default 'basic',
    timezone text not null default 'Asia/Shanghai',
    unit_system text not null default 'metric',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.invite_codes (
    id uuid primary key default gen_random_uuid(),
    code text not null unique,
    status text not null default 'active',
    expires_at timestamptz,
    note text,
    used_by uuid references public.user_profiles(id),
    used_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.newapi_billing_links (
    user_id uuid primary key references public.user_profiles(id) on delete cascade,
    newapi_user_id text not null,
    internal_token_ciphertext text not null,
    plan text not null default 'basic',
    last_synced_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.brew_records (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.user_profiles(id) on delete cascade,
    source_type text not null default 'text',
    raw_input text,
    draft jsonb not null default '{}'::jsonb,
    confirmed_data jsonb not null default '{}'::jsonb,
    recap text,
    suggestions jsonb not null default '[]'::jsonb,
    trace_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists brew_records_user_created_idx
    on public.brew_records(user_id, created_at desc);

create table if not exists public.knowledge_articles (
    slug text primary key,
    title text not null,
    category_key text not null,
    category_label text not null,
    summary text not null default '',
    markdown_path text not null unique,
    markdown text not null,
    toc jsonb not null default '[]'::jsonb,
    sections jsonb not null default '[]'::jsonb,
    related jsonb not null default '[]'::jsonb,
    content_hash text not null,
    updated_at timestamptz not null,
    synced_at timestamptz not null default now()
);

create index if not exists knowledge_articles_category_idx
    on public.knowledge_articles(category_key);

create table if not exists public.public_entity_proposals (
    id uuid primary key default gen_random_uuid(),
    entity_type text not null,
    title text not null,
    payload jsonb not null,
    source_input text,
    trace_id text,
    proposer_id uuid references public.user_profiles(id),
    status text not null default 'pending',
    reviewer_note text,
    applied_markdown_path text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists public_entity_proposals_status_idx
    on public.public_entity_proposals(status, entity_type);

create table if not exists public.proposal_audit_events (
    id uuid primary key default gen_random_uuid(),
    proposal_id uuid not null references public.public_entity_proposals(id) on delete cascade,
    actor_id uuid references public.user_profiles(id),
    action text not null,
    note text,
    created_at timestamptz not null default now()
);

create table if not exists public.ai_audit_events (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references public.user_profiles(id),
    action_type text not null,
    raw_input text,
    model_output jsonb,
    trace_id text,
    result jsonb,
    created_at timestamptz not null default now()
);
