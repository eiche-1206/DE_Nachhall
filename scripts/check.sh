#!/usr/bin/env bash
# 全量检查：后端 ruff + mypy + pytest，前端 tsc + eslint。
#
# 后端的检查工具不在运行镜像里（api 镜像刻意保持轻量），用 de_nachhall-dev。
# 没有就自动建一个。
set -euo pipefail
cd "$(dirname "$0")/.."

# 基于 compose 建出来的 api 镜像，不依赖任何手工 docker build 的产物
BASE=de_nachhall-api
if ! docker image inspect "$BASE" >/dev/null 2>&1; then
  echo "== 构建 api 镜像 =="
  docker compose build api
fi

if ! docker image inspect de_nachhall-dev >/dev/null 2>&1; then
  echo "== 构建 de_nachhall-dev（首次；检查工具不装进运行镜像，那个刻意保持轻量）=="
  docker build --network host \
    --build-arg HTTPS_PROXY="${HTTPS_PROXY:-}" --build-arg HTTP_PROXY="${HTTP_PROXY:-}" \
    -t de_nachhall-dev - <<DOCKERFILE
FROM $BASE
RUN pip install --no-cache-dir "pytest>=8" pytest-asyncio "ruff>=0.8" "black>=24" "mypy>=1.13"
DOCKERFILE
fi

echo "== 后端 =="
# --user 不能省：不带它容器会在 server/ 里留下 root 拥有的缓存目录
docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -v "$PWD/server:/app" -w /app de_nachhall-dev \
  sh -c "ruff check src tests && mypy && python -m pytest -q"

echo
echo "== 前端 =="
docker compose exec -T web sh -c "npx tsc --noEmit && npx eslint src --ext .ts,.tsx --max-warnings 0"
echo "tsc ✓  eslint ✓"
