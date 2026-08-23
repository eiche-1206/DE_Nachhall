#!/usr/bin/env bash
# 把 data/ 的属主改回当前用户。
#
# 为什么会需要：compose 里的服务以 root 跑（没配 user:），它们写出来的
# 库文件和素材目录都归 root。日常使用没影响 —— 读取、备份、界面删除都正常 ——
# 但你想在宿主上手工 rm 一个素材目录时会被拒。
#
# 注意：手工 rm 素材目录会在数据库里留下指向不存在文件的记录，
# 界面上点开只提示「文件不见了」。**推荐用界面删除**，这个脚本是给
# 备份、迁移、排查用的。
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -d data ]] || { echo "没有 data/ —— 还没初始化过？先跑 ./scripts/init.sh"; exit 1; }

echo "把 data/ 改为 $(id -un):$(id -gn) …"
docker run --rm -v "$PWD/data:/data" de_nachhall-api \
  chown -R "$(id -u):$(id -g)" /data

stat -c '%U:%G  %n' data
echo "完成。下次服务写入时新文件仍归 root —— 这个脚本随时可以再跑。"
