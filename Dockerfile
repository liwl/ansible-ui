# ============================================================
# 【废弃文件，请勿使用】
#
# 本文件是早期版本，基础镜像为 python:3.12-alpine，
# 而 ansible-core 2.13（ansible 6.7）在 3.12 / musl 上无法正常工作，
# 用它构建出来的镜像启动即报错。
#
# 正确的构建入口只有一个：deploy/Dockerfile（由 deploy/docker-compose.yml 引用）
#
#   cd deploy
#   cp .env.example .env      # 修改 ADMIN_PASSWORD 和 SECRET_KEY
#   ./deploy.sh up
#
# 保留此文件只是为了让误用 `docker build .` 的人立刻看到明确报错，
# 而不是花半小时构建出一个跑不起来的镜像。
# ============================================================
FROM alpine:3.20

RUN echo "" >&2 \
 && echo "==============================================" >&2 \
 && echo " 构建入口错误：请勿使用根目录的 Dockerfile" >&2 \
 && echo "" >&2 \
 && echo " 正确做法：" >&2 \
 && echo "   cd deploy && cp .env.example .env && ./deploy.sh up" >&2 \
 && echo "==============================================" >&2 \
 && exit 1
