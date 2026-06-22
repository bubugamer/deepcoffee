-- 012: 器具从「整套组合」迁移为「单件库存」，并把冲煮方式/滤材/用水放到杯级记录。
--
-- 旧表 user_equipment_profiles 第一阶段保留，便于回滚观察；业务读写切到 user_equipment_items。

ALTER TABLE brew_records ADD COLUMN IF NOT EXISTS brew_method text;
ALTER TABLE brew_records ADD COLUMN IF NOT EXISTS filter_media text;
ALTER TABLE brew_records ADD COLUMN IF NOT EXISTS water text;

CREATE TABLE IF NOT EXISTS user_equipment_items (
    id text PRIMARY KEY,
    user_id text NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    category text NOT NULL,
    name text NOT NULL,
    normalized_name text NOT NULL,
    notes text,
    is_default boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT user_equipment_items_user_category_name_uq UNIQUE (user_id, category, normalized_name),
    CONSTRAINT user_equipment_items_category_ck CHECK (category IN ('brewer', 'grinder', 'filter_media', 'water'))
);

CREATE INDEX IF NOT EXISTS ix_user_equipment_items_user_id ON user_equipment_items(user_id);
CREATE INDEX IF NOT EXISTS ix_user_equipment_items_category ON user_equipment_items(category);

INSERT INTO user_equipment_items (id, user_id, category, name, normalized_name, notes, is_default, created_at, updated_at)
SELECT 'eqi_' || substr(md5(id || ':brewer:' || dripper), 1, 16),
       user_id, 'brewer', trim(dripper), lower(trim(dripper)), label, is_default, created_at, updated_at
FROM user_equipment_profiles
WHERE nullif(trim(coalesce(dripper, '')), '') IS NOT NULL
ON CONFLICT (user_id, category, normalized_name) DO UPDATE
SET notes = coalesce(user_equipment_items.notes, EXCLUDED.notes),
    is_default = user_equipment_items.is_default OR EXCLUDED.is_default;

INSERT INTO user_equipment_items (id, user_id, category, name, normalized_name, notes, is_default, created_at, updated_at)
SELECT 'eqi_' || substr(md5(id || ':grinder:' || grinder), 1, 16),
       user_id, 'grinder', trim(grinder), lower(trim(grinder)), label, is_default, created_at, updated_at
FROM user_equipment_profiles
WHERE nullif(trim(coalesce(grinder, '')), '') IS NOT NULL
ON CONFLICT (user_id, category, normalized_name) DO UPDATE
SET notes = coalesce(user_equipment_items.notes, EXCLUDED.notes),
    is_default = user_equipment_items.is_default OR EXCLUDED.is_default;

INSERT INTO user_equipment_items (id, user_id, category, name, normalized_name, notes, is_default, created_at, updated_at)
SELECT 'eqi_' || substr(md5(id || ':filter_media:' || filter_media), 1, 16),
       user_id, 'filter_media', trim(filter_media), lower(trim(filter_media)), label, is_default, created_at, updated_at
FROM user_equipment_profiles
WHERE nullif(trim(coalesce(filter_media, '')), '') IS NOT NULL
ON CONFLICT (user_id, category, normalized_name) DO UPDATE
SET notes = coalesce(user_equipment_items.notes, EXCLUDED.notes),
    is_default = user_equipment_items.is_default OR EXCLUDED.is_default;

INSERT INTO user_equipment_items (id, user_id, category, name, normalized_name, notes, is_default, created_at, updated_at)
SELECT 'eqi_' || substr(md5(id || ':water:' || water), 1, 16),
       user_id, 'water', trim(water), lower(trim(water)), label, is_default, created_at, updated_at
FROM user_equipment_profiles
WHERE nullif(trim(coalesce(water, '')), '') IS NOT NULL
ON CONFLICT (user_id, category, normalized_name) DO UPDATE
SET notes = coalesce(user_equipment_items.notes, EXCLUDED.notes),
    is_default = user_equipment_items.is_default OR EXCLUDED.is_default;

WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY user_id, category
               ORDER BY is_default DESC, created_at ASC, id ASC
           ) AS rn
    FROM user_equipment_items
)
UPDATE user_equipment_items item
SET is_default = ranked.rn = 1
FROM ranked
WHERE item.id = ranked.id;
