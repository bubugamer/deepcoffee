#!/usr/bin/env bash
# DeepCoffee 一键启动：先起 new-api（独立 compose）→ 等它就绪 → 再起 deepcoffee（api + frontend）。
#
# 两个栈各自独立、各自的 Docker 网络；api 容器经 host.docker.internal 连 new-api。
# 顺序很重要：new-api 先就绪，deepcoffee 首次 /me 建影子账户才不会降级。
#
# 用法：
#   ./scripts/dc-up.sh            # 起全栈（不重建镜像）
#   ./scripts/dc-up.sh --build    # 透传给 deepcoffee compose（改了后端代码 / 改了端口时用）
#
# 透传参数只作用于 deepcoffee 栈；new-api 是上游镜像，不重建。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NEW_API_PORT="${NEW_API_PORT:-18451}"
WEB_PORT="${WEB_PORT:-3010}"
API_PORT="${API_PORT:-8642}"

echo "▶ [1/3] 启动 new-api 栈 (new-api/docker-compose.yml) ..."
docker compose -f new-api/docker-compose.yml up -d

echo "▶ [2/3] 等待 new-api 就绪 (http://localhost:${NEW_API_PORT}/api/status) ..."
for i in $(seq 1 30); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:${NEW_API_PORT}/api/status" || true)"
  if [ "$code" = "200" ]; then
    echo "  ✓ new-api 就绪"
    break
  fi
  if [ "$i" = "30" ]; then
    echo "  ⚠ new-api 60s 内未就绪：继续起 deepcoffee，但首次建影子账户可能降级（new-api 起来后会自愈）"
  fi
  sleep 2
done

echo "▶ [3/3] 启动 deepcoffee 栈 (api + frontend) ..."
docker compose up -d "$@"

echo
echo "✅ 全栈已启动："
echo "   前端登录        http://localhost:${WEB_PORT}/auth"
echo "   后端 API        http://localhost:${API_PORT}/v1/health"
echo "   new-api 控制台   http://localhost:${NEW_API_PORT}   (root / deepcoffee2026)"
echo
echo "   demo 账号        demo@deepcoffee.app / DeepCoffee2026!"
