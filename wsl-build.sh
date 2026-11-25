#!/usr/bin/env bash
# ============================================================
# 在 WSL 里构建 ansible-ui 镜像
# 用法（在 WSL 终端里执行）：
#   bash /mnt/e/Workspace/ansible-ui/wsl-build.sh
#
# 前提：deploy/dist 里已有前端产物（在 Windows 上执行过）
#       cd deploy && bash deploy.sh frontend
#
# 构建上下文是 deploy 目录（几 MB），不含 node_modules，
# 所以不需要在 Docker 里跑 node，速度快很多。
# ============================================================
set -euo pipefail

SRC="/mnt/e/Workspace/ansible-ui"
DST="$HOME/work/ansible-ui"

if [[ ! -d "$SRC" ]]; then
  echo "找不到源码目录：$SRC"
  exit 1
fi

if [[ ! -d "$SRC/deploy/dist" ]]; then
  echo "缺少前端产物 deploy/dist。"
  echo "请先在 Windows 上执行：cd E:\\Workspace\\ansible-ui\\deploy && bash deploy.sh frontend"
  exit 1
fi

echo "==> [1/3] 同步源码到 WSL 内部目录（排除 node_modules / .git / 运行期数据）"
mkdir -p "$DST"
rsync -a --delete \
  --exclude 'node_modules' \
  --exclude 'dist' \
  --exclude '.git' \
  --exclude '.workbuddy' \
  --exclude 'db' \
  --exclude 'logs' \
  --exclude 'data' \
  --exclude '__pycache__' \
  --exclude 'deploy/context' \
  --exclude 'deploy/.env' \
  "$SRC"/ "$DST"/
# deploy/dist 单独同步（上面的 --exclude 'dist' 会把 web/dist 和 deploy/dist 都排除）
rsync -a --delete "$SRC/deploy/dist/" "$DST/deploy/dist/"
echo "    已同步到 $DST"

cd "$DST/deploy"

echo "==> [2/3] 组装构建上下文"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    已从 .env.example 生成 .env（仅本地测试用）"
fi
bash deploy.sh prepare

echo "==> [3/3] 构建镜像"
docker compose build

echo
echo "============================================================"
echo " 构建完成：ansible-ui:latest"
echo
echo " 本地试跑（Windows 浏览器打开 http://localhost:5001）："
echo "   docker run --rm -p 5001:5000 \\"
echo "     -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD=admin123 \\"
echo "     -e SECRET_KEY=local-test \\"
echo "     ansible-ui:latest"
echo
echo " 或者用 compose（更贴近线上）："
echo "   cd $DST/deploy && ./deploy.sh up"
echo "============================================================"
