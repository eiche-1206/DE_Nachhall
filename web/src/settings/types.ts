/* 设置的形状与默认值。
 *
 * **两个环节开关**（PRD F2.3）：
 *   ① 播放原声      不可关，是闭环的地基 —— 一段没听过就没什么可跟读的
 *   ② 听写          dictation  默认 false（多数人不是每段都想写）
 *   ③ 录音与回放    record     默认 true —— 一个开关驱动三步：
 *                   先自动重听一遍并展示原文，再录音，录完立即回放

 *
 * 「二次播放」不单列开关：它是录音前的准备动作，关掉录音就没有它存在的
 * 理由，单独开着它等于「重听一遍然后什么也不做」。同理回放跟着录音走 ——
 * 录了才有得放。**设置里 2 个开关，运行时最多 6 步**，这是有意的非一一对应。
 *
 * 另有两项**显示偏好**，不是环节开关：
 *   subtitles   字幕是否可见（由 S 键翻转，不在面板里）
 *   segmentBar  视频下方的段落进度条是否显示（在面板里，默认开）
 */

export interface Settings {
  /**
   * 全文播放。开启后 ① 播完不进下一步，而是**进下一段继续播 ①**，
   * 一路连到全文结束。此时听写与录音不参与 —— 这是「听一遍整期」的
   * 模式，不是跟读模式。
   *
   * 默认关：这个产品的地基是回声闭环，连播是另一种用法。
   * 默认开等于一进来就把跟读跳过了。
   */
  continuousPlay: boolean;
  dictation: boolean;
  /** 驱动三步：③ 二次播放＋原文 → ④ 录音 → ⑤ 回放 */
  record: boolean;
  subtitles: boolean;
  /** 视频下方的段落进度条。显示偏好，不影响任何步骤。 */
  segmentBar: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  continuousPlay: false,
  dictation: false,
  record: true,
  subtitles: true,
  segmentBar: true,
};

export type SettingsKey = keyof Settings;

/** 存取的抽象。换后端持久化时只换实现，调用点不动（SPEC §4.3）。 */
export interface SettingsProvider {
  read(): Settings;
  write(next: Settings): void;
}
