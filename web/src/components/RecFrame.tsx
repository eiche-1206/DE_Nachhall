/* 录音边框。核心组件。
 *
 * **双层描边是硬性要求。** 单层青绿放在天空、水面、浅色墙这类画面上会被
 * 吃掉 —— 这期讲洪水，正是最坏情况。外层 --ov-rim（半透明黑）提供任何
 * 亮度的帧上都成立的对比参照。
 *
 * **不做呼吸 / 闪烁动画。** 录音是持续状态不是事件，动起来只会在余光里
 * 制造噪音，与设计原则 1「余光可读」相悖。
 *
 * 计时徽章**只显示已录时长，不显示任何参照值** —— 给出「原声 8.9s」之类
 * 的对照会让人去凑时长，而不是去说清楚。
 */

import { recTime } from '../lib/format';
import './RecFrame.css';

export function RecFrame({ active, elapsedMs }: { active: boolean; elapsedMs: number }) {
  if (!active) return null;
  return (
    <>
      <div className="rec-frame recframe__overlay" aria-hidden="true" />
      <span className="recframe__badge tnum">
        <span className="recframe__dot" />
        {recTime(elapsedMs)}
      </span>
    </>
  );
}
