-- 011: 器具资料拆分「冲煮方式」与「滤杯」
--
-- 背景：原 user_equipment_profiles.brew_method 同时承担了「冲煮方式」和「滤杯」两件事，
-- 实际存的多是滤杯（V60 等）。本次拆成：
--   dripper      —— 滤杯 / 冲煮器具（自由文本，如 V60、Kalita，新增列）
--   brew_method  —— 冲煮方式（保留原列，改为下拉枚举：滤杯冲煮 / 意式 / 法压壶 / 爱乐压 / 浸泡式 / 摩卡壶 / 虹吸壶 / 冷萃）
--
-- 迁移策略：新建 dripper 列；把原本错放在 brew_method 里的滤杯挪到 dripper，
-- brew_method 改填回「冲煮方式」（原值确实是滤杯的回填默认「滤杯冲煮」，原值本就是冲煮方式的按关键词归位）。
-- 两个 SET 在同一条 UPDATE 里都引用「旧的」brew_method 值，故无需先后两步。
-- create_all 只建表不改列，本文件须在 Supabase 手动执行。

ALTER TABLE user_equipment_profiles ADD COLUMN IF NOT EXISTS dripper text;

UPDATE user_equipment_profiles
SET dripper = CASE
        -- 原值本身就是「冲煮方式」（非滤杯）的，dripper 留空，避免「爱乐压」既当方式又当滤杯
        WHEN brew_method ~* '意式|espresso|法压|french|爱乐压|aeropress|摩卡|moka|虹吸|syphon|siphon|冷萃|cold ?brew|浸泡|聪明杯|clever|immers' THEN NULL
        ELSE brew_method
    END,
    brew_method = CASE
        WHEN brew_method ~* '意式|espresso'              THEN '意式'
        WHEN brew_method ~* '法压|french'                THEN '法压壶'
        WHEN brew_method ~* '爱乐压|aeropress'           THEN '爱乐压'
        WHEN brew_method ~* '摩卡|moka'                  THEN '摩卡壶'
        WHEN brew_method ~* '虹吸|syphon|siphon'         THEN '虹吸壶'
        WHEN brew_method ~* '冷萃|cold ?brew'            THEN '冷萃'
        WHEN brew_method ~* '浸泡|聪明杯|clever|immers'  THEN '浸泡式'
        ELSE '滤杯冲煮'
    END
WHERE brew_method IS NOT NULL;
