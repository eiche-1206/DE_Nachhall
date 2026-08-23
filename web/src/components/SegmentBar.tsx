/* 段落进度条。整期按段切成一格一格，点哪格跳哪段。
 *
 * **不是可拖动的播放进度条，是段落导航。** 这个区别是有理由的：
 * 回声闭环的每一步都要精确到段，自由拖动必然停在段中间，
 * 接下来「再听一遍」该从哪儿开始就说不清了。切成格子之后，
 * 点击**必然**落在某一段的开头，跟侧栏点段落是同一个动作。
 *
 * 每格宽度按该段真实时长分配，所以这条也顺带是「这期有多长、我在哪儿」
 * 的全局视图 —— 段落长短不均一眼可见。
 *
 * 键盘不进 tab 序（53 个 tab 停靠点是灾难）：同样的事由 ← → 和右侧
 * 段落侧栏承担，那两条路都是键盘可达的。
 */

import type { ChunkOut } from '../lib/api';
import { shortDuration } from '../lib/format';
import './SegmentBar.css';

interface Props {
  chunks: ChunkOut[];
  currentIdx: number;
  /** 当前播放位置，毫秒。用来画当前格内部的进度。 */
  positionMs: number;
  onPick: (idx: number) => void;
}

export function SegmentBar({ chunks, currentIdx, positionMs, onPick }: Props) {
  if (!chunks.length) return null;

  return (
    <div
      className="segbar"
      role="group"
      aria-label={`段落进度 · 共 ${chunks.length} 段，当前第 ${currentIdx + 1} 段`}
    >
      {chunks.map((c) => {
        const span = Math.max(1, c.end_ms - c.start_ms);
        const current = c.idx === currentIdx;
        const passed = c.idx < currentIdx;
        // 当前格内部的进度条，钳在 0–100 之间（seek 前 positionMs 可能还是旧值）
        const pct = current
          ? Math.max(0, Math.min(100, ((positionMs - c.start_ms) / span) * 100))
          : 0;
        return (
          <button
            key={c.idx}
            className={[
              'segbar__seg',
              current ? 'segbar__seg--current' : '',
              passed ? 'segbar__seg--passed' : '',
            ]
              .filter(Boolean)
              .join(' ')}
            style={{ flexGrow: span }}
            tabIndex={-1}
            onClick={() => onPick(c.idx)}
            title={`#${c.idx + 1} · ${shortDuration(c.start_ms)}–${shortDuration(c.end_ms)}`}
            aria-label={`跳到第 ${c.idx + 1} 段`}
          >
            <span className="segbar__track">
              {current ? <span className="segbar__fill" style={{ width: `${pct}%` }} /> : null}
            </span>
          </button>
        );
      })}
    </div>
  );
}
