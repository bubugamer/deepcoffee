-- 豆卡拼配/多豆源归一：豆子信息（产地/庄园/生豆商/生豆商产品/处理法/品种/海拔/采收期）从顶层列
-- 搬进「豆源」bean_components（单豆 1 条、拼配多条），顶层只留产品级字段。
-- 顺序：加 bean_product_type → 回填 components（顶层→1 条，含已解析实体 id）→ 按条数写 type → 删顶层豆子列。
-- 与 0.29.0 的 016 一起、在部署新后端后执行（016 改 brew_records、017 改 user_bean_cards，不同表互不依赖）。

-- 1) 新增产品类型列（系统按豆源条数维护）。
ALTER TABLE "public"."user_bean_cards"
    ADD COLUMN IF NOT EXISTS bean_product_type text NOT NULL DEFAULT 'single';

-- 2) 回填：bean_components 为空、但有任一顶层豆子字段的卡 → 折成 1 条豆源（连同已解析的实体 id 一并搬入）。
UPDATE "public"."user_bean_cards"
SET bean_components = jsonb_build_array(
        jsonb_strip_nulls(jsonb_build_object(
            'origin_name', origin_name,
            'coffee_source_name', coffee_source_name,
            'green_bean_merchant_name', green_bean_merchant_name,
            'green_bean_product_name', green_bean_product_name,
            'process_name', process_name,
            'altitude_text', altitude_text,
            'harvest_date_text', harvest_date_text,
            'origin_entity_id', origin_entity_id,
            'process_entity_id', process_entity_id,
            'coffee_source_entity_id', coffee_source_entity_id,
            'green_bean_merchant_entity_id', green_bean_merchant_entity_id
        ))
        || jsonb_build_object(
            'varietal_names', COALESCE(varietal_names, '[]'::jsonb),
            'varietal_entity_ids', '[]'::jsonb
        )
    )
WHERE (bean_components IS NULL OR bean_components = '[]'::jsonb)
  AND (
        origin_name IS NOT NULL OR coffee_source_name IS NOT NULL OR green_bean_merchant_name IS NOT NULL
        OR green_bean_product_name IS NOT NULL OR process_name IS NOT NULL OR altitude_text IS NOT NULL
        OR harvest_date_text IS NOT NULL OR (varietal_names IS NOT NULL AND varietal_names <> '[]'::jsonb)
  );

-- 3) 按豆源条数写 bean_product_type（≥2 条→blend，否则 single）。
UPDATE "public"."user_bean_cards"
SET bean_product_type = CASE
        WHEN jsonb_array_length(COALESCE(bean_components, '[]'::jsonb)) >= 2 THEN 'blend'
        ELSE 'single'
    END;

-- 4) 删顶层豆子列（含其外键约束，DROP COLUMN 一并移除）。产品级 roaster/roaster_product 实体 id 保留。
ALTER TABLE "public"."user_bean_cards"
    DROP COLUMN IF EXISTS origin_name,
    DROP COLUMN IF EXISTS process_name,
    DROP COLUMN IF EXISTS varietal_names,
    DROP COLUMN IF EXISTS coffee_source_name,
    DROP COLUMN IF EXISTS green_bean_merchant_name,
    DROP COLUMN IF EXISTS green_bean_product_name,
    DROP COLUMN IF EXISTS altitude_text,
    DROP COLUMN IF EXISTS harvest_date_text,
    DROP COLUMN IF EXISTS origin_entity_id,
    DROP COLUMN IF EXISTS process_entity_id,
    DROP COLUMN IF EXISTS coffee_source_entity_id,
    DROP COLUMN IF EXISTS green_bean_merchant_entity_id,
    DROP COLUMN IF EXISTS green_bean_product_entity_id;
