/* 首页最新一期。
 *
 * 两条硬规则：
 *   1. 日期与标题在**字族、字号、颜色**三通道同时分离（等宽/次级色/14px
 *      对 无衬线/主文字色/20px）。只靠字号拉不开，日期会跟标题争视线。
 *   2. **不显示段数。** 决定「今天练哪条」靠的是要花几分钟；段数是内部
 *      结构，只在回声模式作为进度指示（#11 / 27）出现。
 *
 * 章节可直接进回声闭环，跳过详情页 —— 一期 10 分钟未必想一次练完。
 */

import { mediaUrl } from '../lib/api';
import type { ChapterOut, MediaListItem } from '../lib/api';
import { duration, isoDate, shortDuration } from '../lib/format';
import { Button } from './Button';
import { SourceBadge } from './SourceBadge';
import './HeroCard.css';

interface Props {
  media: MediaListItem;
  chapters: ChapterOut[];
  /** 章节还没生成完时为 true —— 跟读此时已经可用 */
  chaptersPending: boolean;
  /** 点缩略图或标题：打开详情页。与「开始跟读」是两回事 —— 一个是
   *  「先看看这期讲什么」，一个是「现在就练」。 */
  onOpen: () => void;
  onStart: () => void;
  /** 参数是该章**第一段的 chunk 序号**，回声页直接 ?chunk=N 落位 */
  onChapter: (chunkStartIdx: number) => void;
}

export function HeroCard({
  media,
  chapters,
  chaptersPending,
  onOpen,
  onStart,
  onChapter,
}: Props) {
  // chunk.idx 全期连续编号（后端保证），所以某章的首段序号就是前面各章
  // chunk_count 的累加。这样点章节能直接 ?chunk=N 落位，不必先拉全量 chunks。
  let running = 0;
  const chunkStarts = chapters.map((chapter) => {
    const start = running;
    running += chapter.chunk_count;
    return { chapter, start };
  });

  return (
    <article className="hero">
      <header className="hero__head">
        <div className="hero__thumb">
          {media.thumb_path ? <img src={mediaUrl.thumb(media.id)} alt="" /> : null}
          <span className="hero__dur tnum">{duration(media.duration_ms)}</span>
        </div>
        <div className="hero__meta">
          <div className="hero__line">
            <span className="hero__date tnum">{isoDate(media.published_on)}</span>
            <SourceBadge origin={media.origin} />
          </div>
          {/* 卡片链接：真正可点的是标题按钮，它的 ::after 铺满整个 .hero__head，
              所以点缩略图也生效。好处是无障碍树里只有一个可点项，标签就是标题，
              而不是「图片」「标题」两个指向同一处的目标。 */}
          <h2 className="hero__title">
            <button className="hero__open" onClick={onOpen}>
              {media.title}
            </button>
          </h2>
        </div>

        {/* 按钮在标题栏右下角，不再单占一行。
            必须 z-index 抬起来 —— .hero__open::after 铺满整个 head，
            不抬的话点击会被那层吃掉。 */}
        <div className="hero__start">
          <Button variant="primary" onClick={onStart}>
            ▶ 开始跟读
          </Button>
        </div>
      </header>

      {chaptersPending ? (
        <div className="hero__pending">◌ 章节生成中 · 跟读现在就能用</div>
      ) : (
        <ul className="hero__chapters">
          {chunkStarts.map(({ chapter: ch, start }) => (
            <li key={ch.idx}>
              <button className="hero__chapter" onClick={() => onChapter(start)}>
                <span className="hero__num tnum">{String(ch.idx + 1).padStart(2, '0')}</span>
                <span className="hero__name">{ch.title}</span>
                <span className="hero__time tnum">{shortDuration(ch.end_ms - ch.start_ms)}</span>
                <span className="hero__play" aria-hidden="true">
                  ▶
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
