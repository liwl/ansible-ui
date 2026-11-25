# ============================================================
# 运行时镜像：只负责打包，不做任何编译
#
# 前端产物（dist）和 Python 源码都在「外部」准备好，
# docker build 只做三件事：装 Python 依赖、拷贝源码、拷贝静态资源。
#
# 构建上下文 = deploy 目录（不是项目根），所以不会把
# web/node_modules 那 210MB 传进 Docker daemon。
#
# 标准流程：
#   ./deploy.sh frontend    # 本地构建前端 → deploy/dist（需要 node）
#   ./deploy.sh up          # 组装 context → 构建镜像 → 启动
# ============================================================
FROM python:3.10-slim

# 可覆盖的 pip / Debian 源，国内用镜像源否则装 ansible+cryptography 极易超时
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

COPY context/requirements.txt ./
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# 后端源码
COPY context/app/ ./

# 前端已构建产物 + 静态文件（robots.txt 等）
COPY context/public/ ./public/

# 运行时目录由 compose 的 volume 接管，这里先建好空目录
RUN mkdir -p db logs data /tmp/ansible_uploads

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-5000}/" >/dev/null 2>&1 || exit 1'

CMD ["python", "app.py"]
