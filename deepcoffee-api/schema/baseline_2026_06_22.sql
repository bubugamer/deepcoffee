-- DeepCoffee production schema baseline.
-- Generated from the production public schema on 2026-06-22.
-- Use this for fresh database initialization only.
-- Do not run this against an existing production database as a migration.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

SET search_path = public, pg_catalog;

-- Sequences
CREATE SEQUENCE IF NOT EXISTS "public"."admin_audit_events_id_seq" AS integer START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS "public"."ai_usage_adjustments_id_seq" AS integer START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS "public"."ai_usage_events_id_seq" AS integer START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS "public"."entity_aliases_id_seq" AS integer START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS "public"."entity_sources_id_seq" AS integer START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS "public"."knowledge_sync_records_id_seq" AS integer START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1 NO CYCLE;
CREATE SEQUENCE IF NOT EXISTS "public"."proposal_audit_events_id_seq" AS integer START WITH 1 INCREMENT BY 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1 NO CYCLE;

-- Tables
CREATE TABLE IF NOT EXISTS "public"."ai_usage_events" (
    "id" integer DEFAULT nextval('ai_usage_events_id_seq'::regclass) NOT NULL,
    "user_id" character varying NOT NULL,
    "action" character varying NOT NULL,
    "trace_id" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."user_profiles" (
    "id" character varying NOT NULL,
    "email" character varying,
    "display_name" character varying,
    "plan" character varying DEFAULT 'basic'::character varying NOT NULL,
    "timezone" character varying DEFAULT 'Asia/Shanghai'::character varying NOT NULL,
    "unit_system" character varying DEFAULT 'metric'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    "role" text DEFAULT 'user'::text NOT NULL,
    "status" text DEFAULT 'active'::text NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."admin_audit_events" (
    "id" integer DEFAULT nextval('admin_audit_events_id_seq'::regclass) NOT NULL,
    "user_id" character varying NOT NULL,
    "actor_id" character varying,
    "action" character varying NOT NULL,
    "before_value" character varying,
    "after_value" character varying,
    "reason" text,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."ai_usage_adjustments" (
    "id" integer DEFAULT nextval('ai_usage_adjustments_id_seq'::regclass) NOT NULL,
    "user_id" character varying NOT NULL,
    "period_start" timestamp with time zone NOT NULL,
    "period_end" timestamp with time zone NOT NULL,
    "delta" integer NOT NULL,
    "reason" text,
    "actor_id" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."coffea_sessions" (
    "session_id" character varying NOT NULL,
    "user_id" character varying NOT NULL,
    "state" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "recent_messages" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    "summary" jsonb DEFAULT '[]'::jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."invite_codes" (
    "code" character varying NOT NULL,
    "status" character varying DEFAULT 'active'::character varying NOT NULL,
    "expires_at" timestamp with time zone,
    "note" text,
    "used_by" character varying,
    "used_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."public_entities" (
    "id" character varying NOT NULL,
    "entity_type" character varying NOT NULL,
    "canonical_name" character varying NOT NULL,
    "normalized_name" character varying NOT NULL,
    "scope" character varying DEFAULT 'public'::character varying NOT NULL,
    "status" character varying DEFAULT 'active'::character varying NOT NULL,
    "summary" text,
    "created_from" character varying DEFAULT 'admin'::character varying NOT NULL,
    "created_by" character varying,
    "reviewed_by" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."user_ai_quota_settings" (
    "user_id" character varying NOT NULL,
    "monthly_limit" integer,
    "updated_by" character varying,
    "reason" text,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."user_equipment_items" (
    "id" text NOT NULL,
    "user_id" text NOT NULL,
    "category" text NOT NULL,
    "name" text NOT NULL,
    "normalized_name" text NOT NULL,
    "notes" text,
    "is_default" boolean DEFAULT false NOT NULL,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."user_equipment_profiles" (
    "id" character varying NOT NULL,
    "user_id" character varying NOT NULL,
    "brew_method" character varying,
    "grinder" character varying,
    "filter_media" character varying,
    "water" character varying,
    "label" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    "is_default" boolean DEFAULT false NOT NULL,
    "dripper" text
);

CREATE TABLE IF NOT EXISTS "public"."user_memories" (
    "id" character varying NOT NULL,
    "user_id" character varying NOT NULL,
    "kind" character varying NOT NULL,
    "content" text NOT NULL,
    "confidence" double precision DEFAULT 0.6 NOT NULL,
    "source" character varying,
    "source_ref" character varying,
    "status" character varying DEFAULT 'active'::character varying NOT NULL,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."coffee_sources" (
    "entity_id" character varying NOT NULL,
    "source_type" character varying NOT NULL,
    "country" character varying,
    "region" character varying,
    "subregion" character varying,
    "altitude_m_min" integer,
    "altitude_m_max" integer,
    "notes" text
);

CREATE TABLE IF NOT EXISTS "public"."entity_aliases" (
    "id" integer DEFAULT nextval('entity_aliases_id_seq'::regclass) NOT NULL,
    "entity_id" character varying NOT NULL,
    "alias" character varying NOT NULL,
    "normalized_alias" character varying NOT NULL,
    "locale" character varying,
    "source" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."entity_sources" (
    "id" integer DEFAULT nextval('entity_sources_id_seq'::regclass) NOT NULL,
    "entity_id" character varying NOT NULL,
    "source_type" character varying NOT NULL,
    "source_url" character varying,
    "source_title" character varying,
    "source_text" text,
    "captured_at" timestamp with time zone,
    "created_by" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."green_bean_merchants" (
    "entity_id" character varying NOT NULL,
    "country" character varying,
    "region" character varying,
    "website_url" character varying,
    "social_links" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "notes" text,
    "merchant_type" text
);

CREATE TABLE IF NOT EXISTS "public"."green_bean_product_varietals" (
    "green_bean_product_entity_id" character varying NOT NULL,
    "varietal_entity_id" character varying NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."green_bean_products" (
    "entity_id" character varying NOT NULL,
    "merchant_entity_id" character varying,
    "coffee_source_entity_id" character varying,
    "origin_entity_id" character varying,
    "process_entity_id" character varying,
    "lot_name" character varying,
    "batch_code" character varying,
    "crop_year" character varying,
    "harvest_season" character varying,
    "product_url" character varying,
    "cupping_notes" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "extra_data" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "merchant_name" text,
    "product_type" text
);

CREATE TABLE IF NOT EXISTS "public"."knowledge_sync_records" (
    "id" integer DEFAULT nextval('knowledge_sync_records_id_seq'::regclass) NOT NULL,
    "entity_id" character varying NOT NULL,
    "sync_target" character varying NOT NULL,
    "markdown_path" character varying NOT NULL,
    "content_hash" character varying,
    "status" character varying DEFAULT 'pending'::character varying NOT NULL,
    "last_synced_at" timestamp with time zone,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."origins" (
    "entity_id" character varying NOT NULL,
    "country" character varying,
    "region" character varying,
    "subregion" character varying,
    "altitude_m_min" integer,
    "altitude_m_max" integer,
    "notes" text
);

CREATE TABLE IF NOT EXISTS "public"."process_methods" (
    "entity_id" character varying NOT NULL,
    "process_group" character varying,
    "description" text
);

CREATE TABLE IF NOT EXISTS "public"."public_entity_proposals" (
    "id" character varying NOT NULL,
    "entity_type" character varying NOT NULL,
    "title" character varying NOT NULL,
    "payload" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "source_input" text,
    "trace_id" character varying,
    "proposer_id" character varying NOT NULL,
    "status" character varying DEFAULT 'pending'::character varying NOT NULL,
    "reviewer_note" text,
    "applied_markdown_path" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    "applied_entity_id" text
);

CREATE TABLE IF NOT EXISTS "public"."roaster_product_varietals" (
    "roaster_product_entity_id" character varying NOT NULL,
    "varietal_entity_id" character varying NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."roaster_products" (
    "entity_id" character varying NOT NULL,
    "roaster_entity_id" character varying,
    "origin_entity_id" character varying,
    "coffee_source_entity_id" character varying,
    "green_bean_merchant_entity_id" character varying,
    "green_bean_product_entity_id" character varying,
    "process_entity_id" character varying,
    "product_name" character varying,
    "product_url" character varying,
    "official_flavor_notes" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "flavor_profile" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "official_brew_params" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "first_seen_at" timestamp with time zone,
    "last_seen_at" timestamp with time zone,
    "extra_data" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "roaster_name" text,
    "product_type" text
);

CREATE TABLE IF NOT EXISTS "public"."roasters" (
    "entity_id" character varying NOT NULL,
    "country" character varying,
    "region" character varying,
    "website_url" character varying,
    "social_links" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "notes" text,
    "roaster_subtype" text,
    "market" text
);

CREATE TABLE IF NOT EXISTS "public"."user_bean_cards" (
    "id" character varying NOT NULL,
    "user_id" character varying NOT NULL,
    "scope" character varying DEFAULT 'private'::character varying NOT NULL,
    "status" character varying DEFAULT 'active'::character varying NOT NULL,
    "source_type" character varying DEFAULT 'text'::character varying NOT NULL,
    "raw_input" text,
    "name" character varying NOT NULL,
    "roaster_name" character varying,
    "roaster_product_name" character varying,
    "coffee_source_name" character varying,
    "green_bean_merchant_name" character varying,
    "green_bean_product_name" character varying,
    "origin_name" character varying,
    "process_name" character varying,
    "varietal_names" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "roaster_entity_id" character varying,
    "roaster_product_entity_id" character varying,
    "coffee_source_entity_id" character varying,
    "green_bean_merchant_entity_id" character varying,
    "green_bean_product_entity_id" character varying,
    "origin_entity_id" character varying,
    "process_entity_id" character varying,
    "flavor" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "private_notes" text,
    "recommended_record_id" character varying,
    "trace_id" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    "rating" jsonb,
    "altitude_text" text,
    "harvest_date_text" text,
    "roast_date_text" text,
    "net_weight_text" text,
    "bean_components" jsonb DEFAULT '[]'::jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."varietals" (
    "entity_id" character varying NOT NULL,
    "lineage" character varying,
    "species" character varying,
    "description" text
);

CREATE TABLE IF NOT EXISTS "public"."candidate_facts" (
    "id" character varying NOT NULL,
    "entity_type" character varying NOT NULL,
    "fact_type" character varying,
    "title" character varying NOT NULL,
    "payload" jsonb DEFAULT '{}'::jsonb NOT NULL,
    "source_scope" character varying DEFAULT 'private'::character varying NOT NULL,
    "source_table" character varying,
    "source_record_id" character varying,
    "source_user_id" character varying,
    "source_input" text,
    "proposed_entity_id" character varying,
    "proposal_id" character varying,
    "status" character varying DEFAULT 'pending_review'::character varying NOT NULL,
    "reviewer_id" character varying,
    "reviewer_note" text,
    "reviewed_at" timestamp with time zone,
    "trace_id" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."proposal_audit_events" (
    "id" integer DEFAULT nextval('proposal_audit_events_id_seq'::regclass) NOT NULL,
    "proposal_id" character varying NOT NULL,
    "actor_id" character varying,
    "action" character varying NOT NULL,
    "note" text,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL
);

CREATE TABLE IF NOT EXISTS "public"."brew_records" (
    "id" character varying NOT NULL,
    "user_id" character varying NOT NULL,
    "source_type" character varying DEFAULT 'text'::character varying NOT NULL,
    "raw_input" text,
    "bean_name" character varying,
    "origin" character varying,
    "roaster" character varying,
    "process" character varying,
    "varietal" character varying,
    "device" character varying,
    "grinder" character varying,
    "grind_setting" character varying,
    "dose_g" double precision,
    "water_ml" double precision,
    "water_temp_c" double precision,
    "ratio" character varying,
    "ratio_value" double precision,
    "brew_time" character varying,
    "brew_time_seconds" integer,
    "brew_steps" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "evaluation" jsonb,
    "notes" text,
    "recap" text,
    "suggestions" jsonb DEFAULT '[]'::jsonb NOT NULL,
    "trace_id" character varying,
    "created_at" timestamp with time zone DEFAULT now() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT now() NOT NULL,
    "bean_card_id" text,
    "record_type" text DEFAULT 'user'::text NOT NULL,
    "is_user_visible" boolean DEFAULT true NOT NULL,
    "brew_method" text,
    "filter_media" text,
    "water" text,
    "brew_score" integer
);

CREATE TABLE IF NOT EXISTS "public"."user_bean_card_varietals" (
    "bean_card_id" character varying NOT NULL,
    "varietal_entity_id" character varying NOT NULL
);

-- Constraints
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'admin_audit_events_pkey' AND conrelid = 'public.admin_audit_events'::regclass) THEN
        ALTER TABLE "public"."admin_audit_events" ADD CONSTRAINT "admin_audit_events_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ai_usage_adjustments_pkey' AND conrelid = 'public.ai_usage_adjustments'::regclass) THEN
        ALTER TABLE "public"."ai_usage_adjustments" ADD CONSTRAINT "ai_usage_adjustments_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ai_usage_events_pkey' AND conrelid = 'public.ai_usage_events'::regclass) THEN
        ALTER TABLE "public"."ai_usage_events" ADD CONSTRAINT "ai_usage_events_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'brew_records_pkey' AND conrelid = 'public.brew_records'::regclass) THEN
        ALTER TABLE "public"."brew_records" ADD CONSTRAINT "brew_records_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'candidate_facts_pkey' AND conrelid = 'public.candidate_facts'::regclass) THEN
        ALTER TABLE "public"."candidate_facts" ADD CONSTRAINT "candidate_facts_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'coffea_sessions_pkey' AND conrelid = 'public.coffea_sessions'::regclass) THEN
        ALTER TABLE "public"."coffea_sessions" ADD CONSTRAINT "coffea_sessions_pkey" PRIMARY KEY (session_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'coffee_sources_pkey' AND conrelid = 'public.coffee_sources'::regclass) THEN
        ALTER TABLE "public"."coffee_sources" ADD CONSTRAINT "coffee_sources_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_aliases_pkey' AND conrelid = 'public.entity_aliases'::regclass) THEN
        ALTER TABLE "public"."entity_aliases" ADD CONSTRAINT "entity_aliases_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_sources_pkey' AND conrelid = 'public.entity_sources'::regclass) THEN
        ALTER TABLE "public"."entity_sources" ADD CONSTRAINT "entity_sources_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_merchants_pkey' AND conrelid = 'public.green_bean_merchants'::regclass) THEN
        ALTER TABLE "public"."green_bean_merchants" ADD CONSTRAINT "green_bean_merchants_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_product_varietals_pkey' AND conrelid = 'public.green_bean_product_varietals'::regclass) THEN
        ALTER TABLE "public"."green_bean_product_varietals" ADD CONSTRAINT "green_bean_product_varietals_pkey" PRIMARY KEY (green_bean_product_entity_id, varietal_entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_products_pkey' AND conrelid = 'public.green_bean_products'::regclass) THEN
        ALTER TABLE "public"."green_bean_products" ADD CONSTRAINT "green_bean_products_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'invite_codes_pkey' AND conrelid = 'public.invite_codes'::regclass) THEN
        ALTER TABLE "public"."invite_codes" ADD CONSTRAINT "invite_codes_pkey" PRIMARY KEY (code);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_sync_records_pkey' AND conrelid = 'public.knowledge_sync_records'::regclass) THEN
        ALTER TABLE "public"."knowledge_sync_records" ADD CONSTRAINT "knowledge_sync_records_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'origins_pkey' AND conrelid = 'public.origins'::regclass) THEN
        ALTER TABLE "public"."origins" ADD CONSTRAINT "origins_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'process_methods_pkey' AND conrelid = 'public.process_methods'::regclass) THEN
        ALTER TABLE "public"."process_methods" ADD CONSTRAINT "process_methods_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'proposal_audit_events_pkey' AND conrelid = 'public.proposal_audit_events'::regclass) THEN
        ALTER TABLE "public"."proposal_audit_events" ADD CONSTRAINT "proposal_audit_events_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'public_entities_pkey' AND conrelid = 'public.public_entities'::regclass) THEN
        ALTER TABLE "public"."public_entities" ADD CONSTRAINT "public_entities_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'public_entity_proposals_pkey' AND conrelid = 'public.public_entity_proposals'::regclass) THEN
        ALTER TABLE "public"."public_entity_proposals" ADD CONSTRAINT "public_entity_proposals_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_product_varietals_pkey' AND conrelid = 'public.roaster_product_varietals'::regclass) THEN
        ALTER TABLE "public"."roaster_product_varietals" ADD CONSTRAINT "roaster_product_varietals_pkey" PRIMARY KEY (roaster_product_entity_id, varietal_entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_pkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roasters_pkey' AND conrelid = 'public.roasters'::regclass) THEN
        ALTER TABLE "public"."roasters" ADD CONSTRAINT "roasters_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_ai_quota_settings_pkey' AND conrelid = 'public.user_ai_quota_settings'::regclass) THEN
        ALTER TABLE "public"."user_ai_quota_settings" ADD CONSTRAINT "user_ai_quota_settings_pkey" PRIMARY KEY (user_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_card_varietals_pkey' AND conrelid = 'public.user_bean_card_varietals'::regclass) THEN
        ALTER TABLE "public"."user_bean_card_varietals" ADD CONSTRAINT "user_bean_card_varietals_pkey" PRIMARY KEY (bean_card_id, varietal_entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_pkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_equipment_items_pkey' AND conrelid = 'public.user_equipment_items'::regclass) THEN
        ALTER TABLE "public"."user_equipment_items" ADD CONSTRAINT "user_equipment_items_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_equipment_profiles_pkey' AND conrelid = 'public.user_equipment_profiles'::regclass) THEN
        ALTER TABLE "public"."user_equipment_profiles" ADD CONSTRAINT "user_equipment_profiles_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_memories_pkey' AND conrelid = 'public.user_memories'::regclass) THEN
        ALTER TABLE "public"."user_memories" ADD CONSTRAINT "user_memories_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_profiles_pkey' AND conrelid = 'public.user_profiles'::regclass) THEN
        ALTER TABLE "public"."user_profiles" ADD CONSTRAINT "user_profiles_pkey" PRIMARY KEY (id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'varietals_pkey' AND conrelid = 'public.varietals'::regclass) THEN
        ALTER TABLE "public"."varietals" ADD CONSTRAINT "varietals_pkey" PRIMARY KEY (entity_id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_aliases_entity_alias_uq' AND conrelid = 'public.entity_aliases'::regclass) THEN
        ALTER TABLE "public"."entity_aliases" ADD CONSTRAINT "entity_aliases_entity_alias_uq" UNIQUE (entity_id, normalized_alias);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'public_entities_type_name_uq' AND conrelid = 'public.public_entities'::regclass) THEN
        ALTER TABLE "public"."public_entities" ADD CONSTRAINT "public_entities_type_name_uq" UNIQUE (entity_type, normalized_name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_equipment_items_user_category_name_uq' AND conrelid = 'public.user_equipment_items'::regclass) THEN
        ALTER TABLE "public"."user_equipment_items" ADD CONSTRAINT "user_equipment_items_user_category_name_uq" UNIQUE (user_id, category, normalized_name);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_profiles_email_key' AND conrelid = 'public.user_profiles'::regclass) THEN
        ALTER TABLE "public"."user_profiles" ADD CONSTRAINT "user_profiles_email_key" UNIQUE (email);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'brew_records_brew_score_ck' AND conrelid = 'public.brew_records'::regclass) THEN
        ALTER TABLE "public"."brew_records" ADD CONSTRAINT "brew_records_brew_score_ck" CHECK (brew_score IS NULL OR brew_score >= 1 AND brew_score <= 5);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_equipment_items_category_ck' AND conrelid = 'public.user_equipment_items'::regclass) THEN
        ALTER TABLE "public"."user_equipment_items" ADD CONSTRAINT "user_equipment_items_category_ck" CHECK (category = ANY (ARRAY['brewer'::text, 'grinder'::text, 'filter_media'::text, 'water'::text]));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'admin_audit_events_actor_id_fkey' AND conrelid = 'public.admin_audit_events'::regclass) THEN
        ALTER TABLE "public"."admin_audit_events" ADD CONSTRAINT "admin_audit_events_actor_id_fkey" FOREIGN KEY (actor_id) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'admin_audit_events_user_id_fkey' AND conrelid = 'public.admin_audit_events'::regclass) THEN
        ALTER TABLE "public"."admin_audit_events" ADD CONSTRAINT "admin_audit_events_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ai_usage_adjustments_actor_id_fkey' AND conrelid = 'public.ai_usage_adjustments'::regclass) THEN
        ALTER TABLE "public"."ai_usage_adjustments" ADD CONSTRAINT "ai_usage_adjustments_actor_id_fkey" FOREIGN KEY (actor_id) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ai_usage_adjustments_user_id_fkey' AND conrelid = 'public.ai_usage_adjustments'::regclass) THEN
        ALTER TABLE "public"."ai_usage_adjustments" ADD CONSTRAINT "ai_usage_adjustments_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'brew_records_bean_card_id_fkey' AND conrelid = 'public.brew_records'::regclass) THEN
        ALTER TABLE "public"."brew_records" ADD CONSTRAINT "brew_records_bean_card_id_fkey" FOREIGN KEY (bean_card_id) REFERENCES user_bean_cards(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'brew_records_user_id_fkey' AND conrelid = 'public.brew_records'::regclass) THEN
        ALTER TABLE "public"."brew_records" ADD CONSTRAINT "brew_records_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'candidate_facts_proposal_id_fkey' AND conrelid = 'public.candidate_facts'::regclass) THEN
        ALTER TABLE "public"."candidate_facts" ADD CONSTRAINT "candidate_facts_proposal_id_fkey" FOREIGN KEY (proposal_id) REFERENCES public_entity_proposals(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'candidate_facts_proposed_entity_id_fkey' AND conrelid = 'public.candidate_facts'::regclass) THEN
        ALTER TABLE "public"."candidate_facts" ADD CONSTRAINT "candidate_facts_proposed_entity_id_fkey" FOREIGN KEY (proposed_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'candidate_facts_reviewer_id_fkey' AND conrelid = 'public.candidate_facts'::regclass) THEN
        ALTER TABLE "public"."candidate_facts" ADD CONSTRAINT "candidate_facts_reviewer_id_fkey" FOREIGN KEY (reviewer_id) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'candidate_facts_source_user_id_fkey' AND conrelid = 'public.candidate_facts'::regclass) THEN
        ALTER TABLE "public"."candidate_facts" ADD CONSTRAINT "candidate_facts_source_user_id_fkey" FOREIGN KEY (source_user_id) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'coffea_sessions_user_id_fkey' AND conrelid = 'public.coffea_sessions'::regclass) THEN
        ALTER TABLE "public"."coffea_sessions" ADD CONSTRAINT "coffea_sessions_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'coffee_sources_entity_id_fkey' AND conrelid = 'public.coffee_sources'::regclass) THEN
        ALTER TABLE "public"."coffee_sources" ADD CONSTRAINT "coffee_sources_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_aliases_entity_id_fkey' AND conrelid = 'public.entity_aliases'::regclass) THEN
        ALTER TABLE "public"."entity_aliases" ADD CONSTRAINT "entity_aliases_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_sources_created_by_fkey' AND conrelid = 'public.entity_sources'::regclass) THEN
        ALTER TABLE "public"."entity_sources" ADD CONSTRAINT "entity_sources_created_by_fkey" FOREIGN KEY (created_by) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'entity_sources_entity_id_fkey' AND conrelid = 'public.entity_sources'::regclass) THEN
        ALTER TABLE "public"."entity_sources" ADD CONSTRAINT "entity_sources_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_merchants_entity_id_fkey' AND conrelid = 'public.green_bean_merchants'::regclass) THEN
        ALTER TABLE "public"."green_bean_merchants" ADD CONSTRAINT "green_bean_merchants_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_product_varietals_green_bean_product_entity_id_fkey' AND conrelid = 'public.green_bean_product_varietals'::regclass) THEN
        ALTER TABLE "public"."green_bean_product_varietals" ADD CONSTRAINT "green_bean_product_varietals_green_bean_product_entity_id_fkey" FOREIGN KEY (green_bean_product_entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_product_varietals_varietal_entity_id_fkey' AND conrelid = 'public.green_bean_product_varietals'::regclass) THEN
        ALTER TABLE "public"."green_bean_product_varietals" ADD CONSTRAINT "green_bean_product_varietals_varietal_entity_id_fkey" FOREIGN KEY (varietal_entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_products_coffee_source_entity_id_fkey' AND conrelid = 'public.green_bean_products'::regclass) THEN
        ALTER TABLE "public"."green_bean_products" ADD CONSTRAINT "green_bean_products_coffee_source_entity_id_fkey" FOREIGN KEY (coffee_source_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_products_entity_id_fkey' AND conrelid = 'public.green_bean_products'::regclass) THEN
        ALTER TABLE "public"."green_bean_products" ADD CONSTRAINT "green_bean_products_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_products_merchant_entity_id_fkey' AND conrelid = 'public.green_bean_products'::regclass) THEN
        ALTER TABLE "public"."green_bean_products" ADD CONSTRAINT "green_bean_products_merchant_entity_id_fkey" FOREIGN KEY (merchant_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_products_origin_entity_id_fkey' AND conrelid = 'public.green_bean_products'::regclass) THEN
        ALTER TABLE "public"."green_bean_products" ADD CONSTRAINT "green_bean_products_origin_entity_id_fkey" FOREIGN KEY (origin_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'green_bean_products_process_entity_id_fkey' AND conrelid = 'public.green_bean_products'::regclass) THEN
        ALTER TABLE "public"."green_bean_products" ADD CONSTRAINT "green_bean_products_process_entity_id_fkey" FOREIGN KEY (process_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'invite_codes_used_by_fkey' AND conrelid = 'public.invite_codes'::regclass) THEN
        ALTER TABLE "public"."invite_codes" ADD CONSTRAINT "invite_codes_used_by_fkey" FOREIGN KEY (used_by) REFERENCES user_profiles(id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'knowledge_sync_records_entity_id_fkey' AND conrelid = 'public.knowledge_sync_records'::regclass) THEN
        ALTER TABLE "public"."knowledge_sync_records" ADD CONSTRAINT "knowledge_sync_records_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'origins_entity_id_fkey' AND conrelid = 'public.origins'::regclass) THEN
        ALTER TABLE "public"."origins" ADD CONSTRAINT "origins_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'process_methods_entity_id_fkey' AND conrelid = 'public.process_methods'::regclass) THEN
        ALTER TABLE "public"."process_methods" ADD CONSTRAINT "process_methods_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'proposal_audit_events_proposal_id_fkey' AND conrelid = 'public.proposal_audit_events'::regclass) THEN
        ALTER TABLE "public"."proposal_audit_events" ADD CONSTRAINT "proposal_audit_events_proposal_id_fkey" FOREIGN KEY (proposal_id) REFERENCES public_entity_proposals(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'public_entities_created_by_fkey' AND conrelid = 'public.public_entities'::regclass) THEN
        ALTER TABLE "public"."public_entities" ADD CONSTRAINT "public_entities_created_by_fkey" FOREIGN KEY (created_by) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'public_entities_reviewed_by_fkey' AND conrelid = 'public.public_entities'::regclass) THEN
        ALTER TABLE "public"."public_entities" ADD CONSTRAINT "public_entities_reviewed_by_fkey" FOREIGN KEY (reviewed_by) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'public_entity_proposals_applied_entity_id_fkey' AND conrelid = 'public.public_entity_proposals'::regclass) THEN
        ALTER TABLE "public"."public_entity_proposals" ADD CONSTRAINT "public_entity_proposals_applied_entity_id_fkey" FOREIGN KEY (applied_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_product_varietals_roaster_product_entity_id_fkey' AND conrelid = 'public.roaster_product_varietals'::regclass) THEN
        ALTER TABLE "public"."roaster_product_varietals" ADD CONSTRAINT "roaster_product_varietals_roaster_product_entity_id_fkey" FOREIGN KEY (roaster_product_entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_product_varietals_varietal_entity_id_fkey' AND conrelid = 'public.roaster_product_varietals'::regclass) THEN
        ALTER TABLE "public"."roaster_product_varietals" ADD CONSTRAINT "roaster_product_varietals_varietal_entity_id_fkey" FOREIGN KEY (varietal_entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_coffee_source_entity_id_fkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_coffee_source_entity_id_fkey" FOREIGN KEY (coffee_source_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_entity_id_fkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_green_bean_merchant_entity_id_fkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_green_bean_merchant_entity_id_fkey" FOREIGN KEY (green_bean_merchant_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_green_bean_product_entity_id_fkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_green_bean_product_entity_id_fkey" FOREIGN KEY (green_bean_product_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_origin_entity_id_fkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_origin_entity_id_fkey" FOREIGN KEY (origin_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_process_entity_id_fkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_process_entity_id_fkey" FOREIGN KEY (process_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roaster_products_roaster_entity_id_fkey' AND conrelid = 'public.roaster_products'::regclass) THEN
        ALTER TABLE "public"."roaster_products" ADD CONSTRAINT "roaster_products_roaster_entity_id_fkey" FOREIGN KEY (roaster_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'roasters_entity_id_fkey' AND conrelid = 'public.roasters'::regclass) THEN
        ALTER TABLE "public"."roasters" ADD CONSTRAINT "roasters_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_ai_quota_settings_updated_by_fkey' AND conrelid = 'public.user_ai_quota_settings'::regclass) THEN
        ALTER TABLE "public"."user_ai_quota_settings" ADD CONSTRAINT "user_ai_quota_settings_updated_by_fkey" FOREIGN KEY (updated_by) REFERENCES user_profiles(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_ai_quota_settings_user_id_fkey' AND conrelid = 'public.user_ai_quota_settings'::regclass) THEN
        ALTER TABLE "public"."user_ai_quota_settings" ADD CONSTRAINT "user_ai_quota_settings_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_card_varietals_bean_card_id_fkey' AND conrelid = 'public.user_bean_card_varietals'::regclass) THEN
        ALTER TABLE "public"."user_bean_card_varietals" ADD CONSTRAINT "user_bean_card_varietals_bean_card_id_fkey" FOREIGN KEY (bean_card_id) REFERENCES user_bean_cards(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_card_varietals_varietal_entity_id_fkey' AND conrelid = 'public.user_bean_card_varietals'::regclass) THEN
        ALTER TABLE "public"."user_bean_card_varietals" ADD CONSTRAINT "user_bean_card_varietals_varietal_entity_id_fkey" FOREIGN KEY (varietal_entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_coffee_source_entity_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_coffee_source_entity_id_fkey" FOREIGN KEY (coffee_source_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_green_bean_merchant_entity_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_green_bean_merchant_entity_id_fkey" FOREIGN KEY (green_bean_merchant_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_green_bean_product_entity_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_green_bean_product_entity_id_fkey" FOREIGN KEY (green_bean_product_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_origin_entity_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_origin_entity_id_fkey" FOREIGN KEY (origin_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_process_entity_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_process_entity_id_fkey" FOREIGN KEY (process_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_roaster_entity_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_roaster_entity_id_fkey" FOREIGN KEY (roaster_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_roaster_product_entity_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_roaster_product_entity_id_fkey" FOREIGN KEY (roaster_product_entity_id) REFERENCES public_entities(id) ON DELETE SET NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_bean_cards_user_id_fkey' AND conrelid = 'public.user_bean_cards'::regclass) THEN
        ALTER TABLE "public"."user_bean_cards" ADD CONSTRAINT "user_bean_cards_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_equipment_items_user_id_fkey' AND conrelid = 'public.user_equipment_items'::regclass) THEN
        ALTER TABLE "public"."user_equipment_items" ADD CONSTRAINT "user_equipment_items_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_equipment_profiles_user_id_fkey' AND conrelid = 'public.user_equipment_profiles'::regclass) THEN
        ALTER TABLE "public"."user_equipment_profiles" ADD CONSTRAINT "user_equipment_profiles_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'user_memories_user_id_fkey' AND conrelid = 'public.user_memories'::regclass) THEN
        ALTER TABLE "public"."user_memories" ADD CONSTRAINT "user_memories_user_id_fkey" FOREIGN KEY (user_id) REFERENCES user_profiles(id) ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'varietals_entity_id_fkey' AND conrelid = 'public.varietals'::regclass) THEN
        ALTER TABLE "public"."varietals" ADD CONSTRAINT "varietals_entity_id_fkey" FOREIGN KEY (entity_id) REFERENCES public_entities(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Sequence ownership
ALTER SEQUENCE "public"."admin_audit_events_id_seq" OWNED BY "public"."admin_audit_events"."id";
ALTER SEQUENCE "public"."ai_usage_adjustments_id_seq" OWNED BY "public"."ai_usage_adjustments"."id";
ALTER SEQUENCE "public"."ai_usage_events_id_seq" OWNED BY "public"."ai_usage_events"."id";
ALTER SEQUENCE "public"."entity_aliases_id_seq" OWNED BY "public"."entity_aliases"."id";
ALTER SEQUENCE "public"."entity_sources_id_seq" OWNED BY "public"."entity_sources"."id";
ALTER SEQUENCE "public"."knowledge_sync_records_id_seq" OWNED BY "public"."knowledge_sync_records"."id";
ALTER SEQUENCE "public"."proposal_audit_events_id_seq" OWNED BY "public"."proposal_audit_events"."id";

-- Indexes
CREATE INDEX IF NOT EXISTS ix_admin_audit_events_user_id ON public.admin_audit_events USING btree (user_id);
CREATE INDEX IF NOT EXISTS ai_usage_adjustments_user_period_idx ON public.ai_usage_adjustments USING btree (user_id, period_start, period_end);
CREATE INDEX IF NOT EXISTS ix_ai_usage_events_user_id ON public.ai_usage_events USING btree (user_id);
CREATE INDEX IF NOT EXISTS brew_records_bean_card_id_idx ON public.brew_records USING btree (bean_card_id);
CREATE INDEX IF NOT EXISTS brew_records_record_type_idx ON public.brew_records USING btree (record_type);
CREATE INDEX IF NOT EXISTS ix_brew_records_created_at ON public.brew_records USING btree (created_at);
CREATE INDEX IF NOT EXISTS ix_brew_records_user_id ON public.brew_records USING btree (user_id);
CREATE INDEX IF NOT EXISTS ix_candidate_facts_entity_type ON public.candidate_facts USING btree (entity_type);
CREATE INDEX IF NOT EXISTS ix_candidate_facts_proposal_id ON public.candidate_facts USING btree (proposal_id);
CREATE INDEX IF NOT EXISTS ix_candidate_facts_proposed_entity_id ON public.candidate_facts USING btree (proposed_entity_id);
CREATE INDEX IF NOT EXISTS ix_candidate_facts_status ON public.candidate_facts USING btree (status);
CREATE INDEX IF NOT EXISTS ix_coffea_sessions_user_id ON public.coffea_sessions USING btree (user_id);
CREATE INDEX IF NOT EXISTS ix_coffee_sources_source_type ON public.coffee_sources USING btree (source_type);
CREATE INDEX IF NOT EXISTS ix_entity_aliases_entity_id ON public.entity_aliases USING btree (entity_id);
CREATE INDEX IF NOT EXISTS ix_entity_aliases_normalized_alias ON public.entity_aliases USING btree (normalized_alias);
CREATE INDEX IF NOT EXISTS ix_entity_sources_entity_id ON public.entity_sources USING btree (entity_id);
CREATE INDEX IF NOT EXISTS ix_green_bean_products_coffee_source_entity_id ON public.green_bean_products USING btree (coffee_source_entity_id);
CREATE INDEX IF NOT EXISTS ix_green_bean_products_merchant_entity_id ON public.green_bean_products USING btree (merchant_entity_id);
CREATE INDEX IF NOT EXISTS ix_green_bean_products_origin_entity_id ON public.green_bean_products USING btree (origin_entity_id);
CREATE INDEX IF NOT EXISTS ix_green_bean_products_process_entity_id ON public.green_bean_products USING btree (process_entity_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_sync_records_entity_id ON public.knowledge_sync_records USING btree (entity_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_sync_records_markdown_path ON public.knowledge_sync_records USING btree (markdown_path);
CREATE INDEX IF NOT EXISTS ix_knowledge_sync_records_status ON public.knowledge_sync_records USING btree (status);
CREATE INDEX IF NOT EXISTS ix_proposal_audit_events_proposal_id ON public.proposal_audit_events USING btree (proposal_id);
CREATE INDEX IF NOT EXISTS ix_public_entities_entity_type ON public.public_entities USING btree (entity_type);
CREATE INDEX IF NOT EXISTS ix_public_entities_normalized_name ON public.public_entities USING btree (normalized_name);
CREATE INDEX IF NOT EXISTS ix_public_entities_status ON public.public_entities USING btree (status);
CREATE INDEX IF NOT EXISTS ix_public_entity_proposals_entity_type ON public.public_entity_proposals USING btree (entity_type);
CREATE INDEX IF NOT EXISTS ix_public_entity_proposals_status ON public.public_entity_proposals USING btree (status);
CREATE INDEX IF NOT EXISTS public_entity_proposals_applied_entity_id_idx ON public.public_entity_proposals USING btree (applied_entity_id);
CREATE INDEX IF NOT EXISTS ix_roaster_products_coffee_source_entity_id ON public.roaster_products USING btree (coffee_source_entity_id);
CREATE INDEX IF NOT EXISTS ix_roaster_products_green_bean_merchant_entity_id ON public.roaster_products USING btree (green_bean_merchant_entity_id);
CREATE INDEX IF NOT EXISTS ix_roaster_products_green_bean_product_entity_id ON public.roaster_products USING btree (green_bean_product_entity_id);
CREATE INDEX IF NOT EXISTS ix_roaster_products_origin_entity_id ON public.roaster_products USING btree (origin_entity_id);
CREATE INDEX IF NOT EXISTS ix_roaster_products_process_entity_id ON public.roaster_products USING btree (process_entity_id);
CREATE INDEX IF NOT EXISTS ix_roaster_products_roaster_entity_id ON public.roaster_products USING btree (roaster_entity_id);
CREATE INDEX IF NOT EXISTS user_ai_quota_settings_updated_by_idx ON public.user_ai_quota_settings USING btree (updated_by);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_coffee_source_entity_id ON public.user_bean_cards USING btree (coffee_source_entity_id);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_green_bean_merchant_entity_id ON public.user_bean_cards USING btree (green_bean_merchant_entity_id);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_green_bean_product_entity_id ON public.user_bean_cards USING btree (green_bean_product_entity_id);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_origin_entity_id ON public.user_bean_cards USING btree (origin_entity_id);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_process_entity_id ON public.user_bean_cards USING btree (process_entity_id);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_roaster_entity_id ON public.user_bean_cards USING btree (roaster_entity_id);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_roaster_product_entity_id ON public.user_bean_cards USING btree (roaster_product_entity_id);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_status ON public.user_bean_cards USING btree (status);
CREATE INDEX IF NOT EXISTS ix_user_bean_cards_user_id ON public.user_bean_cards USING btree (user_id);
CREATE INDEX IF NOT EXISTS ix_user_equipment_items_category ON public.user_equipment_items USING btree (category);
CREATE INDEX IF NOT EXISTS ix_user_equipment_items_user_id ON public.user_equipment_items USING btree (user_id);
CREATE INDEX IF NOT EXISTS ix_user_equipment_profiles_user_id ON public.user_equipment_profiles USING btree (user_id);
CREATE INDEX IF NOT EXISTS user_memories_user_kind_idx ON public.user_memories USING btree (user_id, kind);
CREATE INDEX IF NOT EXISTS user_memories_user_status_idx ON public.user_memories USING btree (user_id, status);

-- Row-level security
ALTER TABLE "public"."ai_usage_adjustments" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."user_ai_quota_settings" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."user_equipment_items" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."user_memories" ENABLE ROW LEVEL SECURITY;

-- End of DeepCoffee production schema baseline.
