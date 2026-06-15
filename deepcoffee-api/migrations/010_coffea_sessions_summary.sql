-- coffea_sessions 增加 summary 列：主题式长期对话摘要（L2），超窗口的老对话增量并入。
-- create_all 不会给已有表补列，部署本版本前，先在 Supabase SQL Editor 运行本文件；
-- 本地测试库（localhost:5433/deepcoffee_test）同样执行一次。

ALTER TABLE coffea_sessions
    ADD COLUMN IF NOT EXISTS summary JSONB NOT NULL DEFAULT '[]'::jsonb;
