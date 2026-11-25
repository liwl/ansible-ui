#!/usr/bin/env bash
# ============================================================
# ansible-ui 部署脚本（自包含）
#
# 本目录（deploy/）就是一个完整的构建输入包：
#   app/               后端源码
#   dist/              前端产物
#   requirements.txt   Python 依赖
#   Dockerfile / docker-compose*.yml / .env
#
# 可以单独拷到任意装了 Docker 的机器上直接：
#   cp .env.example .env && ./deploy.sh up
# 不需要项目其余部分，也不需要 Node.js。
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(cd .. && pwd)"

HTTPS_FILES="-f docker-compose.yml -f docker-compose.https.yml"

# ---------- 基础检查 ----------
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

# 构建前确认输入齐全（缺了要给出明确的补救办法，而不是让 docker 报天书）
check_inputs() {
  if [ ! -d app ] || [ -z "$(ls -A app 2>/dev/null)" ]; then
    echo "!! deploy/app 为空，缺少后端源码。" >&2
    echo "   在完整项目里执行： ./deploy.sh sync" >&2
    echo "   或者手动把根目录的 *.py 放进 deploy/app/" >&2
    exit 1
  fi
  if [ ! -f dist/index.html ]; then
    echo "!! deploy/dist 缺少前端产物。" >&2
    echo "   在有 Node.js 的机器上执行： ./deploy.sh frontend" >&2
    exit 1
  fi
}

require_site_address() {
  if ! grep -qE '^SITE_ADDRESS=.+' .env 2>/dev/null; then
    echo "!! 请先在 deploy/.env 中设置 SITE_ADDRESS：" >&2
    echo "   SITE_ADDRESS=ansible.example.com   # 公网域名，Caddy 自动申请证书" >&2
    echo "   SITE_ADDRESS=192.168.1.10          # 内网 IP，需改用 Caddyfile.internal（自签）" >&2
    exit 1
  fi
}

# 开发时提醒：根目录源码比 deploy/app 新，说明忘了 sync
warn_stale_backend() {
  if [ -f "$PROJECT_ROOT/app.py" ] && [ -f app/app.py ]; then
    local newer
    newer="$(find "$PROJECT_ROOT" -maxdepth 1 -name '*.py' -newer app/app.py 2>/dev/null | head -1 || true)"
    if [ -n "$newer" ]; then
      echo "    ⚠ 项目根的 $(basename "$newer") 比 deploy/app 新，建议先执行： ./deploy.sh sync"
    fi
  fi
}

# down/logs/status 需要覆盖到 caddy，但 .env 没配 SITE_ADDRESS 时
# compose 会因为 ${SITE_ADDRESS:?...} 直接报错，这里给个无用兜底值
compose_all() {
  SITE_ADDRESS="${SITE_ADDRESS:-unused.local}" \
    docker compose -f docker-compose.yml -f docker-compose.https.yml "$@"
}

# ---------- 子命令 ----------
# 从项目根同步后端源码到 deploy/app（开发者用，服务器上不需要）
sync_sources() {
  if [ ! -f "$PROJECT_ROOT/requirements.txt" ]; then
    echo "找不到项目根（$PROJECT_ROOT）的 requirements.txt，无法同步。" >&2
    echo "只上传 deploy 目录时不需要同步：deploy/app 已是自带副本。" >&2
    exit 1
  fi
  echo "==> 同步后端源码 → deploy/app"
  rm -rf app && mkdir -p app
  cp "$PROJECT_ROOT"/*.py app/
  cp "$PROJECT_ROOT/requirements.txt" ./
  echo "    已同步 $(ls app | wc -l | tr -d ' ') 个 .py"

  for f in robots.txt vite.svg favicon.ico; do
    if [ -f "$PROJECT_ROOT/public/$f" ]; then
      mkdir -p dist && cp "$PROJECT_ROOT/public/$f" dist/
    fi
  done
  echo "==> 完成。提交后服务器上就能直接用： git add deploy/ && git commit"
}

# 本地构建前端并固化到 deploy/dist（需要 Node.js）
frontend() {
  if ! command -v npm >/dev/null 2>&1; then
    echo "错误：未找到 npm，前端构建需要 Node.js。" >&2
    exit 1
  fi
  if [ ! -d "$PROJECT_ROOT/web" ]; then
    echo "错误：找不到 $PROJECT_ROOT/web，前端构建需要在完整项目里执行。" >&2
    exit 1
  fi
  echo "==> 构建前端（$PROJECT_ROOT/web）"
  ( cd "$PROJECT_ROOT/web" && npm run build )

  rm -rf dist && mkdir -p dist
  cp -r "$PROJECT_ROOT/web/dist/." dist/
  for f in robots.txt vite.svg favicon.ico; do
    if [ -f "$PROJECT_ROOT/public/$f" ]; then
      cp "$PROJECT_ROOT/public/$f" dist/
    fi
  done
  echo "==> 已同步到 deploy/dist（$(du -sh dist | cut -f1)）"
  echo "    记得提交： git add deploy/dist && git commit -m 'build: 更新前端产物'"
}

usage() {
  echo "用法: $0 {up|https|build|sync|frontend|down|https-down|restart|logs|status|config}"
  echo ""
  echo "  up          构建镜像并以 HTTP 启动（默认，直接暴露 5000）"
  echo "  https       构建镜像并以 HTTPS 启动（Caddy 反代 + 自动证书）"
  echo "  build       仅构建镜像，不启动"
  echo "  sync        从项目根同步后端源码到 deploy/app（开发机用）"
  echo "  frontend    本地构建前端并同步到 deploy/dist（需要 Node.js）"
  echo "  down        停止并移除容器（保留数据卷与证书）"
  echo "  https-down  同上，显式指定 HTTPS 组合"
  echo "  restart     重启容器（不重新构建）"
  echo "  logs        实时查看日志"
  echo "  status      查看容器状态"
  echo "  config      检查 compose 配置"
}

case "${1:-up}" in
  up)
    require_docker
    ensure_env
    check_inputs
    warn_stale_backend
    docker compose up -d --build
    echo "启动完成，访问 http://localhost:$(grep '^HOST_PORT=' .env | cut -d= -f2 | tr -d '\r')"
    ;;
  https)
    require_docker
    ensure_env
    check_inputs
    require_site_address
    warn_stale_backend
    # HOST_BIND=127.0.0.1：后端端口只绑本机，外部只能经 Caddy 的 443 访问，
    # 避免有人绕过 HTTPS 直接打 5000 明文端口
    HOST_BIND=127.0.0.1 docker compose $HTTPS_FILES up -d --build
    site="$(grep '^SITE_ADDRESS=' .env | cut -d= -f2- | tr -d '\r' | sed 's|^https\?://||')"
    echo "启动完成，访问 https://${site}"
    echo "首次签发证书需要几十秒，可用 ./deploy.sh logs 观察进度"
    ;;
  build)
    require_docker
    ensure_env
    check_inputs
    warn_stale_backend
    docker compose build
    ;;
  sync)
    sync_sources
    ;;
  frontend)
    frontend
    ;;
  down)
    require_docker
    compose_all down
    ;;
  https-down)
    require_docker
    compose_all down
    ;;
  restart)
    require_docker
    compose_all restart
    ;;
  logs)
    require_docker
    compose_all logs -f
    ;;
  status)
    require_docker
    compose_all ps
    ;;
  config)
    require_docker
    compose_all config
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
