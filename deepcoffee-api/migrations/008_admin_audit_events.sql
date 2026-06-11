-- 管理员对用户的修改审计（套餐/角色/状态/额度调整）。
-- 新表：部署后 api 启动时 create_all 会自动建出；本文件留档，手动执行亦幂等。

CREATE TABLE IF NOT EXISTS admin_audit_events (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    actor_id VARCHAR REFERENCES user_profiles(id) ON DELETE SET NULL,
    action VARCHAR NOT NULL,
    before_value VARCHAR,
    after_value VARCHAR,
    reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS admin_audit_events_user_idx
    ON admin_audit_events(user_id, created_at DESC);
