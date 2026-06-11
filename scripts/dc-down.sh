#!/usr/bin/env bash
# 停止 DeepCoffee 全栈。默认保留数据卷。
#
# 用法：
#   ./scripts/dc-down.sh          # 停容器、移网络，数据卷保留
#   ./scripts/dc-down.sh -v       # 连数据卷一起删，慎用
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "▶ 停止 deepcoffee 栈 ..."
docker compose down "$@"

echo "✅ 已停止 deepcoffee"
