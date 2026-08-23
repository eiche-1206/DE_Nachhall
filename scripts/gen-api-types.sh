#!/usr/bin/env bash
# 改了后端接口之后重新生成前端类型。
#
# 前端的 API 类型**全部**来自这份生成文件，手写一份等于给自己留一个
# 和后端悄悄漂移的机会。
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose up -d api >/dev/null
for _ in $(seq 1 20); do curl -sf localhost:8001/api/health >/dev/null && break; sleep 0.5; done

docker compose exec -T web npm run gen:api
echo "已重写 web/src/lib/api.types.ts"
