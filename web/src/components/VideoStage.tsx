/* 视频舞台。
 *
 * **硬规则 · 任何步骤、任何状态下尺寸与位置都不变**（设计原则 3）。
 * 听写输入框与上下叠对照必然超出视口 —— 那时**页面滚动，视频不缩小**。
 * 视频一旦在步骤间忽大忽小，跟读的节奏就断了。
 *
 * 底色是 --n-900：视频加载前不露白，否则每次切段都闪一下。
 */

import { forwardRef } from 'react';
import type { ReactNode } from 'react';

import './VideoStage.css';

interface Props {
  src: string;
  /** 叠在右下的时码 */
  timecode?: string;
  /** RecFrame 等叠层 */
  children?: ReactNode;
  className?: string;
}

export const VideoStage = forwardRef<HTMLVideoElement, Props>(function VideoStage(
  { src, timecode, children, className },
  ref
) {
  return (
    <div className={['vstage', className].filter(Boolean).join(' ')}>
      <div className="vstage__frame">
        {/* 不给 controls：进度条会让人手动拖，而闭环的每一步都要精确到段 */}
        <video ref={ref} className="vstage__video" src={src} playsInline preload="auto" />
        {timecode ? <span className="vstage__tc tnum">{timecode}</span> : null}
        {children}
      </div>
    </div>
  );
});
