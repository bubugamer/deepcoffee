-- user_profiles 增加 role 列：管理员身份持久化（bootstrap 邀请码初始化流程）。
-- create_all 不会给已有表补列，部署带 bootstrap 功能的版本前，先在 Supabase SQL Editor 运行本文件。

ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'user';
