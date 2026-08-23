/* 每一步的编号、标签、字幕语义、以及播完要不要推进。
 *
 * 写成一张表而不是散在 JSX 里 —— 「这一步该不该给 S」「播完要不要推进」
 * 这种判断一旦分散，加第七步时必然漏掉一处。advanceOnSpanEnd 就是这么漏出来的。
 *
 * **S 的语义随步骤反转**（UI-SPEC §6.3）：
 *   ① 播放原声      S = 显示字幕（默认没有）
 *   ② 听写          **不提供 S** —— 看到原文等于直接看答案
 *   ③④⑤            S = 隐藏字幕（这几步默认就展示原文）
 */

import type { StepId } from './types';

export interface StepMeta {
  label: string;
  note: string;
  /** 该步骤默认是否展示原文 */
  textVisible: boolean;
  /** 该步骤是否提供 S 字幕开关 */
  allowSubtitleToggle: boolean;
  /**
   * 段落播完时是否自动进下一步。
   *
   * 只有「这一步的内容**就是**这段播放」才为 true。其余步骤里播放是
   * 辅助动作：听写时点「再听一遍」是为了写得更准，不是宣布听写做完了；
   * 回放时点「▶ 原声」是为了跟自己的录音比，不是要往下走。
   */
  advanceOnSpanEnd: boolean;
}

export const STEP_META: Record<StepId, StepMeta> = {
  play1: {
    label: '播放原声',
    note: '到段尾自动暂停',
    textVisible: false,
    allowSubtitleToggle: true,
    advanceOnSpanEnd: true, // 播原声就是这一步的全部内容
  },
  dictate: {
    label: '听写',
    note: '原文与翻译均不可见',
    textVisible: false,
    allowSubtitleToggle: false, // 硬规则：这一步不给 S
    advanceOnSpanEnd: false, // 「再听一遍」是辅助；这一步靠提交 + 回车结束
  },
  replay2: {
    label: '二次播放',
    note: '重听原声并看到原文 · 接着就录',
    textVisible: true,
    allowSubtitleToggle: true,
    advanceOnSpanEnd: true, // 同 ①，重听完这一步就完了
  },
  record: {
    label: '录音',
    note: '按 Enter 结束 · 180s 自动结束',
    textVisible: true,
    allowSubtitleToggle: true,
    advanceOnSpanEnd: false, // 这一步不播视频段
  },
  playback: {
    label: '回放',
    note: '原声、我的 可反复切换',
    textVisible: true,
    allowSubtitleToggle: true,
    advanceOnSpanEnd: false, // 「▶ 原声」是拿来对比的，不是要往下走
  },
  confirm: {
    label: '等待确认',
    note: '不自动推进 · 录音已释放',
    textVisible: true,
    allowSubtitleToggle: true,
    advanceOnSpanEnd: false, // 终点，不自动推进
  },
};
