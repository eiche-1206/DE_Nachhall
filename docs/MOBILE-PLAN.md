# 手机端适配方案

> 状态：**方案，未实现，未登记任务**。2026-08-24 拟。
>
> 这份文档只描述打算怎么做。要动工时再按 §七 的分期往 `TASKS.md` 里登记，
> 那时才产生任务号。**现在 `TASKS.md` 里没有任何手机端任务。**

---

## 为什么现在做

拿手机连局域网打开 `http://<电脑IP>:8000` 实测过，能用的比预想多：

```
首页 HTML          200
API 健康检查        200
时间线（跨源）      200
缩略图              200
视频 Range          206 Partial Content    ← 逐段 seek 可用
```

播放和段落导航在手机上是通的。但从「能打开」到「能练」隔着三件事，
其中一件是硬阻断。

| | 状态 |
|---|---|
| 手机连得上 | ✅ 已通 |
| **录音可用** | ❌ **硬阻断**：`getUserMedia` 要求安全上下文，HTTP 下 `navigator.mediaDevices` 根本不存在 |
| 界面适配窄屏 | ❌ 固定高度会裁掉内容，交互是键盘优先的 |

---

## 已定的五条

| | 决定 | 影响 |
|---|---|---|
| 平台 | **先安卓**，接口留好 iOS 的位置 | 平台差异关进接口，不散在 `if (isIOS)` |
| 网络 | **现在 LAN + HTTP 够用**，产品级留到后期 | 反向代理与 TLS 不进近期 |
| 隔离 | **手机版可整块删除，不影响桌面版** | 排除了「给桌面 CSS 加断点」这条路 |
| 入口 | **独立路由 `/mobile`** | 桌面路由一行不动 |
| 范围 | **只做首页 + 回声页** | 导入、删除、重试留在电脑上 |

---

## 一、隔离怎么划

### 边界在表现层，不在逻辑层

```
web/src/
├── echo/          ★ 共享，绝不复制    状态机 · 录音 · 播放 · 步骤表
├── lib/           ★ 共享             api · format
├── settings/      ★ 共享
├── components/      桌面呈现         一行不动
├── routes/          桌面页面         一行不动
├── mobile/        ← 新增，整块可删
│   ├── routes/       MobileHome · MobileEcho
│   ├── components/   手机版自己的呈现组件
│   ├── styles/       mobile.css（在根节点上覆盖 token）
│   └── index.ts      唯一对外出口
└── App.tsx          加 2 行 <Route> + 1 行 import
```

实测量级：

```
共享（echo + lib + settings）        2015 行   ← 手机版白拿，零复制
桌面呈现（components + routes .tsx） 1973 行   ← 手机版另写，但范围更窄
其中纯键盘的 useHotkeys                98 行   ← 桌面专用
```

**为什么逻辑必须共享**：复制一份状态机，两边就会各自演化。今天改「⑤ 回放
一秒后自动播放」要改两处，明天加第七个步骤会漏掉一边。这类漂移不会报错，
只会让两端行为悄悄不同。

### 路由

```
/                          桌面首页          ← 不动
/episode/:id               桌面详情页（暂缓） ← 不动
/episode/:id/echo          桌面回声页        ← 不动
/mobile                    手机首页          ← 新增
/mobile/episode/:id/echo   手机回声页        ← 新增
```

同一个服务、同一个端口、同一份数据，只是路径不同。手机上把
`http://<电脑IP>:8000/mobile` 加到主屏幕。

### 怎么删

```bash
rm -rf web/src/mobile/
# App.tsx 里去掉 2 行 <Route> 和 1 行 import
```

桌面版一行 CSS、一行 TSX 都不受影响。**这条要写进 `mobile/index.ts`
的文件头注释**，不然三个月后没人知道边界在哪。

### token 怎么办

**不改 `styles/tokens.css`**——它是两端共享的设计系统。手机版在自己的根节点
上覆盖需要变的那几个：

```css
/* mobile/styles/mobile.css */
.m-root {
  --h-subtitle-area: auto;   /* 桌面 88px */
  --h-transport: auto;       /* 桌面 68px */
  --t-german: 400 17px/1.6 var(--f-ui);
}
```

加法，删目录即消失。代价是手机版的尺寸决策散在两个文件里（token 定义在
共享处、覆盖在手机处），查的时候要看两个地方。

---

## 二、先修两个 bug，它们与手机无关

这两条**逐行核实过**，桌面窗口拖到 1100px 以下同样会中招。它们与手机适配
无关也该修，建议**各自一个 PR**，不要等手机版。

### ⑤ 回放在触摸端是死路

```
stepMeta.ts:65     playback: { advanceOnSpanEnd: false }
EchoPage.tsx:481   playback 的按钮 = again / orig / prev / next / subs   ← 没有出口
```

只有 `Enter` 能从 ⑤ 走到 ⑥。StepBar 只有三格且 confirm 没有格子，也跳不过去。
**手指用户练完一段卡在那里出不来。**

同一处还有：⑥ 的 `allowSubtitleToggle: true`，但按钮列表里没有 S。

### 收起侧栏后右侧 264px 全部点不动

```
EchoPage.tsx:399   <div className="echo__side echo__side--empty" />
EchoPage.css:70    .echo__side--empty { background:none; border-left:0; animation:none }
                   ↑ 只去掉了外观，没有取消 @media 里给 .echo__side 的定位
EchoPage.css:184   @media(max-width:1100px){ .echo__side{ position:absolute; width:264px; z-index:5 } }
EchoPage.css:148   .echo__handle{ z-index: 4 }     ← 被压在下面
```

收起侧栏时，那个占位列变成**不可见的覆盖层**，把手自己被自己盖住。

---

## 三、共享层要先做一次提炼

手机版动工前，把 `EchoPage.tsx:419` 的 `buildActions()`（79 行）提升到
`echo/actions.ts`：

```
buildActions(step, dictationPhase, handlers) → EchoAction[]
```

它的闭包依赖全是可调用项（`machine.*`、`onEnter`、`onSpace`、`playChunk`、
`playRecording`、`recorder.start`，共 11 个），做成参数即可，没有阻力。

**这是最容易漂移的地方**——「哪一步给哪些动作」如果两端各写一份，加步骤时
必然漏掉一边。提炼之后两端共享同一份动作列表，各自决定怎么渲染：桌面渲成
控制条按钮，手机渲成底部大按钮。

`stepMeta.ts` 已经是这个形状，`buildActions` 跟着搬过去即可。

---

## 四、手机版界面怎么设计

### 实测的窄屏问题（390px 宽，内容可用 342px）

| 问题 | 数据 |
|---|---|
| **字幕区裁掉大半** | 真实数据：德语段落字符数中位 **140**、最长 **229**。20px 字号下中位段 5 行 = **162px**、最长段 8 行 = **259px**，而 `--h-subtitle-area: 88px` 且 `overflow: hidden` |
| **控制条溢出** | 每步 4–5 个按钮，估宽合计 460–492px，必然折成 2–3 行（80–124px），而 `--h-transport: 68px` 且无 overflow 处理，与上下元素重叠 |
| 首页标题消失 | `.hero__thumb { flex: 0 0 168px }`（shrink 为 0）+ 按钮 110px = 278px > 可用 262px，中间的 meta 坍缩到 0 |
| Toast 溢出屏幕 | `max-width: 380px` + right 24px = 404px > 390px |
| 段落进度条点不中 | 53 段挤在 342px 里，每格 3–6px |
| 触摸目标过小 | 按钮 36px、阶段胶囊 24px、侧栏关闭 22×22、把手 22×54（贴屏幕最右缘）——均低于 44px 基线 |

### 「视频不跳」这条规则怎么在手机上守住

UI-SPEC 的硬规则是「任何步骤、任何状态下视频尺寸与位置都不变」。桌面上靠
三个固定高度实现（字幕区 88 / 状态行 48 / 控制条 68）。

**规则的意图是「视频不要跳」，固定高度只是桌面上的手段。** 手机上换手段：

```
┌─────────────────────────┐
│   视频  position:sticky  │  ← 吸顶，滚动时不动
│   段落进度条              │
├─────────────────────────┤
│   字幕（min-height，不裁） │  ← 内容多就往下长
│   阶段条                  │
│   ⋮ 听写 / 对照 / 翻译     │  ← 页面在这里滚动
├─────────────────────────┤
│   控制条  bottom sticky   │  ← 吸底，拇指够得到
└─────────────────────────┘
```

视频同样不动，而文字要多高有多高。**规则守住了，手段换了。**

### 触摸交互

| 桌面 | 手机版的等价物 |
|---|---|
| `Space`（重复这一步） | 底部**主按钮**，占整行，文案随步骤变 |
| `Enter`（推进） | 底部**次按钮**「继续 →」。桌面缺的那四步一并补上 |
| `←` `→` | 视频下方段落条 + 底部左右小按钮 |
| `S` `T` | 收进「⋯」二级菜单，不占主区 |
| `Tab`（侧栏） | 顶栏按钮，抽屉带遮罩层 |
| `Esc` | 顶栏返回 |
| hover 才显示的 ▶ | **常显**，或去掉——触摸端没有 hover |
| `title` 里的信息 | 直接写进界面（如段落条的段号） |

其它必须处理的：

- **kbd 徽章全部不渲染**。手机版自己的按钮组件不传 `kbd`，共享层的
  `EchoAction` 里带着 `kbd` 字段但手机版忽略它——不需要为此改共享层
- `100dvh` 取代 `height: 100%`，否则地址栏收缩时布局跳动
- `env(safe-area-inset-*)`，`index.html` 的 viewport 加 `viewport-fit=cover`
  ——**这一处要动共享的 index.html**，是隔离的唯一破例，代价可接受
- 触摸目标一律 ≥44px
- `Popover` 的点外部关闭只监听 `mousedown`，手机版自己的浮层要用 `pointerdown`

---

## 五、为 iOS 留的位置

后端已有 `TranscriptProvider` / `EnrichProvider` 的 Protocol 模式，前端照搬：

| 接口 | 安卓实现 | iOS 以后要处理的 |
|---|---|---|
| `AudioRecorder` | `MediaRecorder` + webm | 产出 `audio/mp4`；权限时机不同 |
| `FrameClock` | `requestVideoFrameCallback` | Safari 15.4+ 才有，回落 rAF（**`useVideoStage` 里已经写好了，可作范例**） |
| `capabilities` | 一处集中探测 | 自动播放策略、安全上下文、PWA 能力 |

关键是**探测能力，不探测机型**——`if (!navigator.mediaDevices)` 而不是
`if (isIOS)`。前者在任何新平台上都对。

---

## 六、录音怎么办

`getUserMedia` 要求安全上下文，没有第二条路。

### 近期：安卓上有个不花钱的口子

```
chrome://flags/#unsafely-treat-insecure-origin-as-secure
填入 http://<电脑IP>:8000
```

只是**你自己手机上的浏览器设置**，不动任何代码。开了之后五步闭环全通。

它不是产品方案——换台手机要再配一次，iOS 没有对应开关——但用来
**验证录音在手机上到底好不好用**够了，而那正是决定要不要为 HTTPS 投入的依据。

### 后期：产品级

现在是两个源（web :8000 / api :8001），API 地址被编译进前端
（`VITE_API_BASE`），换个访问地址就要改配置重启，还得开 `allow_origins=["*"]`。

产品级做法是**单一源 + 反向代理**（Jellyfin、Immich、Nextcloud 都是这个路子）：

```
手机 ──▶ Caddy :443  TLS 终止
           /api/*  ──▶ api
           /*      ──▶ 前端生产构建
```

一次解决四件事：`API_BASE` 变成相对路径（任何地址都能用，零配置）、
CORS 中间件整个删掉、TLS 只配一处、前端上生产构建（130 KB gzip / 3 个请求，
取代开发服务器的几百个模块请求）。

**后端天然支持**：所有业务路径都在 `/api/` 下，反代规则只有两条。

证书三种拿法：

| 方式 | 手机要装东西吗 | 出门在外能用 |
|---|---|---|
| **Tailscale Serve** | 不用（`*.ts.net` 是真证书） | ✅ |
| Caddy + 真域名 + Let's Encrypt | 不用 | ✅ |
| Caddy `tls internal`（自签） | 要装并信任根证书 | ❌ |

---

## 七、分期

| 期 | 内容 | 前置 |
|---|---|---|
| **0** | 修那两个 bug（⑤ 死路、覆盖层） | 无。与手机无关，先做 |
| **1** | 共享层提炼：`buildActions` → `echo/actions.ts` | 无 |
| **2** | `mobile/` 骨架 + 手机首页 + 手机回声页 | 期 1 |
| **3** | 安卓上开 flag 验证录音，决定要不要投 HTTPS | 期 2 |
| **4** | 产品级：单一源 + Caddy + TLS + PWA | 期 3 的结论 |

期 1–2 做的东西，到期 4 一行都不用返工——那时只是换了访问入口，
手机版的组件与样式不受影响。

---

## 八、怎么验

| 期 | 验收 |
|---|---|
| 0 | 桌面窗口拖到 1000px：侧栏把手可点；⑤ 有按钮能走到 ⑥ |
| 1 | `./scripts/check.sh` 全绿；桌面版行为**零变化**（这是重构不是改行为） |
| 2 | 手机开 `/mobile`：字幕完整可见不被裁；控制条不溢出；滚动时视频吸顶不动；所有可点目标 ≥44px；**删掉 `mobile/` 后桌面版 check 仍全绿** |
| 3 | 手机上跑完整五步闭环，录音能录能放 |
| 4 | 手机不装任何证书直接 HTTPS 打开；换 WiFi / 换 IP 后无需改配置 |

期 2 的最后一条是隔离约束的**真实检验**——删完还能过，才算真的隔离了。

---

## 九、这个方案的代价，说在前面

**呈现层要维护两遍。** 这是用户明确选的隔离约束换来的。最容易漂移的
「哪一步给哪些动作」已经用期 1 的提炼堵住，但按钮文案、状态提示这类东西
仍然是两份。

**不做的**：不做原生重写；不做手机端素材管理（导入/删除/重试）；
不做录音上传或云端同步——录音仍然切段即销毁。
