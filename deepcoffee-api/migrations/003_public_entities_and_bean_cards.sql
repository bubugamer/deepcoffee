-- DeepCoffee public entity library and private bean cards.
-- This migration only adds database structure. It does not change API behavior.

create table if not exists public.public_entities (
    id text primary key,
    entity_type text not null,
    canonical_name text not null,
    normalized_name text not null,
    scope text not null default 'public',
    status text not null default 'active',
    summary text,
    created_from text not null default 'admin',
    created_by text references public.user_profiles(id) on delete set null,
    reviewed_by text references public.user_profiles(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint public_entities_type_name_uq unique (entity_type, normalized_name)
);

create index if not exists public_entities_entity_type_idx
    on public.public_entities(entity_type);
create index if not exists public_entities_normalized_name_idx
    on public.public_entities(normalized_name);
create index if not exists public_entities_status_idx
    on public.public_entities(status);

create table if not exists public.roasters (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    country text,
    region text,
    website_url text,
    social_links jsonb not null default '{}'::jsonb,
    notes text
);

create table if not exists public.coffee_sources (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    source_type text not null,
    country text,
    region text,
    subregion text,
    altitude_m_min integer,
    altitude_m_max integer,
    notes text
);

create index if not exists coffee_sources_source_type_idx
    on public.coffee_sources(source_type);

create table if not exists public.green_bean_merchants (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    country text,
    region text,
    website_url text,
    social_links jsonb not null default '{}'::jsonb,
    notes text
);

create table if not exists public.origins (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    country text,
    region text,
    subregion text,
    altitude_m_min integer,
    altitude_m_max integer,
    notes text
);

create table if not exists public.varietals (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    lineage text,
    species text,
    description text
);

create table if not exists public.process_methods (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    process_group text,
    description text
);

create table if not exists public.green_bean_products (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    merchant_entity_id text references public.public_entities(id) on delete set null,
    coffee_source_entity_id text references public.public_entities(id) on delete set null,
    origin_entity_id text references public.public_entities(id) on delete set null,
    process_entity_id text references public.public_entities(id) on delete set null,
    lot_name text,
    batch_code text,
    crop_year text,
    harvest_season text,
    product_url text,
    cupping_notes jsonb not null default '[]'::jsonb,
    extra_data jsonb not null default '{}'::jsonb
);

create index if not exists green_bean_products_merchant_entity_id_idx
    on public.green_bean_products(merchant_entity_id);
create index if not exists green_bean_products_coffee_source_entity_id_idx
    on public.green_bean_products(coffee_source_entity_id);
create index if not exists green_bean_products_origin_entity_id_idx
    on public.green_bean_products(origin_entity_id);
create index if not exists green_bean_products_process_entity_id_idx
    on public.green_bean_products(process_entity_id);

create table if not exists public.roaster_products (
    entity_id text primary key references public.public_entities(id) on delete cascade,
    roaster_entity_id text references public.public_entities(id) on delete set null,
    origin_entity_id text references public.public_entities(id) on delete set null,
    coffee_source_entity_id text references public.public_entities(id) on delete set null,
    green_bean_merchant_entity_id text references public.public_entities(id) on delete set null,
    green_bean_product_entity_id text references public.public_entities(id) on delete set null,
    process_entity_id text references public.public_entities(id) on delete set null,
    product_name text,
    product_url text,
    official_flavor_notes jsonb not null default '[]'::jsonb,
    flavor_profile jsonb not null default '{}'::jsonb,
    official_brew_params jsonb not null default '{}'::jsonb,
    first_seen_at timestamptz,
    last_seen_at timestamptz,
    extra_data jsonb not null default '{}'::jsonb
);

create index if not exists roaster_products_roaster_entity_id_idx
    on public.roaster_products(roaster_entity_id);
create index if not exists roaster_products_origin_entity_id_idx
    on public.roaster_products(origin_entity_id);
create index if not exists roaster_products_coffee_source_entity_id_idx
    on public.roaster_products(coffee_source_entity_id);
create index if not exists roaster_products_green_bean_merchant_entity_id_idx
    on public.roaster_products(green_bean_merchant_entity_id);
create index if not exists roaster_products_green_bean_product_entity_id_idx
    on public.roaster_products(green_bean_product_entity_id);
create index if not exists roaster_products_process_entity_id_idx
    on public.roaster_products(process_entity_id);

create table if not exists public.green_bean_product_varietals (
    green_bean_product_entity_id text not null references public.public_entities(id) on delete cascade,
    varietal_entity_id text not null references public.public_entities(id) on delete cascade,
    primary key (green_bean_product_entity_id, varietal_entity_id)
);

create table if not exists public.roaster_product_varietals (
    roaster_product_entity_id text not null references public.public_entities(id) on delete cascade,
    varietal_entity_id text not null references public.public_entities(id) on delete cascade,
    primary key (roaster_product_entity_id, varietal_entity_id)
);

create table if not exists public.entity_aliases (
    id serial primary key,
    entity_id text not null references public.public_entities(id) on delete cascade,
    alias text not null,
    normalized_alias text not null,
    locale text,
    source text,
    created_at timestamptz not null default now(),
    constraint entity_aliases_entity_alias_uq unique (entity_id, normalized_alias)
);

create index if not exists entity_aliases_entity_id_idx
    on public.entity_aliases(entity_id);
create index if not exists entity_aliases_normalized_alias_idx
    on public.entity_aliases(normalized_alias);

create table if not exists public.entity_sources (
    id serial primary key,
    entity_id text not null references public.public_entities(id) on delete cascade,
    source_type text not null,
    source_url text,
    source_title text,
    source_text text,
    captured_at timestamptz,
    created_by text references public.user_profiles(id) on delete set null,
    created_at timestamptz not null default now()
);

create index if not exists entity_sources_entity_id_idx
    on public.entity_sources(entity_id);

create table if not exists public.user_bean_cards (
    id text primary key,
    user_id text not null references public.user_profiles(id) on delete cascade,
    scope text not null default 'private',
    status text not null default 'active',
    source_type text not null default 'text',
    raw_input text,
    name text not null,
    roaster_name text,
    roaster_product_name text,
    coffee_source_name text,
    green_bean_merchant_name text,
    green_bean_product_name text,
    origin_name text,
    process_name text,
    varietal_names jsonb not null default '[]'::jsonb,
    roaster_entity_id text references public.public_entities(id) on delete set null,
    roaster_product_entity_id text references public.public_entities(id) on delete set null,
    coffee_source_entity_id text references public.public_entities(id) on delete set null,
    green_bean_merchant_entity_id text references public.public_entities(id) on delete set null,
    green_bean_product_entity_id text references public.public_entities(id) on delete set null,
    origin_entity_id text references public.public_entities(id) on delete set null,
    process_entity_id text references public.public_entities(id) on delete set null,
    flavor jsonb not null default '{}'::jsonb,
    private_notes text,
    recommended_record_id text,
    trace_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists user_bean_cards_user_id_idx
    on public.user_bean_cards(user_id);
create index if not exists user_bean_cards_status_idx
    on public.user_bean_cards(status);
create index if not exists user_bean_cards_roaster_entity_id_idx
    on public.user_bean_cards(roaster_entity_id);
create index if not exists user_bean_cards_roaster_product_entity_id_idx
    on public.user_bean_cards(roaster_product_entity_id);
create index if not exists user_bean_cards_coffee_source_entity_id_idx
    on public.user_bean_cards(coffee_source_entity_id);
create index if not exists user_bean_cards_green_bean_merchant_entity_id_idx
    on public.user_bean_cards(green_bean_merchant_entity_id);
create index if not exists user_bean_cards_green_bean_product_entity_id_idx
    on public.user_bean_cards(green_bean_product_entity_id);
create index if not exists user_bean_cards_origin_entity_id_idx
    on public.user_bean_cards(origin_entity_id);
create index if not exists user_bean_cards_process_entity_id_idx
    on public.user_bean_cards(process_entity_id);

create table if not exists public.user_bean_card_varietals (
    bean_card_id text not null references public.user_bean_cards(id) on delete cascade,
    varietal_entity_id text not null references public.public_entities(id) on delete cascade,
    primary key (bean_card_id, varietal_entity_id)
);

alter table public.brew_records
    add column if not exists bean_card_id text,
    add column if not exists record_type text not null default 'user',
    add column if not exists is_user_visible boolean not null default true;

create index if not exists brew_records_bean_card_id_idx
    on public.brew_records(bean_card_id);
create index if not exists brew_records_record_type_idx
    on public.brew_records(record_type);

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'brew_records_bean_card_id_fkey'
    ) then
        alter table public.brew_records
            add constraint brew_records_bean_card_id_fkey
            foreign key (bean_card_id) references public.user_bean_cards(id) on delete set null;
    end if;
end $$;

alter table public.public_entity_proposals
    add column if not exists applied_entity_id text;

create index if not exists public_entity_proposals_applied_entity_id_idx
    on public.public_entity_proposals(applied_entity_id);

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'public_entity_proposals_applied_entity_id_fkey'
    ) then
        alter table public.public_entity_proposals
            add constraint public_entity_proposals_applied_entity_id_fkey
            foreign key (applied_entity_id) references public.public_entities(id) on delete set null;
    end if;
end $$;

create table if not exists public.candidate_facts (
    id text primary key,
    entity_type text not null,
    fact_type text,
    title text not null,
    payload jsonb not null default '{}'::jsonb,
    source_scope text not null default 'private',
    source_table text,
    source_record_id text,
    source_user_id text references public.user_profiles(id) on delete set null,
    source_input text,
    proposed_entity_id text references public.public_entities(id) on delete set null,
    proposal_id text references public.public_entity_proposals(id) on delete set null,
    status text not null default 'pending_review',
    reviewer_id text references public.user_profiles(id) on delete set null,
    reviewer_note text,
    reviewed_at timestamptz,
    trace_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists candidate_facts_entity_type_idx
    on public.candidate_facts(entity_type);
create index if not exists candidate_facts_status_idx
    on public.candidate_facts(status);
create index if not exists candidate_facts_proposed_entity_id_idx
    on public.candidate_facts(proposed_entity_id);
create index if not exists candidate_facts_proposal_id_idx
    on public.candidate_facts(proposal_id);

create table if not exists public.knowledge_sync_records (
    id serial primary key,
    entity_id text not null references public.public_entities(id) on delete cascade,
    sync_target text not null,
    markdown_path text not null,
    content_hash text,
    status text not null default 'pending',
    last_synced_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists knowledge_sync_records_entity_id_idx
    on public.knowledge_sync_records(entity_id);
create index if not exists knowledge_sync_records_markdown_path_idx
    on public.knowledge_sync_records(markdown_path);
create index if not exists knowledge_sync_records_status_idx
    on public.knowledge_sync_records(status);
