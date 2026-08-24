/* 回声闭环的运行时步骤。
 *
 * **两个 settings 开关翻译成最多六个步骤**：
 *
 *   ①  play1     播放原声      始终存在，是闭环的地基
 *   ②  dictate   听写          settings.dictation
 *   ③  replay2   二次播放+原文  settings.record ┐
 *   ④  record    录音          settings.record ├ 一个开关驱动三步 ——
 *   ⑤  playback  回放          settings.record ┘ 有意的非一一对应
 *   ⑥  confirm   等待确认      始终存在，**不自动推进**
 *
 * ③⑤ 为什么跟着 record 走：③ 是录音前的准备（先重听一遍并看到原文），
 * ⑤ 是录音后的对比。关掉录音还单独留着 ③，等于「重听一遍然后什么也不做」。
 *
 * 听写内部还有写作 / 对照两个子态。它们不是独立步骤 —— 对照是提交的
 * 直接结果，做成步骤会让「上一步」的含义变得含糊。
 */

export type StepId = 'play1' | 'dictate' | 'replay2' | 'record' | 'playback' | 'confirm';

/** 听写的子态。writing = 写作中（原文与翻译均不可见），comparing = 对照。 */
export type DictationPhase = 'writing' | 'comparing';

export interface EchoState {
  /** 当前 chunk 在全期中的序号 */
  chunkIdx: number;
  /** 本次配置下的步骤序列，随 settings 变化 */
  steps: StepId[];
  /** 在 steps 里的位置 */
  stepPos: number;
  dictation: DictationPhase;
  draft: string;
  /** 字幕**当前**是否可见。进每一步时按该步的默认值重置，S 在此基础上翻转。 */
  subtitles: boolean;
  /** 用户在设置里的字幕偏好。只作为「这一步默认不展示原文」时的兜底默认值。 */
  prefSubtitles: boolean;
  translationOpen: boolean;
  /**
   * 显式跳转的次数。连播时播放位置会不断把 chunkIdx 往前推（syncChunk），
   * 那不该重新起播；只有用户自己跳段 / 跳步骤 / 重来才该。用一个计数
   * 把这两类变化区分开 —— 光看 chunkIdx 分不出是谁改的。
   */
  seq: number;
}
