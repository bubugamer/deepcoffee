-- user_equipment_profiles 增加 is_default 列：默认器具套（生成冲煮建议时默认使用）。
-- create_all 不会给已有表补列，部署本版本前，先在 Supabase SQL Editor 运行本文件；
-- 本地测试库（localhost:5433/deepcoffee_test）同样执行一次。

ALTER TABLE user_equipment_profiles
    ADD COLUMN IF NOT EXISTS is_default boolean NOT NULL DEFAULT false;
