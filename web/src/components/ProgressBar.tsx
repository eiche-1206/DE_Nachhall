/* 两种形态。
 *
 * **enriching 阶段必须用不确定态**（PRD 约束 C4）：LLM 调用没有可观测的
 * 进度，编一个百分比出来只会在 87% 卡住三十秒，比转圈更伤信任。
 */

import './ProgressBar.css';

export function ProgressBar({
  percent,
  label,
}: {
  /** null = 不确定态（进度不可知），数字 = 确定态 0–100 */
  percent: number | null;
  label?: string;
}) {
  const determinate = percent !== null;
  const clamped = determinate ? Math.max(0, Math.min(100, percent)) : 0;

  return (
    <div className="pbar-row">
      <div
        className={`pbar${determinate ? '' : ' pbar--indeterminate'}`}
        role="progressbar"
        aria-valuemin={determinate ? 0 : undefined}
        aria-valuemax={determinate ? 100 : undefined}
        aria-valuenow={determinate ? clamped : undefined}
        aria-label={label ?? '处理进度'}
      >
        <div className="pbar__fill" style={determinate ? { width: `${clamped}%` } : undefined} />
      </div>
      <span className="pbar-row__value tnum">{determinate ? `${clamped}%` : '◌'}</span>
    </div>
  );
}
