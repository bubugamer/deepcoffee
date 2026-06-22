-- user_profiles 增加 status 列：账号禁用能力（admin 用户管理操作）。
-- create_all 不会给已有表补列，部署带用户管理功能的版本前，先在 Supabase SQL Editor 运行本文件。

ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';
