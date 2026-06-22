-- DeepCoffee schema generated from ORM models (app/models/tables.py)
-- 可直接在 Supabase SQL Editor 运行

CREATE TABLE IF NOT EXISTS ai_usage_events (
	id SERIAL NOT NULL, 
	user_id VARCHAR NOT NULL, 
	action VARCHAR NOT NULL, 
	trace_id VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public_entity_proposals (
	id VARCHAR NOT NULL, 
	entity_type VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	payload JSONB DEFAULT '{}' NOT NULL, 
	source_input TEXT, 
	trace_id VARCHAR, 
	proposer_id VARCHAR NOT NULL, 
	status VARCHAR DEFAULT 'pending' NOT NULL, 
	reviewer_note TEXT, 
	applied_markdown_path VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS user_profiles (
	id VARCHAR NOT NULL, 
	email VARCHAR, 
	display_name VARCHAR, 
	plan VARCHAR DEFAULT 'basic' NOT NULL, 
	timezone VARCHAR DEFAULT 'Asia/Shanghai' NOT NULL, 
	unit_system VARCHAR DEFAULT 'metric' NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (email)
);

CREATE TABLE IF NOT EXISTS brew_records (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	source_type VARCHAR DEFAULT 'text' NOT NULL, 
	raw_input TEXT, 
	bean_name VARCHAR, 
	origin VARCHAR, 
	roaster VARCHAR, 
	process VARCHAR, 
	varietal VARCHAR, 
	device VARCHAR, 
	grinder VARCHAR, 
	grind_setting VARCHAR, 
	dose_g FLOAT, 
	water_ml FLOAT, 
	water_temp_c FLOAT, 
	ratio VARCHAR, 
	ratio_value FLOAT, 
	brew_time VARCHAR, 
	brew_time_seconds INTEGER, 
	brew_steps JSONB DEFAULT '[]' NOT NULL, 
	evaluation JSONB, 
	notes TEXT, 
	recap TEXT, 
	suggestions JSONB DEFAULT '[]' NOT NULL, 
	trace_id VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES user_profiles (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS invite_codes (
	code VARCHAR NOT NULL, 
	status VARCHAR DEFAULT 'active' NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	note TEXT, 
	used_by VARCHAR, 
	used_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (code), 
	FOREIGN KEY(used_by) REFERENCES user_profiles (id)
);

CREATE TABLE IF NOT EXISTS newapi_billing_links (
	user_id VARCHAR NOT NULL, 
	newapi_user_id VARCHAR NOT NULL, 
	internal_token TEXT, 
	plan VARCHAR DEFAULT 'basic' NOT NULL, 
	last_synced_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (user_id), 
	FOREIGN KEY(user_id) REFERENCES user_profiles (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proposal_audit_events (
	id SERIAL NOT NULL, 
	proposal_id VARCHAR NOT NULL, 
	actor_id VARCHAR, 
	action VARCHAR NOT NULL, 
	note TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(proposal_id) REFERENCES public_entity_proposals (id) ON DELETE CASCADE
);
