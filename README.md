# DE_Nachhall

[![repo](https://img.shields.io/badge/github-eiche--1206%2FDE__Nachhall-0d9488)](https://github.com/eiche-1206/DE_Nachhall)

自托管的德语听说跟读训练工具。贴一个视频链接，它把整期切成一段一段，
陪你一段一段地听、写、说、对。素材默认来自 ZDF 的 **logo!** 少儿新闻。

核心是**回声闭环**：一段德语，听原声 → （听写）→ 重听并看到原文 → 录下自己 → 回放对比。
每一段都要过一遍这个循环，练的是「听清 → 说出」这条链路，不是背单词。

> **它不判对错。** 听写不做 diff、不算分、不标高亮；录音不比对发音。
> 对照靠的是把你写的和原文上下叠、同宽同字号——**错位本身就是信号**。
> 这是产品的核心取舍，不是没来得及做（见 `docs/PRD.md` Out of Scope）。

---

## 目录

- [跑起来](#跑起来)
- [进 git 之后](#进-git-之后)
- [启动与关闭](#启动与关闭)
- [导入第一期素材](#导入第一期素材)
- [怎么用](#怎么用)
- [配置](#配置)
- [出问题时](#出问题时)
- [磁盘占用](#磁盘占用)
- [目录结构](#目录结构)
- [文档](#文档)

---

## 跑起来

### 前置条件

| | 要求 | 说明 |
|---|---|---|
| Docker | Compose v2 | `docker compose version` 能跑就行 |
| GPU | 可选 | 只有平台没有字幕、要用 Whisper 转写时才需要。ZDF/logo! 有官方德语字幕，走不到 Whisper |
| 网络 | 能访问素材站 | 国内需要代理，见下 |
| 磁盘 | 每期约 **160 MB** | 见[磁盘占用](#磁盘占用) |

### 三步

```bash
git clone https://github.com/eiche-1206/DE_Nachhall.git
cd DE_Nachhall

# 1. 配置
cp .env.example .env
$EDITOR .env          # 至少确认 LLM_PROVIDER 与 HOST_PROXY，见下方「配置」

# 2. 初始化数据库（建表 + 写入默认用户和 logo! 订阅）
./scripts/init.sh

# 3. 起服务
./scripts/up.sh
```

打开 **http://localhost:8000**。

> **第 2 步不能省。** `docker compose up` 不会自己建表——迁移是有副作用的操作，
> 让它跟着容器每次重启跑一遍，早晚会在某次意外重启时执行到一半。
> 这条命令两步都幂等，重复执行安全。

---

## 进 git 之后

```
https://github.com/eiche-1206/DE_Nachhall.git
```

### 什么不进仓库

`.gitignore` 挡掉的都有理由，别随手 `git add -f`：

| | 为什么 |
|---|---|
| `.env` | **里面有 API key**。模板是 `.env.example`，改了模板记得同步 |
| `data/` | 你的库和素材，220 MB 起步，且是你个人的学习内容 |
| `models/` | Whisper 模型缓存 2.9 GB，机器上重新下就有 |
| `tools/*.mp4` | Sprint 0 的样本视频，40 MB，是证据不是代码 |
| `*.egg-info/` | `pip install -e` 的构建产物。**容器里生成时归 root**，本机 `rm` 会被拒 |

`server/tests/fixtures/logo_20260821.vtt` **要进**——它是真实的 ZDF 字幕，
测试里 175 cue → 118 句 → 53 段那串数字全靠它。

### 换机器

代码进 git，数据不进。换台机器要做的是：

```bash
git clone https://github.com/eiche-1206/DE_Nachhall.git && cd DE_Nachhall
cp .env.example .env && $EDITOR .env
./scripts/init.sh && ./scripts/up.sh
```

想把素材也搬过去，把旧机器的 `data/` 整个拷过来，**跳过 init.sh**——
那个目录里就是完整的库和视频。

### 提交之前

```bash
./scripts/check.sh        # ruff + mypy + pytest + tsc + eslint
```

---

## 启动与关闭

```bash
./scripts/up.sh                   # 全部起来（api + web + worker）
./scripts/up.sh api web           # 只起前后端，不处理新素材（不需要 GPU）
./scripts/down.sh                 # 停，容器留着，下次 up 秒起
./scripts/down.sh --rm            # 停并删容器
./scripts/logs.sh                 # 跟 worker 日志，看素材处理进度
./scripts/logs.sh api             # 跟指定服务
```

不想用脚本的话，底下就是 `docker compose up -d` / `stop` / `down` / `logs -f`。

| 服务 | 地址 | 关掉会怎样 |
|---|---|---|
| `web` | **http://localhost:8000** | 界面打不开 |
| `api` | http://localhost:8001 | 界面打得开但一片空白，提示「连不上服务」 |
| `worker` | 无端口 | 界面照常，但**新导入的素材永远停在排队中** |

> 端口是有意这样排的：**8000 是人要打开的地址**，所以给了界面；
> api 让到 8001。容器内部两者都还是各自的原端口（8000 / 5173），
> 换的只是宿主映射。

数据全部在 `./data`：`de_nachhall.db` 是库，`media/` 是视频与音频。
备份就是把这个目录拷走。

---

## 导入第一期素材

1. 到 https://www.logo.de/ 找按日期命名的整期，链接形如
   `https://www.logo.de/logo-vom-freitag-21-august-2026-100.html`
2. 界面右上角 **＋** → 粘贴 → **导入**
3. 等 1–3 秒，它会回显标题和时长——**这一步就能确认贴对没有**
4. 后台处理：下载 → 转码 → 转写 → 生成章节与翻译。首页会显示进度
5. 转写一完成就能开练，**不用等章节和翻译**

命令行也行：

```bash
./scripts/import.sh https://www.logo.de/logo-vom-freitag-21-august-2026-100.html
./scripts/logs.sh          # 盯进度
```

一期 8 分钟的素材，本机实测约 5 分钟处理完，其中绝大部分是下载。

支持的不止 logo!——底层是 yt-dlp，YouTube、ARD 等常见视频站都能抓。
**纯音频会被拒绝**：回声闭环要画面配合。

---

## 怎么用

详细的操作说明在 **[docs/USER-GUIDE.md](docs/USER-GUIDE.md)**。这里只放最少的：

| 键 | 作用 |
|---|---|
| `Space` | **重复当前这一步**（五个步骤里含义各不相同） |
| `Enter` | 结束录音 / 提交听写 / 继续 |
| `←` `→` | 上一段 / 下一段 |
| `S` | 字幕 |
| `T` | 翻译 |
| `Tab` | 段落侧栏 |
| `Esc` | 返回 |

首页点任何地方——封面、标题、章节、往期——都**直接进跟读**，不经过中间页。

---

## 配置

`.env`，从 `.env.example` 复制。只有两项需要你决定：

### LLM——决定有没有章节和翻译

分章、章节标题、逐句中文翻译是一次 LLM 调用产出的。三选一：

```bash
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...

# 或者换千问 / GPT / DeepSeek / Ollama，一个实现覆盖四家
LLM_PROVIDER=openai_compat
LLM_MODEL=qwen-plus
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_API_KEY=...

# 或者不要
LLM_PROVIDER=null
```

**`null` 不影响跟读**：段落照常切分，只是没有章节标题、没有中文翻译，
详情与侧栏平铺显示。想省钱或者不想接外部服务的话，这是个正经选项。

> `LLM_PROVIDER=claude` 但 key 为空时，**worker 启动即失败**并打出怎么补。
> 这是有意的——把错误推迟到三分钟后炸在处理管线里更难查。
> **api 不受影响**：它从头到尾不碰 LLM，没有 key 照样能播、能跟读。

### 代理——只在直连出不去时才需要

**能直接上网就留空**，`HOST_PROXY=` 空值代表不走代理。

需要的话，值取决于你机器上跑的是什么、监听哪个端口。查自己的：

```bash
env | grep -i proxy
ss -ltnp | grep -iE "clash|mihomo|v2ray|sing-box"
```

然后填进 `.env`：

```bash
HOST_PROXY=http://127.0.0.1:<你的端口>
```

`api` 与 `worker` 都用 `network_mode: host`，所以这里的 `127.0.0.1`
指的就是**宿主的** loopback——这正是要它们用 host 网络的原因：
代理这类工具通常只监听宿主 `127.0.0.1`，bridge 网络的容器够不着。

> **换了代理端口只要改这一行**，然后 `./scripts/up.sh`。
> 别处没有写死的值——compose 里的兜底是空，不是某个端口。

其余项（Whisper 模型、切分目标词数、录音超时）都有可用默认值，
说明写在 `.env.example` 里。

---

## 出问题时

| 现象 | 多半是 |
|---|---|
| 界面提示「连不上服务」 | `api` 没起，或者数据库没初始化（跑 `./scripts/init.sh`）。`./scripts/logs.sh api` |
| `worker` 反复重启 | `LLM_PROVIDER=claude` 而 key 为空。日志里有明确的一行中文 |
| 素材一直「排队中」 | `worker` 没起。`./scripts/up.sh worker` |
| 导入报「这个站点抓不了」 | 换个站点。yt-dlp 没有对应的 extractor |
| 导入报「地域限制」 | 配 `HOST_PROXY` |
| 导入报「这是纯音频」 | 不支持。回声闭环要画面配合 |
| 处理失败停在某一步 | 首页那条素材上点「从该步重试」，已完成的阶段不会重跑 |
| 视频能播但拖不动 | 不该发生。`api` 的流接口支持 Range，若真如此请提 issue |

失败的素材还有一个「**仍然进入**」——生成章节翻译这一步失败不阻塞跟读，
转写已经完成的话段落照样能练。

---

## 磁盘占用

实测一期 8 分 11 秒的 logo!：

```
video.mp4    148.8 MB     前端播放与 seek 的对象
audio.wav     15.7 MB     转写用，16k 单声道
thumb.jpg      1.2 MB     封面
probe.json      64 KB     yt-dlp 元数据
──────────────────────
合计         约 160 MB
```

每天一期的话大约 **1.1 GB / 周**、**58 GB / 年**。

`./scripts/disk.sh` 按期列出占用。

**清理功能本期没做**（已登记为 `TASK-045`）。现在要腾地方只能手动：
界面上删除自行导入的素材会连文件一起回收，或者直接删 `data/media/<id>/`
——但那样数据库里会留下指向不存在文件的记录，界面上点开会提示文件不见了。
**推荐用界面删**。

---

## 目录结构

```
.
├── docker-compose.yml     三个服务：api / web / worker
├── .env                   你的配置（不进仓库）
├── data/                  ★ 全部数据。备份拷这个目录
│   ├── de_nachhall.db    SQLite
│   └── media/<id>/        视频、音频、封面
├── models/                Whisper 模型缓存，避免每次重下 1.5 GB
├── server/                Python · FastAPI · SQLAlchemy
│   ├── src/de_nachhall/
│   │   ├── ingest/        四阶段管线：下载 → 转码 → 转写 → 生成
│   │   ├── providers/     转写与 LLM 的可换实现
│   │   ├── chunking/      句子合并与 bestfit 切段
│   │   ├── routers/       HTTP 路由
│   │   └── repositories/  数据访问
│   └── tests/             229 个测试
├── web/                   React · TypeScript · Vite
│   └── src/
│       ├── echo/          回声状态机、录音、播放、快捷键
│       ├── components/    22 个组件
│       └── routes/        首页 / 详情页 / 回声页
├── scripts/               ★ 日常操作：起停、导入、看占用、跑检查
├── tools/                 一次性验证工具（Range 服务器、seek 基准），非日常使用
└── docs/                  PRD / UI-SPEC / SPEC / TASKS / 用户手册
```

---

## 文档

| 文件 | 内容 |
|---|---|
| **[docs/USER-GUIDE.md](docs/USER-GUIDE.md)** | **怎么用**——五步闭环、快捷键、设置项、常见疑问 |
| [scripts/README.md](scripts/README.md) | 每个脚本做什么 |
| [docs/DEV.md](docs/DEV.md) | 开发：测试怎么跑、改了接口怎么重生成前端类型 |
| [docs/PRD.md](docs/PRD.md) | 产品需求。**先看 Out of Scope**，那里写了哪些事故意不做 |
| [docs/UI-SPEC.md](docs/UI-SPEC.md) | 界面规范。组件、快捷键、以及每条硬规则的理由 |
| [docs/SPEC.md](docs/SPEC.md) | 技术规格。架构图、表结构、实测数据 |
| [docs/TASKS.md](docs/TASKS.md) | 任务清单与依赖图 |
| [docs/sprint0-v2b-report.md](docs/sprint0-v2b-report.md) | 浏览器暂停精度实测报告 |

**本期未做，已登记：**

| 任务 | 内容 |
|---|---|
| `TASK-044` | 全文视图——settings 里的开关，滚动跟随，当前段外淡化 |
| `TASK-045` | 存储清理——按规则回收 `media/`，别让磁盘被素材吃满 |
| 详情页 | 代码与路由都在，暂时不摆在动线上（见 UI-SPEC §6.2） |
