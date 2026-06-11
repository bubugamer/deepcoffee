#!/usr/bin/env bash
# 生成初始化邀请码并写入 deepcoffee-api/.env（DEEPCOFFEE_BOOTSTRAP_INVITE_CODE）。
# 部署时执行一次；启动后用该码注册的首个用户自动成为管理员（仅当系统尚无 admin）。
set -euo pipefail

ENV_FILE="$(cd "$(dirname "$0")/.." && pwd)/deepcoffee-api/.env"

# 与后端邀请码同款字母表（去易混淆字符），格式 DC-XXXX-XXXX
# 注意：不能 `tr </dev/urandom | head`——head 关管道会让 tr 吃 SIGPIPE，
# 在 set -o pipefail 下整个脚本静默失败；改为先读定长随机字节再过滤。
ALPHABET="ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
body=""
while [[ ${#body} -lt 8 ]]; do
  chunk="$(head -c 64 /dev/urandom | LC_ALL=C tr -dc "$ALPHABET")"
  body="${body}${chunk}"
done
body="${body:0:8}"
code="DC-${body:0:4}-${body:4:4}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE 不存在，请先从 .env.example 创建" >&2
  exit 1
fi

if grep -q '^DEEPCOFFEE_BOOTSTRAP_INVITE_CODE=' "$ENV_FILE"; then
  # macOS / GNU sed 兼容写法：写临时文件再覆盖
  tmp="$(mktemp)"
  sed "s/^DEEPCOFFEE_BOOTSTRAP_INVITE_CODE=.*/DEEPCOFFEE_BOOTSTRAP_INVITE_CODE=$code/" "$ENV_FILE" >"$tmp"
  mv "$tmp" "$ENV_FILE"
else
  printf '\nDEEPCOFFEE_BOOTSTRAP_INVITE_CODE=%s\n' "$code" >>"$ENV_FILE"
fi

echo "已写入 $ENV_FILE"
echo "初始化邀请码: $code"
echo "用它在注册页完成注册的首个用户将自动成为管理员。"
