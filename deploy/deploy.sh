#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if ! command -v docker >/dev/null 2>&1; then
  echo "错误：未找到 docker 命令，请先安装 Docker。" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "错误：当前 docker 不支持 'docker compose'，请升级到 Docker Compose v2。" >&2
  exit 1
fi

# 首次运行自动生成 .env
if [ ! -f .env ]; then
  cp .env.example .env
  echo "已生成 deploy/.env，请先修改 ADMIN_PASSWORD 和 SECRET_KEY 再启动。"
  exit 0
fi

usage() {
  echo "用法: $0 {up|down|restart|logs|status|build|config}"
  echo ""
  echo "  up       构建并后台启动（默认）"
  echo "  down     停止并移除容器（保留数据卷）"
  echo "  restart  重启容器"
  echo "  logs     实时查看日志"
  echo "  status   查看容器状态"
  echo "  build    仅重新构建镜像"
  echo "  config   检查 compose 配置"
}

case "${1:-up}" in
  up)
    docker compose up -d --build
    echo "启动完成，访问 http://localhost:$(grep '^HOST_PORT=' .env | cut -d= -f2 | tr -d '\r')"
    ;;
  down)
    docker compose down
    ;;
  restart)
    docker compose restart
    ;;
  logs)
    docker compose logs -f ansible-ui
    ;;
  status)
    docker compose ps
    ;;
  build)
    docker compose build
    ;;
  config)
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
