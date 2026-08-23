/* 首页历史时间线行。
 *
 * 官方源与自导入**混排在同一条时间线**，只用 SourceBadge 区分，不分 Tab ——
 * 订阅已经决定了什么进流，再分类是重复劳动。
 *
 * 和 HeroCard 一样**不显示段数**：首页只谈时长。
 */

import type { MediaListItem } from '../lib/api';
import { duration, shortDate } from '../lib/format';
import { SourceBadge } from './SourceBadge';
import './EpisodeRow.css';

export function EpisodeRow({ media, onOpen }: { media: MediaListItem; onOpen: () => void }) {
  return (
    <li className="erow">
      <button className="erow__btn" onClick={onOpen}>
        <span className="erow__date tnum">{shortDate(media.published_on)}</span>
        <SourceBadge origin={media.origin} />
        <span className="erow__title">{media.title}</span>
        <span className="erow__dur tnum">{duration(media.duration_ms)}</span>
      </button>
    </li>
  );
}
