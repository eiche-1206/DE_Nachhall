#!/usr/bin/env bash
# 从命令行导入一期素材。等价于界面右上角的 ＋。
#
#   ./scripts/import.sh https://www.logo.de/logo-vom-freitag-21-august-2026-100.html
#
# probe 是同步的，所以这条命令会卡 1–3 秒然后回显标题与时长 ——
# 那正是确认链接贴对没有的时机。之后处理在 worker 里进行，用 logs.sh 看进度。
set -euo pipefail
cd "$(dirname "$0")/.."

url="${1-}"
[[ -n "$url" ]] || { echo "用法: $0 <视频链接>"; exit 1; }

api="${API:-http://localhost:8001}"
resp=$(curl -sS -X POST "$api/api/media" \
  -H 'Content-Type: application/json' \
  -d "{\"url\": $(printf '%s' "$url" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}")

python3 - "$resp" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1])
except json.JSONDecodeError:
    print("服务没返回 JSON，检查 api 是否在跑：", sys.argv[1][:200]); raise SystemExit(1)

if "error" in d:
    print(f"[{d['error']['code']}] {d['error']['message']}"); raise SystemExit(1)

mins, secs = divmod(round((d.get("duration_ms") or 0) / 1000), 60)
print(f"media {d['media_id']}  {d['title']}  {mins}:{secs:02d}  [{d.get('platform') or '?'}]")
print("这一期之前就导过，不会重复转写。" if d.get("already_exists")
      else "已加入队列。./scripts/logs.sh 看处理进度。")
PY
