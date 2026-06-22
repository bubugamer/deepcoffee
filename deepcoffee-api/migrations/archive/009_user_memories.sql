-- 用户长期记忆（L3 画像）：从对话 / 冲煮记录沉淀的稳定偏好与事实，跨会话注入。
-- 新表：部署后 api 启动时 create_all 会自动建出；本文件留档，手动执行亦幂等。

CREATE TABLE IF NOT EXISTS user_memories (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    kind VARCHAR NOT NULL,
    content TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.6,
    source VARCHAR,
    source_ref VARCHAR,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS user_memories_user_status_idx
    ON user_memories(user_id, status);
CREATE INDEX IF NOT EXISTS user_memories_user_kind_idx
    ON user_memories(user_id, kind);
