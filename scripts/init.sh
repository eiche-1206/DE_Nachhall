#!/usr/bin/env bash
# 一次性初始化：建表 + 写入种子数据（默认用户、logo! 源、默认订阅）。
#
# 为什么不放进容器启动流程：迁移是有副作用的操作，跟着每次重启跑一遍，
# 早晚会在某次意外重启时执行到一半。所以它是显式的一条命令。
#
# 两步都幂等，重复执行安全。
set -euo pipefail
cd "$(dirname "$0")/.."

[[ -f .env ]] || { echo "没有 .env —— 先 cp .env.example .env 并填好"; exit 1; }

docker compose run --rm api python -m de_nachhall.initdb
