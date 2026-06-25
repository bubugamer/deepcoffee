-- 冲煮记录字段归一：豆名/产地/烘焙商/处理法/品种不再各存快照，统一从关联豆卡现取。
-- 每条记录必须关联一张豆卡：先校验无空值 → 删 5 列 → bean_card_id NOT NULL → 外键改 RESTRICT。
-- 上线顺序：先部署不再读写这 5 列的后端代码，确认无误后再在 Supabase 执行本迁移。

-- 1) 前置 guard：存在 bean_card_id 为空的记录则中止（需先补关联豆卡再跑）。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM brew_records WHERE bean_card_id IS NULL) THEN
        RAISE EXCEPTION '存在 bean_card_id 为空的冲煮记录，需先补关联豆卡再执行本迁移';
    END IF;
END $$;

-- 2) 删掉 5 个快照列（豆名等改由关联豆卡现取）。
ALTER TABLE "public"."brew_records"
    DROP COLUMN IF EXISTS bean_name,
    DROP COLUMN IF EXISTS origin,
    DROP COLUMN IF EXISTS roaster,
    DROP COLUMN IF EXISTS process,
    DROP COLUMN IF EXISTS varietal;

-- 3) bean_card_id 收紧为 NOT NULL（每条记录必须关联豆卡）。
ALTER TABLE "public"."brew_records"
    ALTER COLUMN bean_card_id SET NOT NULL;

-- 4) 外键 ON DELETE SET NULL → RESTRICT（豆卡为逻辑删除，硬删不应发生；RESTRICT 防误删留下孤儿记录）。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'brew_records_bean_card_id_fkey' AND conrelid = 'public.brew_records'::regclass) THEN
        ALTER TABLE "public"."brew_records" DROP CONSTRAINT "brew_records_bean_card_id_fkey";
    END IF;
    ALTER TABLE "public"."brew_records"
        ADD CONSTRAINT "brew_records_bean_card_id_fkey"
        FOREIGN KEY (bean_card_id) REFERENCES user_bean_cards(id) ON DELETE RESTRICT;
END $$;
