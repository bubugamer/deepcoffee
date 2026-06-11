#!/usr/bin/env bash
# DeepCoffee 一键启动：api + frontend。
#
# 用法：
#   ./scripts/dc-up.sh            # 起全栈（不重建镜像）
#   ./scripts/dc-up.sh --build    # 重建镜像后启动
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

WEB_PORT="${WEB_PORT:-3010}"
API_PORT="${API_PORT:-8642}"

echo "▶ 启动 deepcoffee 栈 (api + frontend) ..."
docker compose up -d "$@"

echo
echo "✅ 全栈已启动："
echo "   前端登录        http://localhost:${WEB_PORT}/auth"
echo "   后端 API        http://localhost:${API_PORT}/v1/health"
echo
echo "   demo 账号        demo@deepcoffee.app / DeepCoffee2026!"
