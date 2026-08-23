# 本机开发

## 起停

日常操作都在 `scripts/`，见 [scripts/README.md](../scripts/README.md)：

```bash
./scripts/init.sh                 # 首次：建表 + 种子数据
./scripts/up.sh                   # 起全部
./scripts/up.sh api web           # 只起前后端
./scripts/logs.sh                 # 跟 worker
./scripts/down.sh                 # 停
./scripts/check.sh                # 后端 ruff+mypy+pytest，前端 tsc+eslint
```

| 服务 | 地址 |
|---|---|
| 前端 | **http://localhost:8000** |
| API | http://localhost:8001 |
| OpenAPI | http://localhost:8001/openapi.json |

宿主端口和容器内端口不一样：8000 是人要打开的地址，给了界面；api 让到 8001。
容器内两者仍是各自的 8000 / 5173。

## 前置条件

**worker 起不来的最常见原因是 LLM 配置。** `.env` 里 `LLM_PROVIDER=claude` 但
`ANTHROPIC_API_KEY` 为空时，worker 启动即失败并说明怎么修 —— 这是有意的，
把错误推迟到 enriching 阶段才炸更难查。

**api 不受影响**：它从头到尾不碰 LLM，没有 key 照样能起、能播、能跟读。
只是新导入的素材会停在 enriching 之前。三选一：

```bash
ANTHROPIC_API_KEY=sk-ant-...          # 直连 Claude

LLM_PROVIDER=openai_compat            # 换千问 / GPT / DeepSeek / Ollama
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=...

LLM_PROVIDER=null                     # 跳过分章与翻译，跟读照常可用
```

`worker` 用 `network_mode: host`：宿主代理监听 `127.0.0.1:7897`，
容器内的 `127.0.0.1` 是它自己的 loopback，够不着（SPEC §11.3 B1）。

媒体文件统一在 `./data/media`。**不要再给 `/data/media` 加第二个挂载** ——
`./data:/data` 与 `./media:/data/media` 同时存在时后者会把前者盖住。

## 检查

后端的 pytest / ruff / mypy 不在运行镜像里（api 镜像刻意保持轻量）。
用 `de_nachhall-dev`：

```bash
docker build --network host \
  --build-arg HTTPS_PROXY=$HTTPS_PROXY --build-arg HTTP_PROXY=$HTTP_PROXY \
  -t de_nachhall-dev - <<'EOF'
FROM de_nachhall-api
RUN pip install --no-cache-dir "pytest>=8" pytest-asyncio "ruff>=0.8" "black>=24" "mypy>=1.13"
EOF

docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp \
  -v "$PWD/server:/app" -w /app de_nachhall-dev \
  sh -c "ruff check src tests && mypy && python -m pytest -q"
```

`--user` 不能省：不带它容器会在 `server/` 里留下 root 拥有的
`.pytest_cache` / `.mypy_cache` / `.ruff_cache`。

前端：

```bash
./scripts/check.sh                                            # 前后端一起
docker compose exec web npx vite build --outDir /tmp/dist     # 完整构建验证
```

## 改了后端接口之后

前端的 API 类型是生成的，**不手写**：

```bash
./scripts/gen-api-types.sh        # 重写 web/src/lib/api.types.ts
```

## 手动灌一期素材

worker 没起时也能单独跑一遍管线：

```bash
docker run --rm --network host --user $(id -u):$(id -g) \
  --env-file .env -e LLM_PROVIDER=null -e HOME=/tmp \
  -e DATABASE_URL=sqlite+pysqlite:////data/de_nachhall.db -e MEDIA_ROOT=/data/media \
  -e HTTPS_PROXY=http://127.0.0.1:7897 \
  -v "$PWD/server/src:/app/src" -v "$PWD/data:/data" de_nachhall-worker \
  python -m de_nachhall.worker
```

真实可用的 logo! URL 形如
`https://www.logo.de/logo-vom-freitag-21-august-2026-100.html`
（首页 https://www.logo.de/ 上按日期命名的那一批）。

## 两件别做的事

### 不要删 SQLite 的 `-wal` / `-shm`

WAL 模式下**最近提交的事务住在 `-wal` 里**，checkpoint 之前还没写回主库。
删掉它等于丢掉那些行——2026-08-23 改名时删过一次，两条素材的记录当场消失，
而磁盘上的文件还在，变成孤儿。

要搬库就三个文件一起搬，或者先 checkpoint：

```bash
sqlite3 data/de_nachhall.db "PRAGMA wal_checkpoint(TRUNCATE);"
```

### 不要直接 `rm data/media/<id>/`

数据库里会留下指向不存在文件的记录，界面上点开只提示「文件不见了」——
比磁盘满更难查。用界面删除，或等 TASK-045 的清理功能。

另外 compose 里的 `worker` 以 root 跑，它写出来的文件本机 `rm` 会被拒。
真要删得借容器：

```bash
docker run --rm -v "$PWD/data:/data" de_nachhall-api rm -rf /data/media/<id>
```

## 改名留下的一处约定

Python 包是 `de_nachhall`，发行名是 `de-nachhall`，compose 项目名固定为
`de_nachhall`（写在 `docker-compose.yml` 的 `name:`）。

**项目名写死是有意的**：不写的话 compose 拿目录名当项目名，
换个目录名容器就全变成孤儿。
