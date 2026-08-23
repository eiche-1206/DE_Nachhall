# Sprint 0 · V2b —— seek 与自动暂停精度实测报告

> 2026-08-23 · 对应 `TASK-042` · 验证 UI-SPEC 的 200 ms 指标

## 结论

| 项 | 结论 |
|---|---|
| **200 ms 指标** | ✅ **可达成，但只有用 `requestVideoFrameCallback` 才行** |
| `timeupdate` | ❌ **两个浏览器都不达标**，Firefox 连中位数都超（205.6 ms） |
| seek 落点 | ✅ **两个浏览器都是 0.0 ms** —— 精确 seek，GOP 不影响位置 |
| 浏览器差异 | Chrome rVFC 余量 5.1×，Firefox 2.5×，**结论与浏览器无关** |

## 实测数据（两个浏览器）

素材：logo! 2026-08-21 · 640×360 · 25 fps · 各 12 轮

### Chrome 131

```
seek 落点误差         中位   0.0 ms   P95   0.0 ms
rVFC 暂停误差         中位  15.9 ms   P95  39.5 ms      ← 约 1 帧
timeupdate 暂停误差   中位 170.1 ms   P95 251.0 ms
```

### Firefox 136

```
seek 落点误差         中位   0.0 ms   P95   0.0 ms
rVFC 暂停误差         中位  31.5 ms   P95  78.7 ms      ← 约 2 帧
timeupdate 暂停误差   中位 205.6 ms   P95 277.5 ms
```

### 对比

| | Chrome 131 | Firefox 136 | 预算 |
|---|---|---|---|
| seek 落点 | 0.0 ms | 0.0 ms | — |
| **rVFC P95** | **39.5 ms** | **78.7 ms** | 200 ms |
| rVFC 余量 | **5.1×** | **2.5×** | — |
| timeupdate 中位 | 170.1 ms | **205.6 ms** ❌ | 200 ms |
| timeupdate P95 | **251.0 ms** ❌ | **277.5 ms** ❌ | 200 ms |

**两个浏览器的 `rVFC` 都轻松达标，两个浏览器的 `timeupdate` 都不达标。**
结论与浏览器无关，这比单一浏览器的数据强得多。

Chrome 的 39.5 ms 约等于 25 fps 的一个帧间隔（40 ms）—— **已经贴到理论下限**，
不可能再快。Firefox 是两帧。

## 三条可落地的结论

### 1. `useVideoStage` 必须用 `requestVideoFrameCallback`

不是「推荐」，是**唯一可行**。

- Chrome：`timeupdate` 中位 170.1 ms 勉强压线，但 P95 251.0 ms 超标
- Firefox：**中位数 205.6 ms 就已超标** —— 一半以上的段落会在超标点暂停

也就是说在 Firefox 上这不是尾部风险，是常态；在 Chrome 上是每五段就有一段超标。

```ts
// 正确
const step = (_now, meta) => {
  if (meta.mediaTime >= chunk.endMs / 1000) { video.pause(); return; }
  video.requestVideoFrameCallback(step);
};
video.requestVideoFrameCallback(step);

// 错误 —— 中位数就超标
video.addEventListener('timeupdate', () => {
  if (video.currentTime >= end) video.pause();
});
```

### 2. 不为 seek 精度重新转码 —— 已被实测确认

SPEC v1 假设「GOP 长 → seek 落点偏」，据此要求转码到 `-g 25`。**这个因果链是错的**：

- 实测 seek 落点误差 **0.0 ms**，源视频 GOP 是 2.00 s
- 浏览器做的是**精确 seek**：从前一关键帧解码到目标帧再呈现，落点是准的
- GOP 影响的是 seek **延迟**，不是位置

省下了 15–25% 的转码体积开销。

> **但转码不能完全跳过** —— 见 §「顺带发现」。

### 3. rVFC 的余量是 2.5 倍，但贴着帧率下限

```
25 fps  →  帧间隔 40 ms  →  理论下限就是 40 ms

Chrome  最大 39.5 ms ≈ 1 帧  →  已贴理论下限，无法再快
Firefox 最大 78.7 ms ≈ 2 帧
```

余量够（Chrome 5.1×，Firefox 2.5×），但**帧率越低余量越小**。
若将来素材有 15 fps 的（帧间隔 66.7 ms），Firefox 的最大误差会逼近 130 ms，
余量降到 1.5 倍。届时需重新评估。

## 顺带发现：TS 容器必须重封装

实测过程中卡了两轮，根因不是 seek 也不是 Range：

```
yt-dlp 从 HLS 下载 → 存成 .mp4
实际 format_name = mpegts       ← MPEG-TS，文件头 0x47
流 = 两套节目 + timed_id3 数据流
→ 浏览器完全无法播放
```

**修法：重封装，纯拷贝流不重编码，耗时 0.46 秒。**

```bash
ffmpeg -i in.mp4 -map 0:v:0 -map 0:a:0 \
  -c copy -bsf:a aac_adtstoasc -movflags +faststart out.mp4
```

结果：`mov,mp4,m4a` 单流 h264+aac，`moov` 在字节 36（faststart 生效）。

> 这条修正 `TASK-018 TranscodeStage`：**「不重编码」不等于「不处理」**。
> HLS 来源的素材必须重封装，否则前端播不了。代价极低。

## 浏览器兼容目标 —— 已确认可放宽

UI-SPEC §5.3 原写「桌面 Chrome / Edge 最新版」。实测表明 **Firefox 也完全够用**：

- `requestVideoFrameCallback` 两家都支持
- Firefox 的 rVFC P95 78.7 ms，相对 200 ms 预算仍有 2.5 倍余量

**建议把兼容目标改为「桌面 Chrome / Edge / Firefox 最新版」。**
Firefox 唯一的差别是 rVFC 精度约为 Chrome 的一半，但两者都远在预算内。

## 复现方式

```bash
python3 tools/serve.py        # 支持 Range 的多线程服务，标准库那个不支持
# 浏览器打开 http://127.0.0.1:8099/bench.html
# 点「① 先自检环境」→「▶ 开始实测」
```
