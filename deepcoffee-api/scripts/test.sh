#!/usr/bin/env bash
# 在一次性容器里跑 pytest：用现成的 deepcoffee-api 镜像（已装依赖）+ 挂载宿主源码 +
# 连宿主机的测试库 deepcoffee-pg(:5433)。这样改完宿主代码不必重建镜像即可测。
#
# 用法：
#   ./scripts/test.sh                 # 跑全部
#   ./scripts/test.sh tests/test_beans.py -q   # 透传 pytest 参数
set -euo pipefail

API_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KNOWLEDGE_DIR="$(cd "$API_DIR/../knowledge" && pwd)"
# 源码挂在 /app，故容器内 /app/tests/test_prompts.py 的 parents[2] 解析为 /，
# test_prompts.py 据此到 /docs 找审核文档；这里把宿主 docs 只读挂到 /docs。
DOCS_DIR="$(cd "$API_DIR/../docs" && pwd)"

exec docker run --rm \
  -v "$API_DIR":/app -w /app \
  -v "$KNOWLEDGE_DIR":/knowledge:ro \
  -v "$DOCS_DIR":/docs:ro \
  -e DEEPCOFFEE_KNOWLEDGE_DIR=/knowledge \
  --add-host host.docker.internal:host-gateway \
  -e TEST_DATABASE_URL=postgresql+asyncpg://deepcoffee:deepcoffee@host.docker.internal:5433/deepcoffee_test \
  deepcoffee-api:latest \
  bash -c "pip install -q pytest >/dev/null 2>&1 && python -m pytest ${*:-}"
