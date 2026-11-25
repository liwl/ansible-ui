#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
DEPLOY_DIR="$(pwd)"
PROJECT_ROOT="$(cd .. && pwd)"

# ---------- 工具函数 ----------
require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "错误：未找到 docker 命令，请先安装 Docker。" >&2
    exit 1
  fi
  if ! docker compose version >/dev/null 2>&1; then
    echo "错误：当前 docker 不支持 'docker compose'，请升级到 Docker Compose v2。" >&2
    exit 1
  fi
}

ensure_env() {
  if [ ! -f .env ]; then
    cp .env.example .env
    echo "已生成 deploy/.env，请先修改 ADMIN_PASSWORD 和 SECRET_KEY 再启动。"
    exit 0
  fi
}

# 组装构建上下文：deploy/context/
#   context/app/       后端 *.py
#   context/public/    前端 dist + robots.txt 等静态文件
#   context/requirements.txt
# 这一步在「外部」完成，Dockerfile 里不再有任何构建动作。
prepare() {
  echo "==> 组装构建上下文 deploy/context"
  rm -rf context
  mkdir -p context/app context/public

  cp "$PROJECT_ROOT"/*.py context/app/
  cp "$PROJECT_ROOT/requirements.txt" context/

  if [ -d dist ] && [ -n "$(ls -A dist 2>/dev/null)" ]; then
    cp -r dist/. context/public/
    echo "    前端产物：deploy/dist"
  elif [ -d "$PROJECT_ROOT/web/dist" ] && [ -n "$(ls -A "$PROJECT_ROOT/web/dist" 2>/dev/null)" ]; then
    cp -r "$PROJECT_ROOT/web/dist/." context/public/
    echo "    前端产物：web/dist（建议先执行 $0 frontend 固定到 deploy/dist）"
  else
    echo "!! 找不到前端产物。请在有 node 的机器上先执行： $0 frontend" >&2
    exit 1
  fi

  for f in robots.txt vite.svg favicon.ico; do
    if [ -f "$PROJECT_ROOT/public/$f" ]; then
      cp "$PROJECT_ROOT/public/$f" context/public/
    fi
  done

  echo "    后端文件：$(ls context/app | wc -l | tr -d ' ') 个 .py"
  echo "    静态文件：$(find context/public -type f | wc -l | tr -d ' ') 个"
}

# 本地构建前端并固化成 deploy/dist（之后服务器上就不需要 node）
frontend() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "错误：未找到 npm，前端构建需要 Node.js。" >&2
    exit 1
  fi
  echo "==> 构建前端（$PROJECT_ROOT/web）"
  ( cd "$PROJECT_ROOT/web" && npm run build )
  rm -rf dist && mkdir -p dist
  cp -r "$PROJECT_ROOT/web/dist/." dist/
  echo "==> 已同步到 deploy/dist（$(du -sh dist | cut -f1)）"
  echo "    请提交到 git，这样服务器拉下来直接能构建，不用装 node"
}

usage() {
  echo "用法: $0 {up|build|frontend|prepare|down|restart|logs|status|config}"
  echo ""
  echo "  up        组装上下文 + 构建镜像 + 后台启动（默认）"
  echo "  build     组装上下文 + 仅构建镜像"
  echo "  frontend  本地构建前端并同步到 deploy/dist（需要 node）"
  echo "  prepare   只组装构建上下文，不构建镜像"
  echo "  down      停止并移除容器（保留数据卷）"
  echo "  restart   重启容器"
  echo "  logs      实时查看日志"
  echo "  status    查看容器状态"
  echo "  config    检查 compose 配置"
}

case "${1:-up}" in
  up)
    require_docker
    ensure_env
    prepare
    docker compose up -d --build
    echo "启动完成，访问 http://localhost:$(grep '^HOST_PORT=' .env | cut -d= -f2 | tr -d '\r')"
    ;;
  build)
    require_docker
    ensure_env
    prepare
    docker compose build
    ;;
  frontend)
    frontend
    ;;
  prepare)
    prepare
    ;;
  down)
    require_docker
    docker compose down
    ;;
  restart)
    require_docker
    docker compose restart
    ;;
  logs)
    require_docker
    docker compose logs -f ansible-ui
    ;;
  status)
    require_docker
    docker compose ps
    ;;
  config)
    require_docker
    docker compose config
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "未知命令: $1" >&2
    usage
    exit 1
    ;;
esac
