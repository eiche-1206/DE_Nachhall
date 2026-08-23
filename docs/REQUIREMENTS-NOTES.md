# DE_Nachhall — 需求收敛纪要

> 产出方式：三轮引导式拷问（2026-08-22）。本文件是 `prd-designer` 的输入，不是方案。

> ⚠️ **本文件已被 `PRD.md` 取代（2026-08-22）。** PRD 阶段修订了以下决策，以 PRD 为准：
> - **D5 素材源**：ZDF Mediathek → **logo! 官方 YouTube 频道**（`@logo-nachrichten`），用 yt-dlp
> - **D6 分段**：LLM 只管「新闻条目边界 + 标题 + 翻译」；**段落切分改为纯规则贪心合并**
> - **新增分层**：`fragment` → `sentence` → **`chunk`（~22 词，训练单元）** → `chapter`
> - **D10 播放**：补充「**不自动推进**，每段等确认」
> - **O1 结案**：**不记录学习进度**


## 0. 一句话

参考 Miraa 的 Echo Method，做一个自用的 Web 应用，用 ZDF `logo!` 新闻训练德语听说：
导入一期 → 自动切句 → 逐句「看画面 + 听 + 跟读 + 回放对比」，并支持听写对照。

## 1. 用户画像

| 项 | 值 |
|---|---|
| 用户 | 仅作者本人 |
| 德语水平 | **B2–C1** |
| 主素材 | ZDF `logo!` Nachrichten（约 10 分钟/期，80–120 句） |
| 部署 | 前后端分离，自用（公网/本地待定） |

**B2–C1 推导出的默认界面**：字幕默认**关**（按键临时显示）· 中文翻译默认**折叠** · 听写前听 1 遍 · 跟读窗口 = 句长 × 1.2

## 2. 已定决策

| # | 决策 | 内容 |
|---|---|---|
| D1 | **切句与文本** | 后端 `ingest` 管线跑 **faster-whisper（de）**，一次产出 `{start, end, text}`。抽象为 `TranscriptProvider`，v2 可换 ZDF 官方 VTT / WhisperX 词级对齐 |
| D2 | **回声闭环** | 视频按 segment 播放 → 到 `end` 自动暂停 → 录音（麦克风）→ 跟读完**立即回放一次**（原声 / 我的，可 A/B）→ 切下一句即**丢弃录音，不落盘不上传** |
| D3 | **评分层** | MVP 为 `NullScorer`，UI 预留自评位。抽象为 `ScoreProvider`，v2 可接 ASR-diff 或音素级发音评测 |
| D4 | **视频跟随** | 回声/回放时**画面必须跟着走**（非纯音频）。支持按**句**和按**段落**回放 |
| D5 | **素材导入** | 页面粘贴 ZDF URL → 后端异步 `ingest(url)` 全流程。cron 自动抓取推 v2，**复用同一函数** |
| D6 | **段落划分** | `ingest` 中一次 LLM 调用同时完成「新闻条目分段 + 段落标题 + 逐句中文翻译」。需预留手动调整分段的口子 |
| D7 | **听写** | **不判对错**，写完点「看答案」左右并排对照，无 diff 算法 |
| D8 | **MVP 范围** | 含中文翻译。**明确推 v2**：AI 语法讲解 · 生词本 · SRS 复习队列 |
| D9 | **后端栈** | **Python + FastAPI**（faster-whisper / ffmpeg / 未来 WhisperX 全在 Python 生态） |
| D10 | **播放行为** | 默认按顺序连播到底，但**可从任意一句起播** |

## 3. 关键约束（写进 Spec）

1. **视频文件本地化**：D5 选了「后端下载」，因此播放的是**本地 mp4** 而非 ZDF 的 HLS 流。这规避了 CORS / Geoblocking / m3u8 精确 seek 三个坑，但要求静态服务支持 **Range 请求**（逐句 seek 依赖它）。
2. **seek 精度**：回声引擎逐句跳转依赖关键帧间隔。转码入库时应考虑重新编码以缩短 GOP，否则 `currentTime = seg.start` 会漂。
3. **Whisper 德语转写会错**（专有名词、数字、复合词）。MVP 接受，但因 D7 不判对错，错误只影响"对照"体验而不产生假判罚——这是 D7 的隐含收益。
4. **单次 LLM 调用承担三件事**（D6），prompt 与输出 schema 需一次设计到位。

## 4. 四个页面级组件（来自原始需求）

1. **首页 / 素材列表** — 期数列表，可粘 URL 导入，显示处理状态
2. **详情页** — 视频播放器 + 段落/句子列表，入口到跟读与听写
3. **回声模式** — 核心，逐句自动循环
4. **听写模式** — 听 → 写 → 对照

## 5. 待决（留给 SDD 流程）

| # | 待决项 | 阶段 |
|---|---|---|
| O1 | **是否记录学习进度**（练过哪些句、自评）— 用户最后一题答的是播放行为，未表态；当前假设**MVP 不做** | PRD |
| O2 | 存储形态：视频放文件系统 vs DB blob；完整 schema | Spec |
| O3 | 数据库选型：SQLite vs Postgres | Spec |
| O4 | 前端框架：React / Svelte / 其他 | Spec |
| O5 | Whisper 模型规格与部署（CPU/GPU、模型大小、耗时） | Spec |
| O6 | LLM 供应商与调用方式（分段 + 翻译） | Spec |
| O7 | 部署形态：localhost vs VPS；是否需要鉴权 | Spec |
| O8 | 导入失败 / Whisper 失败 / LLM 失败的降级路径 | Spec |

## 6. 下一步

已安装 SDD skill 链（`~/.claude/skills/`），**需新开会话加载**：

```
/prd-designer   → PRD.md      （吃本文件）
/ui-designer    → UI-SPEC.md
/spec-designer  → SPEC.md
/task-planner   → TASKS.md    （任务 DAG）
/test-planner   → TEST-PLAN.md
```
