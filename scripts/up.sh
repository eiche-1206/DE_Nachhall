#!/usr/bin/env bash
# 起服务。不带参数起全部；`./scripts/up.sh api web` 只起指定的。
#
# 首次使用要先跑 ./scripts/init.sh 建表，否则界面会提示「连不上服务」。
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d "$@"
echo
docker compose ps --format "table {{.Service}}\t{{.Status}}\t{{.Ports}}"
echo
echo "界面  http://localhost:8000"
echo "API   http://localhost:8001/api/health"
