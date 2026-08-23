#!/usr/bin/env bash
# 停服务。默认只停不删（下次 up 秒起）；--rm 连容器一起删。
#
# 两种都不动 ./data —— 数据在那儿，删容器不会丢。
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--rm" ]]; then
  docker compose down
  echo "容器已删除。数据仍在 ./data"
else
  docker compose stop
  echo "已停止。./scripts/up.sh 可以起回来；要删容器用 ./scripts/down.sh --rm"
fi
