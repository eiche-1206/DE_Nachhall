/* 步骤条。占据状态行，替掉原来只读的 StatusChip。
 *
 * 它同时做三件事：**报当前在哪一步**、**说明这一步该做什么**、
 * **让人直接跳到任意一步**。原来的 chip 只做第一件。
 *
 * 显示的是**设置面板里那三个阶段**，不是六个运行时步骤：
 *   「录音与回放」一格盖住 ③④⑤（录音前自动重听并展示原文，录完立即回放）；
 *   等待确认不占格子（它是终点不是阶段）。
 * 六格加序号试过，太杂 —— 一行里塞六个带编号的胶囊，读的成本高过它给的信息。
 *
 * 三条硬规则：
 *   1. **状态永不只靠颜色传达** —— 当前格实心点＋青绿底＋字重 600，
 *      其余一律空心点＋灰底。**只有「当前」和「非当前」两态**：
 *      试过再分一档「走过的」，但把它的点也改成空心之后，它和「没走到」
 *      就只剩字色一点差别 —— 那是纯颜色的区分，正是本条禁止的。
 *   2. **录音格不做脉动动画** —— 录音是持续状态不是事件。
 *   3. **高度恒定** —— 阶段从 2 格变 4 格、说明长短不一，都不能顶动视频。
 */

import { STEP_META } from '../echo/stepMeta';
import type { StepId } from '../echo/types';
import './StepBar.css';

/** 三个阶段与运行时步骤的对应。confirm 不占格。 */
const STAGES: { key: string; label: string; steps: StepId[] }[] = [
  { key: 'play', label: '播放原声', steps: ['play1'] },
  { key: 'dictate', label: '听写', steps: ['dictate'] },
  { key: 'record', label: '录音与回放', steps: ['replay2', 'record', 'playback'] },
];

interface Props {
  steps: StepId[];
  /** 当前在 steps 里的下标 */
  pos: number;
  /** 覆盖说明文字。连播模式下当前这一步在做的事跟平时不同。 */
  note?: string;
  onPick: (pos: number) => void;
}

export function StepBar({ steps, pos, note: noteOverride, onPick }: Props) {
  const current = steps[pos] ?? 'play1';
  const note = noteOverride ?? STEP_META[current].note;
  // 等待确认没有格子：此时没有任何一格是「当前」，说明行写着它
  const finished = current === 'confirm';

  // 只显示本次配置里真实存在的阶段 —— 关掉的步骤连格子都不出现
  const visible = STAGES.map((st) => ({
    ...st,
    firstPos: steps.findIndex((id) => st.steps.includes(id)),
  })).filter((st) => st.firstPos >= 0);

  const activeIdx = finished ? -1 : visible.findIndex((st) => st.steps.includes(current));

  return (
    <div className="stepbar">
      <nav className="stepbar__list" aria-label="回声阶段">
        {visible.map((st, i) => {
          const active = i === activeIdx;
          return (
            <button
              key={st.key}
              className={`stepbar__item${active ? ' stepbar__item--active' : ''}`}
              onClick={() => onPick(st.firstPos)}
              aria-current={active ? 'step' : undefined}
              title={`跳到「${st.label}」`}
            >
              <span className={`stepbar__dot${active ? '' : ' stepbar__dot--hollow'}`} />
              {st.label}
            </button>
          );
        })}
      </nav>
      <p className="stepbar__note">{note}</p>
    </div>
  );
}
