#!/usr/bin/env bash
# 跟日志。默认跟 worker（素材处理最需要盯的就是它）。
#   ./scripts/logs.sh          worker
#   ./scripts/logs.sh api      指定服务
#   ./scripts/logs.sh ''       全部
set -euo pipefail
cd "$(dirname "$0")/.."

svc="${1-worker}"
if [[ -z "$svc" ]]; then
  docker compose logs -f --tail 80
else
  docker compose logs -f --tail 80 "$svc"
fi
