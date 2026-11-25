#!/usr/bin/env bash
# ============================================================
# ansible-ui 部署脚本（自包含）
#
# 本目录（deploy/）就是一个完整的构建输入包：
#   app/               后端源码
#   dist/              前端产物
#   requirements.txt   Python 依赖
#   Dockerfile / docker-compose.yml / .env
#   certs/             证书（./deploy.sh cert 生成后才有）
#
# 可以单独拷到任意装了 Docker 的机器上直接：
#   cp .env.example .env && ./deploy.sh up          # HTTP
#   ./deploy.sh cert 192.168.1.10 && ./deploy.sh up # HTTPS（自签证书）
# 不需要项目其余部分，也不需要 Node.js。
#
# HTTPS 由 Flask 自己装载证书实现，不引入 Nginx/Caddy，因此启动时
# 除了 python 基础镜像不额外下载任何镜像。
# ============================================================
set -euo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(cd .. && pwd)"

# ---------- .env 读写 ----------
get_env_var() {
  [ -f .env ] || return 0
  grep -E "^$1=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\r' || true
}

set_env_var() {
  local key="$1" value="$2"
  touch .env
  if grep -qE "^${key}=" .env 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

# 本机第一个非回环 IP，用于打印访问地址 / 生成证书时自动探测
primary_ip() {
  local ip
  ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -vE '^(127\.|$)' | head -1 || true)"
  if [ -z "$ip" ]; then
    # 没有 hostname -I（老系统/精简镜像）时退回路由探测
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)"
  fi
  if [ -z "$ip" ]; then
    ip="$(hostname -i 2>/dev/null | awk '{print $1}' || true)"
  fi
  printf '%s' "$ip"
}

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

# .env 声明了 HTTPS 就必须真的有证书，否则容器里 Flask 会启动失败
# （bind mount 到不存在的文件时 Docker 会建个空目录，报错信息很难懂）
check_tls_ready() {
  local cert key
  cert="$(get_env_var SSL_CERT_FILE)"
  key="$(get_env_var SSL_KEY_FILE)"

  [ -z "$cert" ] && [ -z "$key" ] && return 0

  if [ -z "$cert" ] || [ -z "$key" ]; then
    echo "!! SSL_CERT_FILE / SSL_KEY_FILE 只填了一个，两个都填或都留空。" >&2
    exit 1
  fi

  local hcert="certs/$(basename "$cert")" hkey="certs/$(basename "$key")"
  if [ ! -f "$hcert" ] || [ ! -f "$hkey" ]; then
    echo "!! .env 已开启 HTTPS，但证书文件不存在：" >&2
    echo "     $hcert" >&2
    echo "     $hkey" >&2
    echo "   生成证书： ./deploy.sh cert <服务器IP或域名>" >&2
    echo "   改回 HTTP： ./deploy.sh http" >&2
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

print_url() {
  local port scheme host
  port="$(get_env_var HOST_PORT)"; port="${port:-5000}"
  if [ -n "$(get_env_var SSL_CERT_FILE)" ]; then scheme=https; else scheme=http; fi
  host="$(primary_ip)"

  echo ""
  echo "启动完成。"
  if [ "$scheme" = https ] && [ "$port" = 443 ]; then
    echo "  访问： https://${host:-<服务器IP>}"
  else
    echo "  访问： ${scheme}://${host:-<服务器IP>}:${port}"
  fi
  if [ "$scheme" = https ]; then
    echo "  自签证书：浏览器首次会提示不安全，点「继续访问」即可；"
    echo "            终端 WebSocket 走 wss://，不受证书警告影响。"
  fi
}

# ---------- 证书 ----------
# 生成自签证书（openssl 配置通过临时文件传，兼容 OpenSSL 1.0.2 没有 -addext 的老系统）
gen_cert() {
  local names=("$@")
  if [ ${#names[@]} -eq 0 ] || [ -z "${names[0]}" ]; then
    local ip; ip="$(primary_ip)"
    names=("${ip:-localhost}")
    echo "==> 未指定域名/IP，自动使用：${names[*]}"
    echo "    如需指定： ./deploy.sh cert 192.168.1.10 或 ./deploy.sh cert ansible.example.com"
  fi

  if ! command -v openssl >/dev/null 2>&1; then
    echo "错误：未找到 openssl，请先安装（yum install openssl / apt install openssl）。" >&2
    exit 1
  fi

  # SAN 必须覆盖实际访问用的地址，否则浏览器/客户端会报「证书不匹配」
  local san="DNS:localhost,IP:127.0.0.1" primary="${names[0]}" n
  local extra_ip; extra_ip="$(primary_ip)"
  if [ -n "$extra_ip" ]; then
    [[ "$san" == *"IP:$extra_ip"* ]] || san="$san,IP:$extra_ip"
  fi
  for n in "${names[@]}"; do
    if [[ "$n" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
      [[ "$san" == *"IP:$n"* ]] || san="$san,IP:$n"
    else
      [[ "$san" == *"DNS:$n"* ]] || san="$san,DNS:$n"
    fi
  done

  local tmpconf; tmpconf="$(mktemp)"
  cat > "$tmpconf" <<EOF
[req]
distinguished_name = dn
x509_extensions = v3
prompt = no
[dn]
CN = ${primary}
O = ansible-ui
[v3]
subjectAltName = ${san}
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
EOF

  mkdir -p certs
  # 已有证书先备份：避免误把正式证书（Let's Encrypt 等）覆盖成自签
  if [ -f certs/server.crt ] || [ -f certs/server.key ]; then
    local ts; ts="$(date +%Y%m%d%H%M%S)"
    [ -f certs/server.crt ] && cp certs/server.crt "certs/server.crt.${ts}.bak"
    [ -f certs/server.key ] && cp certs/server.key "certs/server.key.${ts}.bak"
    echo "==> 检测到已有证书，已备份为 certs/*.${ts}.bak"
  fi

  echo "==> 生成自签证书（RSA 2048 / 10 年）"
  openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -config "$tmpconf" -keyout certs/server.key -out certs/server.crt 2>/dev/null
  rm -f "$tmpconf"
  chmod 600 certs/server.key
  chmod 644 certs/server.crt

  ensure_env
  set_env_var SSL_CERT_FILE /app/certs/server.crt
  set_env_var SSL_KEY_FILE /app/certs/server.key

  local port; port="$(get_env_var HOST_PORT)"
  if [ "$port" != "443" ]; then
    set_env_var HOST_PORT 443
    echo "==> 已把 HOST_PORT 改为 443（原来的 ${port:-5000}）"
  fi
  if command -v ss >/dev/null 2>&1 && ss -lnt 2>/dev/null | grep -q ':443 '; then
    echo "    ⚠ 443 端口已被其他程序占用，请改用别的 HOST_PORT（如 8443）再启动。" >&2
  fi

  local host; host="$(primary_ip)"
  echo ""
  echo "证书已就绪："
  echo "  certs/server.crt   （公钥，有效期 10 年）"
  echo "  certs/server.key   （私钥，权限 600，不要外传）"
  echo "  覆盖地址： ${san}"
  echo "  .env 已自动配置，执行 ./deploy.sh up 即以 HTTPS 启动"
  echo "  访问： https://${host:-<服务器IP>}"
  echo ""
  echo "  换成正式证书：把 fullchain.pem 存为 certs/server.crt、"
  echo "                privkey.pem 存为 certs/server.key，重启容器即可，配置不用改。"
}

# 关掉 HTTPS，回到明文 HTTP
disable_tls() {
  ensure_env
  local port; port="$(get_env_var HOST_PORT)"
  if [ -n "$(get_env_var SSL_CERT_FILE)" ]; then
    set_env_var SSL_CERT_FILE ""
    set_env_var SSL_KEY_FILE ""
    echo "==> 已清空 SSL_CERT_FILE / SSL_KEY_FILE，回到 HTTP 模式"
  else
    echo "==> 当前本来就是 HTTP 模式"
  fi
  if [ "$port" = "443" ]; then
    set_env_var HOST_PORT 5000
    echo "==> HOST_PORT 已改回 5000"
  fi
  echo "    证书文件保留在 certs/，想恢复执行： ./deploy.sh cert <IP>"
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
  echo "用法: $0 {up|cert|http|build|sync|frontend|down|restart|logs|status|config}"
  echo ""
  echo "  up          构建镜像并启动（端口/协议由 .env 决定）"
  echo "  cert [名称…] 生成自签证书并自动开启 HTTPS，可给多个域名/IP"
  echo "              例： $0 cert 192.168.1.10"
  echo "                   $0 cert ansible.example.com 192.168.1.10"
  echo "  http        关闭 HTTPS，回到明文 HTTP"
  echo "  build       仅构建镜像，不启动"
  echo "  sync        从项目根同步后端源码到 deploy/app（开发机用）"
  echo "  frontend    本地构建前端并同步到 deploy/dist（需要 Node.js）"
  echo "  down        停止并移除容器（保留数据卷与证书）"
  echo "  restart     重启容器（不重新构建，换证书后用这个）"
  echo "  logs        实时查看日志"
  echo "  status      查看容器状态"
  echo "  config      检查 compose 配置"
}

case "${1:-up}" in
  up)
    require_docker
    ensure_env
    check_inputs
    check_tls_ready
    warn_stale_backend
    docker compose up -d --build
    print_url
    ;;
  cert)
    shift
    gen_cert "$@"
    ;;
  http)
    disable_tls
    ;;
  build)
    require_docker
    ensure_env
    check_inputs
    check_tls_ready
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
    docker compose down
    ;;
  restart)
    require_docker
    check_tls_ready
    docker compose restart
    echo "已重启，若刚替换了证书，新的证书已生效。"
    ;;
  logs)
    require_docker
    docker compose logs -f
    ;;
  status)
    require_docker
    docker compose ps
    print_url
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
