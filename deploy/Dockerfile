# ---------- 阶段 1：构建前端 ----------
FROM node:22-alpine AS frontend

WORKDIR /build

# 可覆盖的 npm 源：国内构建时传 --build-arg NPM_REGISTRY=https://registry.npmmirror.com
# 不传就用官方源，海外环境不受影响。
ARG NPM_REGISTRY=https://registry.npmjs.org

# 先复制依赖清单，利用 Docker 层缓存
COPY web/package.json web/pnpm-lock.yaml ./
RUN npm config set registry "$NPM_REGISTRY" \
    && npm install -g pnpm@12 \
    && pnpm config set registry "$NPM_REGISTRY" \
    && pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm run build

# ---------- 阶段 2：运行后端 ----------
# 用 3.10 而不是 3.11/3.12：ansible-core 2.13（ansible 6.7）官方只支持到 Python 3.10，
# 3.11+ 上出现过 collections / inspect 相关的兼容问题，用 3.10 最稳。
# 用 slim 而不是 alpine：ansible-core 2.13 对 musl 支持不佳，Debian 兼容性更好。
FROM python:3.10-slim

# 可覆盖的 pip 源与 Debian 源：国内构建时传
#   --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
#   --build-arg DEBIAN_MIRROR=mirrors.aliyun.com
# pip 装 ansible + cryptography 有大包，用官方源在国内基本会超时。
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG DEBIAN_MIRROR=deb.debian.org

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    ANSIBLE_HOST_KEY_CHECKING=False

WORKDIR /app

# openssh-client：ansible 依赖；sshpass：密码认证；curl：健康检查
RUN set -eux; \
    if [ "$DEBIAN_MIRROR" != "deb.debian.org" ]; then \
        sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources 2>/dev/null \
        || sed -i "s|deb.debian.org|${DEBIAN_MIRROR}|g" /etc/apt/sources.list; \
    fi; \
    apt-get update && apt-get install -y --no-install-recommends \
        openssh-client \
        sshpass \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# 先复制静态资源目录（保留 robots.txt），再用构建产物覆盖
COPY public/ ./public/
COPY --from=frontend /build/dist ./public/

COPY *.py ./

# 运行时目录由 compose 的 volume 接管，这里先建好空目录
RUN mkdir -p db logs data /tmp/ansible_uploads

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-5000}/" >/dev/null 2>&1 || exit 1'

CMD ["python", "app.py"]
