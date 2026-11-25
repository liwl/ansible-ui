#!/usr/bin/env bash
# ============================================================
# 在 WSL 里构建 ansible-ui 镜像
# 用法（在 WSL 终端里执行）：
#   bash /mnt/e/Workspace/ansible-ui/wsl-build.sh
#
# 为什么先 rsync 再构建：
#   /mnt/e 是 Windows 盘，Docker 从那里读 context 走 9p 协议，
#   几万个文件的 node_modules 会让构建慢到怀疑人生。
#   先同步到 WSL 内部 ext4 目录（排除 node_modules/.git 等），快一个数量级。
# ============================================================
set -euo pipefail

SRC="/mnt/e/Workspace/ansible-ui"
DST="$HOME/work/ansible-ui"
IMAGE="ansible-ui:dev"

if [[ ! -d "$SRC" ]]; then
  echo "找不到源码目录：$SRC"
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
  "$SRC"/ "$DST"/
echo "    已同步到 $DST"

echo "==> [2/3] 预拉基础镜像（失败时能立刻看出是网络问题，而不是构建问题）"
docker pull node:22-alpine
docker pull python:3.10-slim

echo "==> [3/3] 构建镜像（使用国内镜像源，避免 npm/pip 超时）"
cd "$DST"
docker build \
  -f deploy/Dockerfile \
  --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg DEBIAN_MIRROR=mirrors.aliyun.com \
  -t "$IMAGE" .

echo
echo "============================================================"
echo " 构建完成：$IMAGE"
echo
echo " 本地试跑（Windows 浏览器打开 http://localhost:5001）："
echo "   docker run --rm -p 5001:5000 \\"
echo "     -e ADMIN_USERNAME=admin -e ADMIN_PASSWORD=admin123 \\"
echo "     -e SECRET_KEY=local-test \\"
echo "     $IMAGE"
echo
echo " 或者用 compose（更贴近线上）："
echo "   cd $DST/deploy && cp .env.example .env && ./deploy.sh up"
echo "============================================================"
