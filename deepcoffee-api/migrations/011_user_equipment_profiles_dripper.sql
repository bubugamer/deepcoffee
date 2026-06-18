-- 011: 器具资料拆分「冲煮方式」与「滤杯」
--
-- 背景：原 user_equipment_profiles.brew_method 同时承担了「冲煮方式」和「滤杯」两件事，
-- 实际存的多是滤杯（V60 等）。本次拆成：
--   dripper      —— 滤杯 / 冲煮器具（自由文本，如 V60、Kalita）
--   brew_method  —— 冲煮方式（下拉枚举：滤杯冲煮 / 意式 / 法压壶 / 爱乐压 / 浸泡式 / 摩卡壶 / 虹吸壶 / 冷萃）
--
-- 迁移策略：把旧 brew_method 整列改名为 dripper（V60 等数据原地保留即正确），
-- 再新建 brew_method 列并按关键词回填冲煮方式；旧值确实是「冲煮方式」而非滤杯的，从 dripper 清空。
-- create_all 只建表不改列，本文件须在 Supabase 手动执行。

ALTER TABLE user_equipment_profiles RENAME COLUMN brew_method TO dripper;
ALTER TABLE user_equipment_profiles ADD COLUMN IF NOT EXISTS brew_method text;

UPDATE user_equipment_profiles
SET brew_method = CASE
    WHEN dripper ~* '意式|espresso'              THEN '意式'
    WHEN dripper ~* '法压|french'                THEN '法压壶'
    WHEN dripper ~* '爱乐压|aeropress'           THEN '爱乐压'
    WHEN dripper ~* '摩卡|moka'                  THEN '摩卡壶'
    WHEN dripper ~* '虹吸|syphon|siphon'         THEN '虹吸壶'
    WHEN dripper ~* '冷萃|cold ?brew'            THEN '冷萃'
    WHEN dripper ~* '浸泡|聪明杯|clever|immers'  THEN '浸泡式'
    ELSE '滤杯冲煮'
END
WHERE dripper IS NOT NULL;

-- 旧值本身就是「冲煮方式」（非滤杯）的，dripper 清空，避免「爱乐压」既当方式又当滤杯。
UPDATE user_equipment_profiles
SET dripper = NULL
WHERE brew_method IS NOT NULL AND brew_method <> '滤杯冲煮';
