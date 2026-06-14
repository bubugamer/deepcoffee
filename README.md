# DeepCoffee ☕

精品咖啡 AI 助手：对话式冲煮记录、豆卡识别、冲煮建议与知识库问答。 变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 功能

- **Coffea 对话助手**：统一聊天入口，意图调度后路由到专项能力（豆卡识图录入、冲煮记录解析、参数调整教练、知识库问答、联网核实）。模型不可用时一律降级为本地规则，绝不让功能整体不可用。
- **豆仓**：私有豆卡管理。上传烘焙商豆卡照片即可识别录入（高识别度自动建档、低识别度出草稿确认），支持动态风味维度。
- **冲煮建议**：基于豆子信息与用户器具生成起手参数；支持默认器具套、常见磨豆机的具体研磨刻度区间（内置刻度参考表）。
- **冲煮记录**：自然语言描述一杯冲煮，AI 解析成结构化记录，支持同豆对比。
- **知识库**：Markdown 知识库（冲煮、器具、产地、品种、处理法…），问答基于知识库摘录作答以降低幻觉；客观实体沉淀进公共实体库（管理员审核链路）。
- **邀请制 + 额度自管**：邀请码注册；AI 用量按月计数（入口动作计一次），管理员可调上限与已用数，全部修改留审计。
- **管理后台**：概览、邀请码、用户管理（详情编辑 / 修改历史）、内容审核（提案 / 候选事实 / 实体）、知识库管理。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | Next.js 15 (App Router) + TypeScript + TailwindCSS |
| 后端 | FastAPI + SQLAlchemy (async) + Pydantic |
| 数据库 / 认证 | Supabase（Postgres + Auth，ES256 JWT 经 JWKS 验签） |
| 模型 | 后端直连 OpenAI 兼容接口：文本与 vision 各一条独立通道（base_url + key 可分开配） |
| 联网检索 | Brave Search API（可选，未配则降级回知识库） |
| 可观测 | Sentry + Langfuse（均可选） |

## 目录结构

```
deepcoffee-api/   # FastAPI 后端（app/、tests/、migrations/）
frontend/         # Next.js 前端
knowledge/        # Markdown 知识库（后端只读挂载）
deploy/           # 前端 Dockerfile、引导邀请码生成脚本
scripts/          # 一键启停脚本
docker-compose.yml
```

## 快速开始

1. **配置环境变量**：复制 `deepcoffee-api/.env.example` 为 `deepcoffee-api/.env`，填入 Supabase 连接信息与模型网关配置：

   ```env
   DEEPCOFFEE_MODEL_BASE_URL=https://api.deepseek.com   # 不要带 /v1，会自动拼 /v1/chat/completions
   DEEPCOFFEE_MODEL_API_KEY=sk-...
   DEEPCOFFEE_VISION_MODEL_BASE_URL=https://api.moonshot.cn
   DEEPCOFFEE_VISION_MODEL_API_KEY=sk-...
   ```

   模型配置留空也能跑：所有 AI 能力自动退回本地规则。

2. **初始化数据库**：在 Supabase SQL Editor 依次执行 `deepcoffee-api/migrations/` 下的 SQL（新表会在 api 启动时自动创建，已有表的加列必须手动执行迁移）。

3. **生成引导邀请码**（首个管理员）：

   ```bash
   ./deploy/gen-bootstrap-code.sh   # 写入 .env 的 DEEPCOFFEE_BOOTSTRAP_INVITE_CODE
   ```

   仅当库中尚无管理员时，该码会注册为一次性邀请码；用它注册的用户自动成为管理员。

4. **启动**：

   ```bash
   docker compose up -d --build
   # 前端 http://localhost:3010 · API http://localhost:8642/docs
   ```

## 本地开发

```bash
# 后端（需本地 Postgres 测试库，见 tests/conftest.py）
cd deepcoffee-api && pip install -e ".[dev]" && pytest

# 前端
cd frontend && npm install && npm run dev
```

本地未配 Supabase 时，可用开发 token 调试受保护接口：`Authorization: Bearer dev:<id>:<email>`（生产环境禁用）。

## 设计原则

- **有模型用模型、没有就回退本地**：模型只是增强，绝不是硬依赖；降级对用户显式可见。
- **写库须确认**：聊天单轮不静默修改用户数据（高识别度豆卡自动录入是显式设计的例外）。
- **业务额度与厂商计费分离**：用户额度由 DeepCoffee 自管（月度次数），厂商 key 只在服务端。
- **公共实体人审优先**：用户数据沉淀公共知识一律走管理员审核，人工修改永远优先于自动导入。
