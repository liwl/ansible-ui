# ============================================================
# 运行时镜像：只负责打包，不做任何编译
#
# 构建上下文 = 当前 deploy 目录，里面自带全部构建输入：
#   src/ansible_ui/    后端源码（deploy.sh sync 从项目根 src/ 同步）
#   dist/              前端产物（deploy.sh frontend 生成）
#   requirements.txt   Python 依赖（deploy.sh sync 复制）
#
# 因此这个目录可以单独拷到任意一台装了 Docker 的机器上构建，
# 不需要项目其余部分，也不需要 Node.js。
#
# 用法：
#   docker compose up -d --build      （或 ./deploy.sh up）
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
        tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

# 后端源码（src/ 下只有 ansible_ui 包，复制后落在 /app/ansible_ui）
COPY src/ ./

# 前端已构建产物 + 静态文件（robots.txt 等）
COPY dist/ ./public/

# 运行时目录由 compose 的 volume 接管，这里先建好空目录
# certs/ 是证书挂载点：宿主机 deploy/certs 只读挂到这里，换证书不必重建镜像
RUN mkdir -p db logs data certs /tmp/ansible_uploads

EXPOSE 5000

# HTTPS 模式下 SSL_CERT_FILE 非空，健康检查自动切到 https（-k 容忍自签证书）
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD sh -c 'if [ -n "$SSL_CERT_FILE" ]; then curl -fkS "https://127.0.0.1:${PORT:-5000}/" -o /dev/null || exit 1; else curl -fsS "http://127.0.0.1:${PORT:-5000}/" -o /dev/null || exit 1; fi'

CMD ["python", "-m", "ansible_ui"]
