#!/bin/bash
# 启动 Deep Coffee 知识库（端口 8733）
# 用法：bash serve.sh

PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJ_DIR/.venv/bin/mkdocs"
PORT=8733

if [ ! -f "$VENV" ]; then
  echo "venv 不存在，正在安装依赖..."
  python3 -m venv "$PROJ_DIR/.venv"
  "$PROJ_DIR/.venv/bin/pip" install mkdocs mkdocs-material mkdocs-roamlinks-plugin -q
fi

echo "知识库启动中：http://127.0.0.1:$PORT"
cd "$PROJ_DIR" && "$VENV" serve --dev-addr "127.0.0.1:$PORT"
