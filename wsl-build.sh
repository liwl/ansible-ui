#!/usr/bin/env bash
# ============================================================
# 在 WSL 里构建 ansible-ui 镜像
# 用法（在 WSL 终端里执行）：
#   bash /mnt/e/Workspace/ansible-ui/wsl-build.sh
#
# 前提：deploy/app 和 deploy/dist 已就绪
#   在 Windows 上先执行：
#     cd deploy && ./deploy.sh sync frontend
#
# 构建上下文就是 deploy 目录（几 MB），不需要 Node.js。
# ============================================================
set -euo pipefail

SRC="/mnt/e/Workspace/ansible-ui"
DST="$HOME/work/ansible-ui"

if [[ ! -d "$SRC" ]]; then
  echo "找不到源码目录：$SRC"
  exit 1
fi

if [[ ! -f "$SRC/deploy/dist/index.html" ]]; then
  echo "缺少前端产物 deploy/dist。"
  echo "请先在 Windows 上执行：cd E:\\Workspace\\ansible-ui\\deploy && ./deploy.sh frontend"
  exit 1
fi

if [[ ! -f "$SRC/deploy/app/app.py" ]]; then
  echo "缺少后端源码 deploy/app。"
  echo "请先在 Windows 上执行：cd E:\\Workspace\\ansible-ui\\deploy && ./deploy.sh sync"
  exit 1
fi

echo "==> [1/2] 同步项目到 WSL 内部目录（排除 node_modules 与运行期数据）"
mkdir -p "$DST"
rsync -a --delete \
  --exclude 'web/node_modules' \
  --exclude 'web/dist' \
  --exclude '.git' \
  --exclude '.workbuddy' \
  --exclude 'db' \
  --exclude 'logs' \
  --exclude 'data' \
  --exclude '__pycache__' \
  --exclude 'deploy/.env' \
  "$SRC"/ "$DST"/
echo "    已同步到 $DST"

cd "$DST/deploy"

echo "==> [2/2] 构建镜像"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    已从 .env.example 生成 .env（仅本地测试用）"
fi
./deploy.sh build

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
