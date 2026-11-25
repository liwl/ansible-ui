#!/usr/bin/env bash
# ============================================================
# 在 WSL (Ubuntu 20.04) 里安装 Docker Engine
# 用法（在 WSL 终端里执行）：
#   bash /mnt/e/Workspace/ansible-ui/wsl-setup-docker.sh
#
# 重复执行是安全的：已安装的部分会自动跳过。
# ============================================================
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "请不要用 root 直接跑，用普通用户执行，脚本内部会用 sudo。"
  exit 1
fi

echo "==> [1/6] 安装基础依赖"
sudo apt-get update -qq
sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release rsync

echo "==> [2/6] 添加 Docker 官方 GPG key 与软件源（阿里云镜像，国内更快）"
sudo install -m 0755 -d /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/docker.gpg ]]; then
  curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
fi

CODENAME="$(. /etc/os-release && echo "${VERSION_CODENAME:-focal}")"
ARCH="$(dpkg --print-architecture)"
echo "deb [arch=${ARCH} signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu ${CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

echo "==> [3/6] 安装 Docker Engine + Compose 插件"
sudo apt-get update -qq
sudo apt-get install -y -qq \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

echo "==> [4/6] 配置镜像加速（构建要拉 node/python 基础镜像，不配大概率拉不动）"
sudo mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
  sudo tee /etc/docker/daemon.json > /dev/null <<'JSON'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run"
  ]
}
JSON
  echo "    已写入 /etc/docker/daemon.json"
else
  echo "    /etc/docker/daemon.json 已存在，跳过（如需加速请手动加 registry-mirrors）"
fi

echo "==> [5/6] 启动 Docker 服务"
# Ubuntu 20.04 的 WSL 默认没有 systemd，只能走 SysV 脚本
if sudo service docker status > /dev/null 2>&1; then
  sudo service docker restart
else
  sudo service docker start || {
    echo "    service 启动失败，改用后台直接拉起 dockerd"
    sudo nohup dockerd > /tmp/dockerd.log 2>&1 &
    sleep 5
  }
fi

if ! sudo docker info > /dev/null 2>&1; then
  echo "!! Docker 没能启动，看日志： sudo tail -50 /var/log/docker.log  或  /tmp/dockerd.log"
  exit 1
fi
echo "    版本： $(sudo docker --version)"

echo "==> [6/6] 把当前用户加入 docker 组（免 sudo）"
if ! id -nG "$USER" | grep -qw docker; then
  sudo usermod -aG docker "$USER"
  echo "    已加入 docker 组，本终端执行 newgrp docker 生效（或重开终端）"
else
  echo "    已在 docker 组中"
fi

echo
echo "============================================================"
echo " 完成。接下来："
echo "   newgrp docker            # 让组权限生效"
echo "   bash /mnt/e/Workspace/ansible-ui/wsl-build.sh"
echo "============================================================"
