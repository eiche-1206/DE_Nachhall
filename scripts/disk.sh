#!/usr/bin/env bash
# 看素材占了多少地方，按期列出。
#
# 清理功能本期没做（TASK-045）。要腾地方请用界面删除自行导入的素材 ——
# 那条路会连数据库记录一起清掉。直接 rm 目录会留下指向不存在文件的记录。
set -euo pipefail
cd "$(dirname "$0")/.."

root="${MEDIA_ROOT_HOST:-./data/media}"
[[ -d "$root" ]] || { echo "$root 不存在"; exit 1; }

printf '%-8s %10s  %s\n' 素材 占用 文件
for d in "$root"/*/; do
  [[ -d "$d" ]] || continue
  id=$(basename "$d")
  size=$(du -sh "$d" | cut -f1)
  files=$(ls "$d" | tr '\n' ' ')
  printf '%-8s %10s  %s\n' "$id" "$size" "$files"
done

echo
echo "合计: $(du -sh "$root" | cut -f1)   库: $(du -sh ./data/de_nachhall.db 2>/dev/null | cut -f1)"
echo "参考：一期 8 分钟的 logo! 约 160 MB；每天一期约 1.1 GB/周"
